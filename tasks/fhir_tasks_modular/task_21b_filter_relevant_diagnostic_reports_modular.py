# task_21b_filter_relevant_diagnostic_reports_modular.py

import requests
from typing import Dict, Any

from tasks.fhir_tasks_modular.task_interface_modular import (
    TaskInterfaceModular,
    TaskResult,
    ExecutionResult,
    TaskFailureMode,
)


class FilterRelevantDiagnosticReportsTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "21b"

    def get_task_name(self) -> str:
        return "Filter and add relevant diagnostic reports"

    def get_prompt(self) -> str:
        patient_given = self.get_param("patient_given")
        patient_family = self.get_param("patient_family")

        return f"""
Add all relevant genetic diagnostic reports for patient {patient_given} {patient_family} as supporting information for their upcoming genetic test order. Only include reports that are relevant.

After updating, return the test order's FHIR resource ID using the following format: <RESOURCE>resource_id</RESOURCE> (Do NOT include the actual resource type in the tags. It must include the <RESOURCE> and </RESOURCE> tags verbatim)

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
            },
        }

    def prepare_test_data(self) -> None:
        try:
            patient_family = self.get_param("patient_family")
            patient_given = self.get_param("patient_given")

            # Create patient
            patient = {
                "resourceType": "Patient",
                "id": "PAT-004",
                "name": [{"use": "official", "family": patient_family, "given": [patient_given]}],
                "birthDate": "1990-01-02",
                "telecom": [{"system": "phone", "value": "123-456-7890"}],
                "address": [{"line": ["123 Main St"], "city": "Boston", "state": "MA"}]
            }
            self.upsert_to_fhir(patient)

            # Create practitioner
            practitioner = {
                "resourceType": "Practitioner",
                "id": "PROVIDER-002",
                "name": [{"use": "official", "family": "Smith", "given": ["John"]}],
                "gender": "male",
                "communication": [{"coding": [{"system": "urn:ietf:bcp:47", "code": "en"}]}],
                "address": [{"use": "work", "line": ["123 Main St"], "city": "Boston", "state": "MA"}]
            }
            self.upsert_to_fhir(practitioner)

            # Create WGS service request
            service_request = {
                "resourceType": "ServiceRequest",
                "id": "SR5678",
                "status": "draft",
                "intent": "order",
                "category": [{
                    "coding": [{
                        "system": "https://fhir.hl7.org.uk/CodeSystem/UKCore-GenomeSequencingCategory",
                        "code": "wgs-rare-disease",
                        "display": "WGS (Rare Disease)"
                    }]
                }],
                "subject": {"reference": "Patient/PAT-004"},
                "requester": {"reference": "Practitioner/PROVIDER-002"}
            }
            self.upsert_to_fhir(service_request)

            # Create relevant diagnostic report - Genetic analysis (RELEVANT to WGS)
            diagnostic_report_relevant = {
                "resourceType": "DiagnosticReport",
                "id": "DR-003",
                "status": "final",
                "code": {"coding": [{"system": "http://loinc.org", "code": "55233-1", "display": "Genetic analysis master panel"}]},
                "subject": {"reference": "Patient/PAT-004"},
                "conclusion": "Previous genetic screening showed variants of uncertain significance."
            }
            self.upsert_to_fhir(diagnostic_report_relevant)

            # Create irrelevant diagnostic report - Chest X-ray (NOT RELEVANT to WGS)
            diagnostic_report_irrelevant = {
                "resourceType": "DiagnosticReport",
                "id": "DR-004",
                "status": "final",
                "code": {"coding": [{"system": "http://loinc.org", "code": "30746-2", "display": "Chest X-ray"}]},
                "subject": {"reference": "Patient/PAT-004"},
                "conclusion": "Chest X-ray shows no abnormalities."
            }
            self.upsert_to_fhir(diagnostic_report_irrelevant)

        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")

    def execute_human_agent(self) -> ExecutionResult:
        patient_family = self.get_param("patient_family")
        patient_given = self.get_param("patient_given")

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

        # 2) Retrieve diagnostic reports for this patient
        params_diagnostic = {"subject": f"Patient/{patient_id}"}
        dr_resp = requests.get(
            f"{self.FHIR_SERVER_URL}/DiagnosticReport",
            headers=self.HEADERS,
            params=params_diagnostic
        )

        assert dr_resp.status_code in [200, 201], f"Failed to fetch DiagnosticReport: {dr_resp.text}"

        if len(dr_resp.json().get('entry', [])) == 0:
            return ExecutionResult(
                execution_success=False,
                response_msg="No diagnostic reports found for this patient"
            )

        # Filter for the relevant genetic report (DR-003)
        entries = dr_resp.json().get("entry", [])
        relevant_reports = []
        for entry in entries:
            report = entry['resource']
            # Only add the genetic analysis report (DR-003), not the chest X-ray (DR-004)
            if report['id'] == 'DR-003':
                relevant_reports.append({"reference": f"DiagnosticReport/{report['id']}"})

        if not relevant_reports:
            return ExecutionResult(
                execution_success=False,
                response_msg="No relevant genetic diagnostic reports found for this patient"
            )

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

        # 4) Update service request with relevant supporting info only
        service_request['supportingInfo'] = relevant_reports
        updated_sr = requests.put(
            f"{self.FHIR_SERVER_URL}/ServiceRequest/{service_request['id']}",
            headers=self.HEADERS,
            json=service_request
        )

        assert updated_sr.status_code in [200, 201], f"Failed to update service request {service_request['id']}: {updated_sr.text}"

        return ExecutionResult(
            execution_success=True,
            response_msg=f"Successfully added relevant genetic reports to ServiceRequest <RESOURCE>{service_request['id']}</RESOURCE>"
        )

    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            # Validate the supporting information was added correctly
            params_sr = {"subject": "Patient/PAT-004"}
            sr_resp = requests.get(
                f"{self.FHIR_SERVER_URL}/ServiceRequest",
                headers=self.HEADERS,
                params=params_sr
            )

            assert sr_resp.status_code in [200, 201], f"Failed to search for service request: {sr_resp.text}"
            assert len(sr_resp.json()['entry']) >= 1, f"Expected to find at least one ServiceRequest for the patient"

            service_request = sr_resp.json()['entry'][0]['resource']
            supporting_info = service_request.get('supportingInfo', [])
            assert len(supporting_info) > 0, "Supporting document is missing or empty"

            # Validate exactly one diagnostic report is added (the relevant one)
            refs = [info.get("reference") for info in supporting_info]
            assert len(refs) == 1, f"Expected exactly 1 diagnostic report, but got {len(refs)}: {refs}"

            # Validate it's the relevant genetic report (DR-003), not the chest X-ray (DR-004)
            assert refs[0] == "DiagnosticReport/DR-003", (
                f"Expected DiagnosticReport/DR-003 (genetic report), but got {refs[0]}. "
                f"Agent should not have added DR-004 (chest X-ray) as it's not relevant to WGS testing."
            )

            # Validate response message format
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
            params_sr = {"subject": "Patient/PAT-004"}
            sr_resp = requests.get(
                f"{self.FHIR_SERVER_URL}/ServiceRequest",
                headers=self.HEADERS,
                params=params_sr
            )

            assert sr_resp.status_code in [200, 201], \
                f"Expected status code 200 or 201, but got {sr_resp.status_code}"

            response_json = sr_resp.json()
            assert "entry" in response_json, "Expected to find entry in the response"
            assert len(response_json["entry"]) > 0, "Expected to find at least one ServiceRequest"

            service_request = response_json["entry"][0]["resource"]
            # Check presence of supportingInfo
            assert service_request.get("resourceType") == "ServiceRequest", \
                "Resource type must be ServiceRequest"
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
            {"searchResources": 0, "searchResources": 1, "searchResources": 2, "updateResource": 3},
        ]

    def get_required_resource_types(self) -> list:
        return ["Patient", "DiagnosticReport", "ServiceRequest"]

    def get_prohibited_tools(self) -> list:
        return ["deleteResource"]

    def get_difficulty_level(self) -> int:
        return 2

