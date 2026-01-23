"""
DeepRare evaluation helpers – LLM-based scoring and tool dependency evaluation.

Exports:
- ascore_diagnosis(gold_label, gold_orpha, model_output, model_id) → dict
  Returns a dict with keys: score (0..1), match (bool), reason (str),
  gold_norm (str), pred_norm (str)

- evaluate_constraints_over_csv(csv_path, constraints_yaml) → dict
  Evaluates tool dependency constraints using first-occurrence ordering logic.
  Implements dependency enforcement: "IF tools A and B are both called,
  THEN A must come before B" rather than requiring complete subsequences.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple
import csv
import yaml

from dotenv import load_dotenv
from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model


# Ensure environment/.env is loaded for API keys
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / "environment" / ".env"
load_dotenv(ENV_PATH)


def _safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        return None


async def ascore_diagnosis(
    gold_label: Optional[str],
    gold_orpha: Optional[str],
    model_output: str,
    model_id: str = "openai:gpt-4.1-mini",
) -> Dict[str, Any]:
    """Ask a small LLM to grade the model output against the gold standard.

    Heuristics:
    - Normalise both gold and predicted labels to canonical disease names/IDs if present
    - Return a float score in [0,1] and a boolean match (true if strong match)
    - Always return a compact reason string
    """

    gold_label = (gold_label or "").strip()
    gold_orpha = (gold_orpha or "").strip()

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
            You are an evaluation assistant. Compare a model's diagnosis with a gold standard.
            Return STRICT JSON only with keys: {"score": <0..1>, "match": <true|false>, "reason": "...", "gold_norm": "...", "pred_norm": "..."}.
            Scoring rubric:
            - 1.0: clear exact match or well-known synonym; IDs (e.g., ORPHA/OMIM) align.
            - 0.7: close match (same disease family/subtype) with minor mismatch.
            - 0.3: partially related (symptomatically overlaps) but not the same condition.
            - 0.0: incorrect or unrelated.
            """.strip(),
        ),
        (
            "human",
            """
            Gold label: {gold_label}
            Gold ORPHA: {gold_orpha}

            Model output (free text):
            {model_output}

            Extract the predicted disease name from the model output, normalise names/IDs if present, and grade.
            Return ONLY the JSON object.
            """.strip(),
        ),
    ])

    llm = init_chat_model(model_id)
    resp = await (prompt | llm).ainvoke(
        {"gold_label": gold_label, "gold_orpha": gold_orpha, "model_output": model_output}
    )

    text = getattr(resp, "content", None) if hasattr(resp, "content") else None
    text = text if isinstance(text, str) else json.dumps(resp, ensure_ascii=False, default=str)

    data = _safe_json_loads(text) or {
        "score": 0.0,
        "match": False,
        "reason": "LLM did not return valid JSON",
        "gold_norm": gold_label or gold_orpha,
        "pred_norm": "",
    }

    # Guardrails
    try:
        score = float(data.get("score", 0.0))
        score = max(0.0, min(1.0, score))
        match = bool(data.get("match", score >= 0.7))
        reason = str(data.get("reason", ""))[:600]
        gold_norm = str(data.get("gold_norm", gold_label or gold_orpha or ""))[:160]
        pred_norm = str(data.get("pred_norm", ""))[:160]
        return {
            "score": score,
            "match": match,
            "reason": reason,
            "gold_norm": gold_norm,
            "pred_norm": pred_norm,
            "raw": data,
        }
    except Exception:
        return {
            "score": 0.0,
            "match": False,
            "reason": "Failed to parse scoring fields",
            "gold_norm": gold_label or gold_orpha or "",
            "pred_norm": "",
            "raw": data,
        }


# -----------------------------------------------------------------------------
# Minimal CSV-based evaluator for precedence constraints
# -----------------------------------------------------------------------------
def _split_tool_order(cell: Optional[str]) -> List[str]:
    """Parse the CSV `tool_order` cell into a clean list of tool names.

    The runner writes tool order as a string like:
        "extract_hpo > analyze_hpo > similar_cases"
    """
    if not cell:
        return []
    return [tok.strip() for tok in str(cell).split(">") if tok and tok.strip()]


def _seq_to_tool_list(seq_def: List[Dict[str, Any]]) -> List[str]:
    """Convert a sequence definition from YAML into a plain list of tool names.

    Minimal evaluator: ignore mode/args/when; we only use tool NAMES here.
    """
    tools: List[str] = []
    for step in seq_def or []:
        name = (step.get("tool") or "").strip() if isinstance(step, dict) else ""
        if name:
            tools.append(name)
    return tools


def _all_present(order: List[str], dep: List[str]) -> bool:
    """True iff EVERY tool in dep appears somewhere in order."""
    return all(t in order for t in dep)


def _first_positions(order: List[str], dep: List[str]) -> List[int]:
    """First occurrence index for each tool in dep (assumes presence)."""
    return [order.index(t) for t in dep]


def _check_dependency_order(order: List[str], dep: List[str]) -> Optional[bool]:
    """First-occurrence precedence check.

    Returns:
      - True  → all tools present AND first occurrences are in ascending order
      - False → all tools present BUT out of order (violation)
      - None  → not applicable (one or more tools missing)

    Examples for dep=["extract_hpo","analyze_hpo"]:
      order=["extract_hpo"]           → None   (not applicable)
      order=["analyze_hpo"]           → None   (not applicable)
      order=["extract_hpo","analyze"] → None   (not applicable)
      order=["analyze_hpo","extract_hpo"] → False
      order=["extract_hpo","analyze_hpo"] → True
    """
    if len(dep) < 2:
        return None  # singletons don't define precedence
    if not _all_present(order, dep):
        return None
    pos = _first_positions(order, dep)
    return pos == sorted(pos)


def _load_required_and_prohibited(constraints_yaml: str) -> Tuple[List[List[str]], List[List[str]]]:
    """Load required/prohibited sequences from YAML (tool names only)."""
    try:
        with open(constraints_yaml, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
    except Exception:
        cfg = {}

    constraints = cfg.get("constraints", {}) if isinstance(cfg, dict) else {}
    req_defs = constraints.get("required", []) or []
    pro_defs = constraints.get("prohibited", []) or []

    required: List[List[str]] = []
    prohibited: List[List[str]] = []

    for item in req_defs:
        seq = _seq_to_tool_list(item.get("sequence") or [])
        if len(seq) >= 2:       # ignore singletons
            required.append(seq)

    for item in pro_defs:
        seq = _seq_to_tool_list(item.get("sequence") or [])
        if len(seq) >= 2:       # ignore singletons
            prohibited.append(seq)

    return required, prohibited


def evaluate_constraints_over_csv(
    csv_path: str,
    constraints_yaml: str,
) -> Dict[str, Any]:
    """Evaluate precedence-style constraints over a clinician CSV.

    Minimal semantics (CSV-only):
      - Required: if all tools in a rule appear, their first occurrences must be in order.
      - Prohibited: if all tools in a rule appear, that order must not occur.
      - Single-step rules are ignored (need context/when to be meaningful).
      - Ignores `when`, `mode`, `optional`, `globals`, and param checks.
    """
    required, prohibited = _load_required_and_prohibited(constraints_yaml)

    def seq_str(seq: List[str]) -> str:
        return " → ".join(seq) if seq else ""

    rows_out: List[Dict[str, Any]] = []
    total = req_pass = pro_ok = 0

    with open(csv_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for idx, row in enumerate(reader):
            total += 1
            order = _split_tool_order(row.get("tool_order", ""))

            # Required: presence-gated, precedence only
            violated_dependencies: List[str] = []
            for dep in required:
                res = _check_dependency_order(order, dep)
                if res is False:  # present but out of order
                    violated_dependencies.append(seq_str(dep))

            # Prohibited: presence-gated, flag if prohibited order occurs
            prohibited_violations: List[str] = []
            for dep in prohibited:
                res = _check_dependency_order(order, dep)
                if res is True:   # present and in that (prohibited) order
                    prohibited_violations.append(seq_str(dep))

            required_ok = (len(violated_dependencies) == 0)
            prohibited_ok = (len(prohibited_violations) == 0)

            if required_ok:
                req_pass += 1
            if prohibited_ok:
                pro_ok += 1

            rows_out.append({
                "index": idx,
                "case_id": row.get("case_id", ""),
                "required_pass": required_ok,
                "violated_dependencies": violated_dependencies,
                "prohibited_violations": prohibited_violations,
            })

    return {
        "total_rows": total,
        "required_sequences": [seq_str(s) for s in required],
        "prohibited_sequences": [seq_str(s) for s in prohibited],
        "num_rows_required_pass": req_pass,
        "num_rows_prohibited_ok": pro_ok,
        "coverage_rate": (req_pass / total) if total else 0.0,
        "prohibited_ok_rate": (pro_ok / total) if total else 0.0,
        "rows": rows_out,
    }
