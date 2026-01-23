# task_11c_search_most_recent_slots_by_service_modular.py

import requests
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from tasks.fhir_tasks_modular.task_interface_modular import TaskInterfaceModular, TaskResult, ExecutionResult, TaskFailureMode


class FindSlotsByServiceTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "11c"

    def get_task_name(self) -> str:
        return "Find Slots by Service"

    def get_prompt(self) -> str:
        service_name = self.get_param("service_name")
        return f"""
Find all available slots for a {service_name} service (specialty code: 1234567).

After searching, return the total number of available slots using the following format: <SLOT_COUNT>number</SLOT_COUNT>
If none found, return the exact sentence: No available {service_name} slots found
"""

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["service_name"],
            "properties": {
                "service_specialty_code": {
                    "type": "string",
                    "description": "SNOMED CT code for the service specialty",
                    "examples": ["394580004", "408459003"],
                    "default": "1234567",
                },
                "service_name": {
                    "type": "string",
                    "description": "Human-readable name of the service",
                    "examples": ["genetic counseling", "pediatric cardiology"],
                    "default": "genetic counseling",
                },
                "practitioner_count": {
                    "type": "integer",
                    "description": "Number of practitioners to create",
                    "examples": [4],
                    "default": 4,
                    "minimum": 1,
                    "maximum": 10,
                },
                "slot_count_per_practitioner": {
                    "type": "integer",
                    "description": "Number of slots to create per practitioner",
                    "examples": [3],
                    "default": 3,
                    "minimum": 1,
                    "maximum": 10,
                },
                "slot_start_hour": {
                    "type": "integer",
                    "description": "Starting hour for slots (24-hour format)",
                    "examples": [9],
                    "default": 9,
                    "minimum": 0,
                    "maximum": 23,
                },
                "slot_end_hour": {
                    "type": "integer",
                    "description": "Ending hour for slots (24-hour format)",
                    "examples": [12],
                    "default": 12,
                    "minimum": 0,
                    "maximum": 23,
                },
                "slot_duration_hours": {
                    "type": "integer",
                    "description": "Duration of each slot in hours",
                    "examples": [1],
                    "default": 1,
                    "minimum": 1,
                    "maximum": 24,
                },
                "days_ahead": {
                    "type": "integer",
                    "description": "Number of days ahead to schedule slots",
                    "examples": [1],
                    "default": 1,
                    "minimum": 0,
                    "maximum": 30,
                },
                "free_slot_pattern": {
                    "type": "string",
                    "description": "Pattern for determining free slots",
                    "examples": ["alternating"],
                    "default": "alternating",
                    "enum": ["even", "odd", "alternating", "first", "last"],
                },
                "practitioner_family_names": {
                    "type": "array",
                    "description": "Array of family names for practitioners",
                    "items": {"type": "string"},
                    "examples": [["Smith", "Chen", "Garcia", "Patel"]],
                    "default": ["Smith", "Chen", "Garcia", "Patel"],
                },
                "practitioner_given_names": {
                    "type": "array",
                    "description": "Array of given names for practitioners",
                    "items": {"type": "array", "items": {"type": "string"}},
                    "examples": [[["John"], ["Wei"], ["Maria", "Isabel"], ["Rajesh"]]],
                    "default": [["John"], ["Wei"], ["Maria", "Isabel"], ["Rajesh"]],
                },
                "practitioner_genders": {
                    "type": "array",
                    "description": "Array of genders for practitioners",
                    "items": {"type": "string"},
                    "examples": [["male", "female", "female", "male"]],
                    "default": ["male", "female", "female", "male"],
                },
                "practitioner_languages": {
                    "type": "array",
                    "description": "Array of language codes for practitioners",
                    "items": {"type": "array", "items": {"type": "string"}},
                    "examples": [[["en"], ["en", "zh"], ["en", "es"], ["en", "hi"]]],
                    "default": [["en"], ["en", "zh"], ["en", "es"], ["en", "hi"]],
                },
                "practitioner_addresses": {
                    "type": "array",
                    "description": "Array of addresses for practitioners",
                    "items": {"type": "object"},
                    "examples": [[{"line": ["123 Main St"], "city": "Boston", "state": "MA"}]],
                    "default": [
                        {"line": ["123 Main St"], "city": "Boston", "state": "MA"},
                        {"line": ["123 Main St"], "city": "Boston", "state": "MA"},
                        {"line": ["789 Pine St"], "city": "Los Angeles", "state": "CA"},
                        {"line": ["321 Elm St"], "city": "Chicago", "state": "IL"},
                    ],
                },
                "specialty_codes": {
                    "type": "array",
                    "description": "Array of SNOMED CT specialty codes for practitioners",
                    "items": {"type": "string"},
                    "examples": [["394580004", "408459003", "394580004", "394580004"]],
                    "default": ["394580004", "408459003", "394580004"],
                },
                "specialty_displays": {
                    "type": "array",
                    "description": "Array of specialty display names for practitioners",
                    "items": {"type": "string"},
                    "examples": [["Clinical genetics", "Pediatric cardiology", "Clinical genetics", "Clinical genetics"]],
                    "default": ["Clinical genetics", "Pediatric cardiology", "Clinical genetics"],
                },
            },
        }


    def prepare_test_data(self) -> None:
        try:
            service_name = self.get_param("service_name")
            service_specialty_code = self.get_param("service_specialty_code", "1234567")


            practitioner_count = self.get_param("practitioner_count", 4)
            slot_count_per_practitioner = self.get_param("slot_count_per_practitioner", 3)
            slot_start_hour = self.get_param("slot_start_hour", 9)
            slot_end_hour = self.get_param("slot_end_hour", 12)
            slot_duration_hours = self.get_param("slot_duration_hours", 1)
            days_ahead = self.get_param("days_ahead", 1)
            free_slot_pattern = self.get_param("free_slot_pattern", "alternating")
            practitioner_family_names = self.get_param("practitioner_family_names", ["Smith", "Chen", "Garcia", "Patel"])
            practitioner_given_names = self.get_param("practitioner_given_names", [["John"], ["Wei"], ["Maria", "Isabel"], ["Rajesh"]])
            practitioner_genders = self.get_param("practitioner_genders", ["male", "female", "female", "male"])
            practitioner_languages = self.get_param("practitioner_languages", [["en"], ["en", "zh"], ["en", "es"], ["en", "hi"]])
            practitioner_addresses = self.get_param("practitioner_addresses", [
                {"line": ["123 Main St"], "city": "Boston", "state": "MA"},
                {"line": ["123 Main St"], "city": "Boston", "state": "MA"},
                {"line": ["789 Pine St"], "city": "Los Angeles", "state": "CA"},
                {"line": ["321 Elm St"], "city": "Chicago", "state": "IL"},
            ])
            specialty_codes = self.get_param("specialty_codes", ["394580004", "408459003", "394580004"])
            specialty_displays = self.get_param("specialty_displays", ["Clinical genetics", "Pediatric cardiology", "Clinical genetics"])


            # Adding the required  speciality code and display.
            specialty_codes.insert(0, service_specialty_code)
            specialty_displays.insert(0, service_name)

            # Create practitioners
            for k in range(practitioner_count):
                practitioner = {
                    "resourceType": "Practitioner",
                    "id": f"PROVIDER00{k+1:02d}",
                    "name": [{"use": "official", "family": practitioner_family_names[k], "given": practitioner_given_names[k]}],
                    "gender": practitioner_genders[k],
                    "communication": [{"coding": [{"system": "urn:ietf:bcp:47", "code": lang}]} for lang in practitioner_languages[k]],
                    "address": [{"use": "work", **practitioner_addresses[k]}],
                }
                self.upsert_to_fhir(practitioner)

            # Create schedules
            for k in range(practitioner_count):
                schedule = {
                    "resourceType": "Schedule",
                    "id": f"SCHEDULE00{k+1:02d}",
                    "actor": [{"reference": f"Practitioner/PROVIDER00{k+1:02d}"}],
                    "planningHorizon": {
                        "start": "2025-04-11T00:00:00Z",
                        "end": "2026-04-11T00:00:00Z",
                    },
                    "specialty": [
                        {
                            "coding": [
                                {
                                    "system": "http://snomed.info/sct",
                                    "code": specialty_codes[k],
                                    "display": specialty_displays[k],
                                }
                            ]
                        }
                    ],
                }
                self.upsert_to_fhir(schedule)

            # Create slots
            slot_id_counter = 1
            for k in range(practitioner_count):
                for i in range(slot_start_hour, slot_end_hour):
                    schedule_id = f"SCHEDULE00{k+1:02d}"
                    start = datetime.now(timezone.utc) + timedelta(days=days_ahead)
                    start = start.replace(hour=i, minute=0, second=0, microsecond=0)
                    end = start + timedelta(hours=slot_duration_hours)

                    start_str = start.strftime("%Y-%m-%dT%H:%M:%SZ")
                    end_str = end.strftime("%Y-%m-%dT%H:%M:%SZ")

                    # Determine slot status based on pattern
                    if free_slot_pattern == "even":
                        status = "free" if i % 2 == 0 else "busy"
                    elif free_slot_pattern == "odd":
                        status = "free" if i % 2 == 1 else "busy"
                    elif free_slot_pattern == "alternating":
                        status = "free" if (i + k) % 4 == 0 else "busy"
                    elif free_slot_pattern == "first":
                        status = "free" if i == slot_start_hour else "busy"
                    elif free_slot_pattern == "last":
                        status = "free" if i == slot_end_hour - 1 else "busy"
                    else:
                        status = "free" if (i + k) % 4 == 0 else "busy"

                    slot = {
                        "resourceType": "Slot",
                        "id": f"SLOT00{slot_id_counter:02d}",
                        "schedule": {"reference": f"Schedule/{schedule_id}"},
                        "start": start_str,
                        "end": end_str,
                        "status": status,
                            "specialty": [
                                {
                                    "coding": [
                                        {
                                            "system": "http://snomed.info/sct",
                                            "code": specialty_codes[k],
                                            "display": specialty_displays[k],
                                        }
                                    ]
                                }
                            ],
                            "serviceType": [
                                {
                                    "coding": [
                                        {
                                            "system": "http://snomed.info/sct",
                                            "code": specialty_codes[k],
                                            "display": specialty_displays[k],
                                        }
                                    ]
                                }
                            ],
                        }
                    self.upsert_to_fhir(slot)
                    slot_id_counter += 1

        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")




    def execute_human_agent(self) -> ExecutionResult:
        service_specialty_code = self.get_param("service_specialty_code", "1234567")
        service_name = self.get_param("service_name")

        # Find schedules with the specified specialty
        schedule_params = {"specialty": service_specialty_code}
        schedules_response = requests.get(
            f"{self.FHIR_SERVER_URL}/Schedule", headers=self.HEADERS, params=schedule_params
        )

        if schedules_response.status_code != 200:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"Failed to search schedules: {schedules_response.text}",
            )

        all_slots = []
        schedules_json = schedules_response.json()
        if "entry" in schedules_json:
            for schedule in schedules_json["entry"]:
                # Get free slots for this schedule
                slot_params = {
                    "schedule": f"Schedule/{schedule['resource']['id']}",
                    "status": "free",
                    "_sort": "start",
                }
                slots_response = requests.get(
                    f"{self.FHIR_SERVER_URL}/Slot", headers=self.HEADERS, params=slot_params
                )

                if slots_response.status_code != 200:
                    return ExecutionResult(
                        execution_success=False,
                        response_msg=f"Failed to search slots: {slots_response.text}",
                    )

                slots_json = slots_response.json()
                if "entry" in slots_json:
                    all_slots.extend(slots_json["entry"])

        if not all_slots:
            return ExecutionResult(
                execution_success=True,
                response_msg=f"No available {service_name} slots found",
            )

        return ExecutionResult(
            execution_success=True,
            response_msg=f"Found {len(all_slots)} available {service_name} slots: <SLOT_COUNT>{len(all_slots)}</SLOT_COUNT>",
        )


    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            # Structured-output assertions
            response_msg = execution_result.response_msg
            human_agent_response = self.execute_human_agent()
            if "<SLOT_COUNT>" not in human_agent_response.response_msg:
                service_name = self.get_param("service_name", "genetic counseling")
                assert f"no available {service_name} slots" in response_msg.lower(), f"Expected 'No available {service_name} slots found', got '{response_msg}'"
            else:
                assert response_msg is not None, "Expected to find response message"
                response_msg = response_msg.strip()
                assert "<SLOT_COUNT>" in response_msg, "Expected to find <SLOT_COUNT> tag"
                assert "</SLOT_COUNT>" in response_msg, "Expected to find </SLOT_COUNT> tag"
                slot_count = int(response_msg.split("<SLOT_COUNT>")[1].split("</SLOT_COUNT>")[0])
                expected_count = int(human_agent_response.response_msg.split("<SLOT_COUNT>")[1].split("</SLOT_COUNT>")[0])
                assert slot_count == expected_count, f"Expected slot_count {expected_count}, got {slot_count}"

            return TaskResult(
                task_success=True,
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



    def get_required_tool_call_sets(self) -> list:
        return [
            {"getAllResources": 0},
            {"getAllResources": 0, "getAllResources": 1},
            {"getAllResources": 0, "getResourceById": 1, "getAllResources": 2},
        ]

    def get_required_resource_types(self) -> list:
        return ["Slot"]

    def get_prohibited_tools(self) -> list:
        return ["createResource", "updateResource", "deleteResource"]

    def get_difficulty_level(self) -> int:
        return 2
