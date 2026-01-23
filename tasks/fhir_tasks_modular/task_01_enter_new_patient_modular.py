# task_01_enter_new_patient_modular.py
import requests  # type: ignore
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class EnterNewPatientTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "1"

    def get_task_name(self) -> str:
        return "Enter New Patient"

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_family", "patient_given", "birth_date"],
            "properties": {
                "patient_family": {
                    "type": "string",
                    "description": "Patient family (last) name",
                    "examples": ["Doe"],
                    "default": "Doe",
                },
                "patient_given": {
                    "type": "string",
                    "description": "Patient given (first) name",
                    "examples": ["John"],
                    "default": "John",
                },
                "birth_date": {
                    "type": "string",
                    "description": "Birth date in YYYY-MM-DD",
                    "examples": ["1990-06-15"],
                    "default": "1990-06-15",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                },
                "phone": {
                    "type": "string",
                    "description": "Phone number",
                    "examples": ["(123) 456-7890", "555-123-4567"],
                },
                "address_line": {
                    "type": "string",
                    "description": "Street address line",
                    "examples": ["123 Main St"],
                },
                "city": {
                    "type": "string",
                    "description": "City",
                    "examples": ["Boston"],
                },
                "state": {
                    "type": "string",
                    "description": "State/Province code",
                    "examples": ["MA"],
                },
            },
        }

    def get_prompt(self) -> str:
        given = self.get_param("patient_given")
        family = self.get_param("patient_family")
        birth_date = self.get_param("birth_date")
        phone = self.get_param("phone")
        address_line = self.get_param("address_line")
        city = self.get_param("city")
        state = self.get_param("state")

        lines = [
            "You need to create a new patient with the following information:",
            f"- Full Name: {given} {family}",
            f"- Birth Date: {birth_date}",
        ]
        if phone:
            lines.append(f"- Phone Number: {phone}")
        if address_line or city or state:
            addr_parts = []
            if address_line:
                addr_parts.append(address_line)
            if city:
                addr_parts.append(city)
            if state:
                addr_parts.append(state)
            lines.append(f"- Address: {', '.join(addr_parts)}")

        lines.extend([
            "",
            "Return the created patient's ID from the FHIR server using the following format:",
            "",
            "    <patient_id>PATIENTID</patient_id>",
        ])
        return "\n".join(lines)

    def prepare_test_data(self) -> None:
        try:
            response = requests.get(f"{self.FHIR_SERVER_URL}/metadata", headers=self.HEADERS)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Exception(f"FHIR server is not accessible: {str(e)}")

    def execute_human_agent(self) -> ExecutionResult:
        family = self.get_param("patient_family", "Doe")
        given = self.get_param("patient_given", "John")
        birth_date = self.get_param("birth_date", "1990-06-15")
        phone = self.get_param("phone")
        address_line = self.get_param("address_line")
        city = self.get_param("city")
        state = self.get_param("state")

        payload: Dict[str, Any] = {
            "resourceType": "Patient",
            "name": [
                {
                    "use": "official",
                    "family": family,
                    "given": [given],
                }
            ],
            "birthDate": birth_date,
        }

        if phone:
            payload["telecom"] = [{"system": "phone", "value": phone}]

        if address_line or city or state:
            addr: Dict[str, Any] = {}
            if address_line:
                addr["line"] = [address_line]
            if city:
                addr["city"] = city
            if state:
                addr["state"] = state
            payload["address"] = [addr]

        response = self.post_to_fhir(payload)
        if response.status_code == 201:
            tagged_response = f"<patient_id>{response.json()['id']}</patient_id>"
            response_msg = f'Patient "{given} {family}" created successfully with ID: {tagged_response}'
            success = True
        else:
            response_msg = f"Failed to create patient: {response.status_code} {response.text}"
            success = False

        return ExecutionResult(
            execution_success=success,
            response_msg=response_msg,
        )

    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        family = self.get_param("patient_family")
        given = self.get_param("patient_given")
        birth_date = self.get_param("birth_date")

        try:
            params = {"family": family, "given": given}
            response = requests.get(
                f"{self.FHIR_SERVER_URL}/Patient",
                headers=self.HEADERS,
                params=params,
            )
            assert response.status_code in [200, 201], (
                f"Expected status code 200 or 201, but got {response.status_code}. Response body: {response.text}"
            )

            response_json = response.json()
            assert "entry" in response_json and len(response_json["entry"]) > 0, "No patient found"
            patient = response_json["entry"][0]["resource"]
            assert patient["name"][0]["family"] == family, (
                f"Expected family name '{family}', got {patient['name'][0]['family']}"
            )
            assert patient["name"][0]["given"][0] == given, (
                f"Expected given name '{given}', got {patient['name'][0]['given'][0]}"
            )
            assert patient["birthDate"] == birth_date, (
                f"Expected birth date '{birth_date}', got {patient['birthDate']}"
            )

            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            response_msg = response_msg.strip()
            assert "<patient_id>" in response_msg, "Expected to find <patient_id> tag"
            assert "</patient_id>" in response_msg, "Expected to find </patient_id>tag"
            patient_id = response_msg.split("<patient_id>")[1].split("</patient_id>")[0]
            assert patient_id is not None and patient_id != "", "Expected to find patient_id"

            return TaskResult(
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
                task_success=True,
                assertion_error_message=None,
            )

        except AssertionError as e:
            return TaskResult(
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
                task_success=False,
                assertion_error_message=str(e),
            )
        except Exception as e:
            return TaskResult(
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
                task_success=False,
                assertion_error_message=f"Unexpected error: {str(e)}",
            )

    def validate_response_light(self, execution_result: ExecutionResult) -> TaskResult:
        family = self.get_param("patient_family")
        given = self.get_param("patient_given")

        try:
            params = {"family": family, "given": given}
            response = requests.get(
                f"{self.FHIR_SERVER_URL}/Patient",
                headers=self.HEADERS,
                params=params,
            )
            assert response.status_code in [200, 201], (
                f"Expected status code 200 or 201, but got {response.status_code}"
            )

            response_json = response.json()
            assert "entry" in response_json and len(response_json["entry"]) > 0, "No patient found"
            patient = response_json["entry"][0]["resource"]
            
            assert patient.get("resourceType") == "Patient", "Resource type must be Patient"
            assert patient.get("name") and len(patient["name"]) > 0, "Patient must have name"
            assert patient["name"][0].get("family"), "Patient must have family name"
            assert patient["name"][0].get("given") and len(patient["name"][0]["given"]) > 0, "Patient must have given name"
            assert patient.get("birthDate"), "Patient must have birthDate"

            return TaskResult(
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
                task_success=True,
                assertion_error_message=None,
            )

        except AssertionError as e:
            return TaskResult(
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
                task_success=False,
                assertion_error_message=f"Light validation failed: {str(e)}",
            )
        except Exception as e:
            return TaskResult(
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
                task_success=False,
                assertion_error_message=f"Light validation error: {str(e)}",
            )

    def get_required_tool_call_sets(self) -> list:
        return [
            {"createResource": 0},
            {"getResourceById": 0, "updateResource": 1},
            {"getAllResources": 0, "createResource": 1},
            {'searchResources': 0, 'createResource': 1},            
            
        ]

    def get_required_resource_types(self) -> list:
        return ["Patient"]

    def get_prohibited_tools(self) -> list:
        return ['deleteResource']

    def get_difficulty_level(self) -> int:
        return 1


