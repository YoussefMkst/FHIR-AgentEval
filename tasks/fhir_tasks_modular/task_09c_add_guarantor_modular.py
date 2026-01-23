# task_09c_add_guarantor_modular.py

import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class AddGuarantorTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "9c"

    def get_task_name(self) -> str:
        return "Add Guarantor"

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_id", "related_person_id", "account_id", "relationship_code", "relationship_text"],
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient ID for the account",
                    "examples": ["PAT001"],
                    "default": "PAT001",
                },
                "related_person_id": {
                    "type": "string",
                    "description": "Related person ID to add as guarantor",
                    "examples": ["REL001"],
                    "default": "REL001",
                },
                "account_id": {
                    "type": "string",
                    "description": "Account ID to add guarantor to",
                    "examples": ["ACC001"],
                    "default": "ACC001",
                },
                "relationship_code": {
                    "type": "string",
                    "description": "HL7 role code for the relationship",
                    "examples": ["MOTHER", "FATHER", "GUARDIAN"],
                    "default": "MOTHER",
                },
                "relationship_text": {
                    "type": "string",
                    "description": "Human-readable relationship text",
                    "examples": ["mother", "father", "guardian"],
                    "default": "mother",
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
                "related_person_family": {
                    "type": "string",
                    "description": "Related person's family name",
                    "examples": ["Doe"],
                    "default": "Doe",
                },
                "related_person_given": {
                    "type": "string",
                    "description": "Related person's given name",
                    "examples": ["Alice"],
                    "default": "Alice",
                },
                "related_person_birth_date": {
                    "type": "string",
                    "description": "Related person's birth date in YYYY-MM-DD format",
                    "examples": ["1960-03-01"],
                    "default": "1960-03-01",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                },
                "related_person_gender": {
                    "type": "string",
                    "description": "Related person's gender",
                    "examples": ["female", "male", "other", "unknown"],
                    "default": "female",
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
        related_person_id = self.get_param("related_person_id")
        account_id = self.get_param("account_id")
        relationship_text = self.get_param("relationship_text")
        return f"""

Add the related person with id:{related_person_id} as a guarantor to the account with id: {account_id} with the following details:
- Relationship: {relationship_text}

After updating, return the account ID using the following format: <ACCOUNT>account_id</ACCOUNT>
"""

    def prepare_test_data(self) -> None:
        try:
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

            # Create related person using template parameters
            related_person_id = self.get_param("related_person_id")
            relationship_code = self.get_param("relationship_code")
            relationship_text = self.get_param("relationship_text")
            related_person_family = self.get_param("related_person_family", "Doe")
            related_person_given = self.get_param("related_person_given", "Alice")
            related_person_birth_date = self.get_param("related_person_birth_date", "1960-03-01")
            related_person_gender = self.get_param("related_person_gender", "female")

            related_person_resource = {
                "resourceType": "RelatedPerson",
                "id": related_person_id,
                "patient": {"reference": f"Patient/{patient_id}"},
                "relationship": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
                                "code": relationship_code,
                            }
                        ],
                        "text": relationship_text,
                    }
                ],
                "name": [{"use": "official", "family": related_person_family, "given": [related_person_given]}],
                "gender": related_person_gender,
                "birthDate": related_person_birth_date,
            }
            self.upsert_to_fhir(related_person_resource)

            # Create initial account using template parameters
            account_id = self.get_param("account_id")
            account_status = self.get_param("account_status", "active")

            account_payload = {
                "resourceType": "Account",
                "id": account_id,
                "status": account_status,
                "subject": {"reference": f"Patient/{patient_id}"},
            }
            self.upsert_to_fhir(account_payload)

        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")


    def execute_human_agent(self) -> Dict:
        related_person_id = self.get_param("related_person_id")
        account_id = self.get_param("account_id")
        patient_id = self.get_param("patient_id")
        account_status = self.get_param("account_status", "active")

        update_payload = {
            "resourceType": "Account",
            "id": account_id,
            "status": account_status,
            "subject": {"reference": f"Patient/{patient_id}"},
            "guarantor": [{"party": {"reference": f"RelatedPerson/{related_person_id}"}}],
        }

        # Update the account
        response = requests.put(
            f"{self.FHIR_SERVER_URL}/Account/{account_id}", headers=self.HEADERS, json=update_payload
        )

        if response.status_code not in [200, 201]:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"Failed to update account: {response.text}",
            )

        response_json = response.json()
        account_id = response_json.get("id")
        return ExecutionResult(
            execution_success=True,
            response_msg=f"Updated account with ID <ACCOUNT>{account_id}</ACCOUNT>",
        )


    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            account_id = self.get_param("account_id")
            related_person_id = self.get_param("related_person_id")

            # Verify the account was updated correctly
            response = requests.get(
                f"{self.FHIR_SERVER_URL}/Account/{account_id}", headers=self.HEADERS
            )

            response_json = response.json()
            assert response_json["resourceType"] == "Account", "Invalid resource type"
            assert response_json["status"] == "active", "Account status should be active"
            assert "guarantor" in response_json, "Guarantor not added to account"
            assert response_json["guarantor"][0]["party"]["reference"] == f"RelatedPerson/{related_person_id}", f"Invalid guarantor reference: expected RelatedPerson/{related_person_id}"

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
            account_id = self.get_param("account_id")

            # Same request as validate_response
            response = requests.get(
                f"{self.FHIR_SERVER_URL}/Account/{account_id}", headers=self.HEADERS
            )

            response_json = response.json()
            # Check presence of: resourceType, status, guarantor, guarantor[0].party.reference
            assert response_json.get("resourceType") == "Account", "Resource type must be Account"
            assert response_json.get("status"), "Account must have status"
            assert "guarantor" in response_json, "Account must have guarantor"
            assert response_json["guarantor"][0].get("party", {}).get("reference"), "Account must have guarantor[0].party.reference"

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
            {"updateResource": 0},
            {"getResourceById": 0, "updateResource": 1},
            {"searchResources": 0, "updateResource": 1},
        ]

    def get_required_resource_types(self) -> list:
        return ["Account"]

    def get_prohibited_tools(self) -> list:
        return ['deleteResource']

    def get_difficulty_level(self) -> int:
        return 2
