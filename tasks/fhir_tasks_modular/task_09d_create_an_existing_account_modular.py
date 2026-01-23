# task_09d_create_an_existing_account_modular.py

import time
import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class CreateExistingAccountTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "9d"

    def get_task_name(self) -> str:
        return "Create Account for Existing Patient"

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_id"],
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient ID to check/create account for",
                    "examples": ["PAT001"],
                    "default": "PAT001",
                },
                "account_id": {
                    "type": "string",
                    "description": "Account ID for the existing account",
                    "examples": ["ACC001"],
                    "default": "ACC001",
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
                "account_status": {
                    "type": "string",
                    "description": "Status of the account",
                    "examples": ["active", "inactive", "entered-in-error"],
                    "default": "active",
                },
            },
        }

    def get_prompt(self) -> str:
        patient_id = self.get_param("patient_id")
        return f"""

Create an account resource for the patient with id : {patient_id}.
If the account for given patient is already created, Return "There is already an account for this patient <ACCOUNT>account_id</ACCOUNT>"
"""

    def prepare_test_data(self) -> None:
        # Create patient using template parameters
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

        # Create account using template parameters
        account_id = self.get_param("account_id", "ACC001")
        account_status = self.get_param("account_status", "active")

        account_resource = {
            "resourceType": "Account",
            "id": account_id,
            "status": account_status,
            # Use array form to ensure proper indexing for subject search
            "subject": [{"reference": f"Patient/{patient_id}"}],
        }
        self.upsert_to_fhir(account_resource)


    def execute_human_agent(self) -> ExecutionResult:
        patient_id = self.get_param("patient_id")
        account_id = self.get_param("account_id", "ACC001")

        # First verify the patient exists
        patient_response = requests.get(
            f"{self.FHIR_SERVER_URL}/Patient/{patient_id}", headers=self.HEADERS
        )

        if patient_response.status_code != 200:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"Patient {patient_id} not found: {patient_response.text}",
            )

        # Second check if the account already exists
        account_response = requests.get(
            f"{self.FHIR_SERVER_URL}/Account",
            headers=self.HEADERS,
            params={"subject": f"Patient/{patient_id}"},
        )

        if account_response.status_code in [200, 201]:
            # Poll until the account is indexed in the search results
            wait_time = 0
            while True:
                account_json = account_response.json()
                entries = account_json.get("entry", [])
                if entries:
                    account_id = entries[0]["resource"]["id"]
                    return ExecutionResult(
                        execution_success=True,
                        response_msg=f"There is already an account for this patient <ACCOUNT>{account_id}</ACCOUNT>",
                    )
                time.sleep(2)
                wait_time += 2
                if wait_time > 30:
                    return ExecutionResult(
                        execution_success=False,
                        response_msg=f"Failed to get an account for this patient",
                    )
                account_response = requests.get(
                    f"{self.FHIR_SERVER_URL}/Account",
                    headers=self.HEADERS,
                    params={"subject": f"Patient/{patient_id}"},
                )

        else:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"Failed to get an account for this patient",
            )


    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            patient_id = self.get_param("patient_id")
            
            # Structured-output assertions (agent must emit the ID)
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            response_msg = response_msg.strip()
            assert "<ACCOUNT>" in response_msg and "</ACCOUNT>" in response_msg, "Expected to find <ACCOUNT> tag"
            account_id = response_msg.split("<ACCOUNT>")[1].split("</ACCOUNT>")[0].strip()
            assert account_id, "Expected to find account_id"

            # Verify the returned account exists and is linked to the patient
            acc_resp = requests.get(f"{self.FHIR_SERVER_URL}/Account/{account_id}", headers=self.HEADERS)
            assert acc_resp.status_code == 200, f"Expected status code 200, got {acc_resp.status_code}"
            acct = acc_resp.json()
            subjects = acct.get("subject") or []
            assert any(s.get("reference") == f"Patient/{patient_id}" for s in subjects), "Account not linked to expected patient"

            # And confirm it appears in subject search
            search = requests.get(
                f"{self.FHIR_SERVER_URL}/Account",
                headers=self.HEADERS,
                params={"subject": f"Patient/{patient_id}"},
            )
            assert search.status_code in [200, 201], f"Expected 200 or 201, got {search.status_code}"
            bundle = search.json()
            entries = bundle.get("entry", [])
            assert entries, "Expected to find at least one account for the patient"
            assert any(e.get("resource", {}).get("id") == account_id for e in entries), "Returned account not present in subject search"

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
            
            # Same as validate_response: extract account_id from response_msg
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            response_msg = response_msg.strip()
            assert "<ACCOUNT>" in response_msg and "</ACCOUNT>" in response_msg, "Expected to find <ACCOUNT> tag"
            account_id = response_msg.split("<ACCOUNT>")[1].split("</ACCOUNT>")[0].strip()
            assert account_id, "Expected to find account_id"

            # Same request as validate_response: fetch account by ID
            acc_resp = requests.get(f"{self.FHIR_SERVER_URL}/Account/{account_id}", headers=self.HEADERS)
            assert acc_resp.status_code == 200, f"Expected status code 200, got {acc_resp.status_code}"
            acct = acc_resp.json()
            
            # Check presence of: subject array with at least one reference
            subjects = acct.get("subject") or []
            assert len(subjects) > 0, "Account must have at least one subject"
            assert any(s.get("reference") for s in subjects), "Account must have subject with reference"

            # Same as validate_response: confirm it appears in subject search
            search = requests.get(
                f"{self.FHIR_SERVER_URL}/Account",
                headers=self.HEADERS,
                params={"subject": f"Patient/{patient_id}"},
            )
            assert search.status_code in [200, 201], f"Expected 200 or 201, got {search.status_code}"
            bundle = search.json()
            entries = bundle.get("entry", [])
            assert entries, "Expected to find at least one account for the patient"

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
            {"getResourceById": 0},
        ]

    def get_required_resource_types(self) -> list:
        return ["Account"]

    def get_prohibited_tools(self) -> list:
        return ['deleteResource']

    def get_difficulty_level(self) -> int:
        return 1
