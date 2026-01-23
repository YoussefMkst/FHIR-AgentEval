# task_12c_search_followup_slots_modular.py

import os
import requests
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from tasks.fhir_tasks_modular.task_interface_modular import TaskInterfaceModular, TaskResult, ExecutionResult, TaskFailureMode


class SearchFollowupSlotsTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "12c"

    def get_task_name(self) -> str:
        return "Search Follow-up Slots"

    def get_prompt(self) -> str:
        followup_days = self.get_param("followup_days")
        followup_duration_days = self.get_param("followup_duration_days")
        return f"""

Find available follow-up slots for a patient about {followup_days} day{'s' if followup_days > 1 else ''} from now, within a {followup_duration_days}-day window starting then.
After searching, return all slot IDs using the following format: <SLOT_IDS>id1,id2,…</SLOT_IDS>
If none found, return the exact sentence: No available follow-up slots found
"""


    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["followup_days", "followup_duration_days"],
            "properties": {
                "followup_days": {
                    "type": "integer",
                    "description": "Number of days ahead to search for follow-up slots",
                    "examples": [30, 28, 35],
                    "default": 30,
                    "minimum": 7,
                    "maximum": 90,
                },
                "followup_duration_days": {
                    "type": "integer",
                    "description": "Duration of the follow-up search window in days",
                    "examples": [1, 2, 3],
                    "default": 1,
                    "minimum": 1,
                    "maximum": 7,
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
                "avoid_weekends": {
                    "type": "boolean",
                    "description": "Whether to avoid weekends when searching for follow-up slots",
                    "examples": [True, False],
                    "default": True,
                },
            },
        }

    def prepare_test_data(self) -> None:
        try:
            practitioner_family = self.get_param("practitioner_family", "Smith")
            practitioner_given = self.get_param("practitioner_given", ["John"])
            practitioner_gender = self.get_param("practitioner_gender", "male")
            schedule_days_ahead = self.get_param("schedule_days_ahead", 45)
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

            # Create slots for the specified number of days ahead
            j = 1
            for x in range(schedule_days_ahead):
                for i in range(slot_start_hour, slot_end_hour):
                    slot_start = datetime.now(timezone.utc) + timedelta(days=x)
                    
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
        followup_days = self.get_param("followup_days")
        followup_duration_days = self.get_param("followup_duration_days")
        search_start_hour = self.get_param("search_start_hour", 9)
        avoid_weekends = self.get_param("avoid_weekends", True)
        
        start = datetime.now(timezone.utc) + timedelta(days=followup_days)
        if avoid_weekends and start.weekday() > 4:  # If weekend, move to next weekday
            start = start + timedelta(days=(7 - start.weekday()))
        start = start.replace(hour=search_start_hour, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=followup_duration_days)
        
        params = {
            "start": [
                f'ge{start.strftime("%Y-%m-%dT%H:%M:%SZ")}',
                f'le{end.strftime("%Y-%m-%dT%H:%M:%SZ")}'
            ],
            "status": "free"
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
        slots_found = response_json.get('total', 0)
        if slots_found == 0:
            return ExecutionResult(
                execution_success=True,
                response_msg="No available follow-up slots found"
            )
        else:
            slot_ids = [slot['resource']['id'] for slot in response_json.get('entry', [])]
            return ExecutionResult(
                execution_success=True,
                response_msg=f"Found {slots_found} available follow-up slots: <SLOT_IDS>{','.join(slot_ids)}</SLOT_IDS>"
            )



    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            # Additional eval logic
            response_msg = execution_result.response_msg.strip()
            assert response_msg is not None, "Expected to find response message"
            human_agent_response = self.execute_human_agent()
            if "<SLOT_IDS>" not in human_agent_response.response_msg:
                assert "no available follow-up slots" in response_msg.lower(), "Expected to find no available follow-up slots"
            else:
                assert "<SLOT_IDS>" in response_msg, "Expected to find <SLOT_IDS> tag"
                assert "</SLOT_IDS>" in response_msg, "Expected to find </SLOT_IDS> tag"
                returned_ids = response_msg.split("<SLOT_IDS>")[1].split("</SLOT_IDS>")[0].split(",")
                expected_ids = human_agent_response.response_msg.split("<SLOT_IDS>")[1].split("</SLOT_IDS>")[0].split(",")
                # Normalize whitespace (trim) and drop empty entries
                returned_ids = [s.strip() for s in returned_ids if s.strip()]
                expected_ids = [s.strip() for s in expected_ids if s.strip()]

                assert sorted(returned_ids) == sorted(expected_ids), f"Expected slot_ids {sorted(expected_ids)}, got {sorted(returned_ids)}"
                
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
