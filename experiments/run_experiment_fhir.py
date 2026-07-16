"""
Run each FHIR variation through 5 LangChain `FHIRBaselineAgent` configurations:
  - baseline_nomemory                      : FHIR MCP only
  - baseline_with_references               : FHIR + Specs MCP
  - baseline_with_memory_no_spec           : FHIR + Memory (trained without specs)
  - baseline_mem_spec_trained              : FHIR + Memory (trained with specs, no spec access)
  - baseline_with_memory_and_references    : FHIR + Specs + Memory (trained with specs)

Per-run JSON traces and a CSV summary land in --output-dir. The Claude Code
driver lives in `run_experiment_fhir_claude_code.py`; the per-variation harness
they share lives in `utils/experiment_runner.py`.
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

from agent.fhir_baseline import FHIRBaselineAgent  # type: ignore
from agent.interfaces.core_agent_interface import AgentConfig  # type: ignore
from utils.experiment_runner import build_logger, run_variations  # type: ignore


async def _make_agents(
    fhir_sse_url: str,
    model_id: str,
    paraphrase: bool = False,
) -> Dict[str, FHIRBaselineAgent]:
    """Build and initialize the five LangChain baseline agents."""
    logger = logging.getLogger("run-experiment-fhir")

    mem_prompt_path = ROOT_DIR / "prompts" / "fhir" / "fhir_baseline_system_prompt_with_mem.txt"
    mem_prompt_text = mem_prompt_path.read_text(encoding="utf-8") if mem_prompt_path.exists() else ""
    if not mem_prompt_text:
        logger.warning("Memory system prompt not found at %s", mem_prompt_path)

    ref_prompt_path = ROOT_DIR / "prompts" / "fhir" / "fhir_baseline_system_prompt_with_refs.txt"
    SYSTEM_PROMPT_REF = ref_prompt_path.read_text(encoding="utf-8") if ref_prompt_path.exists() else ""
    if not SYSTEM_PROMPT_REF:
        logger.warning("FHIR refs system prompt not found at %s", ref_prompt_path)

    SEARCH_RETRY_INSTRUCTION = """
    For search/retrieval tasks: if you get zero results, try alternative search parameters (e.g., different field names, reference formats, or without optional filters) before concluding the resource doesn't exist.
    """
    BASELINE_PROMPT = (
        "You are a careful FHIR assistant. Think step-by-step. Use tools precisely "
        "and return concise final answers with required tags."
    )

    specs = {
        "baseline_nomemory": (
            BASELINE_PROMPT + "\n\n" + SEARCH_RETRY_INSTRUCTION,
            [],
        ),
        "baseline_with_references": (
            SYSTEM_PROMPT_REF + "\n\n" + SEARCH_RETRY_INSTRUCTION,
            ["http://localhost:8010/fhir_specs"],
        ),
        "baseline_with_memory_no_spec": (
            mem_prompt_text + SEARCH_RETRY_INSTRUCTION,
            ["http://localhost:8011/memory_fig_3_no_spec"],
        ),
        "baseline_mem_spec_trained": (
            mem_prompt_text + SEARCH_RETRY_INSTRUCTION,
            ["http://localhost:8012/memory_fig_3_with_spec"],
        ),
        "baseline_with_memory_and_references": (
            mem_prompt_text + "\n\n" + SYSTEM_PROMPT_REF + "\n\n" + SEARCH_RETRY_INSTRUCTION,
            ["http://localhost:8012/memory_fig_3_with_spec", "http://localhost:8010/fhir_specs"],
        ),
    }

    agents: Dict[str, FHIRBaselineAgent] = {}
    for tag, (sys_prompt, additional_endpoints) in specs.items():
        cfg = AgentConfig(
            model_id=model_id,
            system_prompt=sys_prompt,
            transport="mcp",
            endpoint=fhir_sse_url,
            extra={"additional_mcp_endpoints": additional_endpoints},
        )
        agents[tag] = FHIRBaselineAgent(cfg, paraphrase=paraphrase)

    await asyncio.gather(*(a.ainit() for a in agents.values()))
    return agents


async def run_experiment(
    variations_yaml: str,
    fhir_sse_url: str,
    model_id: str,
    out_dir: Path,
    logger: logging.Logger,
    paraphrase: bool = False,
) -> None:
    with Path(variations_yaml).open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    variations: List[Dict[str, Any]] = cfg.get("variations", [])

    agents = await _make_agents(
        fhir_sse_url=fhir_sse_url,
        model_id=model_id,
        paraphrase=paraphrase,
    )
    await run_variations(agents=agents, variations=variations, out_dir=out_dir, logger=logger)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run each FHIR variation through 5 LangChain baseline configs. "
                    "Writes per-run JSON traces and a CSV summary to --output-dir."
    )
    parser.add_argument(
        "--variations-yaml",
        default=str(ROOT_DIR / "environment" / "data" / "exp_1_task_variation_updated.yaml"),
        help="Path to variations YAML.",
    )
    parser.add_argument(
        "--fhir-sse-url",
        default=os.getenv("FHIR_MCP_SSE_URL", "http://localhost:8000/fhir_mcp"),
        help="Primary FHIR MCP SSE endpoint.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("BASELINE_MODEL", "openai:gpt-4.1-mini"),
        help="LLM model id (e.g., openai:gpt-4.1-mini).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for per-run JSON traces and the CSV summary.",
    )
    parser.add_argument(
        "--paraphrase",
        action="store_true",
        default=False,
        help="Paraphrase task prompts before execution (default: False).",
    )
    args = parser.parse_args()

    logger = build_logger("run-experiment-fhir")
    ypath = Path(args.variations_yaml)
    if not ypath.is_absolute():
        ypath = ROOT_DIR / ypath
    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT_DIR / out_dir

    logger.info(
        "Starting LangChain 5-config experiment | yaml=%s | endpoint=%s | model=%s | out=%s",
        ypath, args.fhir_sse_url, args.model, out_dir,
    )

    asyncio.run(
        run_experiment(
            variations_yaml=str(ypath),
            fhir_sse_url=args.fhir_sse_url,
            model_id=args.model,
            out_dir=out_dir,
            logger=logger,
            paraphrase=args.paraphrase,
        )
    )


if __name__ == "__main__":
    main()
