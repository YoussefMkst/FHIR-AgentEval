# task_07_enter_insurance_modular.py

import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class EnterInsuranceTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "7"

    def get_task_name(self) -> str:
        return "Enter Insurance"

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_id", "insurance_provider", "policy_start_date", "policy_end_date", "group_id", "plan_id", "relationship_type"],
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient ID to add insurance information for",
                    "examples": ["PAT001"],
                    "default": "PAT001",
                },
                "insurance_provider": {
                    "type": "string",
                    "description": "Name of the insurance provider organization",
                    "examples": ["Acme Health Insurance"],
                    "default": "Acme Health Insurance",
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
                "group_id": {
                    "type": "string",
                    "description": "Group plan identifier",
                    "examples": ["Group-98765"],
                    "default": "Group-98765",
                },
                "plan_id": {
                    "type": "string",
                    "description": "Plan identifier",
                    "examples": ["GOLD123"],
                    "default": "GOLD123",
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
                # "coverage_id": {
                #     "type": "string",
                #     "description": "Custom ID for the coverage resource",
                #     "examples": ["COVERAGE-001"],
                #     "default": "COVERAGE-001",
                # },
                "relationship_type": {
                    "type": "string",
                    "description": "Relationship type for the related person",
                    "examples": ["FATHER", "MOTHER", "GUARDIAN"],
                    "default": "FATHER",
                },
            },
        }

    def get_prompt(self) -> str:
        patient_id = self.get_param("patient_id")
        insurance_provider = self.get_param("insurance_provider", "Acme Health Insurance")
        policy_start_date = self.get_param("policy_start_date")
        policy_end_date = self.get_param("policy_end_date", "2025-12-31")
        group_id = self.get_param("group_id", "Group-98765")
        plan_id = self.get_param("plan_id", "GOLD123")
        relationship_type = self.get_param("relationship_type", "FATHER")

        return f"""
Add insurance information for a patient {patient_id}
   - Insurance provider: {insurance_provider}
   - Policy period: {policy_start_date} to {policy_end_date}
   - Subscriber and policy holder: patient's {relationship_type.lower()}
   - Group Plan: Employer Group Plan (Group ID: {group_id})
   - Plan ID: {plan_id}

After creating the coverage, return the newly created Coverage ID using the following format: <COVERAGE>coverage_id</COVERAGE>
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

            # Create insurance organization using template parameters
            insurance_provider = self.get_param("insurance_provider")
            organization_id = self.get_param("organization_id", "ORG-INSURER001")

            organization_resource = {
                "resourceType": "Organization",
                "id": organization_id,
                "name": insurance_provider,
            }
            self.upsert_to_fhir(organization_resource)
        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")


    def execute_human_agent(self) -> ExecutionResult:
        try:
            patient_id = self.get_param("patient_id")
            relationship_type = self.get_param("relationship_type")
            insurance_provider = self.get_param("insurance_provider")
            policy_start_date = self.get_param("policy_start_date")
            policy_end_date = self.get_param("policy_end_date")
            group_id = self.get_param("group_id")
            plan_id = self.get_param("plan_id")
            organization_id = self.get_param("organization_id", "ORG-INSURER001")
            coverage_id = self.get_param("coverage_id", "COVERAGE-001")

            # Step 1: Create RelatedPerson (father)
            related_person_payload = {
                "resourceType": "RelatedPerson",
                "patient": {"reference": f"Patient/{patient_id}"},
                "relationship": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
                                "code": relationship_type,
                            }
                        ]
                    }
                ],
            }

            related_person_response = requests.post(
                f"{self.FHIR_SERVER_URL}/RelatedPerson",
                headers=self.HEADERS,
                json=related_person_payload,
            )

            if related_person_response.status_code != 201:
                return ExecutionResult(
                    execution_success=False,
                    response_msg=f"Failed to create related person: {related_person_response.text}",
                )

            related_person_id = related_person_response.json()["id"]

            # Step 2: Find insurance organization
            org_params = {"name": insurance_provider}
            org_response = requests.get(
                f"{self.FHIR_SERVER_URL}/Organization", headers=self.HEADERS, params=org_params
            )

            if org_response.status_code != 200:
                return ExecutionResult(
                    execution_success=False,
                    response_msg=f"Failed to find insurance organization: {org_response.text}",
                )

            # Step 3: Create Coverage
            coverage_payload = {
                "resourceType": "Coverage",
                "id": coverage_id,
                "status": "active",
                "kind": {
                    "coding": [
                        {
                            "system": "http://hl7.org/fhir/coverage-kind",
                            "code": "insurance",
                        }
                    ]
                },
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

            coverage_response = self.upsert_to_fhir(coverage_payload)

            coverage_id = coverage_response.json().get("id")
            return ExecutionResult(
                execution_success=True,
                response_msg=f"Successfully created insurance coverage with ID <COVERAGE>{coverage_id}</COVERAGE>",
            )

        except Exception as e:
            return ExecutionResult(
                execution_success=False, response_msg=f"Failed to execute task: {str(e)}"
            )



    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            patient_id = self.get_param("patient_id")
            group_id = self.get_param("group_id")
            plan_id = self.get_param("plan_id")

            # Verify the insurance coverage was created correctly
            response = requests.get(
                f"{self.FHIR_SERVER_URL}/Coverage",
                headers=self.HEADERS,
                params={"beneficiary": f"Patient/{patient_id}", "status": "active", "_summary": "false"},
            )

            assert response.status_code in [200, 201], f"Expected status code 200 or 201, got {response.status_code}"

            response_json = response.json()
            assert "total" in response_json, "Expected to find total in the response"
            assert response_json["total"] >= 1, f"Expected at least one insurance, but got {response_json['total']}"
            assert "entry" in response_json, "Expected to find entry in the response"
            assert len(response_json["entry"]) >= 1, f"Expected at least one insurance, but got {len(response_json['entry'])}"

            # Validate coverage details
            coverage = response_json["entry"][0]["resource"]
            assert coverage["resourceType"] == "Coverage", "Resource type must be Coverage"
            assert coverage["status"] == "active", "Coverage must be active"
            assert coverage["beneficiary"]["reference"] == f"Patient/{patient_id}", f"Invalid beneficiary reference: expected Patient/{patient_id}"

            # Validate coverage class details
            found_group = False
            found_plan = False
            for class_item in coverage["class"]:
                if class_item["value"] == group_id:
                    found_group = True
                elif class_item["value"] == plan_id:
                    found_plan = True
            assert found_group, f"Group ID {group_id} not found in coverage"
            assert found_plan, f"Plan ID {plan_id} not found in coverage"

            # Additional eval logic
            # Structured‐output assertions
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            response_msg = response_msg.strip()
            assert "<COVERAGE>" in response_msg, "Expected to find <COVERAGE> tag"
            assert "</COVERAGE>" in response_msg, "Expected to find </COVERAGE> tag"
            coverage_id = response_msg.split("<COVERAGE>")[1].split("</COVERAGE>")[0]
            assert coverage_id is not None and coverage_id != "", "Expected to find coverage_id"

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
                f"{self.FHIR_SERVER_URL}/Coverage",
                headers=self.HEADERS,
                params={"beneficiary": f"Patient/{patient_id}", "status": "active", "_summary": "false"},
            )

            assert response.status_code in [200, 201], f"Expected status code 200 or 201, got {response.status_code}"

            response_json = response.json()
            assert "total" in response_json, "Expected to find total in the response"
            assert response_json["total"] >= 1, "Expected to find at least one coverage"
            assert "entry" in response_json, "Expected to find entry in the response"
            assert len(response_json["entry"]) >= 1, "Expected to find at least one coverage"

            coverage = response_json["entry"][0]["resource"]
            # Check presence of: resourceType, status, beneficiary.reference, class[]
            assert coverage.get("resourceType") == "Coverage", "Resource type must be Coverage"
            assert coverage.get("status"), "Coverage must have status"
            assert coverage.get("beneficiary", {}).get("reference"), "Coverage must have beneficiary reference"
            assert coverage.get("class") and len(coverage["class"]) > 0, "Coverage must have at least one class"

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
            {"createResource": 0, "createResource": 1},
            {"getResourceById": 0, "updateResource": 1, "createResource": 2},
            {"getAllResources": 0, "deleteResource": 1, "createResource": 2, "createResource": 3},
        ]



    def get_required_resource_types(self) -> list:
        return ["RelatedPerson", "Coverage"]



    def get_prohibited_tools(self) -> list:
        return []


    def get_difficulty_level(self) -> int:
        return 2
