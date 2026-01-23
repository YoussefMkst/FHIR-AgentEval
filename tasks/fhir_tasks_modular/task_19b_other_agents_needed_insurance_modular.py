# task_19b_other_agents_needed_insurance_modular.py

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
        return "19b"

    def get_task_name(self) -> str:
        return "Handle Request Requiring Other Agents (Insurance)"

    def get_prompt(self) -> str:
        patient_id = self.get_param("patient_id", "PAT001")
        procedure = self.get_param("procedure", "whole exome sequencing testing")
        return f"""
                Please check if the patient's ({patient_id}) insurance covers {procedure}.
                """

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": [],
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient identifier for the insurance check",
                    "examples": ["PAT001", "PAT002", "PAT003"],
                    "default": "PAT001",
                },
                "procedure": {
                    "type": "string",
                    "description": "Medical procedure or test to check insurance coverage for",
                    "examples": [
                        "whole exome sequencing testing",
                        "MRI scan",
                        "genetic testing",
                        "chemotherapy",
                        "surgery procedure",
                        "laboratory tests"
                    ],
                    "default": "whole exome sequencing testing",
                },
                "agent_type": {
                    "type": "string",
                    "description": "Type of agent needed to handle the insurance request",
                    "examples": ["<Insurance>", "<Billing>", "<Financial Counselor>", "<Case Manager>"],
                    "default": "<Insurance>",
                },
                "response_message": {
                    "type": "string",
                    "description": "Base message indicating the need for insurance-related agents",
                    "examples": [
                        "Patient wants to check insurance coverage for WES.",
                        "Patient needs to verify insurance benefits for genetic testing.",
                        "Patient requires insurance verification for medical procedure."
                    ],
                    "default": "Patient wants to check insurance coverage for WES.",
                },
                "coverage_type": {
                    "type": "string",
                    "description": "Type of insurance coverage to check",
                    "examples": ["medical", "dental", "vision", "prescription", "mental health"],
                    "default": "medical",
                },
                "urgency_level": {
                    "type": "string",
                    "description": "Urgency level of the insurance check",
                    "examples": ["routine", "urgent", "emergency", "pre-authorization"],
                    "default": "routine",
                    "enum": ["routine", "urgent", "emergency", "pre-authorization"],
                },
                "insurance_provider": {
                    "type": "string",
                    "description": "Insurance provider name (if known)",
                    "examples": ["Blue Cross", "Aetna", "Cigna", "UnitedHealth", "Medicare"],
                    "default": "Unknown",
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
        response_message = self.get_param("response_message", "Patient wants to check insurance coverage for WES.")
        agent_type = self.get_param("agent_type", "<Insurance>")
        
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
            agent_type = self.get_param("agent_type", "<Insurance>")
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
