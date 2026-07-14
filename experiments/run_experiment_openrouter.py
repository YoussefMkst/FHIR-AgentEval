"""
Config-driven OpenRouter experiment runner.

Reads one experiment config (YAML/JSON) and runs every entry in `configs` over
`runs` full passes. Per-task JSON traces are written to:

    <base_dir>/<tag>/run_<n>/<task_module>_v<idx>_<tag>.json

Each config dir also gets a `config.json` (metadata for the dashboard). The
per-task JSON shape is produced by the shared worker `_run_entry_with_agent`,
so it stays identical to the existing runners (backward-compatible).

Roll-up summary JSONs are written later by build_summary (separate step).
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from experiments.config_runner.agent_builder import build_agent  # type: ignore
from experiments.config_runner.build_summary import build_experiment  # type: ignore
from utils.experiment_runner import build_logger, write_json, _run_entry_with_agent  # type: ignore


def _load_config(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.suffix == ".json" else (yaml.safe_load(text) or {})


def _load_variations(variations_yaml: str) -> List[Dict[str, Any]]:
    ypath = Path(variations_yaml)
    if not ypath.is_absolute():
        ypath = ROOT_DIR / variations_yaml
    with ypath.open("r", encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("variations", [])


async def _run_config(entry, run_dir, fhir_sse_url, variations, logger):
    """Run all variations for one config into run_dir (one JSON per variation)."""
    tag = entry["tag"]
    agent = build_agent(entry, fhir_sse_url)
    await agent.ainit()

    seen: Dict[tuple, int] = {}
    for i, var in enumerate(variations, start=1):
        key = (var.get("module", ""), var.get("class", ""))
        idx = seen[key] = seen.get(key, 0) + 1
        logger.info("[%s | %s] %d/%d %s.%s (v%d)",
                    tag, run_dir.name, i, len(variations), key[0], key[1], idx)
        res = await _run_entry_with_agent(agent, var, idx, tag, logger)
        safe_task = key[0].replace("/", "_")
        write_json(run_dir, f"{safe_task}_v{idx}_{tag}", res)


async def run_experiment(config: Dict[str, Any], logger) -> None:
    base_dir = Path(config["base_dir"])
    if not base_dir.is_absolute():
        base_dir = ROOT_DIR / base_dir
    runs = int(config.get("runs", 1))
    default_yaml = config["variations_yaml"]
    fhir_sse_url = config.get("fhir_sse_url", "http://localhost:8000/fhir_mcp")

    for entry in config["configs"]:
        tag = entry["tag"]
        variations = _load_variations(entry.get("variations_yaml", default_yaml))
        config_dir = base_dir / tag
        write_json(config_dir, "config", {
            **entry,
            "variations_yaml": entry.get("variations_yaml", default_yaml),
            "fhir_sse_url": fhir_sse_url,
            "runs": runs,
        })
        for n in range(1, runs + 1):
            await _run_config(entry, config_dir / f"run_{n}", fhir_sse_url, variations, logger)

    summary = build_experiment(base_dir)
    logger.info("Done. Results under %s | summary: %s", base_dir, summary)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a config-driven OpenRouter FHIR experiment.")
    parser.add_argument("--config", required=True, help="Path to experiment config YAML/JSON.")
    args = parser.parse_args()

    logger = build_logger("run-experiment-openrouter")
    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = ROOT_DIR / cfg_path
    config = _load_config(cfg_path)
    logger.info("Loaded experiment config: %s | %d configs | %d runs",
                cfg_path.name, len(config.get("configs", [])), config.get("runs", 1))

    asyncio.run(run_experiment(config, logger))


if __name__ == "__main__":
    main()
