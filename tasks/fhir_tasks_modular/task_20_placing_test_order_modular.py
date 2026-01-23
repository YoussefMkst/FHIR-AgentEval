# task_20_placing_test_order_modular.py

import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class PlaceTestOrderTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "20"

    def get_task_name(self) -> str:
        return "Place WGS test order"

    def get_prompt(self) -> str:
        patient_given = self.get_param("patient_given")
        patient_family = self.get_param("patient_family")
        practitioner_given = self.get_param("practitioner_given", "John")
        practitioner_family = self.get_param("practitioner_family", "Smith")

        return f"""
Place a WGS (Whole Genome Sequencing) test order for patient {patient_given} {patient_family}. The requesting provider is Dr. {practitioner_given} {practitioner_family}. 
Use the code "wgs-rare-disease" from the system "https://fhir.hl7.org.uk/CodeSystem/UKCore-GenomeSequencingCategory" with display "WGS (Rare Disease)".

After creating the order, return the resource ID using the following format: <RESOURCE>resource_id</RESOURCE> (Do NOT include the actual resource type in the tags. It must include the <RESOURCE> and </RESOURCE> tags verbatim)
"""

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_family", "patient_given"],
            "properties": {
                "patient_family": {
                    "type": "string",
                    "description": "Patient's family name",
                    "examples": ["Doe"],
                    "default": "Doe",
                },
                "patient_given": {
                    "type": "string",
                    "description": "Patient's given name",
                    "examples": ["John"],
                    "default": "John",
                },
                "patient_birth_date": {
                    "type": "string",
                    "description": "Patient's birth date in YYYY-MM-DD format",
                    "examples": ["1990-01-02"],
                    "default": "1990-01-02",
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
                "practitioner_family": {
                    "type": "string",
                    "description": "Practitioner's family name",
                    "examples": ["Smith"],
                    "default": "Smith",
                },
                "practitioner_given": {
                    "type": "string",
                    "description": "Practitioner's given name",
                    "examples": ["John"],
                    "default": "John",
                },
            },
        }



    def prepare_test_data(self) -> None:
        try:
            patient_family = self.get_param("patient_family")
            patient_given = self.get_param("patient_given")
            birth_date = self.get_param("patient_birth_date", "1990-01-02")
            phone = self.get_param("patient_phone", "123-456-7890")
            address_line = self.get_param("patient_address_line", "123 Main St")
            city = self.get_param("patient_city", "Boston")
            state = self.get_param("patient_state", "MA")

            patient = {
                "resourceType": "Patient",
                "id": "PAT-002",
                "name": [{"use": "official", "family": patient_family, "given": [patient_given]}],
                "birthDate": birth_date,
                "telecom": [{"system": "phone", "value": phone}],
                "address": [{"line": [address_line], "city": city, "state": state}]
            }
            self.upsert_to_fhir(patient)

            practitioner_family = self.get_param("practitioner_family", "Smith")
            practitioner_given = self.get_param("practitioner_given", "John")

            practitioner = {
                "resourceType": "Practitioner",
                "id": "PROVIDER-001",
                "name": [{"use": "official", "family": practitioner_family, "given": [practitioner_given]}],
                "gender": "male",
                "communication": [{"coding": [{"system": "urn:ietf:bcp:47", "code": "en"}]}],
                "address": [{"use": "work", "line": ["123 Main St"], "city": "Boston", "state": "MA"}],
            }
            self.upsert_to_fhir(practitioner)

        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")

    def execute_human_agent(self) -> ExecutionResult:
        patient_family = self.get_param("patient_family")
        patient_given = self.get_param("patient_given")
        practitioner_family = self.get_param("practitioner_family", "Smith")
        practitioner_given = self.get_param("practitioner_given", "John")

        # 1) Search for patient and get patient ID
        params_patient = {"family": patient_family, "given": patient_given}
        patient_resp = requests.get(
            f"{self.FHIR_SERVER_URL}/Patient",
            headers=self.HEADERS,
            params=params_patient
        )

        assert patient_resp.status_code in [200, 201], f"Failed to search patient: {patient_resp.text}"

        if len(patient_resp.json()['entry']) == 0:
            return ExecutionResult(
                execution_success=False,
                response_msg="Patient does not exist"
            )
        patient_id = patient_resp.json()['entry'][0]['resource']['id']

        # 2) Search for practitioner and get practitioner ID
        params_practitioner = {"family": practitioner_family, "given": practitioner_given}
        practitioner_resp = requests.get(
            f"{self.FHIR_SERVER_URL}/Practitioner",
            headers=self.HEADERS,
            params=params_practitioner
        )

        assert practitioner_resp.status_code in [200, 201], f"Failed to search practitioner: {practitioner_resp.text}"

        if len(practitioner_resp.json()['entry']) == 0:
            return ExecutionResult(
                execution_success=False,
                response_msg="Practitioner does not exist"
            )
        practitioner_id = practitioner_resp.json()["entry"][0]['resource']['id']

        # 3) Create a service request
        service_request = {
            "resourceType": "ServiceRequest",
            "id": "SR1234",
            "status": "draft",
            "intent": "order",
            "category": [{
                "coding": [{
                    "system": "https://fhir.hl7.org.uk/CodeSystem/UKCore-GenomeSequencingCategory",
                    "code": "wgs-rare-disease",
                    "display": "WGS (Rare Disease)"
                }]
            }],
            "subject": {"reference": f"Patient/{patient_id}"},
            "requester": {"reference": f"Practitioner/{practitioner_id}"},
        }
        sr_response = requests.put(
            f"{self.FHIR_SERVER_URL}/ServiceRequest/SR1234",
            headers=self.HEADERS,
            json=service_request
        )

        assert sr_response.status_code in [200, 201], f"Failed to create ServiceRequest: {sr_response.text}"

        return ExecutionResult(
            execution_success=True,
            response_msg=f"Service Request for WGS successfully submitted with ID <RESOURCE>{service_request['id']}</RESOURCE>"
        )

    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            # Validate the service request was created correctly
            params_sr = {"subject": "Patient/PAT-002"}
            sr_response_patient = requests.get(
                f"{self.FHIR_SERVER_URL}/ServiceRequest",
                headers=self.HEADERS,
                params=params_sr
            )

            assert sr_response_patient.status_code in [200, 201], \
                f"Expected status code 200 or 201, but got {sr_response_patient.status_code}"
            assert 'entry' in sr_response_patient.json(), "Expected to find entry in response"
            assert len(sr_response_patient.json()['entry']) >= 1, \
                f"Expected to find at least one ServiceRequest for the patient"

            service_request = sr_response_patient.json()['entry'][0]['resource']
            patient_id = service_request['subject']['reference']
            practitioner_id = service_request['requester']['reference']
            
            # Try category first (UK Core), then code (standard FHIR)
            if 'category' in service_request and len(service_request['category']) > 0:
                test_code = service_request['category'][0]['coding'][0]['code']
            elif 'code' in service_request:
                test_code = service_request['code']['coding'][0]['code']
            else:
                assert False, "Expected to find test code in either category or code field"
            
            intent = service_request.get('intent')
            status = service_request.get('status')

            assert patient_id == 'Patient/PAT-002', \
                f"Expected patient ID to be Patient/PAT-002, but got {patient_id}"
            assert practitioner_id == "Practitioner/PROVIDER-001", \
                f"Expected practitioner ID to be Practitioner/PROVIDER-001, but got {practitioner_id}"
            assert test_code == "wgs-rare-disease", \
                f"Expected test code to be wgs-rare-disease, but got {test_code}"
            assert intent == "order", \
                f"Expected ServiceRequest intent to be 'order', but got {intent}"
            assert status in ["draft", "active"], \
                f"Expected ServiceRequest status to be 'draft' or 'active', but got {status}"

            # Validate response message format
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"

            response_msg = response_msg.strip()
            assert "<RESOURCE>" in response_msg, "Expected to find <RESOURCE> tag in response"
            assert "</RESOURCE>" in response_msg, "Expected to find </RESOURCE> tag in response"

            # Extract the resource ID from the response message
            resource_id = response_msg.split("<RESOURCE>")[1].split("</RESOURCE>")[0].strip()
            assert resource_id is not None and resource_id != "", "Expected to find resource_id in response"

            # Verify the returned resource ID actually exists
            resource_check_response = requests.get(
                f"{self.FHIR_SERVER_URL}/ServiceRequest/{resource_id}",
                headers=self.HEADERS
            )
            assert resource_check_response.status_code in [200, 201], \
                f"ServiceRequest with ID {resource_id} does not exist. Status: {resource_check_response.status_code}"

            # Verify it's the correct resource
            resource_data = resource_check_response.json()
            assert resource_data.get("id") == resource_id, \
                f"Expected ServiceRequest ID to be {resource_id}, but got {resource_data.get('id')}"

            return TaskResult(
                task_success=True,
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result
            )

        except AssertionError as e:
            return TaskResult(
                task_success=False,
                assertion_error_message=str(e),
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result
            )
        except Exception as e:
            return TaskResult(
                task_success=False,
                assertion_error_message=f"Unexpected error: {str(e)}",
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result
            )

    def validate_response_light(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            params_sr = {"subject": "Patient/PAT-002"}
            sr_response = requests.get(
                f"{self.FHIR_SERVER_URL}/ServiceRequest",
                headers=self.HEADERS,
                params=params_sr
            )

            assert sr_response.status_code in [200, 201], \
                f"Expected status code 200 or 201, but got {sr_response.status_code}"

            response_json = sr_response.json()
            assert "total" in response_json, "Expected to find total in the response"
            assert response_json["total"] > 0, "Expected to find at least one ServiceRequest"
            assert "entry" in response_json, "Expected to find entry in the response"
            assert len(response_json["entry"]) > 0, "Expected to find at least one ServiceRequest"

            service_request = response_json["entry"][0]["resource"]
            # Check presence of required fields
            assert service_request.get("resourceType") == "ServiceRequest", \
                "Resource type must be ServiceRequest"
            assert service_request.get("status"), "ServiceRequest must have status"
            assert service_request.get("intent"), "ServiceRequest must have intent"
            assert service_request.get("subject", {}).get("reference"), \
                "ServiceRequest must have subject reference"
            assert service_request.get("requester", {}).get("reference"), \
                "ServiceRequest must have requester reference"
            
            # Check for test code in either category (UK Core) or code (standard FHIR)
            has_category = "category" in service_request and len(service_request["category"]) > 0
            has_code = "code" in service_request and service_request["code"].get("coding")
            assert has_category or has_code, \
                "ServiceRequest must have either category or code with coding"

            return TaskResult(
                task_success=True,
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result
            )

        except AssertionError as e:
            return TaskResult(
                task_success=False,
                assertion_error_message=f"Light validation failed: {str(e)}",
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result
            )
        except Exception as e:
            return TaskResult(
                task_success=False,
                assertion_error_message=f"Light validation error: {str(e)}",
                task_id=self.get_task_id(),
                task_name=self.get_task_name(),
                execution_result=execution_result
            )

    def get_required_tool_call_sets(self) -> list:
        return [
            {"searchResources": 0, "searchResources": 1, "createResource": 2},
            {"searchResources": 0, "searchResources": 1, "updateResource": 2},
        ]

    def get_required_resource_types(self) -> list:
        return ["Patient", "Practitioner", "ServiceRequest"]

    def get_prohibited_tools(self) -> list:
        return ["deleteResource"]

    def get_difficulty_level(self) -> int:
        return 2

