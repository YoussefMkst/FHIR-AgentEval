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

import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional


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
        "difficulty_level": data.get("difficulty_level"),
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
        task_runs: Dict[str, List[Dict[str, Any]]] = {}  # task -> [records across runs]

        for run_dir in run_dirs:
            records = read_run_dir(run_dir).get(tag, [])
            totals = _totals(records)
            run_index = int(run_dir.name.split("_")[-1])
            _write(run_dir / f"run_summary_{tag}.json", {
                "tag": tag, "model": meta.get("model"), "run_index": run_index,
                "num_tasks": totals["total"], "totals": totals, "per_task": records,
            })
            run_totals.append({"run_index": run_index, **totals})
            for r in records:
                task_runs.setdefault(r["task"], []).append(r)

        config_overall = _aggregate_runs(run_totals)
        task_agg = _aggregate_by_task(task_runs)
        _write(tag_dir / f"config_summary_{tag}.json", {
            "tag": tag, "model": meta.get("model"), "runs": len(run_dirs),
            "overall": config_overall, "per_run": run_totals, "by_task": task_agg,
        })
        # per_run totals embedded so the top-level view needs no drill-down.
        by_config[tag] = {"model": meta.get("model"), **config_overall, "per_run": run_totals}
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
    toks = [r["avg_tokens"] for r in run_totals if r["avg_tokens"] is not None]
    ms = [r["avg_exec_ms"] for r in run_totals if r["avg_exec_ms"] is not None]
    return {
        "success_rate_mean": _mean(rates), "success_rate_std": _std(rates),
        "avg_tokens_mean": _mean(toks), "avg_exec_ms_mean": _mean(ms),
    }


def _aggregate_by_task(task_runs: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for task, recs in task_runs.items():
        succ = [1 if r["success"] else 0 for r in recs]
        toks = [r["tokens"] for r in recs if r["tokens"] is not None]
        ms = [r["exec_ms"] for r in recs if r["exec_ms"] is not None]
        out[task] = {
            "difficulty_level": recs[0]["difficulty_level"] if recs else None,
            "success_rate": round(sum(succ) / len(succ), 4) if succ else None,
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
