"""
Build an initialized agent from one experiment-config entry.

A config entry is a dict: {tag, model, system_prompt, mcp_endpoints, ...}.
`system_prompt` is a keyword (baseline | refs | mem) or a literal path to a
prompt file. This replaces the hardcoded 5-config `_make_agents()` in
run_experiment_fhir.py with a data-driven equivalent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from agent.fhir_openrouter_agent import FHIROpenRouterAgent
from agent.interfaces.core_agent_interface import AgentConfig

ROOT_DIR = Path(__file__).resolve().parents[2]
PROMPTS_DIR = ROOT_DIR / "prompts" / "fhir"

# Appended to every system prompt (matches run_experiment_fhir.py).
SEARCH_RETRY_INSTRUCTION = (
    "\n\nFor search/retrieval tasks: if you get zero results, try alternative "
    "search parameters (e.g., different field names, reference formats, or "
    "without optional filters) before concluding the resource doesn't exist."
)

BASELINE_PROMPT = (
    "You are a careful FHIR assistant. Think step-by-step. Use tools precisely "
    "and return concise final answers with required tags."
)

# Keyword → prompt file (baseline has no file; it's the inline text above).
_PROMPT_FILES = {
    "refs": PROMPTS_DIR / "fhir_baseline_system_prompt_with_refs.txt",
    "mem": PROMPTS_DIR / "fhir_baseline_system_prompt_with_mem.txt",
}


def _resolve_part(spec: str) -> str:
    """Resolve one prompt keyword ("baseline"|"refs"|"mem") or file path to text."""
    if spec == "baseline":
        return BASELINE_PROMPT
    if spec in _PROMPT_FILES:
        return _PROMPT_FILES[spec].read_text(encoding="utf-8")
    path = Path(spec)
    if not path.is_absolute():
        path = ROOT_DIR / path
    if not path.exists():
        raise ValueError(f"Unknown system_prompt {spec!r}: not a keyword or existing file")
    return path.read_text(encoding="utf-8")


def resolve_system_prompt(spec) -> str:
    """Turn a `system_prompt` spec into prompt text (+ the shared retry note).

    spec: a keyword ("baseline"|"refs"|"mem") or file path, or a list of them
    joined in order (e.g. ["mem", "refs"] → memory + references prompt).
    """
    parts = spec if isinstance(spec, list) else [spec]
    return "\n\n".join(_resolve_part(p) for p in parts) + SEARCH_RETRY_INSTRUCTION


def build_agent(entry: Dict[str, Any], fhir_sse_url: str) -> FHIROpenRouterAgent:
    """Build (not yet initialized) an agent for one config entry. Call ainit()."""
    cfg = AgentConfig(
        model_id=entry["model"],
        system_prompt=resolve_system_prompt(entry.get("system_prompt", "baseline")),
        transport="mcp",
        endpoint=fhir_sse_url,
        extra={"additional_mcp_endpoints": entry.get("mcp_endpoints", [])},
    )
    return FHIROpenRouterAgent(cfg)
