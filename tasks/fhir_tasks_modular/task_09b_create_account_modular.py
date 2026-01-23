# task_09b_create_account_modular.py

import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class CreateAccountTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "9b"

    def get_task_name(self) -> str:
        return "Create Account"

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_id"],
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient ID to create account for",
                    "examples": ["PAT001"],
                    "default": "PAT001",
                },
                "account_status": {
                    "type": "string",
                    "description": "Status of the account",
                    "examples": ["active", "inactive", "entered-in-error"],
                    "default": "active",
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
                    "examples": ["2010-06-15"],
                    "default": "2010-06-15",
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
        return f"""
Create an account resource for the patient {patient_id}.

After creation, return the new Account ID using the following format: <ACCOUNT>account_id</ACCOUNT>
"""

    def prepare_test_data(self) -> None:
        try:
            # Create test patient using template parameters
            patient_id = self.get_param("patient_id")
            family = self.get_param("patient_family", "Doe")
            given = self.get_param("patient_given", "John")
            birth_date = self.get_param("patient_birth_date", "2010-06-15")
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
        account_status = self.get_param("account_status", "active")

        account_payload = {
            "resourceType": "Account",
            "status": account_status,
            "subject": {"reference": f"Patient/{patient_id}"},
        }

        response = requests.post(
            f"{self.FHIR_SERVER_URL}/Account", headers=self.HEADERS, json=account_payload
        )

        if response.status_code != 201:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"Failed to create account: {response.text}",
            )

        response_json = response.json()
        account_id = response_json.get("id")
        return ExecutionResult(
            execution_success=True,
            response_msg=f"Created account with ID <ACCOUNT>{account_id}</ACCOUNT>",
        )


    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            patient_id = self.get_param("patient_id")

            # Verify the account was created correctly
            response = requests.get(
                f"{self.FHIR_SERVER_URL}/Account",
                headers=self.HEADERS,
                params={"subject": f"Patient/{patient_id}", "_summary": "false"},
            )

            assert response.status_code in [200, 201], f"Expected status code 200 or 201, got {response.status_code}"

            response_json = response.json()
            assert "entry" in response_json, "Expected to find entry in the response"
            assert len(response_json["entry"]) > 0, "Expected to find at least one account"

            account = response_json["entry"][0]["resource"]
            assert account["resourceType"] == "Account", "Invalid resource type"

            # Structured-output assertions
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            response_msg = response_msg.strip()
            assert "<ACCOUNT>" in response_msg, "Expected to find <ACCOUNT> tag"
            assert "</ACCOUNT>" in response_msg, "Expected to find </ACCOUNT> tag"
            account_id = response_msg.split("<ACCOUNT>")[1].split("</ACCOUNT>")[0]
            assert account_id is not None and account_id != "", "Expected to find account_id"

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

    def validate_response_light(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            patient_id = self.get_param("patient_id")

            response = requests.get(
                f"{self.FHIR_SERVER_URL}/Account",
                headers=self.HEADERS,
                params={"subject": f"Patient/{patient_id}", "_summary": "false"},
            )

            assert response.status_code in [200, 201], f"Expected status code 200 or 201, got {response.status_code}"

            response_json = response.json()
            assert "entry" in response_json and len(response_json["entry"]) > 0, "Expected to find at least one account"

            account = response_json["entry"][0]["resource"]
            assert account.get("resourceType") == "Account", "Resource type must be Account"

            return TaskResult(
                task_success=True,
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
            )

        except AssertionError as e:
            return TaskResult(
                task_success=False,
                assertion_error_message=f"Light validation failed: {str(e)}",
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
            )
        except Exception as e:
            return TaskResult(
                task_success=False,
                assertion_error_message=f"Light validation error: {str(e)}",
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
            )

    def get_required_tool_call_sets(self) -> list:
        return [
            {"createResource": 0},
            {"getResourceById": 0, "updateResource": 1},
            {"searchResources": 0, "createResource": 1},
            {"getResourceById": 0, "createResource": 1},
        ]

    def get_required_resource_types(self) -> list:
        return ["Account"]

    def get_prohibited_tools(self) -> list:
        return ['deleteResource']

    def get_difficulty_level(self) -> int:
        return 1
