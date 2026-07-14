"""
Build per-experiment dashboard summaries from a manifest.

Reads a manifest that declares, for each experiment, its configs and which
result dirs (legacy flat OR new nested) contribute to each. Aggregates them
into one JSON per experiment at results/dashboard/exp{id}.json.

Read-only: source result dirs are never modified. The aggregation math is
reused from build_summary (read_run_dir / _totals / _aggregate_*).
"""

from __future__ import annotations

import sys
import yaml
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from experiments.config_runner.build_summary import (
    read_run_dir, _totals, _totals_by, _aggregate_runs,
    _aggregate_grouped, _aggregate_by_task, _write,
)

RESULTS_DIR = ROOT_DIR / "results"


def _build_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate one config across its run dirs, filtering to its agent_tag."""
    tag = cfg["tag"]
    run_totals: List[Dict[str, Any]] = []
    run_diff_totals: List[Dict[str, Any]] = []
    run_cat_totals: List[Dict[str, Any]] = []
    task_runs: Dict[str, List[Dict[str, Any]]] = {}

    for i, run in enumerate(cfg["runs"], start=1):
        records = read_run_dir(RESULTS_DIR / run).get(tag, [])
        run_totals.append({"run_index": i, "run_dir": run, **_totals(records)})
        run_diff_totals.append(_totals_by(records, "difficulty_level"))
        run_cat_totals.append(_totals_by(records, "category"))
        for r in records:
            task_runs.setdefault(r["task"], []).append(r)

    return {
        "label": cfg["label"],
        "source": cfg["source"],
        "model": cfg["model"],
        "tag": tag,
        "runs": len(cfg["runs"]),
        **_aggregate_runs(run_totals),
        "per_run": run_totals,
        "by_difficulty": _aggregate_grouped(run_diff_totals),
        "by_category": _aggregate_grouped(run_cat_totals),
        "by_task": _aggregate_by_task(task_runs),
    }


def build_dashboard_summaries(manifest_path: Path, out_dir: Path) -> List[Path]:
    """Write one exp{id}.json per experiment; return the written paths."""
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    written: List[Path] = []

    for exp in manifest["experiments"]:
        configs = [_build_config(c) for c in exp["configs"]]
        out_path = out_dir / f"{exp['id']}.json"
        _write(out_path, {
            "id": exp["id"],
            "name": exp.get("name"),
            "description": exp.get("description"),
            "configs": configs,
        })
        written.append(out_path)
    return written


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build dashboard summaries from a manifest.")
    ap.add_argument("--manifest", default=str(ROOT_DIR / "experiments" / "configs" / "dashboard_manifest.yaml"))
    ap.add_argument("--out-dir", default=str(RESULTS_DIR / "dashboard"))
    args = ap.parse_args()
    paths = build_dashboard_summaries(Path(args.manifest), Path(args.out_dir))
    print("Wrote:")
    for p in paths:
        print(f"  {p}")
