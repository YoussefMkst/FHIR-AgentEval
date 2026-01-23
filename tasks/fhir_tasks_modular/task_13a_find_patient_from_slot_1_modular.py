# task_13a_find_patient_from_slot_1_modular.py

import os
import requests
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from tasks.fhir_tasks_modular.task_interface_modular import TaskInterfaceModular, TaskResult, ExecutionResult, TaskFailureMode


class FindPatientFromSlotTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "13a"

    def get_task_name(self) -> str:
        return "Find Patient From Slot - Dr. John Smith"

    def get_prompt(self) -> str:
        practitioner_family = self.get_param("practitioner_family")
        practitioner_given = self.get_param("practitioner_given")
        target_day = self.get_param("target_day")
        target_hour = self.get_param("target_hour")
        
        return f"""
Find the patient who has booked Dr. {' '.join(practitioner_given)} {practitioner_family}'s slot next {target_day} morning at {target_hour}:00.

After finding, return the patient ID using the following format: <PATIENT_ID>patient_id</PATIENT_ID>
"""


    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["practitioner_family", "practitioner_given", "target_day", "target_hour"],
            "properties": {
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
                "target_day": {
                    "type": "string",
                    "description": "Target day of the week to search for appointments",
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
                "patient1_family": {
                    "type": "string",
                    "description": "Family name of the first patient",
                    "examples": ["Doe", "Smith", "Johnson"],
                    "default": "Doe",
                },
                "patient1_given": {
                    "type": "array",
                    "description": "Given names of the first patient",
                    "items": {"type": "string"},
                    "examples": [["John"], ["Jane"], ["Mike"]],
                    "default": ["John"],
                },
                "patient1_birth_date": {
                    "type": "string",
                    "description": "Birth date of the first patient (YYYY-MM-DD format)",
                    "examples": ["1990-06-15", "1985-03-22", "1995-12-10"],
                    "default": "1990-06-15",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                },
                "patient1_phone": {
                    "type": "string",
                    "description": "Phone number of the first patient",
                    "examples": ["123-456-7890", "555-123-4567"],
                    "default": "123-456-7890",
                },
                "patient2_family": {
                    "type": "string",
                    "description": "Family name of the second patient",
                    "examples": ["Doe", "Smith", "Johnson"],
                    "default": "Doe",
                },
                "patient2_given": {
                    "type": "array",
                    "description": "Given names of the second patient",
                    "items": {"type": "string"},
                    "examples": [["Jane"], ["John"], ["Sarah"]],
                    "default": ["Jane"],
                },
                "patient2_birth_date": {
                    "type": "string",
                    "description": "Birth date of the second patient (YYYY-MM-DD format)",
                    "examples": ["2020-06-15", "2015-03-22", "2018-12-10"],
                    "default": "2020-06-15",
                    "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                },
                "patient2_phone": {
                    "type": "string",
                    "description": "Phone number of the second patient",
                    "examples": ["123-456-7890", "555-123-4567"],
                    "default": "123-456-7890",
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
            practitioner_family = self.get_param("practitioner_family")
            practitioner_given = self.get_param("practitioner_given")
            practitioner_gender = self.get_param("practitioner_gender", "male")
            patient1_family = self.get_param("patient1_family", "Doe")
            patient1_given = self.get_param("patient1_given", ["John"])
            patient1_birth_date = self.get_param("patient1_birth_date", "1990-06-15")
            patient1_phone = self.get_param("patient1_phone", "123-456-7890")
            patient2_family = self.get_param("patient2_family", "Doe")
            patient2_given = self.get_param("patient2_given", ["Jane"])
            patient2_birth_date = self.get_param("patient2_birth_date", "2020-06-15")
            patient2_phone = self.get_param("patient2_phone", "123-456-7890")
            specialty_code = self.get_param("specialty_code", "394580004")
            specialty_display = self.get_param("specialty_display", "Clinical genetics")
            address_line = self.get_param("address_line", "123 Main St")
            address_city = self.get_param("address_city", "Boston")
            address_state = self.get_param("address_state", "MA")

            # Create first practitioner
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
                "name": [{"use": "official", "family": patient1_family, "given": patient1_given}],
                "birthDate": patient1_birth_date,
                "telecom": [{"system": "phone", "value": patient1_phone}],
                "address": [{"line": [address_line], "city": address_city, "state": address_state}]
            }
            self.upsert_to_fhir(patient1)
            
            target_day = self.get_param("target_day")
            target_hour = self.get_param("target_hour")
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
                "status": "busy",
                "schedule": {"reference": "Schedule/SCHEDULE001"},
            }
            self.upsert_to_fhir(slot1)
            
            appointment1 = {
                "resourceType": "Appointment",
                "id": "APPOINTMENT001",
                "status": "booked",
                "slot": [{"reference": "Slot/SLOT001"}],
                "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "participant": [{"actor": {"reference": "Patient/PAT001"}, "status": "accepted"}, {"actor": {"reference": "Practitioner/PROVIDER001"}, "status": "accepted"}],
            }
            self.upsert_to_fhir(appointment1)

            # Create second practitioner (different name to avoid confusion)
            practitioner2 = {
                "resourceType": "Practitioner",
                "id": "PROVIDER002",
                "name": [{"use": "official", "family": "Johnson", "given": ["Mary"]}],
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
                "name": [{"use": "official", "family": patient2_family, "given": patient2_given}],
                "birthDate": patient2_birth_date,
                "telecom": [{"system": "phone", "value": patient2_phone}],
                "address": [{"line": [address_line], "city": address_city, "state": address_state}]
            }
            self.upsert_to_fhir(patient2)
            
            slot2 = {
                "resourceType": "Slot",
                "id": "SLOT002",
                "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "busy",
                "schedule": {"reference": "Schedule/SCHEDULE002"},
            }
            self.upsert_to_fhir(slot2)
            
            appointment2 = {
                "resourceType": "Appointment",
                "id": "APPOINTMENT002",
                "status": "booked",
                "slot": [{"reference": "Slot/SLOT002"}],
                "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "participant": [{"actor": {"reference": "Patient/PAT002"}, "status": "accepted"}, {"actor": {"reference": "Practitioner/PROVIDER002"}, "status": "accepted"}],
            }
            self.upsert_to_fhir(appointment2)

        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")


    def execute_human_agent(self) -> ExecutionResult:
        practitioner_family = self.get_param("practitioner_family")
        practitioner_given = self.get_param("practitioner_given")
        target_day = self.get_param("target_day")
        target_hour = self.get_param("target_hour")
        
        # Map day names to weekday numbers (Monday = 0, Sunday = 6)
        day_mapping = {
            "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
            "Friday": 4, "Saturday": 5, "Sunday": 6
        }
        target_weekday = day_mapping.get(target_day, 0)
        
        # Find next target day's slot at target hour
        next_target_day = datetime.now(timezone.utc) + timedelta(days=(target_weekday - datetime.now(timezone.utc).weekday()) % 7)
        target_time = next_target_day.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        
        # a bir brittle since it only compares the first name but it's fine for our purposes
        params = {
            "start": target_time.strftime("%Y-%m-%d"),
            "schedule.actor.given": practitioner_given[0],
            "schedule.actor.family": practitioner_family,
        }
        response = requests.get(f"{self.FHIR_SERVER_URL}/Slot", headers=self.HEADERS, params=params)
        if 'entry' not in response.json():
            return ExecutionResult(
                execution_success=False,
                response_msg=f"No slots found for Dr. {' '.join(practitioner_given)} {practitioner_family}"
            )
        slot_id = response.json()['entry'][0]['resource']['id']
        params = {"slot": f"Slot/{slot_id}"}
        response = requests.get(f"{self.FHIR_SERVER_URL}/Appointment", headers=self.HEADERS, params=params)
        patient_id = response.json()['entry'][0]['resource']['participant'][0]['actor']['reference']
        response = requests.get(f"{self.FHIR_SERVER_URL}/{patient_id}", headers=self.HEADERS)

        return ExecutionResult(
            execution_success=True,
            response_msg=f"Successfully found patient <PATIENT_ID>{patient_id}</PATIENT_ID> for Dr. {' '.join(practitioner_given)} {practitioner_family}'s slot"
        )



    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
            # Quick helper function for comparing ids
        def _bare(x: str) -> str:
            x = x.strip()
            return x.split("/", 1)[1].strip() if "/" in x else x
        
        try:
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            response_msg = response_msg.strip()
            assert "<PATIENT_ID>" in response_msg, "Expected to find <PATIENT_ID> tag"
            assert "</PATIENT_ID>" in response_msg, "Expected to find </PATIENT_ID> tag"
            patient_id = response_msg.split("<PATIENT_ID>")[1].split("</PATIENT_ID>")[0]
            expected_id = self.execute_human_agent().response_msg.split("<PATIENT_ID>")[1].split("</PATIENT_ID>")[0]
            # Added fix
            assert _bare(patient_id) == _bare(expected_id), f"Expected patient_id {expected_id}, got {patient_id}"
            
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


    def get_required_tool_call_sets(self) -> list:
        return [
            {"searchResources": 2, "getResourceById": 1}
        ]

    def get_required_resource_types(self) -> list:
        return ["Slot", "Appointment", "Patient"]

    def get_prohibited_tools(self) -> list:
        return ["createResource", "updateResource", "deleteResource"]

    def get_difficulty_level(self) -> int:
        return 2
