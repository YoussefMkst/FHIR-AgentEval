# task_02b_search_nonexistent_patient_modular.py

import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class SearchNonexistentPatientTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "2b"

    def get_task_name(self) -> str:
        return "Search Nonexistent Patient"

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_family", "patient_given", "birth_date"],
            "properties": {
                "patient_family": {
                    "type": "string",
                    "description": "Patient family (last) name to search for",
                    "examples": ["Doe"],
                    "default": "Doe",
                },
                "patient_given": {
                    "type": "string",
                    "description": "Patient given (first) name to search for",
                    "examples": ["John"],
                    "default": "John",
                },
                "birth_date": {
                    "type": "string",
                    "description": "Birth date in YYYY-MM-DD format",
                    "examples": ["1991-06-15"],
                    "default": "1991-06-15",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                },
            },
        }

    def get_prompt(self) -> str:
        family = self.get_param("patient_family")
        given = self.get_param("patient_given")
        birth_date = self.get_param("birth_date")

        return f"""
                Search the database for the following patient:
                - Full Name: {given} {family}
                - Birth Date: {birth_date}

                If the patient exists, return their Patient resource ID using the following format:                    
                 
                <patient_id>PATIENTID</patient_id>
                
                If the patient doesn't exist, return this exact sentence: "This is a new patient"
                """

    def prepare_test_data(self) -> None:
        try:
            # Clean up existing resources to ensure no matching patient exists
            self.delete_all_resources()
        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")

    def execute_human_agent(self) -> ExecutionResult:
        family = self.get_param("patient_family")
        given = self.get_param("patient_given")
        birth_date = self.get_param("birth_date")

        search_params = {
            "family": family,
            "given": given,
            "birthdate": birth_date,
        }

        response = requests.get(
            f"{self.FHIR_SERVER_URL}/Patient",
            headers=self.HEADERS,
            params=search_params,
        )

        if response.status_code != 200:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"Failed to search for patient: {response.text}",
            )

        response_json = response.json()
        if "entry" in response_json and len(response_json["entry"]) > 0:
            # Patient found (unexpected in this task)
            patient_id = response_json["entry"][0]["resource"]["id"]
            return ExecutionResult(
                execution_success=True,
                response_msg=f"<patient_id>{patient_id}</patient_id>",
            )
        # No patient found (expected result)
        return ExecutionResult(
            execution_success=True,
            response_msg="This is a new patient",
        )

    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            assert "new patient" in response_msg.lower(), f"Expected 'This is a new patient', got '{response_msg}'"

            return TaskResult(
                task_success=True,
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
            )

        except AssertionError as e:
            return TaskResult(
                task_success=False,
                assertion_error_message=str(e),
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
            )
        except Exception as e:
            return TaskResult(
                task_success=False,
                assertion_error_message=f"Unexpected error: {str(e)}",
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
            )

    def get_required_tool_call_sets(self) -> list:
        return [
            {"getAllResources": 0},
            {"getResourceById": 0},
        ]

    def get_required_resource_types(self) -> list:
        return ["Patient"]

    def get_prohibited_tools(self) -> list:
        return ["createResource", "updateResource", "deleteResource"]

    def get_difficulty_level(self) -> int:
        return 1
