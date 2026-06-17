"""
FHIRClaudeCodeAgent — drives a remote `claude -p` (Claude Code CLI) over SSH and
shapes the result into the same dict the in-process FHIRBaselineAgent returns,
so the experiment harness, validators, and CSV summary work unchanged.

Wire-level details verified against `claude -p --output-format stream-json`
(Claude Code 2.1.128). NDJSON event types observed:
  - {type:"system", subtype:"init", tools, mcp_servers, session_id, model, ...}
  - {type:"rate_limit_event", ...}                               (informational)
  - {type:"assistant", message:{content:[{type:"text"|"tool_use", ...}], usage:{...}}, ...}
  - {type:"user",      message:{content:[{type:"tool_result", tool_use_id, content:[...]}, ...]}, timestamp, ...}
  - {type:"result", subtype:"success", is_error, duration_ms, num_turns,
                    result, total_cost_usd, usage, permission_denials, ...}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Project root importable
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Load environment/.env so FHIR_SERVER_URL (and any other vars build_task() or
# task subclasses read from os.environ) are populated before the runner builds
# tasks. Mirrors what agent/fhir_baseline.py does at import time.
from dotenv import load_dotenv  # type: ignore
load_dotenv(ROOT_DIR / "environment" / ".env")

from agent.interfaces.core_agent_interface import AgentConfig, AgentRunOptions, CoreResult
from agent.interfaces.fhir_agent_interface import FHIRAgentInterface
from tasks.fhir_tasks_modular.task_interface_modular import ExecutionResult, TaskResult
from utils.fhir_formatting_helpers import build_fhir_execution_metadata
from utils.prompt_paraphraser import paraphrase_prompt
from utils.task_loader import build_task

log = logging.getLogger("fhir-claude-code-agent")

MCP_PREFIX = "mcp__"

# Built-in Claude Code tools we want auto-approved during a benchmark run. This
# is the full default toolset Claude Code 2.x exposes when started in -p mode
# without user-level restrictions. Listing them in --allowedTools means each
# call is auto-approved (no permission prompt) without requiring
# bypassPermissions mode (which Claude Code refuses to run as root).
_DEFAULT_BUILTIN_TOOLS = [
    "Bash",
    "Edit",
    "Write",
    "Read",
    "Glob",
    "Grep",
    "WebFetch",
    "WebSearch",
    "Task",
    "TodoWrite",
    "NotebookEdit",
    "ToolSearch",
    "ListMcpResourcesTool",
    "ReadMcpResourceTool",
    "Skill",
    # AskUserQuestion intentionally omitted: in `-p` mode no human can answer,
    # and giving the model an "ask the user" escape hatch lets it punt instead
    # of solving the task.
]


def _allowed_tools_from_mcp_config(mcp_config_text: str) -> str:
    """Build a combined --allowedTools value covering both MCP servers and the
    Claude Code default built-in toolset. The MCP portion is derived from the
    config JSON's mcpServers keys (e.g. 'mcp__fhir__*'). The built-in portion is
    the constant _DEFAULT_BUILTIN_TOOLS list above."""
    cfg = json.loads(mcp_config_text)
    server_names = list((cfg.get("mcpServers") or {}).keys())
    if not server_names:
        raise ValueError("MCP config has no mcpServers — no MCP tools would be allowed.")
    mcp_patterns = [f"mcp__{name}__*" for name in server_names]
    return ",".join(mcp_patterns + _DEFAULT_BUILTIN_TOOLS)


def _strip_mcp_prefix(name: str) -> str:
    """`mcp__fhir__searchResources` -> `searchResources`. Bare names match the
    validator's required_tool_call_sets."""
    if not name or not name.startswith(MCP_PREFIX):
        return name
    rest = name[len(MCP_PREFIX):]
    parts = rest.split("__", 1)
    return parts[1] if len(parts) == 2 else rest


def _flatten_tool_result_content(content: Any) -> str:
    """tool_result.content is typically a list of {type:'text', text:...} blocks.
    Join their text payloads. Fall back to JSON dump for unknown shapes."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out: List[str] = []
        for block in content:
            if isinstance(block, dict):
                t = block.get("type")
                if t == "text" and isinstance(block.get("text"), str):
                    out.append(block["text"])
                else:
                    out.append(json.dumps(block, ensure_ascii=False))
            else:
                out.append(str(block))
        return "\n".join(out)
    if content is None:
        return ""
    return json.dumps(content, ensure_ascii=False)


@dataclass
class _ToolRecorderShim:
    """Quacks like utils.callbacks.ToolCallRecorder for build_fhir_execution_metadata."""

    records: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class _LLMRecorderShim:
    """Quacks like utils.callbacks.LLMUsageRecorder for build_fhir_execution_metadata."""

    total_tokens: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    calls: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class _ParsedRun:
    """All fields lifted out of a single claude -p stream."""

    tool_recorder: _ToolRecorderShim
    llm_recorder: _LLMRecorderShim
    final_text: str
    is_error: bool
    duration_ms: Optional[float]
    num_turns: Optional[int]
    total_cost_usd: Optional[float]
    session_id: Optional[str]
    model: Optional[str]
    init_tools: List[str]
    init_mcp_servers: List[Dict[str, Any]]
    permission_denials: List[Any]
    terminal_reason: Optional[str]
    raw_events: List[Dict[str, Any]]
    stderr: str
    process_exit_code: int


class FHIRClaudeCodeAgent(FHIRAgentInterface):
    """Adapter: shells out to a remote Claude Code CLI per task and normalizes
    its stream-json output into the same result dict FHIRBaselineAgent returns."""

    def __init__(
        self,
        config: AgentConfig,
        mcp_config_path: Path,
        ssh_target: Optional[str] = None,
        paraphrase: bool = False,
        max_turns: int = 50,
        keep_raw_events: bool = False,
    ) -> None:
        self._config = config
        self._mcp_config_path = Path(mcp_config_path)
        self._ssh_target = ssh_target  # None => run claude locally (useful for smoke tests)
        self._paraphrase = paraphrase
        self._max_turns = max_turns
        self._keep_raw_events = keep_raw_events

        if not self._mcp_config_path.exists():
            raise FileNotFoundError(f"MCP config not found: {self._mcp_config_path}")
        # Validate the JSON parses now so we fail fast.
        try:
            self._mcp_config_text = self._mcp_config_path.read_text(encoding="utf-8")
            json.loads(self._mcp_config_text)
        except Exception as e:
            raise ValueError(f"MCP config at {self._mcp_config_path} is not valid JSON: {e}")

        self._system_prompt = config.system_prompt or ""

    @property
    def name(self) -> str:
        return "fhir-claude-code"

    @property
    def config(self) -> AgentConfig:
        return self._config

    async def ainit(self) -> None:
        """Verify `claude` is reachable wherever we'll invoke it."""
        cmd = self._wrap_remote(["claude", "--version"])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"`claude --version` failed (exit {proc.returncode}) "
                f"on target={self._ssh_target!r}. stderr: {stderr.decode(errors='replace')}"
            )
        log.info(
            "Claude Code reachable on target=%s: %s",
            self._ssh_target or "local",
            stdout.decode(errors="replace").strip(),
        )

    async def arun_text(self, prompt: str, options: Optional[AgentRunOptions] = None) -> CoreResult:
        """Run a free-form prompt; useful for ad-hoc checks. Not used by the harness."""
        parsed = await self._run_remote_claude(prompt)
        return CoreResult(final_text=parsed.final_text)

    async def arun_task_entry(
        self,
        task_entry: Dict[str, Any],
        options: Optional[AgentRunOptions] = None,
    ) -> Dict[str, Any]:
        """Run one task end-to-end (cleanup -> prepare -> remote claude -p ->
        validate). Returns the same dict shape as FHIRBaselineAgent."""
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

        task = build_task(task_entry)
        log.info("Starting task %s.%s", task_entry["module"], task_entry["class"])

        # Retry cleanup+prepare on any failure (most often transient HAPI
        # connection resets during heavy-prep tasks like 12*/14*/15*).
        # Backoff: 10s, 30s, 60s.
        for attempt in range(1, 4):
            try:
                log.info("cleanup_test_data() (attempt %d/3)", attempt)
                task.cleanup_test_data()
                log.info("prepare_test_data() (attempt %d/3)", attempt)
                task.prepare_test_data()
                break
            except Exception as e:
                if attempt == 3:
                    raise Exception(f"Failed to cleanup and prepare test data after 3 attempts: {e}")
                wait = (10, 30, 60)[attempt - 1]
                log.warning("cleanup/prepare error on attempt %d/3: %s — retrying in %ds", attempt, e, wait)
                await asyncio.sleep(wait)

        original_prompt = task.get_prompt()
        task_prompt = paraphrase_prompt(original_prompt) if self._paraphrase else original_prompt
        log.info("Prompt (first 240 chars): %s", task_prompt[:240])

        t0 = time.perf_counter()
        parsed = await self._run_remote_claude(task_prompt)
        wall_ms = round((time.perf_counter() - t0) * 1000.0, 3)

        # build_fhir_execution_metadata uses perf_counter()-now to compute
        # total_exec_ms from started_at. We override with the value Claude Code
        # reports in the result event when available; otherwise fall back to
        # wall-clock measured here.
        meta = build_fhir_execution_metadata(
            prompt=task_prompt,
            final_text=parsed.final_text,
            started_at=t0,
            tool_recorder=parsed.tool_recorder,
            llm_recorder=parsed.llm_recorder,
            name_aliases=None,
        )
        if parsed.duration_ms is not None:
            meta["total_exec_ms"] = parsed.duration_ms
        else:
            meta["total_exec_ms"] = wall_ms

        execution_success = (not parsed.is_error) and parsed.process_exit_code == 0
        exec_res = ExecutionResult(
            execution_success=execution_success,
            response_msg=meta["response_msg"],
            token_total=meta["token_total"],
            input_query=meta["input_query"],
            total_exec_ms=meta["total_exec_ms"],
            tool_order=meta["tool_order"],
            tool_exec_ms=meta["tool_exec_ms"],
            tool_calls=meta["tool_calls"],
            tool_call_counts=meta["tool_call_counts"],
        )

        validator = getattr(task, "validate_response")
        task_result = validator(exec_res)
        failure_mode = task.identify_failure_mode(task_result)
        log.info(
            "Validation -> success=%s | assertions=%s",
            getattr(task_result, "task_success", False),
            getattr(task_result, "assertion_error_message", None),
        )

        light_validator = getattr(task, "validate_response_light", None)
        if callable(light_validator):
            task_result_light = light_validator(exec_res)
        else:
            task_result_light = TaskResult(
                task_success=None,
                assertion_error_message="Light validation not applicable for legacy task type",
                task_id=task.get_task_id(),
                task_name=task.get_task_name(),
                execution_result=exec_res,
            )

        raw_logs: Dict[str, Any] = {
            "tools": parsed.tool_recorder.records,
            "llms": parsed.llm_recorder.calls,
            "session_id": parsed.session_id,
            "model": parsed.model,
            "init_tools": parsed.init_tools,
            "init_mcp_servers": parsed.init_mcp_servers,
            "total_cost_usd": parsed.total_cost_usd,
            "num_turns": parsed.num_turns,
            "permission_denials": parsed.permission_denials,
            "terminal_reason": parsed.terminal_reason,
            "stderr": parsed.stderr,
            "process_exit_code": parsed.process_exit_code,
        }
        if self._keep_raw_events:
            raw_logs["raw_events"] = parsed.raw_events

        return {
            "task_module": task_entry["module"],
            "task_class": task_entry["class"],
            "execution_result": exec_res,
            "task_result": task_result,
            "task_result_light": task_result_light,
            "failure_mode": failure_mode,
            "final_text": parsed.final_text,
            "raw_logs": raw_logs,
            "intermediate_steps": [],
        }

    async def arun_task_variations_from_yaml(
        self,
        yaml_path,
        options: Optional[AgentRunOptions] = None,
    ) -> List[Dict[str, Any]]:
        """Run all task variations in a YAML file sequentially. The experiment
        runner doesn't call this directly (it manages the loop itself for the
        per-tag CSV), but the FHIRAgentInterface ABC requires it."""
        import yaml as _yaml  # local import to avoid top-level dep
        ypath = Path(yaml_path)
        if not ypath.is_absolute():
            ypath = ROOT_DIR / "environment" / "data" / ypath
        with ypath.open("r", encoding="utf-8") as f:
            cfg = _yaml.safe_load(f) or {}
        entries: List[Dict[str, Any]] = cfg.get("variations", [])
        results: List[Dict[str, Any]] = []
        for entry in entries:
            results.append(await self.arun_task_entry(entry, options))
        return results

    # ---- internals --------------------------------------------------------

    def _wrap_remote(self, argv: List[str]) -> List[str]:
        """Wrap a local argv with ssh if a target is configured. Quoting matters
        because ssh re-shell-evaluates the joined command on the remote."""
        if not self._ssh_target:
            return argv
        remote = " ".join(shlex.quote(a) for a in argv)
        return ["ssh", self._ssh_target, remote]

    def _build_claude_argv(self, prompt: str) -> List[str]:
        """The exact `claude -p ...` argv. Inline the MCP config JSON (single
        line) so no droplet-side state is needed.

        Tool policy:
        - --allowedTools enumerates every MCP tool pattern (mcp__<server>__*)
          AND the Claude Code default built-in toolset (Bash, Read, Edit, …,
          WebFetch, WebSearch, etc.). Listing tools in --allowedTools auto-
          approves each call without needing --permission-mode bypassPermissions
          (which Claude Code refuses under root/sudo for safety).
        - --strict-mcp-config still applies so only the MCP servers inlined via
          --mcp-config are loaded (no droplet-side .mcp.json leakage)."""
        mcp_inline = json.dumps(json.loads(self._mcp_config_text), separators=(",", ":"))
        allowed = _allowed_tools_from_mcp_config(self._mcp_config_text)
        argv: List[str] = [
            "claude",
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",  # required by stream-json
            "--strict-mcp-config",
            "--mcp-config",
            mcp_inline,
            "--max-turns",
            str(self._max_turns),
            "--no-session-persistence",
            "--allowedTools",
            allowed,
        ]
        if self._system_prompt:
            argv.extend(["--append-system-prompt", self._system_prompt])
        # Pass a model alias if the AgentConfig requested one. Anthropic-hosted
        # Claude Code accepts e.g. "sonnet"/"opus"/full ids; the AgentConfig
        # in the runner uses prefixes like "openai:gpt-4.1-mini" for the
        # LangChain baselines, which are NOT valid here, so only pass it
        # through if it isn't an openai:* id.
        mid = self._config.model_id or ""
        if mid and not mid.startswith("openai:"):
            argv.extend(["--model", mid])
        argv.append(prompt)
        return argv

    async def _run_remote_claude(self, prompt: str) -> _ParsedRun:
        argv = self._wrap_remote(self._build_claude_argv(prompt))
        log.info("Spawning: %s ... <prompt of %d chars>", " ".join(argv[:6]), len(prompt))

        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Parse stdout incrementally so we can capture event-arrival timestamps
        # for per-tool timing.
        tool_rec = _ToolRecorderShim()
        llm_rec = _LLMRecorderShim()
        raw_events: List[Dict[str, Any]] = []

        # tool_use_id -> {name, input, t_start, order}
        pending: Dict[str, Dict[str, Any]] = {}
        order_counter = 0

        final_text = ""
        is_error = False
        duration_ms: Optional[float] = None
        num_turns: Optional[int] = None
        total_cost_usd: Optional[float] = None
        session_id: Optional[str] = None
        model: Optional[str] = None
        init_tools: List[str] = []
        init_mcp_servers: List[Dict[str, Any]] = []
        permission_denials: List[Any] = []
        terminal_reason: Optional[str] = None

        assert proc.stdout is not None
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # Non-JSON noise (banner, shell rc echo, etc.) — keep for debugging.
                raw_events.append({"_unparsable": line})
                continue
            raw_events.append(event)

            etype = event.get("type")
            now = time.perf_counter()

            if etype == "system" and event.get("subtype") == "init":
                session_id = event.get("session_id")
                model = event.get("model")
                init_tools = list(event.get("tools") or [])
                init_mcp_servers = list(event.get("mcp_servers") or [])
                continue

            if etype == "assistant":
                msg = event.get("message") or {}
                usage = msg.get("usage") or {}
                if usage:
                    in_tok = int(usage.get("input_tokens") or 0)
                    out_tok = int(usage.get("output_tokens") or 0)
                    cache_create = int(usage.get("cache_creation_input_tokens") or 0)
                    cache_read = int(usage.get("cache_read_input_tokens") or 0)
                    llm_rec.calls.append(
                        {
                            "model": msg.get("model"),
                            "input_tokens": in_tok,
                            "output_tokens": out_tok,
                            "cache_creation_input_tokens": cache_create,
                            "cache_read_input_tokens": cache_read,
                        }
                    )
                for block in msg.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "tool_use":
                        tool_id = block.get("id") or ""
                        raw_name = block.get("name") or ""
                        bare_name = _strip_mcp_prefix(raw_name)
                        tool_input = block.get("input") or {}
                        pending[tool_id] = {
                            "name": bare_name,
                            "raw_name": raw_name,
                            "input": tool_input,
                            "t_start": now,
                            "order": order_counter,
                        }
                        order_counter += 1
                    # text blocks are part of the assistant trace; final_text
                    # comes from the result event.
                continue

            if etype == "user":
                msg = event.get("message") or {}
                for block in msg.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_result":
                        continue
                    tool_id = block.get("tool_use_id") or ""
                    pend = pending.pop(tool_id, None)
                    if pend is None:
                        # Result without a matching call — record it anyway
                        # rather than dropping data on the floor.
                        log.warning("tool_result for unknown tool_use_id=%s", tool_id)
                        pend = {
                            "name": "unknown",
                            "raw_name": "unknown",
                            "input": None,
                            "t_start": now,
                            "order": order_counter,
                        }
                        order_counter += 1
                    duration = round((now - pend["t_start"]) * 1000.0, 3)
                    output_text = _flatten_tool_result_content(block.get("content"))
                    tool_rec.records.append(
                        {
                            "order": pend["order"],
                            "name": pend["name"],
                            "raw_name": pend["raw_name"],
                            "input": pend["input"],
                            "output": output_text,
                            "duration_ms": duration,
                        }
                    )
                continue

            if etype == "result":
                final_text = event.get("result") or ""
                is_error = bool(event.get("is_error"))
                duration_ms = event.get("duration_ms")
                num_turns = event.get("num_turns")
                total_cost_usd = event.get("total_cost_usd")
                permission_denials = list(event.get("permission_denials") or [])
                terminal_reason = event.get("terminal_reason")
                usage = event.get("usage") or {}
                in_tok = int(usage.get("input_tokens") or 0)
                out_tok = int(usage.get("output_tokens") or 0)
                cache_create = int(usage.get("cache_creation_input_tokens") or 0)
                cache_read = int(usage.get("cache_read_input_tokens") or 0)
                llm_rec.total_prompt_tokens = in_tok + cache_create + cache_read
                llm_rec.total_completion_tokens = out_tok
                llm_rec.total_tokens = (
                    in_tok + out_tok + cache_create + cache_read
                )
                continue

            # rate_limit_event and any future types: kept in raw_events only.

        stderr_bytes = await proc.stderr.read() if proc.stderr is not None else b""
        await proc.wait()
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            log.warning(
                "claude -p exited %s. stderr (first 500): %s",
                proc.returncode,
                stderr[:500],
            )

        return _ParsedRun(
            tool_recorder=tool_rec,
            llm_recorder=llm_rec,
            final_text=final_text,
            is_error=is_error,
            duration_ms=duration_ms,
            num_turns=num_turns,
            total_cost_usd=total_cost_usd,
            session_id=session_id,
            model=model,
            init_tools=init_tools,
            init_mcp_servers=init_mcp_servers,
            permission_denials=permission_denials,
            terminal_reason=terminal_reason,
            raw_events=raw_events,
            stderr=stderr,
            process_exit_code=proc.returncode if proc.returncode is not None else -1,
        )
