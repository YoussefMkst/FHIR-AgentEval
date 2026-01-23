# task_14b_make_appointment_2_modular.py

import os
import time
import requests
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from tasks.fhir_tasks_modular.task_interface_modular import TaskInterfaceModular, TaskResult, ExecutionResult, TaskFailureMode


class MakeAppointmentTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "14b"

    def get_task_name(self) -> str:
        return "Make Appointment 2"

    def get_prompt(self) -> str:
        patient_family = self.get_param("patient_family")
        patient_given = self.get_param("patient_given")
        practitioner_family = self.get_param("practitioner_family")
        practitioner_given = self.get_param("practitioner_given")
        target_day = self.get_param("target_day")
        target_hour = self.get_param("target_hour")
        return f"""
Make an appointment time for {' '.join(patient_given)} {patient_family} with Provider Dr. {' '.join(practitioner_given)} {practitioner_family} on next {target_day} morning at {target_hour}:00."

After creating the appointment, return the new Appointment ID using the following format: <APPOINTMENT>appointment_id</APPOINTMENT>
"""

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["patient_family", "patient_given", "practitioner_family", "practitioner_given", "target_day", "target_hour"],
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
                    "examples": [["Jane"], ["John"], ["Sarah"]],
                    "default": ["Jane"],
                },
                "patient_birth_date": {
                    "type": "string",
                    "description": "Birth date of the patient (YYYY-MM-DD format)",
                    "examples": ["2020-06-15", "2015-03-22", "2018-12-10"],
                    "default": "2020-06-15",
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
                    "examples": ["John", "Smith", "Williams"],
                    "default": "John",
                },
                "practitioner_given": {
                    "type": "array",
                    "description": "Given names of the practitioner",
                    "items": {"type": "string"},
                    "examples": [["Smith"], ["John"], ["Michael"]],
                    "default": ["Smith"],
                },
                "practitioner_gender": {
                    "type": "string",
                    "description": "Gender of the practitioner",
                    "examples": ["male", "female"],
                    "default": "male",
                    "enum": ["male", "female", "other", "unknown"],
                },
                "target_day": {
                    "type": "string",
                    "description": "Target day of the week for the appointment",
                    "examples": ["Monday", "Tuesday", "Wednesday"],
                    "default": "Monday",
                    "enum": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                },
                "target_hour": {
                    "type": "integer",
                    "description": "Target hour for the appointment (24-hour format)",
                    "examples": [9, 10, 14],
                    "default": 9,
                    "minimum": 0,
                    "maximum": 23,
                },
                "appointment_duration_hours": {
                    "type": "integer",
                    "description": "Duration of the appointment in hours",
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
            patient_birth_date = self.get_param("patient_birth_date", "2020-06-15")
            patient_phone = self.get_param("patient_phone", "123-456-7890")
            practitioner_family = self.get_param("practitioner_family")
            practitioner_given = self.get_param("practitioner_given")
            practitioner_gender = self.get_param("practitioner_gender", "male")
            specialty_code = self.get_param("specialty_code", "394580004")
            specialty_display = self.get_param("specialty_display", "Clinical genetics")
            address_line = self.get_param("address_line", "123 Main St")
            address_city = self.get_param("address_city", "Boston")
            address_state = self.get_param("address_state", "MA")

            # Create first practitioner
            practitioner1 = {
                "resourceType": "Practitioner",
                "id": "PROVIDER001",
                "name": [{"use": "official", "family": "Smith", "given": ["John"]}],
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
                "name": [{"use": "official", "family": "Doe", "given": ["John"]}],
                "birthDate": "1990-06-15",
                "telecom": [{"system": "phone", "value": "123-456-7890"}],
                "address": [{"line": [address_line], "city": address_city, "state": address_state}]
            }
            self.upsert_to_fhir(patient1)
            
            target_day = self.get_param("target_day", "Monday")
            target_hour = self.get_param("target_hour", 9)
            # Map day names to weekday numbers (Monday = 0, Sunday = 6)
            day_mapping = {
                "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
                "Friday": 4, "Saturday": 5, "Sunday": 6
            }
            target_weekday = day_mapping.get(target_day, 0)
            
            start = datetime.now(timezone.utc) + timedelta(days=(target_weekday - datetime.now(timezone.utc).weekday()) % 7)
            start = start.replace(hour=target_hour, minute=0, second=0, microsecond=0)
            slot1 = {
                "resourceType": "Slot",
                "id": "SLOT001",
                "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "free",
                "schedule": {"reference": "Schedule/SCHEDULE001"},
            }
            self.upsert_to_fhir(slot1)

            # Create second practitioner (different name to avoid confusion)
            practitioner2 = {
                "resourceType": "Practitioner",
                "id": "PROVIDER002",
                "name": [{"use": "official", "family": practitioner_family, "given": practitioner_given}],
            }
            self.upsert_to_fhir(practitioner2)   
            
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
            
            patient2 = {
                "resourceType": "Patient",
                "id": "PAT002",
                "name": [{"use": "official", "family": patient_family, "given": patient_given}],
                "birthDate": patient_birth_date,
                "telecom": [{"system": "phone", "value": patient_phone}],
                "address": [{"line": [address_line], "city": address_city, "state": address_state}]
            }
            self.upsert_to_fhir(patient2)
            
            slot2 = {
                "resourceType": "Slot",
                "id": "SLOT002",
                "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "free",
                "schedule": {"reference": "Schedule/SCHEDULE002"},
            }
            self.upsert_to_fhir(slot2)

        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")


    def execute_human_agent(self) -> ExecutionResult:
        target_day = self.get_param("target_day")
        target_hour = self.get_param("target_hour")
        appointment_duration_hours = self.get_param("appointment_duration_hours", 1)
        
        # Map day names to weekday numbers (Monday = 0, Sunday = 6)
        day_mapping = {
            "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
            "Friday": 4, "Saturday": 5, "Sunday": 6
        }
        target_weekday = day_mapping.get(target_day, 0)
        
        start = datetime.now(timezone.utc) + timedelta(days=(target_weekday - datetime.now(timezone.utc).weekday()) % 7)
        start = start.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        
        params = {
            "resourceType": "Appointment",
            "id": "APPOINTMENT002",
            "status": "booked",
            "slot": [{"reference": "Slot/SLOT002"}],
            "participant": [{"actor": {"reference": "Patient/PAT002"}, "status": "accepted"}, 
                            {"actor": {"reference": "Practitioner/PROVIDER002"}, "status": "accepted"}],
            "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": (start + timedelta(hours=appointment_duration_hours)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        response = requests.put(f"{self.FHIR_SERVER_URL}/Appointment/APPOINTMENT002", headers=self.HEADERS, json=params)
        # Added logic
        appointment_id = response.json().get('id')
        assert response.status_code in [201, 200], f"Expected status code 201 or 200, but got {response.status_code}. Response body: {response.text}"
        
        params = {
            "resourceType": "Slot",
            "id": "SLOT002",
            "status": "busy",
        }
        response = requests.put(f"{self.FHIR_SERVER_URL}/Slot/SLOT002", headers=self.HEADERS, json=params)
        assert response.status_code in [200, 201], f"Expected status code 200 or 201, but got {response.status_code}. Response body: {response.text}"

        return ExecutionResult(
            execution_success=True,
            response_msg=f"Successfully created appointment <APPOINTMENT>{appointment_id}</APPOINTMENT>"
        )

    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            target_day = self.get_param("target_day", "Monday")
            target_hour = self.get_param("target_hour", 9)
            
            # Map day names to weekday numbers (Monday = 0, Sunday = 6)
            day_mapping = {
                "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
                "Friday": 4, "Saturday": 5, "Sunday": 6
            }
            target_weekday = day_mapping.get(target_day, 0)
            
            start = datetime.now(timezone.utc) + timedelta(days=(target_weekday - datetime.now(timezone.utc).weekday()) % 7)
            start = start.replace(hour=target_hour, minute=0, second=0, microsecond=0)
            
            # query appointment reference to slot2
            params = {
                "practitioner": "Practitioner/PROVIDER002",
                "date": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            response = requests.get(f"{self.FHIR_SERVER_URL}/Appointment", headers=self.HEADERS, params=params)
            # check the participant is correct
            assert 'entry' in response.json(), "Expected entry in the response"
            assert len(response.json()['entry']) == 1, "Expected one appointment" 
            assert response.json()['entry'][0]['resource']['participant'][0]['actor']['reference'] == "Patient/PAT002", "Expected patient reference to be PAT002"
            assert response.json()['entry'][0]['resource']['participant'][1]['actor']['reference'] == "Practitioner/PROVIDER002", "Expected practitioner reference to be PROVIDER002"
            # check the slot reference is busy
            slot_id = response.json()['entry'][0]['resource']['slot'][0]['reference']
            response = requests.get(f"{self.FHIR_SERVER_URL}/{slot_id}", headers=self.HEADERS)
            assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}. Response body: {response.text}"
            assert response.json()['status'] == "busy", "Expected slot to be busy"

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
            target_day = self.get_param("target_day", "Monday")
            target_hour = self.get_param("target_hour", 9)
            
            # Map day names to weekday numbers (Monday = 0, Sunday = 6)
            day_mapping = {
                "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
                "Friday": 4, "Saturday": 5, "Sunday": 6
            }
            target_weekday = day_mapping.get(target_day, 0)
            
            start = datetime.now(timezone.utc) + timedelta(days=(target_weekday - datetime.now(timezone.utc).weekday()) % 7)
            start = start.replace(hour=target_hour, minute=0, second=0, microsecond=0)
            
            # query appointment reference to slot2
            params = {
                "practitioner": "Practitioner/PROVIDER002",
                "date": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            response = requests.get(f"{self.FHIR_SERVER_URL}/Appointment", headers=self.HEADERS, params=params)
            # check the participant is present (not checking specific values)
            assert 'entry' in response.json(), "Expected entry in the response"
            assert len(response.json()['entry']) == 1, "Expected one appointment" 
            assert response.json()['entry'][0]['resource'].get('participant'), "Expected participant in appointment"
            assert len(response.json()['entry'][0]['resource']['participant']) >= 2, "Expected at least 2 participants"
            assert response.json()['entry'][0]['resource']['participant'][0].get('actor', {}).get('reference'), "Expected participant[0] to have actor.reference"
            assert response.json()['entry'][0]['resource']['participant'][1].get('actor', {}).get('reference'), "Expected participant[1] to have actor.reference"
            # check the slot reference exists and has status
            slot_id = response.json()['entry'][0]['resource']['slot'][0]['reference']
            response = requests.get(f"{self.FHIR_SERVER_URL}/{slot_id}", headers=self.HEADERS)
            assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}. Response body: {response.text}"
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
            {"updateResource": 0, "updateResource": 1},
            {"getResourceById": 0, "updateResource": 1, "updateResource": 2},
        ]

    def get_required_resource_types(self) -> list:
        return ["Appointment", "Slot"]

    def get_prohibited_tools(self) -> list:
        return ["createResource", "getAllResources", "getResourceById", "deleteResource"]

    def get_difficulty_level(self) -> int:
        return 2
