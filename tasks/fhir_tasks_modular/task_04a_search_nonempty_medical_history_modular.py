# task_04a_search_nonempty_medical_history_modular.py

import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class SearchNonemptyMedicalHistoryTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "4a"

    def get_task_name(self) -> str:
        return "Search Existing Medical History"

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_id"],
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient ID to search medical history for",
                    "examples": ["PAT001"],
                    "default": "PAT001",
                },
                "condition_code": {
                    "type": "string",
                    "description": "SNOMED CT code for the medical condition to create",
                    "examples": ["74400008"],
                    "default": "74400008",
                },
                "condition_display": {
                    "type": "string",
                    "description": "Human-readable name of the medical condition",
                    "examples": ["Appendicitis"],
                    "default": "Appendicitis",
                },
                "condition_id": {
                    "type": "string",
                    "description": "Custom ID for the condition resource",
                    "examples": ["Appendicitis001"],
                    "default": "Appendicitis001",
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
                    "examples": ["John"],
                    "default": "John",
                },
                "patient_birth_date": {
                    "type": "string",
                    "description": "Patient's birth date in YYYY-MM-DD format",
                    "examples": ["1990-06-15"],
                    "default": "1990-06-15",
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
                "clinical_status": {
                    "type": "string",
                    "description": "Clinical status of the condition",
                    "examples": ["active", "inactive", "resolved"],
                    "default": "active",
                },
            },
        }

    def get_prompt(self) -> str:
        patient_id = self.get_param("patient_id")
        return f"""
Search for the existing patient id={patient_id} to see if they have any medical history.

If found, return the first condition's ID using the following format: <CONDITION>condition_id</CONDITION>
"""

    def prepare_test_data(self) -> None:
        try:
            # Create test patient using template parameters
            patient_id = self.get_param("patient_id")
            family = self.get_param("patient_family", "Doe")
            given = self.get_param("patient_given", "John")
            birth_date = self.get_param("patient_birth_date", "1990-06-15")
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

            # Create condition for the patient using template parameters
            condition_code = self.get_param("condition_code", "74400008")
            condition_display = self.get_param("condition_display", "Appendicitis")
            condition_id = self.get_param("condition_id", "Appendicitis001")
            clinical_status = self.get_param("clinical_status", "active")

            condition_data = {
                "resourceType": "Condition",
                "id": condition_id,
                "subject": {"reference": f"Patient/{patient_id}"},
                "code": {
                    "coding": [
                        {
                            "system": "http://snomed.info/sct",
                            "code": condition_code,
                            "display": condition_display,
                        }
                    ],
                    "text": condition_display,
                },
                "clinicalStatus": {"coding": [{"code": clinical_status}]},
            }
            self.upsert_to_fhir(condition_data)
        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")


    def execute_human_agent(self) -> ExecutionResult:
        patient_id = self.get_param("patient_id")
        params = {"subject": f"Patient/{patient_id}"}

        response = requests.get(
            f"{self.FHIR_SERVER_URL}/Condition", headers=self.HEADERS, params=params
        )

        if response.status_code != 200:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"Failed to search for medical history: {response.text}",
            )

        response_json = response.json()
        return ExecutionResult(
            execution_success=True,
            response_msg=f"Found {response_json.get('total', 0)} medical condition(s) for patient {patient_id}: <CONDITION>{response.json()['entry'][0]['resource']['id']}</CONDITION>",
        )


    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            # Check if returned result matches the human executed request's return.
            response_msg = execution_result.response_msg

            assert response_msg is not None, "Expected to find response message"

            response_msg = response_msg.strip()
            # match the response message with the expected format
            assert "<CONDITION>" in response_msg, "Expected to find <CONDITION> tag"
            assert "</CONDITION>" in response_msg, "Expected to find </CONDITION>tag"

            # Extract the condition_id from the response message
            condition_id = response_msg.split("<CONDITION>")[1].split("</CONDITION>")[0]

            assert condition_id is not None, "Expected to find condition_id"

            expected_condition_id = self.execute_human_agent().response_msg.split("<CONDITION>")[1].split("</CONDITION>")[0]
            assert condition_id == expected_condition_id, f"Expected condition_id {expected_condition_id}, got {condition_id}"

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
        return ["Condition"]

    def get_prohibited_tools(self) -> list:
        return ["createResource", "updateResource", "deleteResource"]

    def get_difficulty_level(self) -> int:
        return 1
