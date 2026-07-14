"""
Roll per-task JSON traces up into summary JSONs for the dashboard.

Levels (each a strict roll-up of the one below):
  run_summary_<tag>.json    — one config, one run
  config_summary_<tag>.json — one config across its runs (mean +/- std)
  experiment.json           — all configs compared (the file the dashboard loads)

Works on the NEW nested layout (base_dir/<tag>/run_<n>/*.json). Legacy flat dirs
can be read via read_run_dir() too (tags come from each JSON's agent_tag); wiring
their output placement is deferred.
"""

from __future__ import annotations

import importlib
import json
import statistics
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


# Broad workflow category per task, keyed by task_module prefix (task_NN). Used
# for dashboard filtering. Excluded tasks (18a/19x) are intentionally uncategorized.
_CATEGORY_BY_PREFIX = {
    "Patient Records": ["01", "02a", "02b", "03", "04a", "04b", "22"],
    "Insurance & Billing": ["07", "08a", "08b", "09a", "09b", "09c", "09d", "10a", "10b"],
    "Scheduling & Appointments": ["11a", "11b", "11c", "11d", "12a", "12b", "12c", "12d",
                                  "13a", "13b", "14a", "14b", "15a", "15b", "15c",
                                  "16a", "16b", "16c", "17a", "17b"],
    "Surgery & Test Orders": ["05", "06a", "06b", "20", "21a", "21b", "21c"],
}
_CATEGORY = {f"task_{code}": cat for cat, codes in _CATEGORY_BY_PREFIX.items() for code in codes}


def _category(task_module: Optional[str]) -> Optional[str]:
    """Broad workflow category from the task_NN prefix of task_module."""
    if not task_module:
        return None
    code = task_module.split("_")[1] if len(task_module.split("_")) > 1 else ""
    return _CATEGORY.get(f"task_{code}")


@lru_cache(maxsize=None)
def _difficulty(task_module: Optional[str], task_class: Optional[str]) -> Optional[int]:
    """Canonical difficulty from the task class definition (get_difficulty_level).
    Authoritative for both legacy and new results; YAML/embedded values are ignored."""
    if not task_module or not task_class:
        return None
    try:
        mod = importlib.import_module(f"tasks.fhir_tasks_modular.{task_module}_modular")
        cls_name = task_class if task_class.endswith("Modular") else f"{task_class}Modular"
        return getattr(mod, cls_name)(fhir_server_url="http://x").get_difficulty_level()
    except Exception:
        return None


def _mean(xs: List[float]) -> Optional[float]:
    return round(statistics.mean(xs), 4) if xs else None


def _std(xs: List[float]) -> Optional[float]:
    return round(statistics.stdev(xs), 4) if len(xs) > 1 else 0.0


def _write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ── leaf: one per-task JSON → a compact per-task record ──────────────────────
def _task_record(data: Dict[str, Any]) -> Dict[str, Any]:
    exec_res = data.get("execution_result") or {}
    tr = data.get("task_result") or {}
    trl = data.get("task_result_light") or {}
    return {
        "task": data.get("task_module"),
        "variation": data.get("variation"),
        "difficulty_level": _difficulty(data.get("task_module"), data.get("task_class")),
        "category": _category(data.get("task_module")),
        "success": bool(tr.get("task_success")),
        "light_success": trl.get("task_success"),  # True/False/None
        "tokens": exec_res.get("token_total"),
        "exec_ms": exec_res.get("total_exec_ms"),
        "tool_order": exec_res.get("tool_order") or [],
        "failure_mode": data.get("failure_mode") or {},
    }


def _totals(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(records)
    success = sum(1 for r in records if r["success"])
    light = [r for r in records if r["light_success"] is not None]
    light_success = sum(1 for r in light if r["light_success"])
    tokens = [r["tokens"] for r in records if r["tokens"] is not None]
    exec_ms = [r["exec_ms"] for r in records if r["exec_ms"] is not None]
    return {
        "success": success,
        "total": total,
        "success_rate": round(success / total, 4) if total else None,
        "light_success": light_success,
        "light_total": len(light),
        "light_success_rate": round(light_success / len(light), 4) if light else None,
        "avg_tokens": _mean(tokens),
        "avg_exec_ms": _mean(exec_ms),
    }


# ── read one run dir → {tag: [records]} (handles mixed-tag legacy dirs) ───────
def read_run_dir(run_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    by_tag: Dict[str, List[Dict[str, Any]]] = {}
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.startswith(("run_summary", "config_summary", "config")):
            continue
        data = json.loads(jf.read_text(encoding="utf-8"))
        tag = data.get("agent_tag") or "unknown"
        by_tag.setdefault(tag, []).append(_task_record(data))
    return by_tag


# ── build the new nested layout under base_dir ───────────────────────────────
def build_experiment(base_dir: Path) -> Path:
    """Write run/config summaries per tag and one experiment.json at base_dir."""
    by_config: Dict[str, Any] = {}
    by_config_task: Dict[str, Any] = {}
    config_tags: List[str] = []

    for tag_dir in sorted(p for p in base_dir.iterdir() if p.is_dir()):
        tag = tag_dir.name
        run_dirs = sorted(tag_dir.glob("run_*"))
        if not run_dirs:
            continue
        config_tags.append(tag)
        meta = _load_config_meta(tag_dir)

        run_totals: List[Dict[str, Any]] = []
        run_diff_totals: List[Dict[str, Any]] = []
        run_cat_totals: List[Dict[str, Any]] = []
        task_runs: Dict[str, List[Dict[str, Any]]] = {}  # task -> [records across runs]

        for run_dir in run_dirs:
            records = read_run_dir(run_dir).get(tag, [])
            totals = _totals(records)
            diff_totals = _totals_by(records, "difficulty_level")
            cat_totals = _totals_by(records, "category")
            run_index = int(run_dir.name.split("_")[-1])
            _write(run_dir / f"run_summary_{tag}.json", {
                "tag": tag, "model": meta.get("model"), "run_index": run_index,
                "num_tasks": totals["total"], "totals": totals,
                "by_difficulty": diff_totals, "by_category": cat_totals, "per_task": records,
            })
            run_totals.append({"run_index": run_index, **totals})
            run_diff_totals.append(diff_totals)
            run_cat_totals.append(cat_totals)
            for r in records:
                task_runs.setdefault(r["task"], []).append(r)

        config_overall = _aggregate_runs(run_totals)
        diff_agg = _aggregate_grouped(run_diff_totals)
        cat_agg = _aggregate_grouped(run_cat_totals)
        task_agg = _aggregate_by_task(task_runs)
        _write(tag_dir / f"config_summary_{tag}.json", {
            "tag": tag, "model": meta.get("model"), "runs": len(run_dirs),
            "overall": config_overall, "per_run": run_totals,
            "by_difficulty": diff_agg, "by_category": cat_agg, "by_task": task_agg,
        })
        # per_run totals embedded so the top-level view needs no drill-down.
        by_config[tag] = {"model": meta.get("model"), **config_overall, "per_run": run_totals,
                          "by_difficulty": diff_agg, "by_category": cat_agg}
        by_config_task[tag] = task_agg

    exp_path = base_dir / "experiment.json"
    _write(exp_path, {
        "experiment": base_dir.name,
        "configs": config_tags,
        "by_config": by_config,
        "by_config_task": by_config_task,
    })
    return exp_path


def _load_config_meta(tag_dir: Path) -> Dict[str, Any]:
    cfg = tag_dir / "config.json"
    return json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}


def _aggregate_runs(run_totals: List[Dict[str, Any]]) -> Dict[str, Any]:
    rates = [r["success_rate"] for r in run_totals if r["success_rate"] is not None]
    light = [r["light_success_rate"] for r in run_totals if r["light_success_rate"] is not None]
    toks = [r["avg_tokens"] for r in run_totals if r["avg_tokens"] is not None]
    ms = [r["avg_exec_ms"] for r in run_totals if r["avg_exec_ms"] is not None]
    return {
        "success_rate_mean": _mean(rates), "success_rate_std": _std(rates),
        "light_success_rate_mean": _mean(light), "light_success_rate_std": _std(light),
        "avg_tokens_mean": _mean(toks), "avg_exec_ms_mean": _mean(ms),
    }


def _totals_by(records: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    """Group records by `key` field for ONE run: {group: {success, total, success_rate}}."""
    groups: Dict[Any, List[Dict[str, Any]]] = {}
    for r in records:
        groups.setdefault(r[key], []).append(r)
    out: Dict[str, Any] = {}
    for g, recs in groups.items():
        success = sum(1 for r in recs if r["success"])
        light = [r for r in recs if r["light_success"] is not None]
        light_success = sum(1 for r in light if r["light_success"])
        out[str(g)] = {
            "success": success, "total": len(recs),
            "success_rate": round(success / len(recs), 4) if recs else None,
            "light_total": len(light),
            "light_success_rate": round(light_success / len(light), 4) if light else None,
        }
    return out


def _aggregate_grouped(run_group_totals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Mean +/- std of per-group strict & light success_rate ACROSS runs (for error bars)."""
    groups = sorted({g for rt in run_group_totals for g in rt})
    out: Dict[str, Any] = {}
    for g in groups:
        rates = [rt[g]["success_rate"] for rt in run_group_totals if g in rt and rt[g]["success_rate"] is not None]
        light = [rt[g]["light_success_rate"] for rt in run_group_totals if g in rt and rt[g]["light_success_rate"] is not None]
        totals = [rt[g]["total"] for rt in run_group_totals if g in rt]
        light_totals = [rt[g]["light_total"] for rt in run_group_totals if g in rt]
        out[g] = {
            "success_rate_mean": _mean(rates), "success_rate_std": _std(rates),
            "light_success_rate_mean": _mean(light), "light_success_rate_std": _std(light),
            "num_tasks": totals[0] if totals else 0,
            "light_applicable": light_totals[0] if light_totals else 0,
            "runs_included": len(rates),
        }
    return out


def _aggregate_by_task(task_runs: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for task, recs in task_runs.items():
        succ = [1 if r["success"] else 0 for r in recs]
        light = [1 if r["light_success"] else 0 for r in recs if r["light_success"] is not None]
        toks = [r["tokens"] for r in recs if r["tokens"] is not None]
        ms = [r["exec_ms"] for r in recs if r["exec_ms"] is not None]
        out[task] = {
            "difficulty_level": recs[0]["difficulty_level"] if recs else None,
            "category": recs[0]["category"] if recs else None,
            "success_rate": round(sum(succ) / len(succ), 4) if succ else None,
            "light_success_rate": round(sum(light) / len(light), 4) if light else None,
            "runs_included": len(recs),
            "avg_tokens": _mean(toks),
            "avg_exec_ms": _mean(ms),
        }
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build summary JSONs from a nested experiment dir.")
    ap.add_argument("base_dir", help="Experiment base dir (contains <tag>/run_<n>/ ).")
    args = ap.parse_args()
    path = build_experiment(Path(args.base_dir))
    print(f"Wrote {path}")
