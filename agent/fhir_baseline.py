"""
FHIRBaselineAgent — simple, self-contained FHIR agent.

Features:
- Loads tools via a provider (MCP over SSE or REST) and builds a prebuilt agent
- Executes a single TaskInterface entry (cleanup → prepare → run → validate)
- Thin batch wrapper to run tasks from a YAML file (environment/data/run_eval_temp.yaml)
- CLI main for quick test-driving

Notes:
- .env is loaded from environment/.env
- Tool naming mismatches vs. evaluator are tolerated for now
"""

import os
import sys
import json
import re
import time
import importlib
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import logging
from dataclasses import asdict

# Ensure project root is importable whether run as module (-m) or as a script
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import yaml
from dotenv import load_dotenv

from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from pydantic_core import ValidationError

from utils.prompt_paraphraser import paraphrase_prompt
from agent.interfaces.core_agent_interface import (
    AgentConfig,
    AgentRunOptions,
    CoreResult,
)
from agent.interfaces.fhir_agent_interface import FHIRAgentInterface

from utils.tool_providers import MCPToolProvider, RESTToolProvider, ToolProvider, MultiMCPToolProvider
from utils.callbacks import ToolCallRecorder, LLMUsageRecorder
from utils.fhir_formatting_helpers import build_fhir_execution_metadata
from utils.runtime_clock import _build_clock_block

from tasks.fhir_tasks_modular.task_interface_modular import ExecutionResult, TaskResult
from utils.task_loader import build_task


# Load .env from environment/.env
ENV_PATH = ROOT_DIR / "environment" / ".env"
load_dotenv(ENV_PATH)


SYSTEM_PROMPT = """You are a careful FHIR assistant. Think step-by-step. Use tools precisely and return concise final answers with required tags."""


# Logging setup
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fhir-baseline-agent")


def _truncate(value: Any, max_len: int = 300) -> str:
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False) if value is not None else ""
    return s if len(s) <= max_len else (s[:max_len] + "…")


def extract_text_from_agent_result(result: Any) -> str:
    """Best-effort to unwrap LangGraph prebuilt agent outputs into text."""
    try:
        if isinstance(result, dict) and "messages" in result:
            msgs = result["messages"]
            if isinstance(msgs, list) and msgs:
                last = msgs[-1]
                content = getattr(last, "content", None)
                if isinstance(content, str):
                    return content
        content = getattr(result, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False)
    except Exception:
        return str(result)


class FHIRBaselineAgent(FHIRAgentInterface):
    """Baseline FHIR agent: single-model, tool-augmented, no fancy planning."""

    def __init__(self, config: AgentConfig, provider: Optional[ToolProvider] = None, paraphrase: bool = False) -> None:
        """
        Args:
            config: Agent configuration (model, endpoints, system prompt, etc.)
            provider: Optional tool provider; if None, created from config
            paraphrase: If True, paraphrase task prompts before execution (default: False)
        """
        self._config = config
        self._provider = provider
        self._agent = None
        self._tools: List[Any] = []
        self._system = config.system_prompt or SYSTEM_PROMPT
        self._paraphrase = paraphrase

    @property
    def name(self) -> str:
        return "fhir-baseline"

    @property
    def config(self) -> AgentConfig:
        return self._config

    async def ainit(self) -> None:
        """Lazy init: create provider(s) if missing, load tools from all providers, build baseline tools agent."""
        # Create default provider from config if not supplied
        if self._provider is None:
            if (self._config.transport or "mcp").lower() == "rest":
                base_url = self._config.endpoint or os.getenv("FHIR_SERVER_URL", "http://localhost:7070/fhir")
                self._provider = RESTToolProvider(base_url)
                log.info("Using REST tool provider → %s", base_url)
            else:
                # Handle multiple MCP providers
                sse_url = self._config.endpoint or os.getenv("FHIR_MCP_SSE_URL", "http://localhost:8000/fhir_mcp")
                additional_endpoints = self._config.extra.get("additional_mcp_endpoints", []) if hasattr(self._config, 'extra') and self._config.extra else []

                # Combine all MCP endpoints
                all_endpoints = [sse_url] + additional_endpoints
                all_providers = []

                for endpoint in all_endpoints:
                    provider = MCPToolProvider(endpoint)
                    all_providers.append(provider)
                    log.info("Using MCP tool provider (SSE) → %s", endpoint)

                # If only one provider, use it directly for backward compatibility
                if len(all_providers) == 1:
                    self._provider = all_providers[0]
                else:
                    # Create a composite provider that combines tools from all providers
                    self._provider = MultiMCPToolProvider(all_providers)

        # Load tools via provider
        self._tools = await self._provider.get_tools()

        # error hardening for tools
        def _wrap_safe(tool: BaseTool) -> BaseTool:
            # If the tool raises ToolException, return this text to the LLM instead
            tool.handle_tool_error = lambda e: f"TOOL_ERROR: {type(e).__name__}: {e}"
            # If input validation fails, also return a message instead of raising
            tool.handle_validation_error = lambda e: f"VALIDATION_ERROR: {e}"
            return tool

        self._tools = [_wrap_safe(t) for t in self._tools]
        
        try:
            tool_names = [getattr(t, "name", "tool") for t in self._tools]
            log.info("Loaded %d tools: %s", len(self._tools), ", ".join(tool_names))
            # Debug: Check for memory tools
            memory_tools = [name for name in tool_names if 'memory' in name.lower() or 'search' in name.lower()]
            if memory_tools:
                log.info("Memory/reflexion tools found: %s", memory_tools)
            else:
                log.warning("No memory/reflexion tools detected in loaded tools")
        except Exception as e:
            log.info("Loaded %d tools (error getting names: %s)", len(self._tools), e)

        # Build a simple OpenAI Tools agent (no ReAct planning)
        def _normalize_openai_model_id(mid: str) -> str:
            return mid.split(":", 1)[1] if mid and mid.startswith("openai:") else mid

        model_id = _normalize_openai_model_id(self._config.model_id)
        # Testing this out
        llm = ChatOpenAI(
            model=model_id,
            streaming=False,
            model_kwargs={"stream_options": {"include_usage": True}}  # TEST DEBUG
        )


        log.info("Initialized chat model (tools): %s", model_id)

        prompt = ChatPromptTemplate.from_messages([
            ("system", self._system),
            ("system", "{clock}"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        agent = create_openai_tools_agent(llm=llm, tools=self._tools, prompt=prompt)
        self._agent = AgentExecutor(agent=agent, tools=self._tools, verbose=True, return_intermediate_steps=True)
        log.info("Created baseline tools agent (single-turn)")


    async def arun_text(self, prompt: str, options: Optional[AgentRunOptions] = None) -> CoreResult:
        """Run a single prompt through the agent and return CoreResult (domain-agnostic)."""
        if self._agent is None:
            await self.ainit()
        tool_rec, llm_rec = ToolCallRecorder(), LLMUsageRecorder()
        t0 = time.perf_counter()
        clock = _build_clock_block()
        out = await self._agent.ainvoke(
            {"input": prompt, "chat_history": [], "clock": clock},
            config={"callbacks": [tool_rec, llm_rec]},
        )
        final_text = (out.get("output") or "").strip()
        # Populate minimal CoreResult
        return CoreResult(final_text=final_text)


    async def arun_task_entry(
        self,
        task_entry: Dict[str, Any],
        options: Optional[AgentRunOptions] = None,
    ) -> Dict[str, Any]:
        """Run one FHIR task entry end-to-end and return execution + validation results."""
        if self._agent is None:
            await self.ainit()

        # Enforce the required fields present in YAML
        must = [
            "module",
            "class",
            "required_tool_call_sets",
            "required_resource_types",
            "prohibited_tools",
            "difficulty_level",
        ]
        missing = [k for k in must if k not in task_entry]
        if missing:
            raise ValueError(f"Missing required task fields: {missing}")

        # Instantiate the task
        task = build_task(task_entry)
        log.info("Starting task %s.%s", task_entry["module"], task_entry["class"])

        # Clean & seed data (best effort on cleanup)
        try:
            log.info("cleanup_test_data()")
            task.cleanup_test_data()

            log.info("prepare_test_data()")
            task.prepare_test_data()
            
        except Exception:
            raise(Exception("Failed to cleanup and prepare test data"))

        
        # Build the prompt (optionally paraphrased based on self._paraphrase)
        original_prompt = task.get_prompt()
        if self._paraphrase:
            task_prompt = paraphrase_prompt(original_prompt)
            log.info("Paraphrased prompt: %s", _truncate(task_prompt, 240))
        else:
            task_prompt = original_prompt


        clock = _build_clock_block()
        log.info("Prompt (truncated): %s", _truncate(task_prompt, 240))

        # Run model+tools with tracing callbacks
        tool_rec, llm_rec = ToolCallRecorder(), LLMUsageRecorder()
        t0 = time.perf_counter()

        out = await self._agent.ainvoke(
            {"input": task_prompt, "chat_history": [], "clock": clock},
            config={"callbacks": [tool_rec, llm_rec]},
        )

        final_text = (out.get("output") or "").strip()
        log.info("Final text (truncated): %s", _truncate(final_text, 280))

        # Aggregate traces → ExecutionResult-shaped fields
        meta = build_fhir_execution_metadata(
            prompt=f"{task_prompt}\n\n{clock}" if task_prompt else clock,
            final_text=final_text,
            started_at=t0,
            tool_recorder=tool_rec,
            llm_recorder=llm_rec,
            # Optional aliasing (left empty for now; adjust later if needed)
            name_aliases=None,
        )
        log.info("Trace tokens: total=%s, exec_ms=%.1f", meta.get("token_total"), meta.get("total_exec_ms"))
        # Tool usage logs (ordered)
        try:
            ordered = sorted(getattr(tool_rec, "records", []), key=lambda r: r.get("order", 0))
            for r in ordered:
                log.info(
                    "TOOL #%s %s | %sms | args=%s | out=%s",
                    r.get("order"),
                    r.get("name"),
                    r.get("duration_ms"),
                    _truncate(r.get("input", ""), 160),
                    _truncate(r.get("output", ""), 200),
                )
        except Exception:
            pass

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

        # Deterministic validation
        validator = getattr(task, "validate_response")
        task_result = validator(exec_res)
        failure_mode = task.identify_failure_mode(task_result)
        log.info(
            "Validation → success=%s | assertions=%s",
            getattr(task_result, "task_success", False),
            getattr(task_result, "assertion_error_message", None),
        )
        
        # Light validation (checks resource creation with fields present, not values)
        light_validator = getattr(task, "validate_response_light", None)
        if callable(light_validator):
            task_result_light = light_validator(exec_res)
        else:
            # Legacy tasks don't implement light validation; mark as not applicable
            task_result_light = TaskResult(
                task_success=None,
                assertion_error_message="Light validation not applicable for legacy task type",
                task_id=task.get_task_id(),
                task_name=task.get_task_name(),
                execution_result=exec_res,
            )
        log.info(
            "Light validation → success=%s | applicable=%s",
            getattr(task_result_light, "task_success", None),
            getattr(task_result_light, "task_success", None) is not None,
        )

        # Adding raw logs
        try:
            raw_logs = {
                "tools": getattr(tool_rec, "records", []),  
                "llms":  getattr(llm_rec, "calls", []),
            }
        except Exception:
            raw_logs = {}

        return {
            "task_module": task_entry["module"],
            "task_class": task_entry["class"],
            "execution_result": exec_res,
            "task_result": task_result,
            "task_result_light": task_result_light,
            "failure_mode": failure_mode,
            "final_text": final_text,
            "raw_logs": raw_logs,
            "intermediate_steps": out.get("intermediate_steps", []),
        }


    async def arun_task_variations_from_yaml(
        self,
        yaml_path: Union[str, Path],
        options: Optional[AgentRunOptions] = None,
    ) -> List[Dict[str, Any]]:
        """Run task variations defined in a YAML file with `variations` list.

        YAML structure:
        variations:
          - module: task_01_enter_new_patient
            class: EnterNewPatientTask
            template_params: {...}
            required_tool_call_sets: [...]
            required_resource_types: [...]
            prohibited_tools: [...]
            difficulty_level: 1
        """
        ypath = Path(yaml_path)
        if not ypath.is_absolute():
            ypath = ROOT_DIR / "environment" / "data" / ypath
        with open(ypath, "r") as f:
            cfg = yaml.safe_load(f) or {}
        vars_list: List[Dict[str, Any]] = cfg.get("variations", [])
        log.info("Loaded %d task variations from YAML: %s", len(vars_list), ypath)
        results: List[Dict[str, Any]] = []
        for entry in vars_list:
            log.info("→ Run variation %s.%s", entry.get("module"), entry.get("class"))
            res = await self.arun_task_entry(entry, options)
            results.append(res)
        log.info("Completed %d variations", len(results))
        return results


def _build_cli() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="FHIR Baseline Agent (MCP or REST tools)")
    ap.add_argument("--variations-yaml", dest="variations_yaml", 
                    default="exp_1_task_variation_updated.yaml",
                    help="YAML with task variations (module/class/template_params). Relative to environment/data if not absolute")
    ap.add_argument("--transport", default=os.getenv("FHIR_TRANSPORT", "mcp"), choices=["mcp", "rest"], help="Tool transport")
    ap.add_argument("--fhir-sse-url", default=os.getenv("FHIR_MCP_SSE_URL", "http://localhost:8000/fhir_mcp"))
    ap.add_argument("--rest-base-url", default=os.getenv("FHIR_SERVER_URL", "http://localhost:7070/fhir"))
    ap.add_argument("--model", default=os.getenv("BASELINE_MODEL", "openai:gpt-4.1-mini"))
    return ap


def main() -> None:
    ap = _build_cli()
    args = ap.parse_args()
    log.info("YAML: %s | transport=%s | model=%s", args.variations_yaml, args.transport, args.model)

    # Choose provider based on transport
    if args.transport == "rest":
        provider = RESTToolProvider(args.rest_base_url)
        endpoint = args.rest_base_url
    else:
        provider = MCPToolProvider(args.fhir_sse_url)
        endpoint = args.fhir_sse_url

    cfg = AgentConfig(
        model_id=args.model,
        system_prompt=SYSTEM_PROMPT,
        transport=args.transport,
        endpoint=endpoint,
    )

    agent = FHIRBaselineAgent(cfg, provider)

    import asyncio

    async def _run():
        await agent.ainit()
        results = await agent.arun_task_variations_from_yaml(args.variations_yaml)
        print(json.dumps(str(results), indent=2, ensure_ascii=False))

    asyncio.run(_run())


if __name__ == "__main__":
    main()