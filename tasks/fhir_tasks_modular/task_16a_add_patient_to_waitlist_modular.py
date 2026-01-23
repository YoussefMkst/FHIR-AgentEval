# task_16a_add_patient_to_waitlist_modular.py

import os
import time
import requests
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from tasks.fhir_tasks_modular.task_interface_modular import TaskInterfaceModular, TaskResult, ExecutionResult, TaskFailureMode


class AddPatientToWaitlistTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "16a"

    def get_task_name(self) -> str:
        return "Add Patient to Waitlist"

    def get_prompt(self) -> str:
        patient_family = self.get_param("patient_family")
        patient_given = self.get_param("patient_given")
        practitioner_family = self.get_param("practitioner_family")
        practitioner_given = self.get_param("practitioner_given")
        waitlist_start_days = self.get_param("waitlist_start_days", 1)
        waitlist_duration_days = self.get_param("waitlist_duration_days", 6)
        # return f"""
        # Patient {' '.join(patient_given)} {patient_family} id=PAT001 wants an earlier time with Dr. {' '.join(practitioner_given)} {practitioner_family}. Add them to the waitlist.
        # After adding, return the new waitlist Appointment ID using the following format: <APPOINTMENT>appointment_id</APPOINTMENT>
        # """
        return f"""
        Patient {' '.join(patient_given)} {patient_family} id=PAT001 wants an earlier time with Dr. {' '.join(practitioner_given)} {practitioner_family}; add them to the waitlist for a window starting 
        in {waitlist_start_days} days and lasting {waitlist_duration_days} days.
        After adding, return the new waitlist Appointment ID using the following format: <APPOINTMENT>appointment_id</APPOINTMENT>
        """





    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_family", "patient_given", "practitioner_family", "practitioner_given", "waitlist_start_days", "waitlist_duration_days"],
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
            for x in range(slot_creation_days):
                for i in range(slot_start_hour, slot_end_hour):
                    # Check if we should create slots for this day
                    if weekdays_only and datetime.now(timezone.utc).weekday() >= 5:  # Skip weekends
                        continue
                    
                    start_time = datetime.now(timezone.utc) + timedelta(days=x)
                    start_time = start_time.replace(hour=i, minute=0, second=0, microsecond=0)
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

        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")



    def execute_human_agent(self) -> ExecutionResult:
        waitlist_start_days = self.get_param("waitlist_start_days")
        waitlist_duration_days = self.get_param("waitlist_duration_days")
        appointment_id = self.get_param("appointment_id", "APPOINTMENT001")
        # Create waitlist appointment
        start = datetime.now(timezone.utc) + timedelta(days=waitlist_start_days)
        end = datetime.now(timezone.utc) + timedelta(days=waitlist_start_days + waitlist_duration_days)
        
        params = {
            "resourceType": "Appointment",
            "id": appointment_id,
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
        # changed from post to put
        response = requests.put(f"{self.FHIR_SERVER_URL}/Appointment/{appointment_id}", headers=self.HEADERS, json=params)
        assert response.status_code == 201 or response.status_code == 200, f"Expected status code 201 or 200, but got {response.status_code}. Response body: {response.text}"
        
        # Additional logic
        appointment_id = response.json().get('id')
        return ExecutionResult(
            execution_success=True,
            response_msg=f"Successfully added patient to waitlist: <APPOINTMENT>{appointment_id}</APPOINTMENT>"
        )



    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            # Verify that the waitlist appointment exists
            params = {
                "patient": "Patient/PAT001",
                "status": "waitlist",
            }
            response = requests.get(f"{self.FHIR_SERVER_URL}/Appointment", headers=self.HEADERS, params=params)
            assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}. Response body: {response.text}"
            assert 'entry' in response.json(), "Expected to find the waitlist appointment"
            assert len(response.json()['entry']) == 1, "Expected to find exactly one waitlist appointment"
            
            # Verify the appointment details
            appointment = response.json()['entry'][0]['resource']
            assert appointment['status'] == 'waitlist', "Expected appointment status to be 'waitlist'"
            assert appointment['participant'][0]['actor']['reference'] == 'Patient/PAT001', "Expected patient to be PAT001"
            assert appointment['participant'][1]['actor']['reference'] == 'Practitioner/PROVIDER001', "Expected practitioner to be PROVIDER001"
            
            # Verify the requested period
            waitlist_start_days = self.get_param("waitlist_start_days")
            waitlist_duration_days = self.get_param("waitlist_duration_days")

            start_date = datetime.strptime(appointment['requestedPeriod'][0]['start'], "%Y-%m-%dT%H:%M:%SZ")
            end_date = datetime.strptime(appointment['requestedPeriod'][0]['end'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            assert end_date <= datetime.now(timezone.utc) + timedelta(days=waitlist_start_days + waitlist_duration_days), f"Expected end date to be within {waitlist_start_days + waitlist_duration_days} days"

            # Additional logic
            response_msg = execution_result.response_msg.strip()
            assert "<APPOINTMENT>" in response_msg and "</APPOINTMENT>" in response_msg, "Missing <APPOINTMENT> tag"
            appointment_id = response_msg.split("<APPOINTMENT>")[1].split("</APPOINTMENT>")[0]
            # Verify the Appointment resource exists and is on the waitlist
            appt_resp = requests.get(f"{self.FHIR_SERVER_URL}/Appointment/{appointment_id}", headers=self.HEADERS)
            assert appt_resp.status_code == 200 and appt_resp.json().get("status") == "waitlist", f"Appointment {appointment_id} not on waitlist"

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
            # Verify that the waitlist appointment exists
            params = {
                "patient": "Patient/PAT001",
                "status": "waitlist",
            }
            response = requests.get(f"{self.FHIR_SERVER_URL}/Appointment", headers=self.HEADERS, params=params)
            assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}. Response body: {response.text}"
            assert 'entry' in response.json(), "Expected to find the waitlist appointment"
            assert len(response.json()['entry']) == 1, "Expected to find exactly one waitlist appointment"
            
            # Verify the appointment has required fields (not checking specific values)
            appointment = response.json()['entry'][0]['resource']
            assert appointment.get('status'), "Expected appointment to have status"
            assert appointment.get('participant'), "Expected appointment to have participant"
            assert len(appointment['participant']) >= 2, "Expected at least 2 participants"
            assert appointment['participant'][0].get('actor', {}).get('reference'), "Expected first participant to have actor reference"
            assert appointment['participant'][1].get('actor', {}).get('reference'), "Expected second participant to have actor reference"
            
            # Verify the requested period exists
            assert appointment.get('requestedPeriod'), "Expected appointment to have requestedPeriod"
            assert len(appointment['requestedPeriod']) > 0, "Expected at least one requestedPeriod"
            assert appointment['requestedPeriod'][0].get('start'), "Expected requestedPeriod to have start"
            assert appointment['requestedPeriod'][0].get('end'), "Expected requestedPeriod to have end"

            # Additional logic - check tags exist
            response_msg = execution_result.response_msg.strip()
            assert "<APPOINTMENT>" in response_msg and "</APPOINTMENT>" in response_msg, "Missing <APPOINTMENT> tag"
            appointment_id = response_msg.split("<APPOINTMENT>")[1].split("</APPOINTMENT>")[0]
            
            # Verify the Appointment resource exists and has status
            appt_resp = requests.get(f"{self.FHIR_SERVER_URL}/Appointment/{appointment_id}", headers=self.HEADERS)
            assert appt_resp.status_code == 200, f"Appointment {appointment_id} not found"
            assert appt_resp.json().get("status"), f"Appointment {appointment_id} must have status"

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
            {"createResource": 0},
            {"updateResource": 0},
            {"searchResources": 0, "createResource": 1}
        ]

    def get_required_resource_types(self) -> list:
        return ["Appointment"]

    def get_prohibited_tools(self) -> list:
        return ["deleteResource"]

    def get_difficulty_level(self) -> int:
        return 2
