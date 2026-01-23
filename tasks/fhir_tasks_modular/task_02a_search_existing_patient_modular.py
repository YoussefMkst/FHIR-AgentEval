# task_02a_search_existing_patient_modular.py

import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class SearchExistingPatientTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "2a"

    def get_task_name(self) -> str:
        return "Search Existing Patient"

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
                    "examples": ["1990-06-15"],
                    "default": "1990-06-15",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                },
                "phone": {
                    "type": "string",
                    "description": "Phone number for test data creation",
                    "examples": ["123-456-7890"],
                },
                "address_line": {
                    "type": "string",
                    "description": "Street address line for test data",
                    "examples": ["123 Main St"],
                },
                "city": {
                    "type": "string",
                    "description": "City for test data",
                    "examples": ["Boston"],
                },
                "state": {
                    "type": "string",
                    "description": "State/Province code for test data",
                    "examples": ["MA"],
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

                If the patient exists, return their Patient resource ID.
                If the patient doesn't exist, classify them as a new patient.

                Return the searched patient's ID from the FHIR server using the following format:
                
                    <patient_id>PATIENTID</patient_id>
                """

    def prepare_test_data(self) -> None:
        try:
            # Clean up existing resources
            self.delete_all_resources()

            # Create test patient using template parameters
            family = self.get_param("patient_family", "Doe")
            given = self.get_param("patient_given", "John")
            birth_date = self.get_param("birth_date", "1990-06-15")
            phone = self.get_param("phone")
            address_line = self.get_param("address_line")
            city = self.get_param("city")
            state = self.get_param("state")

            patient_resource = {
                "resourceType": "Patient",
                "id": "PAT001",
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
        tagged_response = f"<patient_id>{response_json['entry'][0]['resource']['id']}</patient_id>"

        return ExecutionResult(
            execution_success=True,
            response_msg=f"Found patient with ID {tagged_response}",
        )

    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            # Check if returned result matches the human executed request's return.
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"

            # Parse the response message
            response_msg = response_msg.strip()
            # match the response message with the expected format
            assert "<patient_id>" in response_msg, "Expected to find <patient_id> tag"
            assert "</patient_id>" in response_msg, "Expected to find </patient_id>tag"

            # Extract the patient_id from the response message
            patient_id = response_msg.split("<patient_id>")[1].split("</patient_id>")[0]
            assert patient_id is not None, "Expected to find patient_id"

            # slot id should be
            expected_patient_id = (
                self.execute_human_agent().response_msg.split("<patient_id>")[1].split("</patient_id>")[0]
            )
            assert patient_id == expected_patient_id, f"Expected patient_id {expected_patient_id}, got {patient_id}"

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
