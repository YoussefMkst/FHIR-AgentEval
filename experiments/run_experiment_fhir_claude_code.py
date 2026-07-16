"""
Run each FHIR variation through a single Claude-Code-driven configuration.

The agent connects to the FHIR MCP server (port 8000) on the droplet and uses
Claude Code's full default toolset (Bash, Read, Edit, Write, Glob, Grep,
WebFetch, WebSearch, Task, TodoWrite, …) on top of it. No memory or specs MCP
servers in this setup — keep it simple while we benchmark.

The MCP server (:8000) is expected to run on the droplet that hosts `claude`,
reachable as localhost from Claude Code's perspective. The local runner only
drives `claude -p` over SSH (via --ssh-target) and reaches the droplet's HAPI
directly via HTTP for cleanup/prepare — set FHIR_SERVER_URL in environment/.env
to the droplet's HAPI URL.

Per-run JSON traces and a CSV summary land in --output-dir. The LangChain
counterpart (5 configs) lives in `run_experiment_fhir.py`; the per-variation
harness they share lives in `utils/experiment_runner.py`.
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from agent.fhir_claude_code_agent import FHIRClaudeCodeAgent  # type: ignore
from agent.interfaces.core_agent_interface import AgentConfig  # type: ignore
from utils.experiment_runner import build_logger, run_variations_single  # type: ignore

CLAUDE_CODE_CONFIG_PATH = ROOT_DIR / "experiments" / "claude_code_configs" / "claude_code.json"
CLAUDE_CODE_TAG = "claude_code"


async def _make_agent(
    model_id: str,
    ssh_target: Optional[str],
    paraphrase: bool = False,
    max_turns: int = 50,
) -> FHIRClaudeCodeAgent:
    """Build and initialize the single Claude Code agent (FHIR MCP only,
    Claude Code default toolset enabled)."""
    logger = logging.getLogger("run-experiment-fhir-cc")

    BASELINE_PROMPT = (
        "You are a careful FHIR assistant. Think step-by-step. Use tools precisely "
        "and return concise final answers with required tags."
    )
    SEARCH_RETRY_INSTRUCTION = (
        "\n\nFor search/retrieval tasks: if you get zero results, try alternative "
        "search parameters (e.g., different field names, reference formats, or "
        "without optional filters) before concluding the resource doesn't exist."
    )
    system_prompt = BASELINE_PROMPT + SEARCH_RETRY_INSTRUCTION

    agent_cfg = AgentConfig(
        model_id=model_id,
        system_prompt=system_prompt,
        transport="claude_code",
        endpoint=str(CLAUDE_CODE_CONFIG_PATH),
        extra={"ssh_target": ssh_target, "claude_code_max_turns": max_turns},
    )
    agent = FHIRClaudeCodeAgent(
        config=agent_cfg,
        mcp_config_path=CLAUDE_CODE_CONFIG_PATH,
        ssh_target=ssh_target,
        paraphrase=paraphrase,
        max_turns=max_turns,
    )
    await agent.ainit()
    logger.info("Claude Code agent initialized (tag=%s, mcp_config=%s)", CLAUDE_CODE_TAG, CLAUDE_CODE_CONFIG_PATH.name)
    return agent


async def run_experiment(
    variations_yaml: str,
    model_id: str,
    out_dir: Path,
    logger: logging.Logger,
    ssh_target: Optional[str] = None,
    paraphrase: bool = False,
    max_turns: int = 50,
) -> None:
    with Path(variations_yaml).open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    variations: List[Dict[str, Any]] = cfg.get("variations", [])

    agent = await _make_agent(
        model_id=model_id,
        ssh_target=ssh_target,
        paraphrase=paraphrase,
        max_turns=max_turns,
    )
    await run_variations_single(
        agent=agent,
        variations=variations,
        out_dir=out_dir,
        logger=logger,
        tag=CLAUDE_CODE_TAG,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run each FHIR variation through one Claude Code config "
                    "(driving `claude -p` over SSH). Writes per-run JSON traces "
                    "and a CSV summary to --output-dir."
    )
    parser.add_argument(
        "--variations-yaml",
        default=str(ROOT_DIR / "environment" / "data" / "exp_1_task_variation_updated.yaml"),
        help="Path to variations YAML.",
    )
    parser.add_argument(
        "--ssh-target",
        default=os.getenv("CLAUDE_CODE_SSH_TARGET"),
        help="SSH target where `claude` runs (e.g. user@droplet). Omit to run "
             "claude on the local machine.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("CLAUDE_CODE_MODEL", "sonnet"),
        help="--model passed to `claude -p` (e.g. 'sonnet', 'opus', or a full id). "
             "Use a Claude Code-friendly id; openai:* values are not valid here.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=50,
        help="--max-turns passed to `claude -p`.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Base output dir; '_run_<i>' is appended per run "
             "(e.g. --output-dir results/exp_fig_1_claude_code → "
             "results/exp_fig_1_claude_code_run_1, _run_2, _run_3).",
    )
    parser.add_argument(
        "--paraphrase",
        action="store_true",
        default=False,
        help="Paraphrase task prompts before execution (default: False).",
    )
    args = parser.parse_args()

    logger = build_logger("run-experiment-fhir-cc")
    ypath = Path(args.variations_yaml)
    if not ypath.is_absolute():
        ypath = ROOT_DIR / ypath
    out_dir_base = Path(args.output_dir)
    if not out_dir_base.is_absolute():
        out_dir_base = ROOT_DIR / out_dir_base

    # RUNNING THE EXPERIMENT 3 TIMES.
    for i in range(1, 4):
        out_dir = out_dir_base.parent / f"{out_dir_base.name}_run_{i}"

        logger.info(
            "Starting Claude Code single-config experiment | yaml=%s | model=%s | out=%s%s",
            ypath, args.model, out_dir,
            f" | ssh-target={args.ssh_target}" if args.ssh_target else " (local)",
        )

        asyncio.run(
            run_experiment(
                variations_yaml=str(ypath),
                model_id=args.model,
                out_dir=out_dir,
                logger=logger,
                ssh_target=args.ssh_target,
                paraphrase=args.paraphrase,
                max_turns=args.max_turns,
            )
        )


if __name__ == "__main__":
    main()
