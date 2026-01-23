# task_15a_cancel_appointment_modular.py

import os
import time
import requests
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from tasks.fhir_tasks_modular.task_interface_modular import TaskInterfaceModular, TaskResult, ExecutionResult, TaskFailureMode


class CancelAppointmentTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "15a"

    def get_task_name(self) -> str:
        return "Cancel Next Appointment"

    def get_prompt(self) -> str:
        patient_family = self.get_param("patient_family")
        patient_given = self.get_param("patient_given")
        return f"""
Cancel Patient {' '.join(patient_given)} {patient_family}'s next coming appointment.

After cancellation, return the cancelled appointment ID and freed slot ID using the following format:
<APPOINTMENT>appointment_id</APPOINTMENT>
<SLOT_ID>slot_id</SLOT_ID>
"""

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_family", "patient_given"],
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
                "first_appointment_day": {
                    "type": "string",
                    "description": "Day of the week for the first appointment",
                    "examples": ["Monday", "Tuesday", "Wednesday"],
                    "default": "Monday",
                    "enum": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                },
                "first_appointment_hour": {
                    "type": "integer",
                    "description": "Hour for the first appointment (24-hour format)",
                    "examples": [9, 10, 14],
                    "default": 9,
                    "minimum": 0,
                    "maximum": 23,
                },
                "second_appointment_day_offset": {
                    "type": "integer",
                    "description": "Days offset from first appointment for the second appointment",
                    "examples": [1, 2, 3],
                    "default": 1,
                    "minimum": 1,
                    "maximum": 7,
                },
                "second_appointment_hour": {
                    "type": "integer",
                    "description": "Hour for the second appointment (24-hour format)",
                    "examples": [9, 10, 14],
                    "default": 9,
                    "minimum": 0,
                    "maximum": 23,
                },
                "appointment_duration_hours": {
                    "type": "integer",
                    "description": "Duration of each appointment in hours",
                    "examples": [1, 2],
                    "default": 1,
                    "minimum": 1,
                    "maximum": 8,
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
            practitioner_family = self.get_param("practitioner_family", "Smith")
            practitioner_given = self.get_param("practitioner_given", ["John"])
            practitioner_gender = self.get_param("practitioner_gender", "male")
            first_appointment_day = self.get_param("first_appointment_day", "Monday")
            first_appointment_hour = self.get_param("first_appointment_hour", 9)
            second_appointment_day_offset = self.get_param("second_appointment_day_offset", 1)
            second_appointment_hour = self.get_param("second_appointment_hour", 9)
            appointment_duration_hours = self.get_param("appointment_duration_hours", 1)
            specialty_code = self.get_param("specialty_code", "394580004")
            specialty_display = self.get_param("specialty_display", "Clinical genetics")
            address_line = self.get_param("address_line", "123 Main St")
            address_city = self.get_param("address_city", "Boston")
            address_state = self.get_param("address_state", "MA")

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
            
            patient1 = {
                "resourceType": "Patient",
                "id": "PAT001",
                "name": [{"use": "official", "family": patient_family, "given": patient_given}],
                "birthDate": patient_birth_date,
                "telecom": [{"system": "phone", "value": patient_phone}],
                "address": [{"line": [address_line], "city": address_city, "state": address_state}]
            }
            self.upsert_to_fhir(patient1)
            
            # Map day names to weekday numbers (Monday = 0, Sunday = 6)
            day_mapping = {
                "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
                "Friday": 4, "Saturday": 5, "Sunday": 6
            }
            first_target_weekday = day_mapping.get(first_appointment_day, 0)
            
            # Create first appointment
            start = datetime.now(timezone.utc) + timedelta(days=(first_target_weekday - datetime.now(timezone.utc).weekday()) % 7)
            start = start.replace(hour=first_appointment_hour, minute=0, second=0, microsecond=0)
            slot1 = {
                "resourceType": "Slot",
                "id": "SLOT001",
                "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": (start + timedelta(hours=appointment_duration_hours)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "busy",
                "schedule": {"reference": "Schedule/SCHEDULE001"},
            }
            self.upsert_to_fhir(slot1)
            
            appointment1 = {
                "resourceType": "Appointment",
                "id": "APPOINTMENT001",
                "status": "booked",
                "slot": [{"reference": "Slot/SLOT001"}],
                "participant": [{"actor": {"reference": "Patient/PAT001"}, "status": "accepted"}, 
                              {"actor": {"reference": "Practitioner/PROVIDER001"}, "status": "accepted"}],
                "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": (start + timedelta(hours=appointment_duration_hours)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            self.upsert_to_fhir(appointment1)

            # Create a second appointment for the same patient
            start = start + timedelta(days=second_appointment_day_offset)
            start = start.replace(hour=second_appointment_hour, minute=0, second=0, microsecond=0)
            slot2 = {
                "resourceType": "Slot",
                "id": "SLOT002",
                "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": (start + timedelta(hours=appointment_duration_hours)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "busy",
                "schedule": {"reference": "Schedule/SCHEDULE001"},
            }
            self.upsert_to_fhir(slot2)
            
            appointment2 = {
                "resourceType": "Appointment",
                "id": "APPOINTMENT002",
                "status": "booked",
                "slot": [{"reference": "Slot/SLOT002"}],
                "participant": [{"actor": {"reference": "Patient/PAT001"}, "status": "accepted"}, 
                              {"actor": {"reference": "Practitioner/PROVIDER001"}, "status": "accepted"}],
                "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": (start + timedelta(hours=appointment_duration_hours)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            self.upsert_to_fhir(appointment2)

        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")


    def execute_human_agent(self) -> ExecutionResult:
        # Find the next appointment for the specified patient
        params = {
            "patient": "Patient/PAT001",
            "status": "booked",
        }
        response = requests.get(f"{self.FHIR_SERVER_URL}/Appointment", headers=self.HEADERS, params=params)
        assert response.status_code in [200, 201], f"Expected status code 200 or 201, but got {response.status_code}. Response body: {response.text}"
        assert 'entry' in response.json(), "Expected to find at least one appointment"
        
        # Find the appointment with the earliest start date
        appointment_to_cancel = None
        earliest_start_date = datetime.max
        for appointment in response.json()['entry']:
            slot = appointment['resource']['slot'][0]['reference']
            slot_response = requests.get(f"{self.FHIR_SERVER_URL}/{slot}", headers=self.HEADERS)
            assert slot_response.status_code in [200, 201], f"Expected status code 200 or 201, but got {slot_response.status_code}. Response body: {slot_response.text}"
            start_date = slot_response.json()['start']
            if datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%SZ") < earliest_start_date:
                earliest_start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%SZ")
                appointment_to_cancel = appointment

        assert appointment_to_cancel is not None, "Expected to find an appointment to cancel"
        
        # Cancel the appointment by updating its status to 'cancelled'
        appointment_id = appointment_to_cancel['resource']['id']
        slot_id = appointment_to_cancel['resource']['slot'][0]['reference'].split('/')[-1]
        
        # Update appointment status to cancelled
        params = {
            "resourceType": "Appointment",
            "id": appointment_id,
            "status": "cancelled",
            "slot": appointment_to_cancel['resource']['slot'],
            "participant": appointment_to_cancel['resource']['participant'],
            "start": appointment_to_cancel['resource']['start'],
            "end": appointment_to_cancel['resource']['end'],
        }
        response = requests.put(f"{self.FHIR_SERVER_URL}/Appointment/{appointment_id}", headers=self.HEADERS, json=params)
        assert response.status_code in [200, 201], f"Expected status code 200 or 201, but got {response.status_code}. Response body: {response.text}"

        # Update slot status back to free
        params = {
            "resourceType": "Slot",
            "id": slot_id,
            "status": "free",
            "start": earliest_start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": (earliest_start_date + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "schedule": {"reference": "Schedule/SCHEDULE001"},
        }
        response = requests.put(f"{self.FHIR_SERVER_URL}/Slot/{slot_id}", headers=self.HEADERS, json=params)
        assert response.status_code in [200, 201], f"Expected status code 200 or 201, but got {response.status_code}. Response body: {response.text}"

        return ExecutionResult(
            execution_success=True,
            response_msg=(
                f"Successfully cancelled appointment "
                f"<APPOINTMENT>{appointment_id}</APPOINTMENT> "
                f"and freed slot <SLOT_ID>{slot_id}</SLOT_ID>"
            )
        )


    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            # Verify that the earliest appointment is cancelled
            params = {
                "patient": "Patient/PAT001",
                "status": "cancelled",
            }
            response = requests.get(f"{self.FHIR_SERVER_URL}/Appointment", headers=self.HEADERS, params=params)
            assert response.status_code in [200, 201], f"Expected status code 200 or 201, but got {response.status_code}. Response body: {response.text}"
            assert 'entry' in response.json(), "Expected to find the cancelled appointment"
            assert len(response.json()['entry']) == 1, "Expected to find exactly one cancelled appointment"
            
            # Verify that the slot is now free
            slot_id = response.json()['entry'][0]['resource']['slot'][0]['reference']
            response = requests.get(f"{self.FHIR_SERVER_URL}/{slot_id}", headers=self.HEADERS)
            assert response.status_code in [200, 201], f"Expected status code 200 or 201, but got {response.status_code}. Response body: {response.text}"
            assert response.json()['status'] == "free", "Expected slot to be free after cancellation"

            # Additional logic
            response_msg = execution_result.response_msg.strip()
            # Appointment tag assertions
            assert "<APPOINTMENT>" in response_msg, "Expected to find <APPOINTMENT> tag"
            assert "</APPOINTMENT>" in response_msg, "Expected to find </APPOINTMENT> tag"
            appointment_id_tag = response_msg.split("<APPOINTMENT>")[1].split("</APPOINTMENT>")[0]
           
            # Slot tag assertions
            assert "<SLOT_ID>" in response_msg, "Expected to find <SLOT_ID> tag"
            assert "</SLOT_ID>" in response_msg, "Expected to find </SLOT_ID> tag"
            slot_id_tag = response_msg.split("<SLOT_ID>")[1].split("</SLOT_ID>")[0]
           
            # human task result
            human_response = execution_result.response_msg.strip()
            expected_appointment_id = human_response.split("<APPOINTMENT>")[1].split("</APPOINTMENT>")[0]
            expected_slot_id = human_response.split("<SLOT_ID>")[1].split("</SLOT_ID>")[0]
            
            assert appointment_id_tag == expected_appointment_id, f"Expected appointment_id {expected_appointment_id}, got {appointment_id_tag}"
            assert slot_id_tag == expected_slot_id, f"Expected slot_id {expected_slot_id}, got {slot_id_tag}"
            
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
            # Verify that the earliest appointment is cancelled
            params = {
                "patient": "Patient/PAT001",
                "status": "cancelled",
            }
            response = requests.get(f"{self.FHIR_SERVER_URL}/Appointment", headers=self.HEADERS, params=params)
            assert response.status_code in [200, 201], f"Expected status code 200 or 201, but got {response.status_code}. Response body: {response.text}"
            assert 'entry' in response.json(), "Expected to find the cancelled appointment"
            assert len(response.json()['entry']) == 1, "Expected to find exactly one cancelled appointment"
            
            # Verify that the slot has status (not checking specific value)
            slot_id = response.json()['entry'][0]['resource']['slot'][0]['reference']
            response = requests.get(f"{self.FHIR_SERVER_URL}/{slot_id}", headers=self.HEADERS)
            assert response.status_code in [200, 201], f"Expected status code 200 or 201, but got {response.status_code}. Response body: {response.text}"
            assert response.json().get('status'), "Expected slot to have status"

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
            {"getAllResources": 0, "getResourceById": 1, "updateResource": 2, "updateResource": 3},
            {"searchResources": 0, "updateResource": 1, "getResourceById": 2, "updateResource": 3},
            {"searchResources": 0, "getResourceById": 1, "updateResource": 2, "updateResource": 3, "updateResource": 4},
        ]

    def get_required_resource_types(self) -> list:
        return ["Appointment", "Slot"]

    def get_prohibited_tools(self) -> list:
        return ["createResource", "deleteResource"]

    def get_difficulty_level(self) -> int:
        return 3
