# task_09a_create_related_person_modular.py

import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class CreateRelatedPersonTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "9a"

    def get_task_name(self) -> str:
        return "Create Related Person"

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_id", "related_person_family", "related_person_given", "relationship_text", "related_person_birth_date"],
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient ID to create related person for",
                    "examples": ["PAT001"],
                    "default": "PAT001",
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
        related_person_family = self.get_param("related_person_family")
        related_person_given = self.get_param("related_person_given")
        relationship_text = self.get_param("relationship_text")
        related_person_birth_date = self.get_param("related_person_birth_date")

        return f"""

Create a related person resource for the patient {patient_id} with the following details:
- Name: {related_person_given} {related_person_family}
- Relationship: {relationship_text}
- Date of Birth: {related_person_birth_date}

After creation, return the new RelatedPerson ID using the following format: <RELATED_PERSON>related_person_id</RELATED_PERSON>
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
        related_person_family = self.get_param("related_person_family")
        related_person_given = self.get_param("related_person_given")
        relationship_code = self.get_param("relationship_code")
        relationship_text = self.get_param("relationship_text")
        related_person_birth_date = self.get_param("related_person_birth_date", "1960-03-01")
        related_person_gender = self.get_param("related_person_gender", "female")

        related_person_payload = {
            "resourceType": "RelatedPerson",
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

        response = requests.post(
            f"{self.FHIR_SERVER_URL}/RelatedPerson",
            headers=self.HEADERS,
            json=related_person_payload,
        )

        if response.status_code != 201:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"Failed to create related person: {response.text}",
            )

        response_json = response.json()
        related_person_id = response_json.get("id")
        return ExecutionResult(
            execution_success=True,
            response_msg=f"Created related person with ID <RELATED_PERSON>{related_person_id}</RELATED_PERSON>",
        )


    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            patient_id = self.get_param("patient_id")
            related_person_family = self.get_param("related_person_family")
            related_person_given = self.get_param("related_person_given")
            related_person_birth_date = self.get_param("related_person_birth_date", "1960-03-01")

            # Extract the created RelatedPerson ID from the gold output
            response_msg = (execution_result.response_msg or "").strip()
            assert "<RELATED_PERSON>" in response_msg and "</RELATED_PERSON>" in response_msg, "Missing <RELATED_PERSON> tag"
            related_person_id = response_msg.split("<RELATED_PERSON>")[1].split("</RELATED_PERSON>")[0].strip()
            assert related_person_id, "Expected to find related_person_id"

            # Fetch that exact resource and validate fields safely
            rp_resp = requests.get(f"{self.FHIR_SERVER_URL}/RelatedPerson/{related_person_id}", headers=self.HEADERS)
            assert rp_resp.status_code == 200, f"Expected status code 200, got {rp_resp.status_code}"
            related_person = rp_resp.json()

            assert related_person.get("resourceType") == "RelatedPerson", "Invalid resource type"
            patient_ref = (related_person.get("patient") or {}).get("reference")
            assert patient_ref == f"Patient/{patient_id}", f"Invalid patient reference: expected Patient/{patient_id}"
            assert related_person.get("birthDate") == related_person_birth_date, f"Invalid birth date: expected {related_person_birth_date}"
            name0 = (related_person.get("name") or [{}])[0]
            assert name0.get("family") == related_person_family, f"Invalid family name: expected {related_person_family}"
            given_list = name0.get("given") or []
            assert related_person_given in given_list, f"Invalid given name: expected {related_person_given}"

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
            response_msg = (execution_result.response_msg or "").strip()
            assert "<RELATED_PERSON>" in response_msg and "</RELATED_PERSON>" in response_msg, "Missing <RELATED_PERSON> tag"
            related_person_id = response_msg.split("<RELATED_PERSON>")[1].split("</RELATED_PERSON>")[0].strip()
            assert related_person_id, "Expected to find related_person_id"

            rp_resp = requests.get(f"{self.FHIR_SERVER_URL}/RelatedPerson/{related_person_id}", headers=self.HEADERS)
            assert rp_resp.status_code == 200, f"Expected status code 200, got {rp_resp.status_code}"
            related_person = rp_resp.json()

            assert related_person.get("resourceType") == "RelatedPerson", "Resource type must be RelatedPerson"
            assert related_person.get("patient", {}).get("reference"), "RelatedPerson must have patient reference"
            assert related_person.get("name") and len(related_person["name"]) > 0, "RelatedPerson must have name"
            assert related_person["name"][0].get("family"), "RelatedPerson must have family name"
            assert related_person["name"][0].get("given") and len(related_person["name"][0]["given"]) > 0, "RelatedPerson must have given name"
            assert related_person.get("birthDate"), "RelatedPerson must have birthDate"

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
            {"searchResources": 0, "createResource": 1},
            {"searchResources": 0, "updateResource": 1},
            {"getResourceById": 0, "updateResource": 1},
            {"getResourceById": 0, "createResource": 1},
        ]

    def get_required_resource_types(self) -> list:
        return ["RelatedPerson"]

    def get_prohibited_tools(self) -> list:
        return ['deleteResource']

    def get_difficulty_level(self) -> int:
        return 1
