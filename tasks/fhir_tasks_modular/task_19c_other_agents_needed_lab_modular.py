# task_19c_other_agents_needed_lab_modular.py

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
        return "19c"

    def get_task_name(self) -> str:
        return "Handle Request Requiring Other Agents (Lab)"

    def get_prompt(self) -> str:
        patient_id = self.get_param("patient_id", "PAT001")
        test_name = self.get_param("test_name", "BRCA1 test")
        return f"""
                Please order a {test_name} for patient's ({patient_id}).
                """

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": [],
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient identifier for the lab order",
                    "examples": ["PAT001", "PAT002", "PAT003"],
                    "default": "PAT001",
                },
                "test_name": {
                    "type": "string",
                    "description": "Laboratory test or procedure to be ordered",
                    "examples": [
                        "BRCA1 test",
                        "complete blood count",
                        "genetic testing",
                        "urinalysis",
                        "lipid panel",
                        "glucose test"
                    ],
                    "default": "BRCA1 test",
                },
                "agent_type": {
                    "type": "string",
                    "description": "Type of agent needed to handle the lab request",
                    "examples": ["<Lab>", "<Laboratory>", "<Pathologist>", "<Technician>"],
                    "default": "<Lab>",
                },
                "response_message": {
                    "type": "string",
                    "description": "Base message indicating the need for lab-related agents",
                    "examples": [
                        "Patient wants to order a BRCA1 test.",
                        "Patient needs to schedule a laboratory test.",
                        "Patient requires lab work order."
                    ],
                    "default": "Patient wants to order a BRCA1 test.",
                },
                "test_category": {
                    "type": "string",
                    "description": "Category of laboratory test",
                    "examples": ["genetic", "hematology", "chemistry", "microbiology", "immunology"],
                    "default": "genetic",
                },
                "urgency_level": {
                    "type": "string",
                    "description": "Urgency level of the lab order",
                    "examples": ["routine", "urgent", "stat", "pre-operative"],
                    "default": "routine",
                    "enum": ["routine", "urgent", "stat", "pre-operative"],
                },
                "test_frequency": {
                    "type": "string",
                    "description": "Frequency of the test if recurring",
                    "examples": ["one-time", "daily", "weekly", "monthly", "as needed"],
                    "default": "one-time",
                },
                "special_instructions": {
                    "type": "string",
                    "description": "Special instructions for the lab test",
                    "examples": ["fasting required", "morning collection", "special handling", "none"],
                    "default": "none",
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
        response_message = self.get_param("response_message", "Patient wants to order a BRCA1 test.")
        agent_type = self.get_param("agent_type", "<Lab>")
        
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
            agent_type = self.get_param("agent_type", "<Lab>")
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
