# task_16b_move_patient_out_of_waitlist_modular.py

import os
import time
import requests
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from tasks.fhir_tasks_modular.task_interface_modular import TaskInterfaceModular, TaskResult, ExecutionResult, TaskFailureMode


class MovePatientOutOfWaitlistTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "16b"

    def get_task_name(self) -> str:
        return "Move Patient Out of Waitlist"

    def get_prompt(self) -> str:
        patient_family = self.get_param("patient_family")
        patient_given = self.get_param("patient_given")
        practitioner_family = self.get_param("practitioner_family")
        practitioner_given = self.get_param("practitioner_given")
        return f"""
    Move patient {' '.join(patient_given)} {patient_family} (with id PAT001) out of the waitlist by booking them into an available slot within the waitlist appointment's requested window with Dr. {' '.join(practitioner_given)} {practitioner_family}. 
    If an appointment with the same patient and practitioner already exists, book them into that appointment with the necessary changes.
    After moving, return the appointment ID and slot ID using the following format:
    <APPOINTMENT>appointment_id</APPOINTMENT>
    <SLOT_ID>slot_id</SLOT_ID>
"""

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_family", "patient_given", "practitioner_family", "practitioner_given"],
            "properties": {
                "patient_family": {
                    "type": "string",
                    "description": "Family name of the patient",
                    "examples": ["Doe", "Smith", "Johnson"],
                    "default": "Doe",
                },
                "patient_given": {
                    "type": "array",
                    "description": "Given names of the patient",
                    "items": {"type": "string"},
                    "examples": [["John"], ["Jane"], ["Mike"]],
                    "default": ["John"],
                },
                "patient_birth_date": {
                    "type": "string",
                    "description": "Birth date of the patient (YYYY-MM-DD format)",
                    "examples": ["1990-06-15", "1985-03-22", "1995-12-10"],
                    "default": "1990-06-15",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                },
                "patient_phone": {
                    "type": "string",
                    "description": "Phone number of the patient",
                    "examples": ["123-456-7890", "555-123-4567"],
                    "default": "123-456-7890",
                },
                "practitioner_family": {
                    "type": "string",
                    "description": "Family name of the practitioner",
                    "examples": ["Smith", "Johnson", "Williams"],
                    "default": "Smith",
                },
                "practitioner_given": {
                    "type": "array",
                    "description": "Given names of the practitioner",
                    "items": {"type": "string"},
                    "examples": [["John"], ["Sarah"], ["Michael"]],
                    "default": ["John"],
                },
                "practitioner_gender": {
                    "type": "string",
                    "description": "Gender of the practitioner",
                    "examples": ["male", "female"],
                    "default": "male",
                    "enum": ["male", "female", "other", "unknown"],
                },
                "waitlist_start_days": {
                    "type": "integer",
                    "description": "Days from now to start the waitlist period",
                    "examples": [1, 2, 3],
                    "default": 1,
                    "minimum": 0,
                    "maximum": 30,
                },
                "waitlist_duration_days": {
                    "type": "integer",
                    "description": "Duration of the waitlist period in days",
                    "examples": [5, 6, 7],
                    "default": 6,
                    "minimum": 1,
                    "maximum": 30,
                },
                "slot_creation_days": {
                    "type": "integer",
                    "description": "Number of days ahead to create slots for",
                    "examples": [7, 14, 21],
                    "default": 14,
                    "minimum": 7,
                    "maximum": 30,
                },
                "slot_start_hour": {
                    "type": "integer",
                    "description": "Starting hour for slot creation (24-hour format)",
                    "examples": [8, 9, 10],
                    "default": 9,
                    "minimum": 0,
                    "maximum": 23,
                },
                "slot_end_hour": {
                    "type": "integer",
                    "description": "Ending hour for slot creation (24-hour format)",
                    "examples": [11, 12, 13],
                    "default": 12,
                    "minimum": 0,
                    "maximum": 23,
                },
                "busy_slots_days": {
                    "type": "integer",
                    "description": "Number of days from now where slots are marked as busy",
                    "examples": [5, 7, 10],
                    "default": 7,
                    "minimum": 0,
                    "maximum": 30,
                },
                "weekdays_only": {
                    "type": "boolean",
                    "description": "Whether to create slots only on weekdays",
                    "examples": [True, False],
                    "default": True,
                },
                "specialty_code": {
                    "type": "string",
                    "description": "SNOMED CT code for the practitioner's specialty",
                    "examples": ["394580004", "408459003"],
                    "default": "394580004",
                },
                "specialty_display": {
                    "type": "string",
                    "description": "Display name for the practitioner's specialty",
                    "examples": ["Clinical genetics", "Pediatric cardiology"],
                    "default": "Clinical genetics",
                },
                "address_line": {
                    "type": "string",
                    "description": "Address line for practitioners and patients",
                    "examples": ["123 Main St", "456 Oak Ave"],
                    "default": "123 Main St",
                },
                "address_city": {
                    "type": "string",
                    "description": "City for practitioners and patients",
                    "examples": ["Boston", "New York", "Los Angeles"],
                    "default": "Boston",
                },
                "address_state": {
                    "type": "string",
                    "description": "State for practitioners and patients",
                    "examples": ["MA", "NY", "CA"],
                    "default": "MA",
                },
            },
        }



    def prepare_test_data(self) -> None:
        try:
            patient_family = self.get_param("patient_family")
            patient_given = self.get_param("patient_given")
            patient_birth_date = self.get_param("patient_birth_date", "1990-06-15")
            patient_phone = self.get_param("patient_phone", "123-456-7890")
            practitioner_family = self.get_param("practitioner_family")
            practitioner_given = self.get_param("practitioner_given")
            practitioner_gender = self.get_param("practitioner_gender", "male")
            waitlist_start_days = self.get_param("waitlist_start_days", 1)
            waitlist_duration_days = self.get_param("waitlist_duration_days", 6)
            slot_creation_days = self.get_param("slot_creation_days", 14)
            slot_start_hour = self.get_param("slot_start_hour", 9)
            slot_end_hour = self.get_param("slot_end_hour", 12)
            busy_slots_days = self.get_param("busy_slots_days", 7)
            weekdays_only = self.get_param("weekdays_only", True)
            specialty_code = self.get_param("specialty_code", "394580004")
            specialty_display = self.get_param("specialty_display", "Clinical genetics")
            address_line = self.get_param("address_line", "123 Main St")
            address_city = self.get_param("address_city", "Boston")
            address_state = self.get_param("address_state", "MA")

            # Create patient
            patient1 = {
                "resourceType": "Patient",
                "id": "PAT001",
                "name": [{"use": "official", "family": patient_family, "given": patient_given}],
                "birthDate": patient_birth_date,
                "telecom": [{"system": "phone", "value": patient_phone}],
                "address": [{"line": [address_line], "city": address_city, "state": address_state}]
            }
            self.upsert_to_fhir(patient1)

            # Create practitioner
            practitioner1 = {
                "resourceType": "Practitioner",
                "id": "PROVIDER001",
                "name": [{"use": "official", "family": practitioner_family, "given": practitioner_given}],
                "gender": practitioner_gender,
                "communication": [{"coding": [{"system": "urn:ietf:bcp:47", "code": "en"}]}],
                "address": [{"use": "work", "line": [address_line], "city": address_city, "state": address_state}],
            }
            self.upsert_to_fhir(practitioner1)

            # Create schedule
            start = datetime.now(timezone.utc)
            end = start + timedelta(days=365)
            schedule1 = {
                "resourceType": "Schedule",
                "id": "SCHEDULE001",
                "actor": [{"reference": "Practitioner/PROVIDER001"}],
                "planningHorizon": {
                    "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": end.strftime("%Y-%m-%dT%H:%M:%SZ")
                },
                "specialty": [{"coding": [{"system": "http://snomed.info/sct", "code": specialty_code, "display": specialty_display}]}],
            }
            self.upsert_to_fhir(schedule1)

            # Create slots for specified days ahead, specified hours only
            j = 1
            for x in range(1, slot_creation_days):
                for i in range(slot_start_hour, slot_end_hour):
                    start_time = datetime.now(timezone.utc) + timedelta(days=x)
                    start_time = start_time.replace(hour=i, minute=0, second=0, microsecond=0)
                    if weekdays_only and start_time.weekday() >= 5:  # Skip weekends based on slot date
                        continue
                    end_time = start_time + timedelta(hours=1)

                    # First N days are busy, rest are free
                    status = "busy" if x < busy_slots_days else "free"

                    slot = {
                        "resourceType": "Slot",
                        "id": f"SLOT00{j}",
                        "schedule": {"reference": "Schedule/SCHEDULE001"},
                        "start": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "end": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "status": status
                    }
                    self.upsert_to_fhir(slot)
                    j += 1

            # Create a waitlist appointment
            start = datetime.now(timezone.utc) + timedelta(days=waitlist_start_days)
            start = start.replace(hour=slot_start_hour, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=waitlist_duration_days)
            waitlist_appointment = {
                "resourceType": "Appointment",
                "id": "APPOINTMENT001",
                "status": "waitlist",
                "participant": [
                    {"actor": {"reference": "Patient/PAT001"}, "status": "accepted"},
                    {"actor": {"reference": "Practitioner/PROVIDER001"}, "status": "accepted"}
                ],
                "requestedPeriod": [{
                    "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": end.strftime("%Y-%m-%dT%H:%M:%SZ")
                }]
            }
            self.upsert_to_fhir(waitlist_appointment)
            time.sleep(60)  # hot fix for https://github.com/stormliucong/RESCUE-n8n/issues/77
            
            # make the SLOT002 10am slots free
            slot002 = requests.get(f"{self.FHIR_SERVER_URL}/Slot/SLOT002", headers=self.HEADERS)
            slot002 = slot002.json()
            slot002['status'] = 'free'
            response = requests.put(f"{self.FHIR_SERVER_URL}/Slot/SLOT002", headers=self.HEADERS, json=slot002)            
            assert response.status_code in [200, 201], f"Expected status code 200 or 201, but got {response.status_code}. Response body: {response.text}"

        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")



    def execute_human_agent(self) -> ExecutionResult:
        # Find the waitlist appointment (polling)
        params = {
            "patient": "Patient/PAT001",
            "status": "waitlist",
        }
        wait_s = 0
        waitlist_appointment = None
        while wait_s <= 30:
            response = requests.get(f"{self.FHIR_SERVER_URL}/Appointment", headers=self.HEADERS, params=params)
            assert response.status_code in [200, 201], f"Expected status code 200 or 201, but got {response.status_code}. Response body: {response.text}"
            data = response.json()
            entries = data.get("entry", [])
            if entries:
                chosen = None
                for e in entries:
                    if e.get("resource", {}).get("id") == "APPOINTMENT001":
                        chosen = e["resource"]
                        break
                waitlist_appointment = chosen or entries[0]["resource"]
                break
            time.sleep(2)
            wait_s += 2
        assert waitlist_appointment is not None, "Expected to find exactly one waitlist appointment"
        
        # Find an available slot within the requested period
        start_date = datetime.strptime(waitlist_appointment['requestedPeriod'][0]['start'], "%Y-%m-%dT%H:%M:%SZ")
        end_date = datetime.strptime(waitlist_appointment['requestedPeriod'][0]['end'], "%Y-%m-%dT%H:%M:%SZ")
       
        params = {
            "schedule": "Schedule/SCHEDULE001",
            "status": "free",
            "start": [f'gt{start_date.strftime("%Y-%m-%dT%H:%M:%SZ")}', f'lt{end_date.strftime("%Y-%m-%dT%H:%M:%SZ")}'],
        }        
        response = requests.get(f"{self.FHIR_SERVER_URL}/Slot", headers=self.HEADERS, params=params)
        assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}. Response body: {response.text}"
        assert 'entry' in response.json(), "Expected to find available slots"
        
        # Get the first available slot
        available_slot = response.json()['entry'][0]['resource']
        
        # Update the slot status to busy
        available_slot['status'] = 'busy'
        response = requests.put(f"{self.FHIR_SERVER_URL}/Slot/{available_slot['id']}", headers=self.HEADERS, json=available_slot)
        assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}. Response body: {response.text}"
        
        # Update the appointment to booked status and link it to the slot
        waitlist_appointment['status'] = 'booked'
        waitlist_appointment['slot'] = [{"reference": f"Slot/{available_slot['id']}"}]
        waitlist_appointment['start'] = available_slot['start']  # Only proposed or cancelled appointments can be missing start/end dates
        waitlist_appointment['end'] = available_slot['end']
        del waitlist_appointment['requestedPeriod']
        
        response = requests.put(f"{self.FHIR_SERVER_URL}/Appointment/{waitlist_appointment['id']}", headers=self.HEADERS, json=waitlist_appointment)
        assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}. Response body: {response.text}"
        
        # Additional logic
        appointment_id = waitlist_appointment['id']
        slot_id = available_slot['id']
        return ExecutionResult(
            execution_success=True,
            response_msg=(
                f"Successfully moved patient from waitlist to booked appointment "
                f"<APPOINTMENT>{appointment_id}</APPOINTMENT> with slot "
                f"<SLOT_ID>{slot_id}</SLOT_ID>"
            )
        )


    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            # Verify that there are no waitlist appointments
            params = {
                "patient": "Patient/PAT001",
                "status": "waitlist",
            }
            response = requests.get(f"{self.FHIR_SERVER_URL}/Appointment", headers=self.HEADERS, params=params)
            assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}. Response body: {response.text}"
            
            # verify that the waitlist appointment is not in the response
            if 'entry' in response.json():
                for entry in response.json()['entry']:
                    if entry['resource']['id'] == 'APPOINTMENT001':
                        assert entry['resource']['status'] == 'booked', "Expected waitlist appointment to be booked"
            
            # Parse agent output and verify the specific appointment is booked
            response_msg = execution_result.response_msg.strip()
            assert "<APPOINTMENT>" in response_msg and "</APPOINTMENT>" in response_msg, "Missing <APPOINTMENT> tag"
            assert "<SLOT_ID>" in response_msg and "</SLOT_ID>" in response_msg, "Missing <SLOT_ID> tag"
            appointment_id = response_msg.split("<APPOINTMENT>")[1].split("</APPOINTMENT>")[0]
            slot_id = response_msg.split("<SLOT_ID>")[1].split("</SLOT_ID>")[0]

            # Poll appointment by ID until status becomes 'booked' (handles indexing/consistency lag)
            waited = 0
            appt_resp = None
            while waited <= 30:
                appt_resp = requests.get(f"{self.FHIR_SERVER_URL}/Appointment/{appointment_id}", headers=self.HEADERS)
                if appt_resp.status_code == 200 and appt_resp.json().get("status") == "booked":
                    break
                time.sleep(2)
                waited += 2
            assert appt_resp is not None and appt_resp.status_code == 200, f"Appointment {appointment_id} not found"
            appointment = appt_resp.json()
            assert appointment.get('status') == 'booked', "Expected appointment status to be 'booked'"
            assert appointment['participant'][0]['actor']['reference'] == 'Patient/PAT001', "Expected patient to be PAT001"
            assert appointment['participant'][1]['actor']['reference'] == 'Practitioner/PROVIDER001', "Expected practitioner to be PROVIDER001"
            assert 'slot' in appointment, "Expected appointment to have a slot"
            assert "start" in appointment, "Expected appointment to have a start time"
            assert "end" in appointment, "Expected appointment to have an end time"

            # Additional logic
            response_msg = execution_result.response_msg.strip()
            assert "<APPOINTMENT>" in response_msg and "</APPOINTMENT>" in response_msg, "Missing <APPOINTMENT> tag"
            assert "<SLOT_ID>" in response_msg and "</SLOT_ID>" in response_msg, "Missing <SLOT_ID> tag"

            appointment_id = response_msg.split("<APPOINTMENT>")[1].split("</APPOINTMENT>")[0]
            slot_id = response_msg.split("<SLOT_ID>")[1].split("</SLOT_ID>")[0]

            # Verify appointment is booked
            appt_resp = requests.get(f"{self.FHIR_SERVER_URL}/Appointment/{appointment_id}", headers=self.HEADERS)
            assert appt_resp.status_code == 200 and appt_resp.json().get("status") == "booked", f"Appointment {appointment_id} not booked"

            # Verify slot is busy
            slot_resp = requests.get(f"{self.FHIR_SERVER_URL}/Slot/{slot_id}", headers=self.HEADERS)
            assert slot_resp.status_code == 200 and slot_resp.json().get("status") == "busy", f"Slot {slot_id} not busy"
            
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
            # Verify that there are no waitlist appointments
            params = {
                "patient": "Patient/PAT001",
                "status": "waitlist",
            }
            response = requests.get(f"{self.FHIR_SERVER_URL}/Appointment", headers=self.HEADERS, params=params)
            assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}. Response body: {response.text}"
            
            # verify that the waitlist appointment is not in the response (or is booked if present)
            if 'entry' in response.json():
                for entry in response.json()['entry']:
                    if entry['resource']['id'] == 'APPOINTMENT001':
                        assert entry['resource'].get('status'), "Expected appointment to have status"
            
            # Parse agent output and verify the specific appointment exists
            response_msg = execution_result.response_msg.strip()
            assert "<APPOINTMENT>" in response_msg and "</APPOINTMENT>" in response_msg, "Missing <APPOINTMENT> tag"
            assert "<SLOT_ID>" in response_msg and "</SLOT_ID>" in response_msg, "Missing <SLOT_ID> tag"
            appointment_id = response_msg.split("<APPOINTMENT>")[1].split("</APPOINTMENT>")[0]
            slot_id = response_msg.split("<SLOT_ID>")[1].split("</SLOT_ID>")[0]

            # Poll appointment by ID until it exists (handles indexing/consistency lag)
            waited = 0
            appt_resp = None
            while waited <= 30:
                appt_resp = requests.get(f"{self.FHIR_SERVER_URL}/Appointment/{appointment_id}", headers=self.HEADERS)
                if appt_resp.status_code == 200 and appt_resp.json().get("status"):
                    break
                time.sleep(2)
                waited += 2
            assert appt_resp is not None and appt_resp.status_code == 200, f"Appointment {appointment_id} not found"
            appointment = appt_resp.json()
            assert appointment.get('status'), "Expected appointment to have status"
            assert appointment.get('participant'), "Expected appointment to have participant"
            assert len(appointment['participant']) >= 2, "Expected at least 2 participants"
            assert appointment['participant'][0].get('actor', {}).get('reference'), "Expected first participant to have actor reference"
            assert appointment['participant'][1].get('actor', {}).get('reference'), "Expected second participant to have actor reference"
            assert appointment.get('slot'), "Expected appointment to have a slot"
            assert appointment.get("start"), "Expected appointment to have a start time"
            assert appointment.get("end"), "Expected appointment to have an end time"

            # Additional logic - verify tags
            response_msg = execution_result.response_msg.strip()
            assert "<APPOINTMENT>" in response_msg and "</APPOINTMENT>" in response_msg, "Missing <APPOINTMENT> tag"
            assert "<SLOT_ID>" in response_msg and "</SLOT_ID>" in response_msg, "Missing <SLOT_ID> tag"

            appointment_id = response_msg.split("<APPOINTMENT>")[1].split("</APPOINTMENT>")[0]
            slot_id = response_msg.split("<SLOT_ID>")[1].split("</SLOT_ID>")[0]

            # Verify appointment exists and has status
            appt_resp = requests.get(f"{self.FHIR_SERVER_URL}/Appointment/{appointment_id}", headers=self.HEADERS)
            assert appt_resp.status_code == 200, f"Appointment {appointment_id} not found"
            assert appt_resp.json().get("status"), f"Appointment {appointment_id} must have status"

            # Verify slot exists and has status
            slot_resp = requests.get(f"{self.FHIR_SERVER_URL}/Slot/{slot_id}", headers=self.HEADERS)
            assert slot_resp.status_code == 200, f"Slot {slot_id} not found"
            assert slot_resp.json().get("status"), f"Slot {slot_id} must have status"
            
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
            {"searchResources": 0, "searchResources": 1, "getResourceById": 2, "updateResource": 3, "updateResource": 4},
            {"searchResources": 0, "searchResources": 1, "updateResource": 2, "updateResource": 3},
            {"searchResources": 0, "getResourceById": 1, "updateResource": 2, "updateResource": 3},
            {"searchResources": 0, "getResourceById": 1, "updateResource": 2, "getResourceById": 3, "updateResource": 4},
            {"searchResources": 0, "createResource": 1, "searchResources": 2, "updateResource": 3, "updateResource": 4},
        ]

    def get_required_resource_types(self) -> list:
        return ["Appointment", "Slot"]

    def get_prohibited_tools(self) -> list:
        return []

    def get_difficulty_level(self) -> int:
        return 3
