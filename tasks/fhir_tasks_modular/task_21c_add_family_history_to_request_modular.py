# task_21c_add_family_history_to_request_modular.py

import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class AddFamilyHistoryToRequestTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "21c"

    def get_task_name(self) -> str:
        return "Add family history to genetic test request"

    def get_prompt(self) -> str:
        patient_given = self.get_param("patient_given")
        patient_family = self.get_param("patient_family")
        relative = self.get_param("relative_relationship")
        condition = self.get_param("condition_name")
        age = self.get_param("condition_age")

        return f"""
Patient {patient_given} {patient_family}'s {relative} had {condition} diagnosed at age {age}. Add this family history information as supporting information to their upcoming genetic test order.

After updating, return the test order's FHIR resource ID using the following format: <RESOURCE>resource_id</RESOURCE> (Do NOT include the actual resource type in the tags. It must include the <RESOURCE> and </RESOURCE> tags verbatim)

"""

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_family", "patient_given", "relative_relationship", "condition_name", "condition_age"],
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
                "relative_relationship": {
                    "type": "string",
                    "description": "Relationship of family member (e.g., mother, father, sister)",
                    "examples": ["mother", "father", "sister"],
                    "default": "mother",
                },
                "relationship_code": {
                    "type": "string",
                    "description": "FHIR relationship code (MTH, FTH, SIS, etc.)",
                    "examples": ["MTH", "FTH", "SIS"],
                    "default": "MTH",
                },
                "condition_name": {
                    "type": "string",
                    "description": "Condition/disease name",
                    "examples": ["breast cancer", "colon cancer"],
                    "default": "breast cancer",
                },
                "condition_age": {
                    "type": "integer",
                    "description": "Age at diagnosis",
                    "examples": [45, 52],
                    "default": 45,
                },
            },
        }

    def prepare_test_data(self) -> None:
        try:
            patient_family = self.get_param("patient_family")
            patient_given = self.get_param("patient_given")

            # Create patient
            patient = {
                "resourceType": "Patient",
                "id": "PAT-005",
                "name": [{"use": "official", "family": patient_family, "given": [patient_given]}],
                "birthDate": "1990-01-02",
                "gender": "male",
                "telecom": [{"system": "phone", "value": "123-456-7890"}],
                "address": [{"line": ["123 Main St"], "city": "Boston", "state": "MA"}]
            }
            self.upsert_to_fhir(patient)

            # Create practitioner
            practitioner = {
                "resourceType": "Practitioner",
                "id": "PROVIDER-003",
                "name": [{"use": "official", "family": "Smith", "given": ["John"]}],
                "gender": "male",
                "communication": [{"coding": [{"system": "urn:ietf:bcp:47", "code": "en"}]}],
                "address": [{"use": "work", "line": ["123 Main St"], "city": "Boston", "state": "MA"}]
            }
            self.upsert_to_fhir(practitioner)

            # Create WGS service request
            service_request = {
                "resourceType": "ServiceRequest",
                "id": "SR-GENETIC-001",
                "status": "draft",
                "intent": "order",
                "category": [{
                    "coding": [{
                        "system": "https://fhir.hl7.org.uk/CodeSystem/UKCore-GenomeSequencingCategory",
                        "code": "wgs-rare-disease",
                        "display": "WGS (Rare Disease)"
                    }]
                }],
                "subject": {"reference": "Patient/PAT-005"},
                "requester": {"reference": "Practitioner/PROVIDER-003"}
            }
            self.upsert_to_fhir(service_request)

        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")

    def execute_human_agent(self) -> ExecutionResult:
        patient_family = self.get_param("patient_family")
        patient_given = self.get_param("patient_given")
        relative = self.get_param("relative_relationship")
        relationship_code = self.get_param("relationship_code", "MTH")
        condition = self.get_param("condition_name")
        condition_age = self.get_param("condition_age")

        # 1) Search for patient
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

        # 2) Create FamilyMemberHistory resource
        family_history = {
            "resourceType": "FamilyMemberHistory",
            "status": "completed",
            "patient": {"reference": f"Patient/{patient_id}"},
            "relationship": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
                    "code": relationship_code,
                    "display": relative
                }]
            },
            "condition": [{
                "code": {
                    "text": condition
                },
                "onsetAge": {
                    "value": condition_age,
                    "unit": "years",
                    "system": "http://unitsofmeasure.org",
                    "code": "a"
                }
            }]
        }

        fh_resp = requests.post(
            f"{self.FHIR_SERVER_URL}/FamilyMemberHistory",
            headers=self.HEADERS,
            json=family_history
        )

        assert fh_resp.status_code in [200, 201], f"Failed to create FamilyMemberHistory: {fh_resp.text}"

        family_history_id = fh_resp.json()['id']

        # 3) Get service request for this patient
        params_sr = {"subject": f"Patient/{patient_id}"}
        sr_resp = requests.get(
            f"{self.FHIR_SERVER_URL}/ServiceRequest",
            headers=self.HEADERS,
            params=params_sr
        )

        assert sr_resp.status_code in [200, 201], f"Failed to search for service request: {sr_resp.text}"

        if len(sr_resp.json()['entry']) == 0:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"Cannot find any service request for patient {patient_given} {patient_family}"
            )

        service_request = sr_resp.json()['entry'][0]['resource']

        # 4) Update service request with family history as supporting info
        supporting_info = service_request.get('supportingInfo', [])
        supporting_info.append({"reference": f"FamilyMemberHistory/{family_history_id}"})
        service_request['supportingInfo'] = supporting_info

        updated_sr = requests.put(
            f"{self.FHIR_SERVER_URL}/ServiceRequest/{service_request['id']}",
            headers=self.HEADERS,
            json=service_request
        )

        assert updated_sr.status_code in [200, 201], f"Failed to update service request {service_request['id']}: {updated_sr.text}"

        return ExecutionResult(
            execution_success=True,
            response_msg=f"Successfully added family history to genetic test request <RESOURCE>{service_request['id']}</RESOURCE>"
        )

    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            relative = self.get_param("relative_relationship")
            relationship_code = self.get_param("relationship_code", "MTH")
            condition = self.get_param("condition_name")
            condition_age = self.get_param("condition_age")

            # 1) Validate FamilyMemberHistory was created
            params_fh = {"patient": "Patient/PAT-005"}
            fh_resp = requests.get(
                f"{self.FHIR_SERVER_URL}/FamilyMemberHistory",
                headers=self.HEADERS,
                params=params_fh
            )

            assert fh_resp.status_code in [200, 201], f"Failed to search for FamilyMemberHistory: {fh_resp.text}"
            assert len(fh_resp.json().get('entry', [])) > 0, "Expected to find at least one FamilyMemberHistory"

            family_history = fh_resp.json()['entry'][0]['resource']

            # Validate family member relationship display
            relationship = family_history.get('relationship', {})
            relationship_display = relationship.get('coding', [{}])[0].get('display', '').lower()
            relationship_text = relationship.get('text', '').lower()
            assert relative.lower() in relationship_display or relative.lower() in relationship_text, \
                f"Expected relationship to be '{relative}', but got display='{relationship_display}' text='{relationship_text}'"

            # Validate relationship code
            actual_code = relationship.get('coding', [{}])[0].get('code')
            assert actual_code == relationship_code, \
                f"Expected relationship code '{relationship_code}', but got {actual_code}"

            # Validate condition mentions the expected condition
            fh_condition = family_history.get('condition', [{}])[0]
            condition_display = fh_condition.get('code', {}).get('coding', [{}])[0].get('display', '').lower()
            condition_text = fh_condition.get('code', {}).get('text', '').lower()
            
            # Split condition name into words and check each is present
            condition_words = condition.lower().split()
            condition_found = all(
                word in condition_display or word in condition_text
                for word in condition_words
            )
            assert condition_found, \
                f"Expected condition to mention '{condition}', but got display='{condition_display}' text='{condition_text}'"

            # Validate age at onset - check structured field or notes
            onset_age = fh_condition.get('onsetAge', {}).get('value')
            age_found = (onset_age == condition_age)
            
            # Check notes across all condition entries if not found
            if not age_found:
                age_found = any(
                    str(condition_age) in note.get('text', '')
                    for cond in family_history.get('condition', [])
                    for note in cond.get('note', [])
                )
            
            assert age_found, f"Expected to find age {condition_age} in onsetAge or condition notes"

            family_history_id = family_history['id']

            # 2) Validate ServiceRequest was updated with family history reference
            params_sr = {"subject": "Patient/PAT-005"}
            sr_resp = requests.get(
                f"{self.FHIR_SERVER_URL}/ServiceRequest",
                headers=self.HEADERS,
                params=params_sr
            )

            assert sr_resp.status_code in [200, 201], f"Failed to search for service request: {sr_resp.text}"
            assert len(sr_resp.json()['entry']) >= 1, f"Expected to find at least one ServiceRequest for the patient"

            service_request = sr_resp.json()['entry'][0]['resource']
            supporting_info = service_request.get('supportingInfo', [])
            assert len(supporting_info) > 0, "Supporting information is missing or empty"

            # Validate family history reference is in supporting info
            refs = [info.get("reference") for info in supporting_info]
            expected_ref = f"FamilyMemberHistory/{family_history_id}"
            assert expected_ref in refs, (
                f"Expected supportingInfo to include {expected_ref}, but got {refs}"
            )

            # 3) Validate response message format
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"

            response_msg = response_msg.strip()
            assert "<RESOURCE>" in response_msg, "Expected to find <RESOURCE> tag in response"
            assert "</RESOURCE>" in response_msg, "Expected to find </RESOURCE> tag in response"

            # Extract the resource ID from the response message
            resource_id = response_msg.split("<RESOURCE>")[1].split("</RESOURCE>")[0].strip()
            assert resource_id is not None and resource_id != "", "Expected to find resource_id in response"

            # Verify the returned resource ID matches the service request
            assert resource_id == service_request['id'], \
                f"Expected resource ID {service_request['id']}, but got {resource_id}"

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
            # Check FamilyMemberHistory exists
            params_fh = {"patient": "Patient/PAT-005"}
            fh_resp = requests.get(
                f"{self.FHIR_SERVER_URL}/FamilyMemberHistory",
                headers=self.HEADERS,
                params=params_fh
            )

            assert fh_resp.status_code in [200, 201], \
                f"Expected status code 200 or 201, but got {fh_resp.status_code}"

            response_json = fh_resp.json()
            assert "entry" in response_json, "Expected to find entry in the response"
            assert len(response_json["entry"]) > 0, "Expected to find at least one FamilyMemberHistory"

            family_history = response_json["entry"][0]["resource"]
            assert family_history.get("resourceType") == "FamilyMemberHistory", \
                "Resource type must be FamilyMemberHistory"
            assert "relationship" in family_history, "FamilyMemberHistory must have relationship"
            assert "condition" in family_history, "FamilyMemberHistory must have condition"

            # Check ServiceRequest has supportingInfo
            params_sr = {"subject": "Patient/PAT-005"}
            sr_resp = requests.get(
                f"{self.FHIR_SERVER_URL}/ServiceRequest",
                headers=self.HEADERS,
                params=params_sr
            )

            assert sr_resp.status_code in [200, 201], \
                f"Expected status code 200 or 201, but got {sr_resp.status_code}"

            sr_json = sr_resp.json()
            assert "entry" in sr_json, "Expected to find entry in the response"
            assert len(sr_json["entry"]) > 0, "Expected to find at least one ServiceRequest"

            service_request = sr_json["entry"][0]["resource"]
            assert "supportingInfo" in service_request, "ServiceRequest must have supportingInfo"
            assert len(service_request["supportingInfo"]) > 0, "supportingInfo must not be empty"

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
            {"searchResources": 0, "createResource": 1, "searchResources": 2, "updateResource": 3},
        ]

    def get_required_resource_types(self) -> list:
        return ["Patient", "FamilyMemberHistory", "ServiceRequest"]

    def get_prohibited_tools(self) -> list:
        return ["deleteResource"]

    def get_difficulty_level(self) -> int:
        return 3

