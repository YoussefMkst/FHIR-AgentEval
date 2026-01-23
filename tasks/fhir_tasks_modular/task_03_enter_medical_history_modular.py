# task_03_enter_medical_history_modular.py

import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class EnterMedicalHistoryTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "3"

    def get_task_name(self) -> str:
        return "Enter Medical History"

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_id", "condition_code", "condition_display"],
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient ID to associate the condition with",
                    "examples": ["PAT001"],
                    "default": "PAT001",
                },
                "condition_code": {
                    "type": "string",
                    "description": "SNOMED CT code for the medical condition",
                    "examples": ["38341003"],
                    "default": "38341003",
                },
                "condition_display": {
                    "type": "string",
                    "description": "Human-readable name of the medical condition",
                    "examples": ["Hypertension"],
                    "default": "Hypertension",
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
                "clinical_status": {
                    "type": "string",
                    "description": "Clinical status of the condition",
                    "examples": ["active", "inactive", "resolved"],
                    "default": "active",
                },
            },
        }

    def get_prompt(self) -> str:
        patient_id = self.get_param("patient_id")
        condition_display = self.get_param("condition_display")
        condition_code = self.get_param("condition_code")

        return f"""

Record a medical condition for the patient id={patient_id} in his medical history that he has {condition_display} with code {condition_code}.
Using SNOMED CT (http://snomed.info/sct) for coding.

Return the recorded condition's ID using the following format: <CONDITION>condition_id</CONDITION>
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
        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")

    def execute_human_agent(self) -> ExecutionResult:
        patient_id = self.get_param("patient_id")
        condition_code = self.get_param("condition_code", "38341003")
        condition_display = self.get_param("condition_display", "Hypertension")
        clinical_status = self.get_param("clinical_status", "active")

        condition_data = {
            "resourceType": "Condition",
            "subject": {"reference": f"Patient/{patient_id}"},
            "code": {
                "coding": [
                    {
                        "system": "http://snomed.info/sct",
                        "code": condition_code,
                        "display": condition_display,
                    }
                ],
                "text": condition_display,
            },
            "clinicalStatus": {"coding": [{"code": clinical_status}]},
        }

        response = requests.post(
            f"{self.FHIR_SERVER_URL}/Condition",
            headers=self.HEADERS,
            json=condition_data,
        )

        if response.status_code != 201:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"Failed to create medical condition: {response.text}",
            )

        response_json = response.json()
        return ExecutionResult(
            execution_success=True,
            response_msg=f"Successfully created medical condition with ID: <CONDITION>{response_json.get('id')}</CONDITION>",
        )

    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            patient_id = self.get_param("patient_id")
            condition_code = self.get_param("condition_code")
            condition_display = self.get_param("condition_display")
            clinical_status = self.get_param("clinical_status", "active")

            # Verify the medical condition was created correctly
            response = requests.get(
                f"{self.FHIR_SERVER_URL}/Condition",
                headers=self.HEADERS,
                params={"subject": f"Patient/{patient_id}", "clinical-status": clinical_status},
            )

            assert response.status_code in [200, 201], f"Expected status code 200 or 201, got {response.status_code}"

            response_json = response.json()
            assert "total" in response_json, "Expected to find total in the response"
            assert response_json["total"] > 0, f"Expected to find at least one condition, but got {response_json['total']}"
            assert "entry" in response_json, "Expected to find entry in the response"
            assert len(response_json["entry"]) > 0, f"Expected to find at least one condition, but got {len(response_json['entry'])}"

            # Validate the condition details
            condition = response_json["entry"][0]["resource"]
            assert condition["resourceType"] == "Condition", "Resource type must be Condition"
            assert condition["subject"]["reference"] == f"Patient/{patient_id}", f"Subject reference must be Patient/{patient_id}"
            assert condition["clinicalStatus"]["coding"][0]["code"] == clinical_status, f"Condition must be {clinical_status}"

            # Validate the condition code
            assert "code" in condition, "Expected to find code in condition"
            assert condition["code"]["coding"][0]["system"] == "http://snomed.info/sct", "Coding system must be SNOMED CT"
            assert condition["code"]["coding"][0]["code"] == condition_code, f"Invalid condition code: expected {condition_code}"
            # removed after review
            #assert condition["code"]["text"] == condition_display, f"Invalid condition text: expected {condition_display}"
            
            # Testing this instead
            assert (
                condition["code"].get("text") == condition_display
                or condition["code"]["coding"][0].get("display") == condition_display
            ), f"Invalid condition text: expected {condition_display} but got {condition['code'].get('text')} or {condition['code']['coding'][0].get('display')}"


            # Validate response message format
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"

            response_msg = response_msg.strip()
            # match the response message with the expected format
            assert "<CONDITION>" in response_msg, "Expected to find <CONDITION> tag"
            assert "</CONDITION>" in response_msg, "Expected to find </CONDITION>tag"

            # Extract the condition_id from the response message
            condition_id = response_msg.split("<CONDITION>")[1].split("</CONDITION>")[0]
            assert condition_id is not None and condition_id != "", "Expected to find condition_id"

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
            clinical_status = self.get_param("clinical_status", "active")

            response = requests.get(
                f"{self.FHIR_SERVER_URL}/Condition",
                headers=self.HEADERS,
                params={"subject": f"Patient/{patient_id}", "clinical-status": clinical_status},
            )

            assert response.status_code in [200, 201], f"Expected status code 200 or 201, got {response.status_code}"

            response_json = response.json()
            assert "total" in response_json, "Expected to find total in the response"
            assert response_json["total"] > 0, "Expected to find at least one condition"
            assert "entry" in response_json, "Expected to find entry in the response"
            assert len(response_json["entry"]) > 0, "Expected to find at least one condition"

            condition = response_json["entry"][0]["resource"]
            # Check presence of: resourceType, subject.reference, clinicalStatus.coding[0].code, code, code.coding[0].system, code.coding[0].code, code.text or code.coding[0].display
            assert condition.get("resourceType") == "Condition", "Resource type must be Condition"
            assert condition.get("subject", {}).get("reference"), "Condition must have subject reference"
            assert condition.get("clinicalStatus", {}).get("coding") and len(condition["clinicalStatus"]["coding"]) > 0, "Condition must have clinicalStatus.coding"
            assert condition["clinicalStatus"]["coding"][0].get("code"), "Condition must have clinicalStatus.coding[0].code"
            assert "code" in condition, "Condition must have code"
            assert condition["code"].get("coding") and len(condition["code"]["coding"]) > 0, "Condition must have code.coding"
            assert condition["code"]["coding"][0].get("system"), "Condition must have code.coding[0].system"
            assert condition["code"]["coding"][0].get("code"), "Condition must have code.coding[0].code"
            assert condition["code"].get("text") or condition["code"]["coding"][0].get("display"), "Condition must have code.text or code.coding[0].display"

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
            {"searchResources": 0, "updateResource": 1},
        ]

    def get_required_resource_types(self) -> list:
        return ["Condition"]

    def get_prohibited_tools(self) -> list:
        return ["deleteResource"]

    def get_difficulty_level(self) -> int:
        return 2
