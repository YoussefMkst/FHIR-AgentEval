"""
verify_modular_tasks.py — Run modular FHIR tasks using the gold-standard
execute_human_agent() and validate the outcomes.

For each variation in the provided YAML, this script:
  1) Instantiates the modular task (via utils.task_loader.build_task)
  2) cleanup_test_data() → prepare_test_data()
  3) Executes execute_human_agent()
  4) Runs validate_response(execution_result)
  5) Prints a concise per-task status and any assertion/error message

Exit code is 0 if all tasks succeeded, 1 otherwise.
"""

from __future__ import annotations

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml
from dotenv import load_dotenv  # type: ignore


# Ensure project root on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))


from utils.task_loader import build_task  # noqa: E402


def build_logger() -> logging.Logger:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    return logging.getLogger("verify-modular-tasks")


def load_variations(yaml_path: Path) -> List[Dict[str, Any]]:
    with yaml_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    variations: List[Dict[str, Any]] = cfg.get("variations", [])
    return variations


def run_one_variation(entry: Dict[str, Any], logger: logging.Logger) -> Tuple[bool, str]:
    """Run one modular task entry using the human benchmark + validation.

    Returns (success, message) where message contains assertion/error details on failure.
    """
    task_module: str = entry.get("module", "")
    task_class: str = entry.get("class", "")

    # Instantiate (modular if 'template_params' present)
    task = build_task(entry)

    logger.info(f"Verifying task instance: {type(task).__name__} (modular={'Modular' in type(task).__name__})")

    # Best-effort cleanup before preparing data (mirrors baseline agent flow)
    try:
        logger.debug("cleanup_test_data()")
        task.cleanup_test_data()
    except Exception as e:
        # Continue; cleanup is best-effort
        logger.debug("cleanup_test_data raised: %s", e)

    if hasattr(task, "prepare_test_data"):
        logger.debug("prepare_test_data()")
        task.prepare_test_data()

    # Execute gold-standard flow and validate
    try:
        exec_res = task.execute_human_agent()
    except Exception as e:
        return False, f"execute_human_agent() error: {str(e)}"

    try:
        # Use deterministic validator (not the benchmark wrapper)
        task_result = task.validate_response(exec_res)
    except Exception as e:
        return False, f"validate_response() error: {str(e)}"

    # Normalize outcome
    success = bool(getattr(task_result, "task_success", False))
    assertion_msg = getattr(task_result, "assertion_error_message", None)
    logger.info(f"task_result: {getattr(task_result, "task_success")}")
    if success:
        return True, ""
    return False, (assertion_msg or "")


def main() -> None:
    # Load environment/.env for endpoints and configuration
    load_dotenv(ROOT_DIR / "environment" / ".env")

    parser = argparse.ArgumentParser(description="Verify modular tasks using execute_human_agent + validate_response")
    parser.add_argument(
        "--variations-yaml",
        default=str(ROOT_DIR / "environment" / "data" / "task_variations_single.yaml"),
        help="Path to variations YAML (defaults to environment/data/task_variations_single.yaml)",
    )
    args = parser.parse_args()

    logger = build_logger()

    ypath = Path(args.variations_yaml)
    if not ypath.is_absolute():
        ypath = ROOT_DIR / ypath

    if not ypath.exists():
        print(f"Variations YAML not found: {ypath}")
        sys.exit(1)

    variations = load_variations(ypath)
    total = len(variations)
    print(f"Loaded {total} modular task variations from {ypath}")

    results: List[Tuple[str, bool, str]] = []
    for idx, entry in enumerate(variations, start=1):
        task_module: str = entry.get("module", "")
        task_class: str = entry.get("class", "")
        task_label = f"{task_module}.{task_class}"

        logger.info("[%d/%d] %s — execute_human_agent + validate_response", idx, total, task_label)
        ok, msg = run_one_variation(entry, logger)
        results.append((task_label, ok, msg))

        status = "OK" if ok else "FAIL"
        if ok:
            print(f"[{idx:02d}/{total:02d}] {status}  {task_label}")
        else:
            detail = msg or "(no assertion message)"
            print(f"[{idx:02d}/{total:02d}] {status}  {task_label}  —  {detail}")

    # Summary
    num_ok = sum(1 for _, ok, _ in results if ok)
    num_fail = total - num_ok
    print("\nSummary:")
    print(f"  Success: {num_ok}")
    print(f"  Failed : {num_fail}")

    if num_fail > 0:
        print("\nFailures:")
        for task_label, ok, msg in results:
            if not ok:
                print(f"  - {task_label}: {msg or '(no assertion message)'}")

    # Exit code indicates overall success
    sys.exit(0 if num_fail == 0 else 1)


if __name__ == "__main__":
    main()


