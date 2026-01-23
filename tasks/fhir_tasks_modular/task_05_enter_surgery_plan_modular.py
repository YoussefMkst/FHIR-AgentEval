# task_05_enter_surgery_plan_modular.py

import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class EnterSurgeryPlanTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "5"

    def get_task_name(self) -> str:
        return "Enter Surgery Plan"

    def get_prompt(self) -> str:
        patient_id = self.get_param("patient_id")
        procedure_display = self.get_param("procedure_display")
        surgery_date = self.get_param("surgery_date")

        return f"""
    Record a surgery plan for patient with id {patient_id} for a {procedure_display} surgery planned for {surgery_date}. The plan is confirmed. 

    Once done, return the surgery plan ID in the following format: <surgery_plan>surgeryPlan</surgery_plan>
    """

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_id", "procedure_code", "procedure_display", "surgery_date"],
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient ID to associate the surgery plan with",
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
                "surgery_date": {
                    "type": "string",
                    "description": "Planned surgery date in YYYY-MM-DD format",
                    "examples": ["2025-05-01"],
                    "default": "2025-05-01",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
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

    

    def prepare_test_data(self) -> None:
        try:
            # Create test patient using template parameters
            patient_id = self.get_param("patient_id")
            family = self.get_param("patient_family")
            given = self.get_param("patient_given")
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
        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")



    def execute_human_agent(self) -> ExecutionResult:
        patient_id = self.get_param("patient_id")
        procedure_code = self.get_param("procedure_code")
        procedure_display = self.get_param("procedure_display")
        surgery_date = self.get_param("surgery_date")
        service_status = self.get_param("service_status")
        service_intent = self.get_param("service_intent")

        service_request = {
            "resourceType": "ServiceRequest",
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
            "occurrenceDateTime": surgery_date,
        }

        response = requests.post(
            f"{self.FHIR_SERVER_URL}/ServiceRequest",
            headers=self.HEADERS,
            json=service_request,
        )

        if response.status_code != 201:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"Failed to create surgery plan: {response.text}",
            )

        response_json = response.json()
        return ExecutionResult(
            execution_success=True,
            response_msg=f"Successfully created surgery plan with ID <surgery_plan>{response_json.get('id')}</surgery_plan>",
        )


    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            patient_id = self.get_param("patient_id")
            procedure_code = self.get_param("procedure_code")
            procedure_display = self.get_param("procedure_display")
            surgery_date = self.get_param("surgery_date")
            service_status = self.get_param("service_status", 'active')

            # Verify the surgery plan was created correctly
            response = requests.get(
                f"{self.FHIR_SERVER_URL}/ServiceRequest",
                headers=self.HEADERS,
                params={"subject": f"Patient/{patient_id}", "status": service_status},
            )

            assert response.status_code in [200, 201], f"Expected status code 200 or 201, got {response.status_code}"

            response_json = response.json()
            print("response_json", response_json)
            assert "total" in response_json, "Expected to find total in the response"
            assert response_json["total"] > 0, f"Expected to find at least one surgery plan, but got {response_json['total']}"
            assert "entry" in response_json, "Expected to find entry in the response!"
            assert len(response_json["entry"]) > 0, f"Expected to find at least one surgery plan, but got {len(response_json['entry'])}"

            # Validate the service request details
            service_request = response_json["entry"][0]["resource"]
            assert service_request["resourceType"] == "ServiceRequest", "Resource type must be ServiceRequest"
            assert service_request["status"] == service_status, f"Service request must be {service_status}"
            assert service_request["subject"]["reference"] == f"Patient/{patient_id}", f"Subject reference must be Patient/{patient_id}"

            # Validate the procedure code
            assert "code" in service_request, "Expected to find code in service request"
            assert service_request["code"]["coding"][0]["code"] == procedure_code, f"Invalid procedure code: expected {procedure_code}"
            # removed after review
            #assert service_request["code"]["text"] == procedure_display, f"Invalid procedure text: expected {procedure_display}"

            # Testing this instead
            code_text = service_request["code"].get("text")
            code_display = service_request["code"]["coding"][0].get("display")
            combined_text = code_text or code_display or ""

            assert procedure_display.lower() in combined_text.lower(), (
                f"Invalid procedure text: expected something containing {procedure_display!r} "
                f"but got text={code_text!r} display={code_display!r}"
            )

            # Validate the scheduled date
            assert service_request["occurrenceDateTime"] == surgery_date, f"Incorrect surgery date: expected {surgery_date}"

            # Check if returned result matches the human executed request's return.
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"

            # Parse the response message
            response_msg = response_msg.strip()
            # match the response message with the expected format
            assert "<surgery_plan>" in response_msg, "Expected to find <surgery_plan> tag"
            assert "</surgery_plan>" in response_msg, "Expected to find </surgery_plan>tag"

            # Extract the surgery_plan from the response message
            surgery_plan = response_msg.split("<surgery_plan>")[1].split("</surgery_plan>")[0]
            assert surgery_plan is not None and surgery_plan != "", "Expected to find surgery_plan"

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
            service_status = self.get_param("service_status", 'active')

            response = requests.get(
                f"{self.FHIR_SERVER_URL}/ServiceRequest",
                headers=self.HEADERS,
                params={"subject": f"Patient/{patient_id}"},
            )

            assert response.status_code in [200, 201], f"Expected status code 200 or 201, got {response.status_code}"

            response_json = response.json()
            assert "total" in response_json, "Expected to find total in the response"
            assert response_json["total"] > 0, "Expected to find at least one surgery plan"
            assert "entry" in response_json, "Expected to find entry in the response"
            assert len(response_json["entry"]) > 0, "Expected to find at least one surgery plan"

            service_request = response_json["entry"][0]["resource"]
            # Check presence of: resourceType, status, subject.reference, code, code.coding[0].code, code.text or code.coding[0].display, occurrenceDateTime
            assert service_request.get("resourceType") == "ServiceRequest", "Resource type must be ServiceRequest"
            assert service_request.get("status"), "ServiceRequest must have status"
            assert service_request.get("subject", {}).get("reference"), "ServiceRequest must have subject reference"
            assert "code" in service_request, "ServiceRequest must have code"
            assert service_request["code"].get("coding") and len(service_request["code"]["coding"]) > 0, "ServiceRequest must have code.coding"
            assert service_request["code"]["coding"][0].get("code"), "ServiceRequest must have code.coding[0].code"
            assert service_request["code"].get("text") or service_request["code"]["coding"][0].get("display"), "ServiceRequest must have code.text or code.coding[0].display"
            assert service_request.get("occurrenceDateTime"), "ServiceRequest must have occurrenceDateTime"

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
            {"getAllResources": 0, "createResource": 1},
        ]

    def get_required_resource_types(self) -> list:
        return ["ServiceRequest"]

    def get_prohibited_tools(self) -> list:
        return ["deleteResource"]

    def get_difficulty_level(self) -> int:
        return 2
