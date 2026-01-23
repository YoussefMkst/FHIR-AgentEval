"""
Callback Utilities

This module contains callback functions and utilities for the AGENDA system,
including logging, monitoring, and event handling.
""" 

from langchain.callbacks.base import BaseCallbackHandler
from langchain_core.messages import AIMessage, ToolMessage
import json
import time
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict


class HistorySink(BaseCallbackHandler):
    """Append tool calls/observations to conversation_history as they happen (TOOLS API style)."""
    def __init__(self, history):
        self.history = history
        self._run_name = {}  # run_id -> tool name

    def on_tool_start(self, serialized, input_str, run_id, **kw):
        name = (serialized or {}).get("name", "tool")
        args_str = input_str if isinstance(input_str, str) else json.dumps(input_str)
        self._run_name[str(run_id)] = name
        self.history.append(
            AIMessage(
                content="",
                additional_kwargs={
                    "tool_calls": [{
                        "id": str(run_id),
                        "type": "function",
                        "function": {"name": name, "arguments": args_str}
                    }]
                }
            )
        )

    def on_tool_end(self, output, run_id, **kw):
        rid = str(run_id)
        name = self._run_name.get(rid, "tool")
        self.history.append(
            ToolMessage(
                content=str(output),
                name=name,
                tool_call_id=rid,
            )
        )

    def on_tool_error(self, error, run_id, **kw):
        # History still gets an observation; the tool wrapper below will also *return* a string
        rid = str(run_id)
        name = self._run_name.get(rid, "tool")
        self.history.append(
            ToolMessage(
                content=f"[{name} ERROR] {type(error).__name__}: {error}",
                name=name,
                tool_call_id=rid,
            )
        )



# ----------------------------------------------------------------------------
# Tracing helpers (reusable across agents)
# ----------------------------------------------------------------------------
def _stringify(value):
    if isinstance(value, str):
        return value
    content = getattr(value, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(value, dict) and isinstance(value.get("content"), str):
        return value["content"]
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)



class ToolCallRecorder(BaseCallbackHandler):
    """Record MCP/LangChain tool calls with order, args, outputs, and timing."""

    def __init__(self, truncate_chars: int = 800):
        self.truncate_chars = truncate_chars
        self._order = 0
        self._pending: Dict[str, Dict[str, Any]] = {}
        self.records: List[Dict[str, Any]] = []

    # Accept both old/new signatures across LangChain versions
    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: Optional[str] = None,
        *,
        run_id=None,
        parent_run_id=None,
        inputs: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        name = None
        if isinstance(serialized, dict):
            name = serialized.get("name") or serialized.get("id") or serialized.get("tool")
        name = str(name) if name is not None else str(serialized)

        if input_str is None and inputs is not None:
            input_str = _stringify(inputs)

        self._pending[str(run_id)] = {
            "order": None,
            "name": name,
            "run_id": str(run_id) if run_id else None,
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "start_time": time.perf_counter(),
            "input": input_str or "",
            "output": None,
            "error": None,
            "duration_ms": None,
        }

    def on_tool_end(self, output, *, run_id=None, parent_run_id=None, **kwargs):
        rid = str(run_id)
        rec = self._pending.pop(rid, {"name": "unknown_tool", "start_time": time.perf_counter()})
        rec["order"] = self._order
        self._order += 1
        rec["parent_run_id"] = str(parent_run_id) if parent_run_id else rec.get("parent_run_id")
        rec["output"] = _stringify(output)
        rec["duration_ms"] = round((time.perf_counter() - rec.get("start_time", time.perf_counter())) * 1000.0, 3)
        if self.truncate_chars:
            rec["input"] = rec.get("input", "")
            rec["output"] = rec.get("output", "") # MOD: removed truncation
        self.records.append(rec)

    def on_tool_error(self, error, *, run_id=None, parent_run_id=None, **kwargs):
        rid = str(run_id)
        rec = self._pending.pop(rid, {"name": "unknown_tool", "start_time": time.perf_counter()})
        rec["order"] = self._order
        self._order += 1
        rec["parent_run_id"] = str(parent_run_id) if parent_run_id else rec.get("parent_run_id")
        rec["error"] = str(error)
        rec["duration_ms"] = round((time.perf_counter() - rec.get("start_time", time.perf_counter())) * 1000.0, 3)
        if self.truncate_chars:
            rec["input"] = rec.get("input", "")[: self.truncate_chars]
        self.records.append(rec)


class LLMUsageRecorder(BaseCallbackHandler):
    """
    Capture per-call timing, token usage, prompts & outputs; robust to provider variations.
    Works with LangChain ChatModels (OpenAI/Responses API, Anthropic, etc.)
    """

    def __init__(self, keep_previews: int = 500):
        self.calls: List[Dict[str, Any]] = []
        self._start: Dict[str, float] = {}
        self._inputs: Dict[str, Any] = {}   # run_id -> {"messages": ..., "serialized": ...}
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.keep_previews = keep_previews

    # ── Lifecycle hooks ──────────────────────────────────────────────────────
    def on_chat_model_start(self, serialized: Dict[str, Any], messages, *, run_id=None, parent_run_id=None, **kwargs):
        rid = str(run_id)
        self._start[rid] = time.perf_counter()
        self._inputs[rid] = {
            "messages": messages,
            "serialized": serialized or {},
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
        }

    # Some providers emit only LLM hooks; normalize to chat expectations
    def on_llm_start(self, serialized: Dict[str, Any], prompts, *, run_id=None, parent_run_id=None, **kwargs):
        msgs = [{"role": "user", "content": p} for p in (prompts or [])]
        self.on_chat_model_start(serialized, msgs, run_id=run_id, parent_run_id=parent_run_id, **kwargs)

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _extract_usage_from_ai_message(self, msg) -> Tuple[int, int, int, Dict[str, Any]]:
        """Return (prompt_tokens, completion_tokens, total_tokens, raw_dict) from an AIMessage-like object."""
        # 1) New unified path
        um = getattr(msg, "usage_metadata", None) or {}
        if isinstance(um, dict) and (um.get("input_tokens") is not None or um.get("output_tokens") is not None):
            ip = int(um.get("input_tokens") or 0)
            op = int(um.get("output_tokens") or 0)
            to = int(um.get("total_tokens") or (ip + op))
            return ip, op, to, {"usage_metadata": um}

        # 2) Older path on response_metadata
        rm = getattr(msg, "response_metadata", None) or {}
        tu = rm.get("token_usage") or rm.get("usage") or {}
        if isinstance(tu, dict) and (tu.get("input_tokens") is not None or tu.get("prompt_tokens") is not None):
            ip = int(tu.get("input_tokens") or tu.get("prompt_tokens") or 0)
            op = int(tu.get("output_tokens") or tu.get("completion_tokens") or 0)
            to = int(tu.get("total_tokens") or (ip + op))
            return ip, op, to, {"response_token_usage": tu}

        # 3) Some providers stash usage in additional_kwargs["usage"]
        ak = getattr(msg, "additional_kwargs", {}) or {}
        aku = ak.get("usage") or {}
        if isinstance(aku, dict) and (aku.get("input_tokens") is not None or aku.get("prompt_tokens") is not None):
            ip = int(aku.get("input_tokens") or aku.get("prompt_tokens") or 0)
            op = int(aku.get("output_tokens") or aku.get("completion_tokens") or 0)
            to = int(aku.get("total_tokens") or (ip + op))
            return ip, op, to, {"additional_usage": aku}

        return 0, 0, 0, {}

    def _sum_from_generations(self, output) -> Tuple[int, int, int, Dict[str, Any], str]:
        """
        Aggregate usage across generations and return (prompt_tokens, completion_tokens, total_tokens, raw_dict, preview_text).
        Handles both ChatResult (with .generations) and single AIMessage-like outputs.
        """
        pt = ct = tt = 0
        raw: Dict[str, Any] = {}
        preview_text = ""

        gens = getattr(output, "generations", None) or []
        # Fallback: some providers emit a single AIMessage instead of a ChatResult
        if not gens:
            try:
                msg = getattr(output, "message", None) or output
                ip, op, to, raw_piece = self._extract_usage_from_ai_message(msg)
                if ip or op or to:
                    pt += ip
                    ct += op
                    tt += to
                    if raw_piece:
                        for k, v in raw_piece.items():
                            raw.setdefault(k, []).append(v)
                if not preview_text:
                    preview_text = getattr(msg, "content", "") or ""
                return pt, ct, (tt or pt + ct), raw, preview_text
            except Exception:
                pass

        for row in gens:
            if not isinstance(row, list):
                continue
            for gen in row:
                msg = getattr(gen, "message", None)

                # 1) Usage from AIMessage (usage_metadata / response_metadata / additional_kwargs)
                if msg is not None:
                    ip, op, to, raw_piece = self._extract_usage_from_ai_message(msg)
                    pt += ip
                    ct += op
                    tt += to
                    for k, v in raw_piece.items():
                        raw.setdefault(k, []).append(v)

                    # Build a human-friendly preview once (prefer text if present)
                    if not preview_text:
                        preview_text = getattr(gen, "text", None) or getattr(msg, "content", "") or ""

                # 2) Some providers put usage on generation_info
                gi = getattr(gen, "generation_info", {}) or {}
                gi_usage = gi.get("token_usage") or gi.get("usage") or {}
                if isinstance(gi_usage, dict):
                    ip = int(gi_usage.get("input_tokens") or gi_usage.get("prompt_tokens") or 0)
                    op = int(gi_usage.get("output_tokens") or gi_usage.get("completion_tokens") or 0)
                    to = int(gi_usage.get("total_tokens") or (ip + op))
                    if ip or op or to:
                        pt += ip
                        ct += op
                        tt += to
                        raw.setdefault("generation_info_token_usage", []).append(gi_usage)

                # 3) Capture tool_calls in a normalized way
                if msg is not None:
                    tc = getattr(msg, "tool_calls", None)
                    if not tc:
                        tc = (getattr(msg, "additional_kwargs", {}) or {}).get("tool_calls")
                    if tc:
                        raw.setdefault("tool_calls", []).append(tc)
                        if not preview_text:
                            try:
                                names = []
                                for c in tc:
                                    fn = (c.get("function", {}) if isinstance(c, dict) else {}) or {}
                                    names.append(fn.get("name", "tool"))
                                preview_text = f"[{len(tc)} tool call(s)] " + ", ".join(names)
                            except Exception:
                                preview_text = f"[{len(tc)} tool call(s)]"

        return pt, ct, (tt or pt + ct), raw, preview_text

    # ── Completion hooks ─────────────────────────────────────────────────────
    def on_chat_model_end(self, output, *, run_id=None, parent_run_id=None, **kwargs):

        # TEMPORARY DEBUG - remove after diagnosing
        print(f"\n{'='*60}")
        print(f"DEBUG: on_chat_model_end called, run_id={run_id}")
        print(f"  output type: {type(output)}")
        print(f"  output dir: {[x for x in dir(output) if not x.startswith('_')]}")
        if hasattr(output, 'usage_metadata'):
            print(f"  output.usage_metadata: {output.usage_metadata}")
        if hasattr(output, 'response_metadata'):
            print(f"  output.response_metadata: {output.response_metadata}")
        if hasattr(output, 'generations'):
            print(f"  output.generations: {output.generations}")
        print(f"{'='*60}\n")
        # END DEBUG

        rid = str(run_id)
        start = self._start.pop(rid, time.perf_counter())
        inputs = self._inputs.pop(rid, {})
        duration_ms = round((time.perf_counter() - start) * 1000.0, 3)

        # 1) Prefer message/generation paths
        pt, ct, tt, raw, preview = self._sum_from_generations(output)

        # 2) Strong fallback: top-level llm_output["token_usage"]
        if not (pt or ct or tt):
            try:
                llm_output = getattr(output, "llm_output", None) or {}
                tu = llm_output.get("token_usage") or llm_output.get("usage") or {}
                ip = int(tu.get("input_tokens") or tu.get("prompt_tokens") or 0)
                op = int(tu.get("output_tokens") or tu.get("completion_tokens") or 0)
                pt, ct, tt = ip, op, int(tu.get("total_tokens") or (ip + op))
                if tu:
                    raw.setdefault("llm_output", {}).update(tu)
            except Exception:
                pass

        # Update totals
        self.total_prompt_tokens += pt
        self.total_completion_tokens += ct
        self.total_tokens += tt

        # Build prompt/response previews
        msgs = inputs.get("messages") or []
        prompt_preview_lines = []
        for m in msgs:
            try:
                role = getattr(m, "type", None) or getattr(m, "role", "user")
                content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else None) or ""
                prompt_preview_lines.append(f"{role}: {content}")
            except Exception:
                continue
        prompt_preview = "\n".join(prompt_preview_lines)
        if self.keep_previews:
            prompt_preview = prompt_preview[: self.keep_previews]
            preview = (preview or "")[: self.keep_previews]

        # Pull model name if available
        serialized = inputs.get("serialized", {})
        model = (serialized.get("kwargs") or {}).get("model") or serialized.get("name")

        self.calls.append({
            "duration_ms": duration_ms,
            "usage": {
                "prompt_tokens": pt,
                "completion_tokens": ct,
                "total_tokens": tt,
                "raw": raw,
            },
            "model": model,
            "run_id": rid,
            "parent_run_id": inputs.get("parent_run_id") or (str(parent_run_id) if parent_run_id else None),
            "prompt_preview": prompt_preview,
            "response_preview": preview,
        })

    # Fallback path for non-chat LLMs
    def on_llm_end(self, response, *, run_id=None, **kwargs):
        try:
            self.on_chat_model_end(response, run_id=run_id, **kwargs)
        except Exception:
            pass




def aggregate_trace(tool_recorder: ToolCallRecorder, llm_recorder: LLMUsageRecorder, started_at: float) -> Dict[str, Any]:
    tool_exec_ms = defaultdict(float)
    tool_counts = defaultdict(int)
    grouped = defaultdict(list)
    for r in tool_recorder.records:
        name = r.get("name") or "tool"
        tool_exec_ms[name] += float(r.get("duration_ms") or 0.0)
        tool_counts[name] += 1
        grouped[name].append(r)
    return {
        "tool_order": [r.get("name") or "tool" for r in sorted(tool_recorder.records, key=lambda x: x.get("order", 0))],
        "tool_exec_ms": dict(tool_exec_ms),
        "tool_call_counts": dict(tool_counts),
        "tool_calls_grouped": dict(grouped),
        "token_breakdown": {
            "prompt_tokens": llm_recorder.total_prompt_tokens,
            "completion_tokens": llm_recorder.total_completion_tokens,
            "total_tokens": llm_recorder.total_tokens,
        },
        "total_exec_ms": round((time.perf_counter() - started_at) * 1000.0, 3),
        "raw_log": {"tools": tool_recorder.records, "llms": llm_recorder.calls},
    }
