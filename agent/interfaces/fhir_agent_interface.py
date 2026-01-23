"""
FHIR agent interface — domain-specific contract on top of the core agent base.

Agents implementing this interface must be able to:
- run a single FHIR task entry (from YAML) and return an ExecutionResult-like dict
- run a set of tasks defined in a YAML file

Returned dicts should populate fields consumed by tasks/fhir_tasks_modular/task_interface_modular.py:
  response_msg, token_total, input_query, total_exec_ms,
  tool_order, tool_exec_ms, tool_calls, tool_call_counts
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .core_agent_interface import BaseAgent, AgentRunOptions


class FHIRAgentInterface(BaseAgent, ABC):
    """FHIR-specific batch/run APIs layered on top of BaseAgent."""

    @abstractmethod
    async def arun_task_entry(
        self,
        task_entry: Dict[str, Any],
        options: Optional[AgentRunOptions] = None,
    ) -> Dict[str, Any]:
        """Run a single YAML task entry and return an ExecutionResult-like dict.

        Major steps typically include:
        - build TaskInterface from module/class in task_entry
        - prepare/cleanup data as needed
        - run model/tools with callbacks
        - aggregate callbacks into ExecutionResult fields and validate
        """

    @abstractmethod
    async def arun_task_variations_from_yaml(
        self,
        yaml_path: Union[str, Path],
        options: Optional[AgentRunOptions] = None,
    ) -> List[Dict[str, Any]]:
        """Run all task variations listed in a YAML file and return a list of results.

        Implementations should resolve relative paths as needed and reuse
        arun_task_entry() for each task entry.
        """


