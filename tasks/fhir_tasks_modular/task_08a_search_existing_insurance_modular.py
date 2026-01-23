# task_08a_search_existing_insurance_modular.py

import time
import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class SearchExistingInsuranceTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "8a"

    def get_task_name(self) -> str:
        return "Search Existing Insurance"

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_id", "patient_family", "patient_given"],
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient ID to search insurance information for",
                    "examples": ["PAT001"],
                    "default": "PAT001",
                },
                "insurance_provider": {
                    "type": "string",
                    "description": "Name of the insurance provider organization",
                    "examples": ["Acme Health Insurance"],
                    "default": "Acme Health Insurance",
                },
                "group_id": {
                    "type": "string",
                    "description": "Group plan identifier",
                    "examples": ["Group-98765"],
                    "default": "Group-98765",
                },
                "plan_id": {
                    "type": "string",
                    "description": "Plan identifier",
                    "examples": ["Plan-GOLD123"],
                    "default": "Plan-GOLD123",
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
                "organization_id": {
                    "type": "string",
                    "description": "Custom ID for the insurance organization",
                    "examples": ["ORG-INSURER001"],
                    "default": "ORG-INSURER001",
                },
                "related_person_id": {
                    "type": "string",
                    "description": "Custom ID for the related person resource",
                    "examples": ["PAT001-FATHER"],
                    "default": "PAT001-FATHER",
                },
                "coverage_id": {
                    "type": "string",
                    "description": "Custom ID for the coverage resource",
                    "examples": ["COV-PAT001"],
                    "default": "COV-PAT001",
                },
                "policy_start_date": {
                    "type": "string",
                    "description": "Policy start date in YYYY-MM-DD format",
                    "examples": ["2024-01-01"],
                    "default": "2024-01-01",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                },
                "policy_end_date": {
                    "type": "string",
                    "description": "Policy end date in YYYY-MM-DD format",
                    "examples": ["2025-12-31"],
                    "default": "2025-12-31",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                },
            },
        }

    def get_prompt(self) -> str:
        patient_id = self.get_param("patient_id")
        patient_family = self.get_param("patient_family")
        patient_given = self.get_param("patient_given")
        return f"""
Search if patient insurance information has been entered in the system for:
- Beneficiary: {patient_given} {patient_family} (id={patient_id})

If found, return the coverage ID using the following format: <COVERAGE>coverage_id</COVERAGE>
"""

    def prepare_test_data(self) -> None:
        try:
            # Create test patient using template parameters
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

            # Create insurance organization using template parameters
            insurance_provider = self.get_param("insurance_provider", "Acme Health Insurance")
            organization_id = self.get_param("organization_id", "ORG-INSURER001")

            organization_resource = {
                "resourceType": "Organization",
                "id": organization_id,
                "name": insurance_provider,
            }
            self.upsert_to_fhir(organization_resource)

            # Create related person using template parameters
            related_person_id = self.get_param("related_person_id", "PAT001-FATHER")

            related_person_resource = {
                "resourceType": "RelatedPerson",
                "id": related_person_id,
                "patient": {"reference": f"Patient/{patient_id}"},
            }
            self.upsert_to_fhir(related_person_resource)

            # Create coverage using template parameters
            coverage_id = self.get_param("coverage_id", "COV-PAT001")
            policy_start_date = self.get_param("policy_start_date", "2024-01-01")
            policy_end_date = self.get_param("policy_end_date", "2025-12-31")
            group_id = self.get_param("group_id", "Group-98765")
            plan_id = self.get_param("plan_id", "Plan-GOLD123")

            coverage_resource = {
                "resourceType": "Coverage",
                "id": coverage_id,
                "status": "active",
                "kind": {"coding": [{"system": "http://hl7.org/fhir/coverage-kind", "code": "insurance"}]},
                "subscriber": {"reference": f"RelatedPerson/{related_person_id}"},
                "beneficiary": {"reference": f"Patient/{patient_id}"},
                "insurer": {"reference": f"Organization/{organization_id}"},
                "period": {"start": policy_start_date, "end": policy_end_date},
                "class": [
                    {
                        "type": {
                            "coding": [
                                {
                                    "system": "https://terminology.hl7.org/6.2.0/CodeSystem-coverage-class.html",
                                    "code": "group",
                                }
                            ]
                        },
                        "value": group_id,
                    },
                    {
                        "type": {
                            "coding": [
                                {
                                    "system": "https://terminology.hl7.org/6.2.0/CodeSystem-coverage-class.html",
                                    "code": "plan",
                                }
                            ]
                        },
                        "value": plan_id,
                    },
                ],
            }
            # upsert_to_fhir either succeeds (returns response) or raises RuntimeError on failure
            self.upsert_to_fhir(coverage_resource)

            # TEST
            # Testing POLL to wait for the server to finish indexing..
            self.poll_until_exists("Patient", patient_id)
            self.poll_until_exists("Organization", organization_id)
            self.poll_until_exists("RelatedPerson", related_person_id)
            self.poll_until_exists("Coverage", coverage_id)


        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")


    def execute_human_agent(self) -> ExecutionResult:
        """Return structured success / failure; retry until the index sees it."""
        patient_id = self.get_param("patient_id")
        params = {"beneficiary": f"Patient/{patient_id}", "status": "active", "_summary": "false"}

        # ── at most three quick polls: 0.1 s, 0.2 s, 0.4 s
        delay = 0.1
        for attempt in range(5):
            resp = requests.get(f"{self.FHIR_SERVER_URL}/Coverage", headers=self.HEADERS, params=params)
            #resp = requests.get(f"{self.FHIR_SERVER_URL}/Coverage", params=params)

            if resp.status_code != 200:
                return ExecutionResult(
                    False, f"FHIR search failed: {resp.status_code} {resp.text}"
                )

            bundle = resp.json()
            if bundle.get("total", 0) > 0:
                cov_id = bundle["entry"][0]["resource"]["id"]
                return ExecutionResult(True, f"Found coverage <COVERAGE>{cov_id}</COVERAGE>")

            time.sleep(delay)
            delay *= 2

        # still nothing after three tries
        return ExecutionResult(
            False, f"No active coverage found for patient {patient_id} after 3 retries"
        )


    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            # Structured-output assertions
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            response_msg = response_msg.strip()
            assert "<COVERAGE>" in response_msg, "Expected to find <COVERAGE> tag"
            assert "</COVERAGE>" in response_msg, "Expected to find </COVERAGE> tag"
            coverage_id = response_msg.split("<COVERAGE>")[1].split("</COVERAGE>")[0]
            assert coverage_id is not None, "Expected to find coverage_id"
            # Added logic to check if the coverage_id is the same as the expected_coverage_id
            expected_coverage_id = self.execute_human_agent().response_msg.split("<COVERAGE>")[1].split("</COVERAGE>")[0]
            assert coverage_id == expected_coverage_id, f"Expected coverage_id {expected_coverage_id}, got {coverage_id}"


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
