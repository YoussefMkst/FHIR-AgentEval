# task_18a_out_of_scope_request_modular.py

import os
import requests  # type: ignore
import json
from typing import Dict, Any
from tasks.fhir_tasks_modular.task_interface_modular import TaskInterfaceModular, TaskResult, ExecutionResult, TaskFailureMode
from dataclasses import asdict
from dotenv import load_dotenv
import re

class OutOfScopeRequestTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "18a"

    def get_task_name(self) -> str:
        return "Handle Out of Scope Request"

    def get_prompt(self) -> str:
        request_type = self.get_param("request_type", "weather")
        city_name = self.get_param("city_name", "Boston")
        time_frame = self.get_param("time_frame", "tomorrow")
        return f"""
                Task: Handle an out-of-scope request

                Please find the {request_type} in the city of {city_name} for {time_frame}.
                """

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": [],
            "properties": {
                "request_type": {
                    "type": "string",
                    "description": "Type of out-of-scope request being made",
                    "examples": ["weather", "traffic", "restaurant", "shopping"],
                    "default": "weather",
                },
                "city_name": {
                    "type": "string",
                    "description": "City name for the out-of-scope request",
                    "examples": ["Boston", "New York", "Los Angeles", "Chicago"],
                    "default": "Boston",
                },
                "time_frame": {
                    "type": "string",
                    "description": "Time frame for the out-of-scope request",
                    "examples": ["today", "tomorrow", "next week", "this weekend"],
                    "default": "tomorrow",
                },
                "response_format": {
                    "type": "string",
                    "description": "Expected response format for out-of-scope requests",
                    "examples": ["<Patient>", "<OutOfScope>", "<NotSupported>"],
                    "default": "<Patient>",
                },
                "out_of_scope_message": {
                    "type": "string",
                    "description": "Message to include indicating the request is out of scope",
                    "examples": [
                        "This is out of scope of the system's services.",
                        "This request is not supported by the FHIR system.",
                        "This functionality is outside our scope."
                    ],
                    "default": "This is out of scope of the system's services.",
                },
            },
        }

    def prepare_test_data(self) -> None:
        # Check if FHIR server is accessible
        try:
            response = requests.get(f"{self.FHIR_SERVER_URL}/metadata", headers=self.HEADERS)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Exception(f"FHIR server is not accessible: {str(e)}")

    def execute_human_agent(self) -> ExecutionResult:
        out_of_scope_message = self.get_param("out_of_scope_message", "This is out of scope of the system's services.")
        response_format = self.get_param("response_format", "<Patient>")
        
        # Simulate an out-of-scope request
        response_msg = out_of_scope_message
        response_msg += response_format
        
        execution_result = ExecutionResult(
            execution_success=True,  # Successfully identified as out of scope
            response_msg=response_msg,
        )
        return execution_result

    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            
            # according to the system prompts for multi-agents, the response should be in the following format:
            out_of_scope_message = self.get_param("out_of_scope_message", "This is out of scope of the system's services.")
            response_format = self.get_param("response_format", "<Patient>")
            
            assert "out of scope" in response_msg.lower(), "Expected to find out of scope in the response message"
            assert response_format in response_msg, f"Expected to find {response_format} tag in the response message"
            
            return TaskResult(
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
                task_success=True,
                assertion_error_message=None,
            )

        except AssertionError as e:
            return TaskResult(
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
                task_success=False,
                assertion_error_message=str(e),
            )
        except Exception as e:
            return TaskResult(
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
                task_success=False,
                assertion_error_message=f"Unexpected error: {str(e)}",
            )

    def get_required_tool_call_sets(self) -> list:
        return [
           
        ]

    def get_required_resource_types(self) -> list:
        return []

    def get_prohibited_tools(self) -> list:
        return ["createResource", "updateResource", "deleteResource", "getAllResources", "getResourceById"]

    def get_difficulty_level(self) -> int:
        return 1
