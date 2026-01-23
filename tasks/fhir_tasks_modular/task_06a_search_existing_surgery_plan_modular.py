# task_06a_search_existing_surgery_plan_modular.py

import requests
from typing import Dict, Any
from datetime import datetime, timedelta

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class SearchExistingSurgeryPlanTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "6a"

    def get_task_name(self) -> str:
        return "Search Existing Surgery Plan"

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_id", "search_days_ahead"],
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient ID to search surgery plans for",
                    "examples": ["PAT001"],
                    "default": "PAT001",
                },
                "procedure_code": {
                    "type": "string",
                    "description": "SNOMED CT code for the surgical procedure",
                    "examples": ["80146002"],
                    "default": "80146002",
                },
                "procedure_display": {
                    "type": "string",
                    "description": "Human-readable name of the surgical procedure",
                    "examples": ["Appendectomy"],
                    "default": "Appendectomy",
                },
                "surgery_plan_id": {
                    "type": "string",
                    "description": "Custom ID for the surgery plan resource",
                    "examples": ["APPENDECTOMY-REQUEST-001"],
                    "default": "APPENDECTOMY-REQUEST-001",
                },
                "days_ahead": {
                    "type": "integer",
                    "description": "Number of days ahead to schedule the surgery",
                    "examples": [7],
                    "default": 7,
                    "minimum": 1,
                },
                "search_days_ahead": {
                    "type": "integer",
                    "description": "Number of days ahead to search for surgery plans",
                    "examples": [14],
                    "default": 14,
                    "minimum": 1,
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
                "service_status": {
                    "type": "string",
                    "description": "Status of the service request",
                    "examples": ["active", "completed", "cancelled"],
                    "default": "active",
                },
                "service_intent": {
                    "type": "string",
                    "description": "Intent of the service request",
                    "examples": ["order", "plan", "proposal"],
                    "default": "order",
                },
            },
        }

    def get_prompt(self) -> str:
        patient_id = self.get_param("patient_id")
        search_days_ahead = self.get_param("search_days_ahead")
        return f"""

Search and find if patient id={patient_id} has any surgery plan within {search_days_ahead} days from now.

If found, return the surgery plan's ID using the following format: <SURGERY_PLAN>plan_id</SURGERY_PLAN>
"""

    def prepare_test_data(self) -> None:
        try:
            today = datetime.today().date()
            days_ahead = self.get_param("days_ahead", 7)
            surgery_date = today + timedelta(days=days_ahead)

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

            # Create service request using template parameters
            procedure_code = self.get_param("procedure_code", "80146002")
            procedure_display = self.get_param("procedure_display", "Appendectomy")
            surgery_plan_id = self.get_param("surgery_plan_id", "APPENDECTOMY-REQUEST-001")
            service_status = self.get_param("service_status", "active")
            service_intent = self.get_param("service_intent", "order")

            service_request = {
                "resourceType": "ServiceRequest",
                "id": surgery_plan_id,
                "status": service_status,
                "intent": service_intent,
                "code": {
                    "coding": [
                        {
                            "system": "http://snomed.info/sct",
                            "code": procedure_code,
                            "display": procedure_display,
                        }
                    ],
                    "text": procedure_display,
                },
                "subject": {"reference": f"Patient/{patient_id}"},
                "occurrenceDateTime": surgery_date.strftime("%Y-%m-%d"),
            }
            self.upsert_to_fhir(service_request)
        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")

    def execute_human_agent(self) -> ExecutionResult:
        patient_id = self.get_param("patient_id")
        search_days_ahead = self.get_param("search_days_ahead")
        
        today = datetime.today().date()
        two_weeks_later = today + timedelta(days=search_days_ahead)

        params = {
            "subject": f"Patient/{patient_id}",
            "occurrence": [
                f"ge{today.isoformat()}",
                f"le{two_weeks_later.isoformat()}",
            ],
        }

        response = requests.get(
            f"{self.FHIR_SERVER_URL}/ServiceRequest", headers=self.HEADERS, params=params
        )

        if response.status_code != 200:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"Failed to search for surgery plans: {response.text}",
            )

        response_json = response.json()
        return ExecutionResult(
            execution_success=True,
            response_msg=(
                f"Found {response_json.get('total', 0)} surgery plan(s) for patient {patient_id}: "
                f"<SURGERY_PLAN>{response_json['entry'][0]['resource']['id']}</SURGERY_PLAN>"
            ),
        )

    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            # Structured‐output assertions
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            response_msg = response_msg.strip()
            assert "<SURGERY_PLAN>" in response_msg, "Expected to find <SURGERY_PLAN> tag"
            assert "</SURGERY_PLAN>" in response_msg, "Expected to find </SURGERY_PLAN> tag"
            surgery_plan_id = response_msg.split("<SURGERY_PLAN>")[1].split("</SURGERY_PLAN>")[0]
            assert surgery_plan_id is not None, "Expected to find surgery_plan_id"
            expected_id = self.execute_human_agent().response_msg.split("<SURGERY_PLAN>")[1].split("</SURGERY_PLAN>")[0]
            assert surgery_plan_id == expected_id, f"Expected surgery_plan_id {expected_id}, got {surgery_plan_id}"

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
        return ["ServiceRequest"]

    def get_prohibited_tools(self) -> list:
        return ["createResource", "updateResource", "deleteResource"]

    def get_difficulty_level(self) -> int:
        return 1
