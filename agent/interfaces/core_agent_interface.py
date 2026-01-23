"""
Core agent interface and common types used by all agents.

This layer defines:
- AgentConfig / AgentRunOptions: configuration and per-run options
- CoreResult / CoreMetrics / CoreToolCall: normalized outputs for generic runs
- BaseAgent: minimal lifecycle and single-run contract (domain-agnostic)

Domain interfaces (FHIR, DeepRare) extend this core to add their own batch APIs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class AgentConfig:
    """Static configuration for an agent instance.

    Fields are intentionally generic so the same config can be reused across
    transports (MCP / REST) and architectures (Baseline, ReAct, Plan–Execute).
    """

    model_id: str
    system_prompt: Optional[str] = None

    # Transport and endpoints (e.g., "mcp"|"rest").
    transport: str = "mcp"
    endpoint: Optional[str] = None                 # SSE URL or REST base URL
    headers: Optional[Dict[str, str]] = None       # Optional HTTP headers

    # Environment and runtime knobs
    env_path: Optional[Path] = None
    recursion_limit: Optional[int] = None
    temperature: Optional[float] = None

    # Freeform extension point for experiment-specific knobs
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRunOptions:
    """Per-run options that do not belong to static config.

    Callers can pass callback handlers for tracing/telemetry via `callbacks`.
    """

    callbacks: Optional[Sequence[Any]] = None
    trace: bool = True
    timeout_s: Optional[float] = None
    tool_filter: Optional[List[str]] = None
    recursion_limit: Optional[int] = None


@dataclass
class CoreToolCall:
    """A single tool invocation captured during a run."""

    name: str
    raw_input: Any
    raw_output: Any
    duration_ms: Optional[float] = None
    error: Optional[str] = None


@dataclass
class CoreMetrics:
    """Top-level metrics for a run (latency and token usage)."""

    latency_ms: Optional[int] = None
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    tokens_total: Optional[int] = None
    tool_calls_count: Optional[int] = None


@dataclass
class CoreResult:
    """Domain-agnostic result for a single prompt run.

    Domain agents (FHIR / DeepRare) may attach additional fields downstream.
    """

    final_text: str
    metrics: CoreMetrics = field(default_factory=CoreMetrics)
    tool_calls: List[CoreToolCall] = field(default_factory=list)
    trace: Optional[Dict[str, Any]] = None
    raw_output: Any = None


class BaseAgent(ABC):
    """Minimal base for all agents.

    Concrete agents should:
    - lazily connect/load resources in ainit()
    - implement arun_text() to run a single prompt and return CoreResult
    - optionally expose astream_text() for UI/telemetry streaming
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable agent name (for logs/reports)."""

    @property
    @abstractmethod
    def config(self) -> AgentConfig:
        """Return the static configuration used by this agent instance."""

    @abstractmethod
    async def ainit(self) -> None:
        """Lazy initialization (load env, connect tool providers, build graphs)."""

    @abstractmethod
    async def arun_text(self, prompt: str, options: Optional[AgentRunOptions] = None) -> CoreResult:
        """Run a single prompt and return a normalized CoreResult.

        Major steps typically include:
        - attach callbacks (for tracing) if requested
        - invoke model/tools with the prompt
        - aggregate metrics/trace into CoreResult
        """

    async def astream_text(self, prompt: str, options: Optional[AgentRunOptions] = None):
        """Optional event stream (LLM/tool lifecycle) for UIs and telemetry."""
        raise NotImplementedError

    async def aclose(self) -> None:
        """Optional cleanup hook (close connections, release resources)."""
        return


