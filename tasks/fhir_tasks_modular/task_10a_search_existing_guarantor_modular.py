# task_10a_search_existing_guarantor_modular.py

import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class SearchExistingGuarantorTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "10a"

    def get_task_name(self) -> str:
        return "Search Existing Guarantor"

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_id", "patient_family", "patient_given"],
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient ID to search guarantor for",
                    "examples": ["PAT001"],
                    "default": "PAT001",
                },
                "related_person_id": {
                    "type": "string",
                    "description": "Related person ID who is the guarantor",
                    "examples": ["REL001"],
                    "default": "REL001",
                },
                "account_id": {
                    "type": "string",
                    "description": "Account ID containing the guarantor",
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
                "relationship_text": {
                    "type": "string",
                    "description": "Human-readable relationship text",
                    "examples": ["mother", "father", "guardian"],
                    "default": "mother",
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
        patient_family = self.get_param("patient_family")
        patient_given = self.get_param("patient_given")
        return f"""
Identify and confirm the guarantor responsible for this patient's insurance policy.
Patient's details:
- Name: {patient_given} {patient_family}
- ID: {patient_id}

If found, return the guarantor's ID using the following format: <GUARANTOR>guarantor_id</GUARANTOR>
"""

    def prepare_test_data(self) -> None:
        try:
            # Create patient using template parameters
            patient_id = self.get_param("patient_id")
            family = self.get_param("patient_family")
            given = self.get_param("patient_given")
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
            related_person_id = self.get_param("related_person_id", "REL001")
            relationship_text = self.get_param("relationship_text", "mother")
            related_person_family = self.get_param("related_person_family", "Doe")
            related_person_given = self.get_param("related_person_given", "Alice")
            related_person_birth_date = self.get_param("related_person_birth_date", "1960-03-01")
            related_person_gender = self.get_param("related_person_gender", "female")

            related_person_resource = {
                "resourceType": "RelatedPerson",
                "id": related_person_id,
                "patient": {"reference": f"Patient/{patient_id}"},
                "relationship": [{"text": relationship_text}],
                "name": [{"use": "official", "family": related_person_family, "given": [related_person_given]}],
                "gender": related_person_gender,
                "birthDate": related_person_birth_date,
            }
            self.upsert_to_fhir(related_person_resource)

            # Create account with guarantor using template parameters
            account_id = self.get_param("account_id", "ACC001")
            account_status = self.get_param("account_status", "active")

            account_resource = {
                "resourceType": "Account",
                "id": account_id,
                "status": account_status,
                "subject": {"reference": f"Patient/{patient_id}"},
                "guarantor": [{"party": {"reference": f"RelatedPerson/{related_person_id}"}}],
            }
            self.upsert_to_fhir(account_resource)
        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")


    def execute_human_agent(self) -> ExecutionResult:
        patient_id = self.get_param("patient_id")
        params = {"patient": f"Patient/{patient_id}"}

        response = requests.get(
            f"{self.FHIR_SERVER_URL}/Account", headers=self.HEADERS, params=params
        )

        if response.status_code != 200:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"Failed to search account: {response.text}",
            )

        response_json = response.json()
        if "entry" not in response_json or len(response_json["entry"]) == 0:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"No account found for patient {patient_id}",
            )

        account = response_json["entry"][0]["resource"]
        if "guarantor" not in account:
            return ExecutionResult(
                execution_success=False,
                response_msg="No guarantor found in account",
            )

        guarantor_reference = account["guarantor"][0]["party"]["reference"]
        guarantor_id = guarantor_reference.split("/")[-1]
        return ExecutionResult(
            execution_success=True,
            response_msg=f"Found guarantor {guarantor_reference} for patient {patient_id}: <GUARANTOR>{guarantor_id}</GUARANTOR>",
        )


    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            # Structured-output assertions
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            response_msg = response_msg.strip()
            assert "<GUARANTOR>" in response_msg, "Expected to find <GUARANTOR> tag"
            assert "</GUARANTOR>" in response_msg, "Expected to find </GUARANTOR> tag"
            guarantor_id = response_msg.split("<GUARANTOR>")[1].split("</GUARANTOR>")[0]
            expected_id = self.execute_human_agent().response_msg.split("<GUARANTOR>")[1].split("</GUARANTOR>")[0]
            assert guarantor_id == expected_id, f"Expected guarantor_id {expected_id}, got {guarantor_id}"

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
        return ["Account"]

    def get_prohibited_tools(self) -> list:
        return ["createResource", "updateResource", "deleteResource"]

    def get_difficulty_level(self) -> int:
        return 2
