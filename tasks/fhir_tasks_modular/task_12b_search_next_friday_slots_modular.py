# task_12b_search_next_friday_slots_modular.py

import os
import requests
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from tasks.fhir_tasks_modular.task_interface_modular import TaskInterfaceModular, TaskResult, ExecutionResult, TaskFailureMode


class SearchNextFridaySlotsTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "12b"


    def get_task_name(self) -> str:
        return "Search Next Friday Slots"


    def get_prompt(self) -> str:
        target_day = self.get_param("target_day")
        return f"""
    Patient needs a general visit on next {target_day}. Find all available slots.

    After searching, return all slot IDs using the following format: <SLOT_IDS>id1,id2,…</SLOT_IDS>
    If none found, return the exact sentence: No available slots for next {target_day}
    """


    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["target_day"],
            "properties": {
                "target_day": {
                    "type": "string",
                    "description": "Target day of the week to search for slots",
                    "examples": ["Friday", "Monday", "Wednesday"],
                    "default": "Friday",
                    "enum": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
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
                "schedule_days_ahead": {
                    "type": "integer",
                    "description": "Number of days ahead to create schedule",
                    "examples": [35, 30, 60],
                    "default": 35,
                    "minimum": 30,
                    "maximum": 90,
                },
                "slot_start_hour": {
                    "type": "integer",
                    "description": "Starting hour for slots (24-hour format)",
                    "examples": [9, 8, 10],
                    "default": 9,
                    "minimum": 0,
                    "maximum": 23,
                },
                "slot_end_hour": {
                    "type": "integer",
                    "description": "Ending hour for slots (24-hour format)",
                    "examples": [12, 17, 18],
                    "default": 12,
                    "minimum": 0,
                    "maximum": 23,
                },
                "slot_duration_hours": {
                    "type": "integer",
                    "description": "Duration of each slot in hours",
                    "examples": [1, 2],
                    "default": 1,
                    "minimum": 1,
                    "maximum": 8,
                },
                "weekdays_only": {
                    "type": "boolean",
                    "description": "Whether to create slots only on weekdays",
                    "examples": [True, False],
                    "default": True,
                },
                "free_slot_pattern": {
                    "type": "string",
                    "description": "Pattern for determining free slots",
                    "examples": ["alternating", "even", "odd"],
                    "default": "alternating",
                    "enum": ["even", "odd", "alternating", "first", "last"],
                },
                "search_start_hour": {
                    "type": "integer",
                    "description": "Starting hour for search (24-hour format)",
                    "examples": [9, 8, 10],
                    "default": 9,
                    "minimum": 0,
                    "maximum": 23,
                },
                "search_end_hour": {
                    "type": "integer",
                    "description": "Ending hour for search (24-hour format)",
                    "examples": [17, 18, 20],
                    "default": 17,
                    "minimum": 0,
                    "maximum": 23,
                },
            },
        }


    def prepare_test_data(self) -> None:
        try:
            practitioner_family = self.get_param("practitioner_family", "Smith")
            practitioner_given = self.get_param("practitioner_given", ["John"])
            practitioner_gender = self.get_param("practitioner_gender", "male")
            schedule_days_ahead = self.get_param("schedule_days_ahead", 35)
            slot_start_hour = self.get_param("slot_start_hour", 9)
            slot_end_hour = self.get_param("slot_end_hour", 12)
            slot_duration_hours = self.get_param("slot_duration_hours", 1)
            weekdays_only = self.get_param("weekdays_only", True)
            free_slot_pattern = self.get_param("free_slot_pattern", "alternating")

            # Create test practitioner
            practitioner = {
                "resourceType": "Practitioner",
                "id": "PROVIDER001",
                "name": [{"use": "official", "family": practitioner_family, "given": practitioner_given}],
                "gender": practitioner_gender,
            }
            self.upsert_to_fhir(practitioner)

            # Create schedule
            schedule = {
                "resourceType": "Schedule",
                "id": "SCHEDULE001",
                "actor": [{"reference": "Practitioner/PROVIDER001"}],
                "planningHorizon": {
                    "start": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": (datetime.now(timezone.utc) + timedelta(days=schedule_days_ahead)).strftime("%Y-%m-%dT%H:%M:%SZ")
                }
            }
            self.upsert_to_fhir(schedule)

            # Get current date
            current_date = datetime.now(timezone.utc)
            # Create slots for the specified number of days ahead
            j = 1
            for x in range(schedule_days_ahead):
                for i in range(slot_start_hour, slot_end_hour):
                    slot_start = current_date + timedelta(days=x)
                    
                    # Apply weekday filter if specified
                    if weekdays_only and slot_start.weekday() >= 5:  # Saturday = 5, Sunday = 6
                        continue
                    
                    slot_start = slot_start.replace(hour=i, minute=0, second=0, microsecond=0)
                    slot_end = slot_start + timedelta(hours=slot_duration_hours)
                    
                    # Determine slot status based on pattern
                    if free_slot_pattern == "even":
                        status = "free" if i % 2 == 0 else "busy"
                    elif free_slot_pattern == "odd":
                        status = "free" if i % 2 == 1 else "busy"
                    elif free_slot_pattern == "alternating":
                        status = "free" if (i + x) % 2 == 0 else "busy"
                    elif free_slot_pattern == "first":
                        status = "free" if i == slot_start_hour else "busy"
                    elif free_slot_pattern == "last":
                        status = "free" if i == slot_end_hour - 1 else "busy"
                    else:
                        status = "free" if (i + x) % 2 == 0 else "busy"
                    
                    slot = {
                        "resourceType": "Slot",
                        "id": f"SLOT00{j}",
                        "schedule": {"reference": "Schedule/SCHEDULE001"},
                        "start": slot_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "end": slot_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "status": status
                    }
                    self.upsert_to_fhir(slot)
                    j += 1

        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")



    def execute_human_agent(self) -> ExecutionResult:
        target_day = self.get_param("target_day")
        search_start_hour = self.get_param("search_start_hour", 9)
        search_end_hour = self.get_param("search_end_hour", 17)
        
        # Map day names to weekday numbers (Monday = 0, Sunday = 6)
        day_mapping = {
            "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
            "Friday": 4, "Saturday": 5, "Sunday": 6
        }
        target_weekday = day_mapping.get(target_day, 4)  # Default to Friday
        
        # Get current date in UTC
        now_utc = datetime.now(timezone.utc)
        next_target_date = now_utc + timedelta(days=(target_weekday - now_utc.weekday()) % 7)
        # Ensure strictly NEXT (not today if today is friday)
        if next_target_date.date() == now_utc.date():
            next_target_date += timedelta(days=7)

        start_dt = next_target_date.replace(hour=search_start_hour, minute=0, second=0, microsecond=0)
        end_dt = next_target_date.replace(hour=search_end_hour, minute=0, second=0, microsecond=0)

        params = {
            "start": [
                f'ge{start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")}',
                f'le{end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")}',
            ],
            "status": "free",
        }
                
        response = requests.get(
            f"{self.FHIR_SERVER_URL}/Slot",
            headers=self.HEADERS,
            params=params
        )
        
        if response.status_code != 200:
            return ExecutionResult(
                execution_success=False,
                response_msg=f"Failed to search slots: {response.text}"
            )

        response_json = response.json()
        slots = response_json.get('entry', [])
        if not slots:
            return ExecutionResult(
                execution_success=True,
                response_msg=f"No available slots for next {target_day}"
            )

        slot_ids = [e['resource']['id'] for e in slots]
        ids_str = ",".join(slot_ids)
        return ExecutionResult(
            execution_success=True,
            response_msg=(
                f"Found {len(slot_ids)} available slots for next {target_day}: "
                f"<SLOT_IDS>{ids_str}</SLOT_IDS>"
            )
        )



    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            # Additional eval logic
            response_msg = execution_result.response_msg.strip()
            assert response_msg is not None, "Expected to find response message"
            human_agent_response = self.execute_human_agent()
            if "<SLOT_IDS>" not in human_agent_response.response_msg:
                target_day = self.get_param("target_day")
                assert f"no available slots for next {target_day.lower()}" in response_msg.lower(), f"Expected to find no available slots for next {target_day}"
            else:
                assert "<SLOT_IDS>" in response_msg, "Expected to find <SLOT_IDS> tag"
                assert "</SLOT_IDS>" in response_msg, "Expected to find </SLOT_IDS> tag"
                returned_ids = response_msg.split("<SLOT_IDS>")[1].split("</SLOT_IDS>")[0].split(",")
                expected_ids = human_agent_response.response_msg.split("<SLOT_IDS>")[1].split("</SLOT_IDS>")[0].split(",")
                assert sorted(returned_ids) == sorted(expected_ids), f"Expected slot_ids {expected_ids}, got {returned_ids}"
            
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
            {"searchResources": 0}
        ]

    def get_required_resource_types(self) -> list:
        return ["Slot"]

    def get_prohibited_tools(self) -> list:
        return ["createResource", "updateResource", "deleteResource"]

    def get_difficulty_level(self) -> int:
        return 2
