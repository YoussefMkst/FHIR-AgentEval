# task_10b_search_nonexistent_guarantor_modular.py

import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class SearchNonexistentGuarantorTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "10b"

    def get_task_name(self) -> str:
        return "Search Nonexistent Guarantor"

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_id", "patient_family", "patient_given"],
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Patient ID to search guarantor for (should have no guarantor)",
                    "examples": ["PAT002"],
                    "default": "PAT002",
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
                    "examples": ["Jane"],
                    "default": "Jane",
                },
                "patient_birth_date": {
                    "type": "string",
                    "description": "Patient's birth date in YYYY-MM-DD format",
                    "examples": ["2020-06-15"],
                    "default": "2020-06-15",
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
        patient_family = self.get_param("patient_family")
        patient_given = self.get_param("patient_given")
        return f"""
    Identify and confirm the guarantor responsible for this patient's insurance policy.
    Patient's details:
    - Name: {patient_given} {patient_family}
    - ID: {patient_id}

    If found, return the guarantor's ID using the following format: <GUARANTOR>guarantor_id</GUARANTOR>
    If none found, return the exact sentence: "No guarantor found for patient {patient_id}"
    """


    def prepare_test_data(self) -> None:
        try:
            # Create patient without any account or guarantor using template parameters
            patient_id = self.get_param("patient_id")
            family = self.get_param("patient_family")
            given = self.get_param("patient_given")
            birth_date = self.get_param("patient_birth_date", "2020-06-15")
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
        if response_json.get("total", 0) > 0:
            guarantor_reference = response_json["entry"][0]["resource"]["guarantor"][0]["party"]["reference"]
            guarantor_id = guarantor_reference.split("/")[-1]
            return ExecutionResult(
                execution_success=True,
                response_msg=f"Found guarantor {guarantor_reference} for patient {patient_id}: <GUARANTOR>{guarantor_id}</GUARANTOR>",
            )
        else:
            return ExecutionResult(
                execution_success=True,
                response_msg=f"No guarantor found for patient {patient_id}",
            )



    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            patient_id = self.get_param("patient_id")

            # Structured-output assertions
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            response_msg = response_msg.strip()
            assert "no guarantor found" in response_msg.lower(), f"Expected 'No guarantor found for patient {patient_id}', got '{response_msg}'"

            task_result = TaskResult(
                task_success=True,
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result,
            )

            failure_mode = self.identify_failure_mode(task_result)
            if failure_mode:
                assert failure_mode.incorrect_tool_selection is not True, "Incorrect tool selection"
                assert failure_mode.incorrect_tool_order is not True, "Incorrect tool order"
                assert failure_mode.incorrect_resource_type is not True, "Incorrect resource type"
                assert failure_mode.prohibited_tool_used is not True, "Prohibited tool used"

            return task_result

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
        return 1
