# task_08b_search_nonexistent_insurance_modular.py

import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class SearchNonexistentInsuranceTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "8b"

    def get_task_name(self) -> str:
        return "Search Nonexistent Insurance"

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_id", "patient_family", "patient_given"],
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient ID to search insurance information for (should have no insurance)",
                    "examples": ["PAT002"],
                    "default": "PAT002",
                },
                "patient_family": {
                    "type": "string",
                    "description": "Patient's family name for test data creation",
                    "examples": ["Doe"],
                    "default": "Doe",
                },
                "patient_given": {
                    "type": "string",
                    "description": "Patient's given name for test data creation",
                    "examples": ["Jane"],
                    "default": "Jane",
                },
                "patient_birth_date": {
                    "type": "string",
                    "description": "Patient's birth date in YYYY-MM-DD format",
                    "examples": ["2020-06-15"],
                    "default": "2020-06-15",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                },
                "patient_phone": {
                    "type": "string",
                    "description": "Patient's phone number for test data",
                    "examples": ["123-456-7890"],
                },
                "patient_address_line": {
                    "type": "string",
                    "description": "Patient's street address for test data",
                    "examples": ["123 Main St"],
                },
                "patient_city": {
                    "type": "string",
                    "description": "Patient's city for test data",
                    "examples": ["Boston"],
                },
                "patient_state": {
                    "type": "string",
                    "description": "Patient's state/province for test data",
                    "examples": ["MA"],
                },
            },
        }

    def get_prompt(self) -> str:
        patient_id = self.get_param("patient_id")
        patient_family = self.get_param("patient_famil")
        patient_given = self.get_param("patient_given")
        return f"""
Search if patient insurance information has been entered in the system for:
- Beneficiary: {patient_given} {patient_family} (id={patient_id})

If found, return the coverage ID using the following format: <COVERAGE>coverage_id</COVERAGE>
If none found, return the exact sentence: "No insurance coverage found"
"""

    def prepare_test_data(self) -> None:
        try:
            # Create test patient without insurance using template parameters
            patient_id = self.get_param("patient_id")
            family = self.get_param("patient_family")
            given = self.get_param("patient_given")
            birth_date = self.get_param("patient_birth_date", "2020-06-15")
            phone = self.get_param("patient_phone", "123-456-7890")
            address_line = self.get_param("patient_address_line", "123 Main St")
            city = self.get_param("patient_city", "Boston")
            state = self.get_param("patient_state", "MA")

            patient_resource = {
                "resourceType": "Patient",
                "id": patient_id,
                "name": [{"use": "official", "family": family, "given": [given]}],
                "birthDate": birth_date,
            }

            # Add optional fields if provided
            if phone:
                patient_resource["telecom"] = [{"system": "phone", "value": phone}]
            if address_line or city or state:
                address = {}
                if address_line:
                    address["line"] = [address_line]
                if city:
                    address["city"] = city
                if state:
                    address["state"] = state
                patient_resource["address"] = [address]

            self.upsert_to_fhir(patient_resource)
        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")



    def execute_human_agent(self) -> ExecutionResult:
        patient_id = self.get_param("patient_id")
        params = {"beneficiary": f"Patient/{patient_id}", "status": "active"}

        response = requests.get(
            f"{self.FHIR_SERVER_URL}/Coverage", headers=self.HEADERS, params=params
        )

        if response.status_code != 200:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"Failed to search for insurance: {response.text}",
            )
        # added logic
        response_json = response.json()
        if response_json.get("total", 0) > 0:
            coverage_id = response_json["entry"][0]["resource"]["id"]
            return ExecutionResult(
                execution_success=True,
                response_msg=f"Found {response_json['total']} insurance coverage(s) for patient {patient_id}: <COVERAGE>{coverage_id}</COVERAGE>",
            )
        else:
            return ExecutionResult(
                execution_success=True, response_msg="No insurance coverage found"
            )



    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            # Structured-output assertions
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            assert "no insurance coverage found" in response_msg.lower(), f"Expected 'No insurance coverage found', got '{response_msg}'"

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
        return [{"getAllResources": 0}, {"getResourceById": 0}]

    def get_required_resource_types(self) -> list:
        return ["Coverage"]

    def get_prohibited_tools(self) -> list:
        return ["createResource", "updateResource", "deleteResource"]

    def get_difficulty_level(self) -> int:
        return 1
