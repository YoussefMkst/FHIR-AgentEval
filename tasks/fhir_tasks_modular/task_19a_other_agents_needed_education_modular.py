# task_19a_other_agents_needed_education_modular.py

import os
import requests  # type: ignore
import json
from typing import Dict, Any
from tasks.fhir_tasks_modular.task_interface_modular import TaskInterfaceModular, TaskResult, ExecutionResult, TaskFailureMode
from dataclasses import asdict
from dotenv import load_dotenv
import re

class OtherAgentsNeededTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "19a"

    def get_task_name(self) -> str:
        return "Handle Request Requiring Other Agents (Education)"

    def get_prompt(self) -> str:
        topic = self.get_param("topic", "whole exome sequencing")
        patient_context = self.get_param("patient_context", "patient")
        return f"""
                Please explain what is a {topic} to the {patient_context}.
                """

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": [],
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Medical topic or procedure to be explained",
                    "examples": [
                        "whole exome sequencing",
                        "genetic testing",
                        "MRI scan",
                        "chemotherapy",
                        "surgery procedure"
                    ],
                    "default": "whole exome sequencing",
                },
                "patient_context": {
                    "type": "string",
                    "description": "Context of who needs the explanation",
                    "examples": ["patient", "family member", "caregiver", "parent"],
                    "default": "patient",
                },
                "agent_type": {
                    "type": "string",
                    "description": "Type of agent needed to handle the request",
                    "examples": ["<Counselor>", "<Educator>", "<Genetic Counselor>", "<Nurse>"],
                    "default": "<Counselor>",
                },
                "response_message": {
                    "type": "string",
                    "description": "Base message indicating the need for other agents",
                    "examples": [
                        "Patient wants to know what is a whole exome sequencing.",
                        "Family member needs education about genetic testing.",
                        "Caregiver requires explanation of medical procedure."
                    ],
                    "default": "Patient wants to know what is a whole exome sequencing.",
                },
                "complexity_level": {
                    "type": "string",
                    "description": "Complexity level of the medical topic",
                    "examples": ["basic", "intermediate", "advanced", "expert"],
                    "default": "intermediate",
                    "enum": ["basic", "intermediate", "advanced", "expert"],
                },
                "specialty_area": {
                    "type": "string",
                    "description": "Medical specialty area for the topic",
                    "examples": ["genetics", "oncology", "cardiology", "neurology", "general"],
                    "default": "genetics",
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
        response_message = self.get_param("response_message", "Patient wants to know what is a whole exome sequencing.")
        agent_type = self.get_param("agent_type", "<Counselor>")
        
        response_msg = response_message
        response_msg += agent_type
        
        execution_result = ExecutionResult(
            execution_success=True,  # Successfully identified need for other agents
            response_msg=response_msg,
        )
        return execution_result

    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            
            # according to the system prompts for multi-agents, the response should be in the following format:
            agent_type = self.get_param("agent_type", "<Counselor>")
            assert agent_type in response_msg, f"Expected to find {agent_type} tag in the response message"
            
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
