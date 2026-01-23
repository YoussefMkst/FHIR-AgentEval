# task_19d_other_agents_needed_manager_modular.py

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
        return "19d"

    def get_task_name(self) -> str:
        return "Handle Request Requiring Other Agents (Manager)"

    def get_prompt(self) -> str:
        balance_amount = self.get_param("balance_amount", "$1000")
        request_type = self.get_param("request_type", "appointment")
        return f"""
                Patient has an outstanding balance of {balance_amount}, and needs to make an {request_type}. 
                """

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": [],
            "properties": {
                "balance_amount": {
                    "type": "string",
                    "description": "Outstanding balance amount for the patient",
                    "examples": ["$1000", "$500", "$2500", "$750", "No balance"],
                    "default": "$1000",
                },
                "request_type": {
                    "type": "string",
                    "description": "Type of request the patient needs help with",
                    "examples": [
                        "appointment",
                        "procedure",
                        "consultation",
                        "referral",
                        "billing question"
                    ],
                    "default": "appointment",
                },
                "agent_type": {
                    "type": "string",
                    "description": "Type of agent needed to handle the manager request",
                    "examples": ["<Manager>", "<Supervisor>", "<Administrator>", "<Case Manager>"],
                    "default": "<Manager>",
                },
                "response_message": {
                    "type": "string",
                    "description": "Base message indicating the need for manager-related agents",
                    "examples": [
                        "Patient has an outstanding balance of $1000, and needs to make an appointment.",
                        "Patient requires financial assistance for medical procedure.",
                        "Patient needs to discuss payment arrangements."
                    ],
                    "default": "Patient has an outstanding balance of $1000, and needs to make an appointment.",
                },
                "issue_category": {
                    "type": "string",
                    "description": "Category of issue requiring manager attention",
                    "examples": ["financial", "billing", "scheduling", "policy", "complaint"],
                    "default": "financial",
                },
                "urgency_level": {
                    "type": "string",
                    "description": "Urgency level of the manager request",
                    "examples": ["routine", "urgent", "emergency", "escalation"],
                    "default": "routine",
                    "enum": ["routine", "urgent", "emergency", "escalation"],
                },
                "patient_status": {
                    "type": "string",
                    "description": "Current status of the patient",
                    "examples": ["active", "inactive", "new", "returning", "vip"],
                    "default": "active",
                },
                "department": {
                    "type": "string",
                    "description": "Department that needs manager attention",
                    "examples": ["billing", "scheduling", "clinical", "administrative", "general"],
                    "default": "billing",
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
        response_message = self.get_param("response_message", "Patient has an outstanding balance of $1000, and needs to make an appointment.")
        agent_type = self.get_param("agent_type", "<Manager>")
        
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
            agent_type = self.get_param("agent_type", "<Manager>")
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
