# task_17b_reschedule_with_another_provider_modular.py

import json
import os
import time
import requests
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from tasks.fhir_tasks_modular.task_interface_modular import ExecutionResult, TaskFailureMode, TaskInterfaceModular, TaskResult

class RescheduleWithAnotherProviderTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "17b"

    def get_task_name(self) -> str:
        return "Reschedule Appointment with Another Provider"

    def get_prompt(self) -> str:
        patient_family = self.get_param("patient_family")
        patient_given = self.get_param("patient_given")
        target_day = self.get_param("target_day")
        target_hour = self.get_param("target_hour")
        return f"""
        Reschedule {' '.join(patient_given)} {patient_family}'s (FHIR Resource ID: PAT001) appointment at next {target_day} {target_hour}am with another provider who has availability at the same time.
        Return the new Appointment ID and Slot ID using:
        <APPOINTMENT>appointment_id</APPOINTMENT>
        <SLOT_ID>slot_id</SLOT_ID>"""


    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_family", "patient_given", "target_day", "target_hour"],
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
                "current_practitioner_family": {
                    "type": "string",
                    "description": "Family name of the current practitioner",
                    "examples": ["Smith", "Johnson", "Williams"],
                    "default": "Smith",
                },
                "current_practitioner_given": {
                    "type": "array",
                    "description": "Given names of the current practitioner",
                    "items": {"type": "string"},
                    "examples": [["John"], ["Sarah"], ["Michael"]],
                    "default": ["John"],
                },
                "current_practitioner_gender": {
                    "type": "string",
                    "description": "Gender of the current practitioner",
                    "examples": ["male", "female"],
                    "default": "male",
                    "enum": ["male", "female", "other", "unknown"],
                },
                "new_practitioner_family": {
                    "type": "string",
                    "description": "Family name of the new practitioner",
                    "examples": ["Johnson", "Williams", "Brown"],
                    "default": "Johnson",
                },
                "new_practitioner_given": {
                    "type": "array",
                    "description": "Given names of the new practitioner",
                    "items": {"type": "string"},
                    "examples": [["Jane"], ["Robert"], ["Lisa"]],
                    "default": ["Jane"],
                },
                "new_practitioner_gender": {
                    "type": "string",
                    "description": "Gender of the new practitioner",
                    "examples": ["female", "male"],
                    "default": "female",
                    "enum": ["male", "female", "other", "unknown"],
                },
                "target_day": {
                    "type": "string",
                    "description": "Target day of the week for rescheduling",
                    "examples": ["Monday", "Tuesday", "Wednesday"],
                    "default": "Monday",
                    "enum": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                },
                "target_hour": {
                    "type": "integer",
                    "description": "Target hour for the rescheduled appointment (24-hour format)",
                    "examples": [9, 10, 14],
                    "default": 9,
                    "minimum": 0,
                    "maximum": 23,
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
                "current_address_line": {
                    "type": "string",
                    "description": "Address line for the current practitioner",
                    "examples": ["123 Main St", "456 Oak Ave"],
                    "default": "123 Main St",
                },
                "current_address_city": {
                    "type": "string",
                    "description": "City for the current practitioner",
                    "examples": ["Boston", "New York", "Los Angeles"],
                    "default": "Boston",
                },
                "current_address_state": {
                    "type": "string",
                    "description": "State for the current practitioner",
                    "examples": ["MA", "NY", "CA"],
                    "default": "MA",
                },
                "new_address_line": {
                    "type": "string",
                    "description": "Address line for the new practitioner",
                    "examples": ["456 Oak St", "789 Pine Ave"],
                    "default": "456 Oak St",
                },
                "new_address_city": {
                    "type": "string",
                    "description": "City for the new practitioner",
                    "examples": ["Boston", "New York", "Los Angeles"],
                    "default": "Boston",
                },
                "new_address_state": {
                    "type": "string",
                    "description": "State for the new practitioner",
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
            current_practitioner_family = self.get_param("current_practitioner_family", "Smith")
            current_practitioner_given = self.get_param("current_practitioner_given", ["John"])
            current_practitioner_gender = self.get_param("current_practitioner_gender", "male")
            new_practitioner_family = self.get_param("new_practitioner_family", "Johnson")
            new_practitioner_given = self.get_param("new_practitioner_given", ["Jane"])
            new_practitioner_gender = self.get_param("new_practitioner_gender", "female")
            target_day = self.get_param("target_day")
            target_hour = self.get_param("target_hour")
            slot_creation_days = self.get_param("slot_creation_days", 14)
            slot_start_hour = self.get_param("slot_start_hour", 9)
            slot_end_hour = self.get_param("slot_end_hour", 12)
            weekdays_only = self.get_param("weekdays_only", False) # ADDED FOR EXPERIMENT 17A_17B
            specialty_code = self.get_param("specialty_code", "394580004")
            specialty_display = self.get_param("specialty_display", "Clinical genetics")
            current_address_line = self.get_param("current_address_line", "123 Main St")
            current_address_city = self.get_param("current_address_city", "Boston")
            current_address_state = self.get_param("current_address_state", "MA")
            new_address_line = self.get_param("new_address_line", "456 Oak St")
            new_address_city = self.get_param("new_address_city", "Boston")
            new_address_state = self.get_param("new_address_state", "MA")

            # Create patient
            patient1 = {
                "resourceType": "Patient",
                "id": "PAT001",
                "name": [{"use": "official", "family": patient_family, "given": patient_given}],
                "birthDate": patient_birth_date,
                "telecom": [{"system": "phone", "value": patient_phone}],
                "address": [{"line": [current_address_line], "city": current_address_city, "state": current_address_state}]
            }
            self.upsert_to_fhir(patient1)

            # Create first practitioner (current provider)
            practitioner1 = {
                "resourceType": "Practitioner",
                "id": "PROVIDER001",
                "name": [{"use": "official", "family": current_practitioner_family, "given": current_practitioner_given}],
                "gender": current_practitioner_gender,
                "communication": [{"coding": [{"system": "urn:ietf:bcp:47", "code": "en"}]}],
                "address": [{"use": "work", "line": [current_address_line], "city": current_address_city, "state": current_address_state}],
            }
            self.upsert_to_fhir(practitioner1)

            # Create second practitioner (new provider)
            practitioner2 = {
                "resourceType": "Practitioner",
                "id": "PROVIDER002",
                "name": [{"use": "official", "family": new_practitioner_family, "given": new_practitioner_given}],
                "gender": new_practitioner_gender,
                "communication": [{"coding": [{"system": "urn:ietf:bcp:47", "code": "en"}]}],
                "address": [{"use": "work", "line": [new_address_line], "city": new_address_city, "state": new_address_state}],
            }
            self.upsert_to_fhir(practitioner2)

            # Create schedule for first practitioner
            start = datetime.now(timezone.utc)
            end = start + timedelta(days=slot_creation_days)
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

            # Create schedule for second practitioner
            schedule2 = {
                "resourceType": "Schedule",
                "id": "SCHEDULE002",
                "actor": [{"reference": "Practitioner/PROVIDER002"}],
                "planningHorizon": {
                    "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": end.strftime("%Y-%m-%dT%H:%M:%SZ")
                },
                "specialty": [{"coding": [{"system": "http://snomed.info/sct", "code": specialty_code, "display": specialty_display}]}],
            }
            self.upsert_to_fhir(schedule2)

            # Create slots for first practitioner (all busy)
            j = 1
            for x in range(slot_creation_days):
                for i in range(slot_start_hour, slot_end_hour):
                    start_time = datetime.now(timezone.utc) + timedelta(days=x)
                    
                    if weekdays_only and start_time.weekday() >= 5:  # Skip weekends
                        continue
                    
                    start_time = start_time.replace(hour=i, minute=0, second=0, microsecond=0)
                    end_time = start_time + timedelta(hours=1)
                    
                    slot = {
                        "resourceType": "Slot",
                        "id": f"SLOT00{j}",
                        "schedule": {"reference": "Schedule/SCHEDULE001"},
                        "start": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "end": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "status": "busy"
                    }
                    self.upsert_to_fhir(slot)
                    j += 1

            # Create slots for second practitioner (all free)
            for x in range(slot_creation_days):
                for i in range(slot_start_hour, slot_end_hour):
                    start_time = datetime.now(timezone.utc) + timedelta(days=x)
                    
                    if weekdays_only and start_time.weekday() >= 5:  # Skip weekends
                        continue
                    
                    start_time = start_time.replace(hour=i, minute=0, second=0, microsecond=0)
                    end_time = start_time + timedelta(hours=1)
                    
                    slot = {
                        "resourceType": "Slot",
                        "id": f"SLOT{j}",
                        "schedule": {"reference": "Schedule/SCHEDULE002"},
                        "start": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "end": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "status": "free"
                    }
                    self.upsert_to_fhir(slot)
                    j += 1

            # Create current appointment with first practitioner at next target day at target hour
            day_mapping = {
                "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
                "Friday": 4, "Saturday": 5, "Sunday": 6
            }
            target_weekday = day_mapping.get(target_day, 0)
            start_time = datetime.now(timezone.utc) + timedelta(days=(target_weekday - datetime.now(timezone.utc).weekday()) % 7)
            start_time = start_time.replace(hour=target_hour, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(hours=1)
            
            # Find current slot with first practitioner at next target day at target hour
            params = {
                "schedule": "Schedule/SCHEDULE001",
                "start": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            response = requests.get(f"{self.FHIR_SERVER_URL}/Slot", headers=self.HEADERS, params=params)
            assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}. Response body: {response.text}"
            current_slot = response.json()['entry'][0]['resource']
            current_slot_id = current_slot['id']

            # First provider declines the appointment
            current_appointment = {
                "resourceType": "Appointment",
                "id": "APPOINTMENT001",
                "status": "proposed",
                "slot": [{"reference": f"Slot/{current_slot_id}"}],
                "participant": [
                    {"actor": {"reference": "Patient/PAT001"}, "status": "accepted"},
                    {"actor": {"reference": "Practitioner/PROVIDER001"}, "status": "declined"}
                ],
                "start": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            self.upsert_to_fhir(current_appointment)

        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")


    def execute_human_agent(self) -> ExecutionResult:
        target_day = self.get_param("target_day", "Monday")
        target_hour = self.get_param("target_hour", 9)
        
        # Find the current appointment at Next target day at target hour.
        day_mapping = {
            "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
            "Friday": 4, "Saturday": 5, "Sunday": 6
        }
        target_weekday = day_mapping.get(target_day, 0)
        start_time = datetime.now(timezone.utc) + timedelta(days=(target_weekday - datetime.now(timezone.utc).weekday()) % 7)
        start_time = start_time.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=1)
        
        params = {
            "patient": "Patient/PAT001",
            "date": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        response = requests.get(f"{self.FHIR_SERVER_URL}/Appointment", headers=self.HEADERS, params=params)
        assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}. Response body: {response.text}"
        assert 'entry' in response.json(), "Expected to find the current appointment"
        assert len(response.json()['entry']) == 1, "Expected to find exactly one appointment"
        current_appointment = [entry['resource'] for entry in response.json()['entry']][0]
        current_slot_start = current_appointment['start']
        
        # Find the schedule reference for the second practitioner
        params = {
            "actor": "Practitioner/PROVIDER002",
        }
        response = requests.get(f"{self.FHIR_SERVER_URL}/Schedule", headers=self.HEADERS, params=params)
        assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}. Response body: {response.text}"
        assert 'entry' in response.json(), "Expected to find the schedule for the second practitioner"  
        assert len(response.json()['entry']) == 1, "Expected to find exactly one schedule for the second practitioner"
        schedule_ref = response.json()['entry'][0]['resource']['id']
        assert schedule_ref == "SCHEDULE002", "Expected schedule reference to be SCHEDULE002"

        # Find an available slot with the second practitioner at the same time
        params = {
            "schedule": f"Schedule/{schedule_ref}",
            "status": "free",
            "start": current_slot_start,
        }
        response = requests.get(f"{self.FHIR_SERVER_URL}/Slot", headers=self.HEADERS, params=params)
        assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}. Response body: {response.text}"
        assert 'entry' in response.json(), "Expected to find available slots"
        assert len(response.json()['entry']) == 1, "Expected to find exactly one available slot"
        new_slot = response.json()['entry'][0]['resource']
        
        # Free the current slot --> newly added. TO BE TESTED.
        current_slot_resp = requests.get(f"{self.FHIR_SERVER_URL}/{current_appointment['slot'][0]['reference']}", headers=self.HEADERS)
        assert current_slot_resp.status_code == 200, f"Failed to read current slot: {current_slot_resp.text}"
        current_slot = current_slot_resp.json()
        current_slot['status'] = 'free'
        resp_free = requests.put(f"{self.FHIR_SERVER_URL}/Slot/{current_slot['id']}", headers=self.HEADERS, json=current_slot)
        assert resp_free.status_code == 200, f"Failed to free current slot: {resp_free.text}"

               
        # Update the new slot to busy
        new_slot['status'] = 'busy'
        response = requests.put(f"{self.FHIR_SERVER_URL}/Slot/{new_slot['id']}", headers=self.HEADERS, json=new_slot)
        assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}. Response body: {response.text}"
        
        # Update the appointment to the new slot and practitioner
        current_appointment['slot'] = [{"reference": f"Slot/{new_slot['id']}"}]
        current_appointment['start'] = new_slot['start']
        current_appointment['end'] = new_slot['end']
        # find ith element in the participant array that has the actor reference of the current provider
        j = 0
        for i, participant in enumerate(current_appointment['participant']):
            if participant['actor']['reference'].startswith("Practitioner"):
                j = i
                break
        current_appointment['participant'][j]['actor']['reference'] = "Practitioner/PROVIDER002"
        #current_appointment['participant'][j]['actor']['status'] = "accepted"
        current_appointment['participant'][j]['status'] = "accepted" # added this to TEST.
        current_appointment['status'] = 'booked'
        
        response = requests.put(f"{self.FHIR_SERVER_URL}/Appointment/{current_appointment['id']}", headers=self.HEADERS, json=current_appointment)
        assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}. Response body: {response.text}"

        # Additional logic
        appointment_id = current_appointment['id']
        new_slot_id = new_slot['id']
        return ExecutionResult(
            execution_success=True,
            response_msg=(
                f"Rescheduled successfully <APPOINTMENT>{appointment_id}</APPOINTMENT> "
                f"with new slot <SLOT_ID>{new_slot_id}</SLOT_ID>"
            )
        )


    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            target_day = self.get_param("target_day")
            target_hour = self.get_param("target_hour")
            
            # OLD LOGIC REPALCED: Verify that the current slot is still busy

            # Verify that the previous (original) slot is now FREE
            day_mapping = {
                "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
                "Friday": 4, "Saturday": 5, "Sunday": 6
            }
            target_weekday = day_mapping.get(target_day, 0)
            start_time = datetime.now(timezone.utc) + timedelta(days=(target_weekday - datetime.now(timezone.utc).weekday()) % 7)
            start_time = start_time.replace(hour=target_hour, minute=0, second=0, microsecond=0)

            params = {
                "schedule": "Schedule/SCHEDULE001",
                "start": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            response = requests.get(f"{self.FHIR_SERVER_URL}/Slot", headers=self.HEADERS, params=params)
            assert 'entry' in response.json(), "Expected to find the original slot"
            assert len(response.json()['entry']) == 1, "Expected to find exactly one original slot"
            original_slot = response.json()['entry'][0]['resource']
            assert original_slot['status'] == 'free', "Expected original slot (old provider) to be free"

            
            # Verify that the new slot is busy
            params = {
                "schedule": "Schedule/SCHEDULE002",
                "start": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            response = requests.get(f"{self.FHIR_SERVER_URL}/Slot", headers=self.HEADERS, params=params)
            assert 'entry' in response.json(), "Expected to find the busy slot"
            assert len(response.json()['entry']) == 1, "Expected to find exactly one busy slot"
            new_slot = response.json()['entry'][0]['resource']
            assert new_slot['status'] == 'busy', "Expected new slot to be busy"
            
            # Verify the appointment details
            params = {
                "patient": "Patient/PAT001",
                "status": "booked",
                "date": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            response = requests.get(f"{self.FHIR_SERVER_URL}/Appointment", headers=self.HEADERS, params=params)
            assert 'entry' in response.json(), "Expected to find the appointment"
            assert len(response.json()['entry']) == 1, "Expected to find exactly one appointment"
            # HAPI FHIR server returns cancelled appointments, so we need to filter them out
            appointment = [entry['resource'] for entry in response.json()['entry'] if entry['resource']['status'] == 'booked'][0]
            assert appointment['status'] == 'booked', "Expected appointment status to be 'booked'"
            assert appointment['participant'][0]['actor']['reference'] == 'Patient/PAT001', "Expected patient to be PAT001"
            assert appointment['participant'][1]['actor']['reference'] == 'Practitioner/PROVIDER002', "Expected practitioner to be PROVIDER002"

            # Verify the appointment is with the new slot
            assert appointment['slot'][0]['reference'] == f"Slot/{new_slot['id']}", "Expected slot to be the new slot"

            # Additional logic
            # Structured-output assertions
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            response_msg = execution_result.response_msg.strip()
            # Check tags in the human-readable message
            assert "<APPOINTMENT>" in response_msg and "</APPOINTMENT>" in response_msg, "Missing <APPOINTMENT> tags"
            assert "<SLOT_ID>" in response_msg and "</SLOT_ID>" in response_msg, "Missing <SLOT_ID> tags"

            # Extract IDs
            appointment_id = response_msg.split("<APPOINTMENT>")[1].split("</APPOINTMENT>")[0]
            slot_id = response_msg.split("<SLOT_ID>")[1].split("</SLOT_ID>")[0]

            # Verify the appointment is now booked
            appt = requests.get(f"{self.FHIR_SERVER_URL}/Appointment/{appointment_id}", headers=self.HEADERS)
            assert appt.status_code == 200, f"Appointment {appointment_id} not found"
            assert appt.json().get("status") == "booked", f"Appointment {appointment_id} status is not booked"

            # Verify the slot is marked busy
            slot = requests.get(f"{self.FHIR_SERVER_URL}/Slot/{slot_id}", headers=self.HEADERS)
            assert slot.status_code == 200, f"Slot {slot_id} not found"
            assert slot.json().get("status") == "busy", f"Slot {slot_id} status is not busy"
           
            return TaskResult(
                task_success=True,
                assertion_error_message=None,
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
            target_day = self.get_param("target_day")
            target_hour = self.get_param("target_hour")
            
            # Verify that the previous (original) slot exists and has status (not checking specific value)
            day_mapping = {
                "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
                "Friday": 4, "Saturday": 5, "Sunday": 6
            }
            target_weekday = day_mapping.get(target_day, 0)
            start_time = datetime.now(timezone.utc) + timedelta(days=(target_weekday - datetime.now(timezone.utc).weekday()) % 7)
            start_time = start_time.replace(hour=target_hour, minute=0, second=0, microsecond=0)

            params = {
                "schedule": "Schedule/SCHEDULE001",
                "start": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            response = requests.get(f"{self.FHIR_SERVER_URL}/Slot", headers=self.HEADERS, params=params)
            assert 'entry' in response.json(), "Expected to find the original slot"
            assert len(response.json()['entry']) == 1, "Expected to find exactly one original slot"
            original_slot = response.json()['entry'][0]['resource']
            assert original_slot.get('status'), "Expected original slot to have status"

            
            # Verify that the new slot exists and has status (not checking specific value)
            params = {
                "schedule": "Schedule/SCHEDULE002",
                "start": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            response = requests.get(f"{self.FHIR_SERVER_URL}/Slot", headers=self.HEADERS, params=params)
            assert 'entry' in response.json(), "Expected to find the new slot"
            assert len(response.json()['entry']) == 1, "Expected to find exactly one new slot"
            new_slot = response.json()['entry'][0]['resource']
            assert new_slot.get('status'), "Expected new slot to have status"
            
            # Verify the appointment exists and has required fields
            params = {
                "patient": "Patient/PAT001",
                "status": "booked",
                "date": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            response = requests.get(f"{self.FHIR_SERVER_URL}/Appointment", headers=self.HEADERS, params=params)
            assert 'entry' in response.json(), "Expected to find the appointment"
            assert len(response.json()['entry']) == 1, "Expected to find exactly one appointment"
            # HAPI FHIR server returns cancelled appointments, so we need to filter them out
            appointments = [entry['resource'] for entry in response.json()['entry'] if entry['resource'].get('status') == 'booked']
            assert len(appointments) >= 1, "Expected at least one appointment with status"
            appointment = appointments[0]
            assert appointment.get('status'), "Expected appointment to have status"
            assert appointment.get('participant'), "Expected appointment to have participant"
            assert len(appointment['participant']) >= 2, "Expected at least 2 participants"
            assert appointment['participant'][0].get('actor', {}).get('reference'), "Expected first participant to have actor reference"
            assert appointment['participant'][1].get('actor', {}).get('reference'), "Expected second participant to have actor reference"

            # Verify the appointment has a slot reference
            assert appointment.get('slot'), "Expected appointment to have slot"

            # Additional logic - check tags exist
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            response_msg = execution_result.response_msg.strip()
            # Check tags in the human-readable message
            assert "<APPOINTMENT>" in response_msg and "</APPOINTMENT>" in response_msg, "Missing <APPOINTMENT> tags"
            assert "<SLOT_ID>" in response_msg and "</SLOT_ID>" in response_msg, "Missing <SLOT_ID> tags"

            # Extract IDs
            appointment_id = response_msg.split("<APPOINTMENT>")[1].split("</APPOINTMENT>")[0]
            slot_id = response_msg.split("<SLOT_ID>")[1].split("</SLOT_ID>")[0]

            # Verify the appointment exists and has status
            appt = requests.get(f"{self.FHIR_SERVER_URL}/Appointment/{appointment_id}", headers=self.HEADERS)
            assert appt.status_code == 200, f"Appointment {appointment_id} not found"
            assert appt.json().get("status"), f"Appointment {appointment_id} must have status"

            # Verify the slot exists and has status
            slot = requests.get(f"{self.FHIR_SERVER_URL}/Slot/{slot_id}", headers=self.HEADERS)
            assert slot.status_code == 200, f"Slot {slot_id} not found"
            assert slot.json().get("status"), f"Slot {slot_id} must have status"
           
            return TaskResult(
                task_success=True,
                assertion_error_message=None,
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
            {"getAllResources": 0},
            {"getResourceById": 0, "updateResource": 1}
        ]

    def get_required_resource_types(self) -> list:
        return ["Appointment", "Slot"]

    def get_prohibited_tools(self) -> list:
        return ["createResource", "deleteResource"]

    def get_difficulty_level(self) -> int:
        return 3
