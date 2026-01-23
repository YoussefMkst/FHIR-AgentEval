"""
Utility to get task difficulty level from task modules.
"""

import importlib
from typing import Optional


def get_task_difficulty(task_module: str, task_class: str) -> Optional[int]:
    """
    Get the difficulty level for a task by importing its modular class.
    
    Args:
        task_module: Task module name (e.g., "task_01_enter_new_patient")
        task_class: Task class name (e.g., "EnterNewPatientTask")
    
    Returns:
        Difficulty level as integer, or None if not found
    
    Example:
        >>> get_task_difficulty("task_01_enter_new_patient", "EnterNewPatientTask")
        1
    """
    try:
        # Import the modular task module
        module_path = f"tasks.fhir_tasks_modular.{task_module}_modular"
        mod = importlib.import_module(module_path)
        
        # Add "Modular" suffix to class name if not already present
        class_name = f"{task_class}Modular" if not task_class.endswith("Modular") else task_class
        
        # Get the class
        task_cls = getattr(mod, class_name)
        
        # Instantiate with minimal required parameters (we're not executing, just getting difficulty)
        task_instance = task_cls(
            fhir_server_url="http://localhost:7070/fhir",  # Dummy value
            n8n_url=None,
            n8n_execution_url=None,
            template_params={}
        )
        
        # Return difficulty level
        return task_instance.get_difficulty_level()
        
    except Exception as e:
        print(f"Warning: Could not get difficulty for {task_module}.{task_class}: {e}")
        return None

