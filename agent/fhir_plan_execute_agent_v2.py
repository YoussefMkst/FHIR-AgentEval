# v2 — FHIRPlanExecuteAgent with tools-based Planner and single, long-lived Tools Executor

"""
FHIRPlanExecuteAgent — Plan-and-Execute agent for FHIR tasks.

- Planner (OpenAI Tools agent) can call memory/FHIR tools to draft a plan.
- Executor (OpenAI Tools agent) runs each step; NOT rebuilt per step; has all tools but is prompted to only use the step’s tool.
- Finalizer LLM synthesizes the final answer from step results.
- Uses standard ToolProvider (MCP/REST), callbacks, and evaluation harness.
"""

import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Ensure project root is importable
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import yaml
from dotenv import load_dotenv

from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import BaseMessage
from langchain.chat_models import init_chat_model
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

# NEW: tools agent primitives
from langchain.agents import AgentExecutor, create_openai_tools_agent

from agent.interfaces.core_agent_interface import AgentConfig, AgentRunOptions, CoreResult
from agent.interfaces.fhir_agent_interface import FHIRAgentInterface
from utils.tool_providers import MCPToolProvider, RESTToolProvider, ToolProvider, MultiMCPToolProvider
from utils.callbacks import ToolCallRecorder, LLMUsageRecorder
from utils.fhir_formatting_helpers import build_fhir_execution_metadata
from tasks.fhir_tasks_modular.task_interface_modular import ExecutionResult
from utils.task_loader import build_task

# --- Setup ---
ENV_PATH = ROOT_DIR / "environment" / ".env"
load_dotenv(ENV_PATH)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fhir-plan-execute-agent")

# --- Prompts ---
def _load_prompt(filename: str) -> str:
    """Load a prompt from prompts/fhir/ directory."""
    filepath = ROOT_DIR / "prompts" / "fhir" / filename
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    log.warning("Prompt file not found: %s", filepath)
    return ""

DEFAULT_PLANNER_SYSTEM_PROMPT = _load_prompt("fhir_planner_default_system_prompt.txt")

# IMPORTANT: single, persistent executor; prompt enforces "only the allowed tool"
EXECUTOR_SYSTEM_PROMPT = """You are the FHIR Execution Agent.
You MUST execute ONLY the tool named: {allowed_tool}.
- Do not call any other tools unless {allowed_tool} is empty or explicitly "null".

When the step is satisfied, produce a concise result for THIS step (not the final answer).
"""

FINALIZER_SYSTEM_PROMPT = "You are a careful assistant. Produce the final answer for the original objective using the notes compiled from the executed plan."

# --- Helpers ---
def _truncate(value: Any, max_len: int = 300) -> str:
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str) if value is not None else ""
    return s if len(s) <= max_len else (s[:max_len] + "…")

def _extract_text_from_result(result: Any) -> str:
    try:
        if isinstance(result, dict) and "messages" in result:
            msgs = result["messages"]
            if isinstance(msgs, list) and msgs:
                content = getattr(msgs[-1], "content", None)
                if isinstance(content, str):
                    return content
        content = getattr(result, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        return str(result)


class FHIRPlanExecuteAgent(FHIRAgentInterface):
    def __init__(self, config: AgentConfig, provider: Optional[ToolProvider] = None, planner_system_prompt: Optional[str] = None) -> None:
        self._config = config
        self._provider = provider
        self._tools: List[Any] = []
        self._planner_agent_exec: Optional[AgentExecutor] = None
        self._executor_agent_exec: Optional[AgentExecutor] = None
        self._finalizer = None
        self._planner_system_prompt: str = planner_system_prompt or DEFAULT_PLANNER_SYSTEM_PROMPT

    @property
    def name(self) -> str:
        return "fhir-plan-execute"

    @property
    def config(self) -> AgentConfig:
        return self._config

    async def ainit(self) -> None:
        # Build provider(s)
        if self._provider is None:
            if (self._config.transport or "mcp").lower() == "rest":
                base_url = self._config.endpoint or os.getenv("FHIR_SERVER_URL", "http://localhost:7070/fhir")
                self._provider = RESTToolProvider(base_url)
                log.info("Using REST tool provider → %s", base_url)
            else:
                # Support multiple MCP endpoints (e.g., FHIR + memory)
                sse_url = self._config.endpoint or os.getenv("FHIR_MCP_SSE_URL", "http://localhost:8000/fhir_mcp")
                additional_endpoints = self._config.extra.get("additional_mcp_endpoints", []) if hasattr(self._config, 'extra') and self._config.extra else []
                all_endpoints = [sse_url] + additional_endpoints
                providers = [MCPToolProvider(ep) for ep in all_endpoints]
                for ep in all_endpoints:
                    log.info("Using MCP tool provider (SSE) → %s", ep)
                self._provider = providers[0] if len(providers) == 1 else MultiMCPToolProvider(providers)

        # Load tools
        self._tools = await self._provider.get_tools()

        # Harden tools
        def _wrap_safe(tool: BaseTool) -> BaseTool:
            tool.handle_tool_error = lambda e: f"TOOL_ERROR: {type(e).__name__}: {e}"
            tool.handle_validation_error = lambda e: f"VALIDATION_ERROR: {e}"
            return tool
        self._tools = [_wrap_safe(t) for t in self._tools]

        try:
            tool_names = [getattr(t, "name", "tool") for t in self._tools]
            log.info("Loaded %d tools: %s", len(self._tools), ", ".join(tool_names))
        except Exception as e:
            log.info("Loaded %d tools (error getting names: %s)", len(self._tools), e)

                # Build a simple OpenAI Tools agent (no ReAct planning)
        def _normalize_openai_model_id(mid: str) -> str:
            return mid.split(":", 1)[1] if mid and mid.startswith("openai:") else mid

        model_id = _normalize_openai_model_id(self._config.model_id)
        # Build models
        planner_llm = init_chat_model(self._config.model_id)
        #planner_llm = ChatOpenAI(model=model_id, streaming=False)
        executor_llm = init_chat_model(self._config.model_id)
        #executor_llm = ChatOpenAI(model=model_id, streaming=False)
        self._finalizer = init_chat_model(self._config.model_id)
        #self._finalizer = ChatOpenAI(model=model_id, streaming=False)
        log.info("Initialized LLMs for Planner, Executor, Finalizer")

        # ---- Planner: OpenAI Tools agent (can call memory/FHIR tools during planning) ----
        planner_prompt = ChatPromptTemplate.from_messages([
            ("system", self._planner_system_prompt),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "Objective:\n{objective}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        planner_agent = create_openai_tools_agent(llm=planner_llm, tools=self._tools, prompt=planner_prompt)
        self._planner_agent_exec = AgentExecutor(
            agent=planner_agent,
            tools=self._tools,
            verbose=True,
            return_intermediate_steps=True
        )

        # ---- Executor: single, long-lived OpenAI Tools agent (ALL tools bound) ----
        executor_prompt = ChatPromptTemplate.from_messages([
            ("system", EXECUTOR_SYSTEM_PROMPT),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        executor_agent = create_openai_tools_agent(llm=executor_llm, tools=self._tools, prompt=executor_prompt)
        self._executor_agent_exec = AgentExecutor(
            agent=executor_agent,
            tools=self._tools,
            verbose=True,
            return_intermediate_steps=True
        )
        log.info("Planner & Executor agents created (tools-enabled). Finalizer is plain LLM.")

    async def _get_plan(self, objective: str, callbacks: list) -> (List[str], List[Optional[str]]):
        """Call the planner agent (tools-enabled) to produce a JSON plan."""
        log.info("PLANNING PHASE")
        assert self._planner_agent_exec is not None, "Planner agent not initialized"
        res = await self._planner_agent_exec.ainvoke(
            {"objective": objective, "chat_history": []},
            config={"callbacks": callbacks}
        )
        text = (res.get("output") or "").strip()
        log.info("Raw plan: %s", _truncate(text, 1200))

        steps: List[str] = []
        planned_tools: List[Optional[str]] = []
        try:
            data = json.loads(text)
            for s in data.get("steps", []):
                if isinstance(s, dict):
                    steps.append(s.get("step", "").strip())
                    planned_tools.append(s.get("tool"))
                elif isinstance(s, str):
                    steps.append(s.strip())
                    planned_tools.append(None)
        except Exception:
            # Fallback: line-split
            steps = [s.strip("-• ").strip() for s in text.split("\n") if s.strip()]
            planned_tools = [None] * len(steps)

        if not steps:
            steps = [f"Execute the objective: {objective}"]
            planned_tools = [None]

        log.info("Parsed plan (%d steps)", len(steps))
        for i, (s, tname) in enumerate(zip(steps, planned_tools), 1):
            log.info("  %d) %s | tool=%s", i, s, tname)
        return steps, planned_tools


    async def arun_task_entry(self, task_entry: Dict[str, Any], options: Optional[AgentRunOptions] = None) -> Dict[str, Any]:
        if not all([self._planner_agent_exec, self._executor_agent_exec, self._finalizer]):
            await self.ainit()

        # Required fields check
        must = ["module", "class", "required_tool_call_sets", "required_resource_types", "prohibited_tools", "difficulty_level"]
        missing = [k for k in must if k not in task_entry]
        if missing:
            raise ValueError(f"Missing required task fields: {missing}")

        # Task build & fixture hooks
        task = build_task(task_entry)
        log.info("Starting task %s.%s", task_entry["module"], task_entry["class"])
        try:
            if hasattr(task, "cleanup_test_data"):
                task.cleanup_test_data()
        except Exception:
            pass
        task.prepare_test_data()

        # Objective and tracing
        objective = task.get_prompt()
        log.info("Objective: %s", _truncate(objective, 240))
        tool_rec, llm_rec = ToolCallRecorder(), LLMUsageRecorder()
        shared_callbacks = [tool_rec, llm_rec]
        t0 = time.perf_counter()

        # 1) Plan
        steps, planned_tools = await self._get_plan(objective, shared_callbacks)
        log.info("Plan is: %s", steps)

        # 2) Execute (single executor reused across steps)
        notes: List[str] = []
        for idx, (step, allowed_tool) in enumerate(zip(steps, planned_tools), 1):
            log.info("--- Executing step %d/%d: %s (allowed_tool=%s) ---", idx, len(steps), step, allowed_tool)
            # Build a concise instruction for THIS step
            human_input = (
                f"Current step:\n{step}\n\n"
                f"Notes so far (observations and prior results):\n{_truncate('\\n'.join(notes), 2000) or '(none)'}"
            )
            res = await self._executor_agent_exec.ainvoke(
                {
                    "input": human_input,
                    "allowed_tool": (allowed_tool or ""),
                    "chat_history": [],
                },
                config={"callbacks": shared_callbacks}
            )
            step_result = (res.get("output") or "").strip()
            if step_result:
                notes.append(f"[Step {idx} Result] {step_result}")
            log.info("Step %d result: %s", idx, _truncate(step_result, 400))

        # 3) Finalize
        final_prompt = ChatPromptTemplate.from_messages([
            ("system", FINALIZER_SYSTEM_PROMPT),
            ("human", f"Objective:\n{objective}\n\nNotes from executed plan:\n" + ("\n".join(notes) if notes else "(none)")),
        ])
        chain = final_prompt | self._finalizer
        final_resp = await chain.ainvoke({}, config={"callbacks": shared_callbacks})
        final_text = _extract_text_from_result(final_resp).strip()
        log.info("Final Answer: %s", _truncate(final_text, 280))

        # Tool logs
        try:
            ordered = sorted(getattr(tool_rec, "records", []), key=lambda r: r.get("order", 0))
            for rec in ordered:
                log.info(
                    "TOOL #%s %s | %sms | args=%s | out=%s",
                    rec.get("order"),
                    rec.get("name"),
                    rec.get("duration_ms"),
                    _truncate(rec.get("input", ""), 200),
                    _truncate(rec.get("output", ""), 200),
                )
        except Exception:
            pass

        # 4) Evaluate / package
        meta = build_fhir_execution_metadata(
            prompt=objective,
            final_text=final_text,
            started_at=t0,
            tool_recorder=tool_rec,
            llm_recorder=llm_rec,
        )
        exec_res = ExecutionResult(
            execution_success=True,
            response_msg=meta["response_msg"],
            token_total=meta["token_total"],
            input_query=meta["input_query"],
            total_exec_ms=meta["total_exec_ms"],
            tool_order=meta["tool_order"],
            tool_exec_ms=meta["tool_exec_ms"],
            tool_calls=meta["tool_calls"],
            tool_call_counts=meta["tool_call_counts"],
        )

        validator = getattr(task, "validate_response_with_benchmark", getattr(task, "validate_response"))
        validator = getattr(task, "validate_response")
        task_result = validator(exec_res)
        failure_mode = task.identify_failure_mode(task_result)
        log.info("Validation → success=%s | assertions=%s", getattr(task_result, "task_success", False), getattr(task_result, "assertion_error_message", None))

        # Raw logs
        try:
            raw_logs = {
                "tools": getattr(tool_rec, "records", []),
                "llms": getattr(llm_rec, "calls", []),
            }
        except Exception:
            raw_logs = {}

        return {
            "task_module": task_entry["module"],
            "task_class": task_entry["class"],
            "execution_result": exec_res,
            "task_result": task_result,
            "failure_mode": failure_mode,
            "final_text": final_text,
            "planner_steps": steps,
            "planned_tools": planned_tools,
            "raw_logs": raw_logs
        }

    async def arun_text(self, prompt: str, options: Optional[AgentRunOptions] = None) -> CoreResult:
        if not all([self._planner_agent_exec, self._executor_agent_exec, self._finalizer]):
            await self.ainit()
        tool_rec, llm_rec = ToolCallRecorder(), LLMUsageRecorder()
        callbacks = [tool_rec, llm_rec]

        steps, planned_tools = await self._get_plan(prompt, callbacks)
        notes: List[str] = []
        for idx, (step, allowed_tool) in enumerate(zip(steps, planned_tools), 1):
            human_input = f"Current step:\n{step}\n\nNotes so far:\n{_truncate('\\n'.join(notes), 1800) or '(none)'}"
            res = await self._executor_agent_exec.ainvoke(
                {"input": human_input, "allowed_tool": (allowed_tool or ""), "chat_history": []},
                config={"callbacks": callbacks}
            )
            txt = (res.get("output") or "").strip()
            if txt:
                notes.append(txt)

        final_prompt = ChatPromptTemplate.from_messages([
            ("system", FINALIZER_SYSTEM_PROMPT),
            ("human", f"Objective:\n{prompt}\n\nNotes:\n" + ("\n".join(notes) if notes else "(none)")),
        ])
        chain = final_prompt | self._finalizer
        final_resp = await chain.ainvoke({}, config={"callbacks": callbacks})
        final_text = _extract_text_from_result(final_resp).strip()
        return CoreResult(final_text=final_text)

    async def arun_task_variations_from_yaml(self, yaml_path: Union[str, Path], options: Optional[AgentRunOptions] = None) -> List[Dict[str, Any]]:
        ypath = Path(yaml_path)
        if not ypath.is_absolute():
            ypath = ROOT_DIR / "environment" / "data" / ypath
        with open(ypath, "r") as f:
            cfg = yaml.safe_load(f) or {}
        vars_list = cfg.get("variations", [])
        log.info("Loaded %d task variations from %s", len(vars_list), ypath)
        results = []
        for entry in vars_list:
            log.info("→ Run variation %s.%s", entry.get("module"), entry.get("class"))
            results.append(await self.arun_task_entry(entry, options))
        log.info("Completed %d variations", len(results))
        return results


def main() -> None:
    ap = argparse.ArgumentParser(description="FHIR Plan-and-Execute Agent v2")
    ap.add_argument("--variations-yaml", dest="variations_yaml",
                    default="exp_1_task_variation_updated.yaml",
                    help="YAML with task variations (module/class/template_params). Relative to environment/data if not absolute")
    ap.add_argument("--transport", default=os.getenv("FHIR_TRANSPORT", "mcp"), choices=["mcp", "rest"])
    ap.add_argument("--fhir-sse-url", default=os.getenv("FHIR_MCP_SSE_URL", "http://localhost:8000/fhir_mcp"))
    ap.add_argument("--rest-base-url", default=os.getenv("FHIR_SERVER_URL", "http://localhost:7070/fhir"))
    ap.add_argument("--model", default=os.getenv("PLANEXEC_MODEL", "openai:gpt-4.1-mini"))
    args = ap.parse_args()

    log.info("YAML: %s | transport=%s | model=%s", args.variations_yaml, args.transport, args.model)
    endpoint = args.rest_base_url if args.transport == "rest" else args.fhir_sse_url
    cfg = AgentConfig(model_id=args.model, transport=args.transport, endpoint=endpoint)
    agent = FHIRPlanExecuteAgent(cfg)

    import asyncio

    async def _run():
        await agent.ainit()
        results = await agent.arun_task_variations_from_yaml(args.variations_yaml)
        print("TOOLS USED (ordered):", " → ".join([t for r in results for t in (r["execution_result"].tool_order or [])]))
        print(json.dumps({"summary": [{
            "task": f"{r['task_module']}.{r['task_class']}",
            "success": bool(getattr(r.get("task_result"), "task_success")),
            "assertions": getattr(r.get("task_result"), "assertion_error_message", None),
            "final_text": r.get("final_text", ""),
        } for r in results]}, indent=2, ensure_ascii=False, default=str))

    asyncio.run(_run())

if __name__ == "__main__":
    main()
