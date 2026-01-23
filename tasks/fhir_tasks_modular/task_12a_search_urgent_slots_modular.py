# task_12a_search_urgent_slots_modular.py

import os
import requests
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from tasks.fhir_tasks_modular.task_interface_modular import TaskInterfaceModular, TaskResult, ExecutionResult, TaskFailureMode


class SearchUrgentSlotsTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "12a"

    def get_task_name(self) -> str:
        return "Search Urgent Slots"

    def get_prompt(self) -> str:
        urgency_days = self.get_param("urgency_days")
        urgency_end_hour = self.get_param("urgency_end_hour")
        return f"""
Patient needs an urgent visit within the next {urgency_days} day{'s' if urgency_days > 1 else ''} from today, starting now and no later than {urgency_end_hour}:00 on the last day. Find all available slots in this time window.

After searching, return the number of available slots using the following format: <SLOT_COUNT>number</SLOT_COUNT>
If none found, return the exact sentence: No urgent slots available
"""


    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["urgency_days", "urgency_end_hour"],
            "properties": {
                "urgency_days": {
                    "type": "integer",
                    "description": "Number of days ahead to search for urgent slots",
                    "examples": [1, 2, 3],
                    "default": 1,
                    "minimum": 1,
                    "maximum": 7,
                },
                "urgency_end_hour": {
                    "type": "integer",
                    "description": "End hour for urgent slot search (24-hour format)",
                    "examples": [17, 18, 20],
                    "default": 17,
                    "minimum": 0,
                    "maximum": 23,
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
        urgency_days = self.get_param("urgency_days")
        urgency_end_hour = self.get_param("urgency_end_hour")
        
        start = datetime.now(timezone.utc)
        end = start + timedelta(days=urgency_days)
        end = end.replace(hour=urgency_end_hour, minute=0, second=0, microsecond=0)
        
        params = {
            "start": [
                f'gt{start.strftime("%Y-%m-%dT%H:%M:%SZ")}',
                f'lt{end.strftime("%Y-%m-%dT%H:%M:%SZ")}'
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
        if slots_found > 0:
            return ExecutionResult(
                execution_success=True,
                response_msg=f"Found {slots_found} available slots for urgent visit: <SLOT_COUNT>{slots_found}</SLOT_COUNT>"
            )
        else:
            return ExecutionResult(
                execution_success=True,
                response_msg="No urgent slots available"
            )


    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            # Structured-output assertions
            response_msg = execution_result.response_msg
            assert response_msg is not None, "Expected to find response message"
            response_msg = response_msg.strip()
            human_agent_response = self.execute_human_agent()
            if "<SLOT_COUNT>" not in human_agent_response.response_msg:
                assert "no urgent slots available" in response_msg.lower(), "Expected to find no available slots"
            else:
                assert "<SLOT_COUNT>" in response_msg, "Expected to find <SLOT_COUNT> tag"
                assert "</SLOT_COUNT>" in response_msg, "Expected to find </SLOT_COUNT> tag"
                slot_count = int(response_msg.split("<SLOT_COUNT>")[1].split("</SLOT_COUNT>")[0])
                expected_count = int(human_agent_response.response_msg.split("<SLOT_COUNT>")[1].split("</SLOT_COUNT>")[0])
                assert slot_count == expected_count, f"Expected slot_count {expected_count}, got {slot_count}"

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
