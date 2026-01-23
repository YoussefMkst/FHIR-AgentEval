"""
Task loader for modular FHIR tasks.

Rules:
- Modular tasks live in `tasks.fhir_tasks_modular.{module}_modular` with class `{class}Modular`.
- YAML entries should include `template_params` for parameterized tasks.

This avoids duplicating loader logic across agents.
"""

from __future__ import annotations

import os
import importlib
import inspect
from typing import Any, Dict


def build_task(task_entry: Dict[str, Any]) -> Any:
    """Instantiate a modular task class from YAML entry.

    Import from `tasks.fhir_tasks_modular.{module}_modular` and pass common
    ctor kwargs from env + YAML.
    """
    module_name: str = task_entry["module"]
    class_name: str = task_entry["class"]

    # Import from modular package; file names use `_modular` suffix
    mod = importlib.import_module(f"tasks.fhir_tasks_modular.{module_name}_modular")
    cls_name = class_name if class_name.endswith("Modular") else f"{class_name}Modular"

    TaskClass = getattr(mod, cls_name)

    # Required ctor kwargs
    kwargs: Dict[str, Any] = {
        "fhir_server_url": os.getenv("FHIR_SERVER_URL", "http://localhost:7070/fhir"),
        "required_tool_call_sets": task_entry.get("required_tool_call_sets", []),
        "required_resource_types": task_entry.get("required_resource_types", []),
        "prohibited_tools": task_entry.get("prohibited_tools", []),
        "difficulty_level": task_entry.get("difficulty_level"),
    }

    # Modular params if supported by ctor
    if "template_params" in inspect.signature(TaskClass.__init__).parameters:
        kwargs["template_params"] = task_entry.get("template_params", {})

    return TaskClass(**kwargs)


