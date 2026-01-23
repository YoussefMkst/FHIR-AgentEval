# task_11d_search_most_recent_slots_by_provider_modular.py

import requests
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from tasks.fhir_tasks_modular.task_interface_modular import TaskInterfaceModular, TaskResult, ExecutionResult, TaskFailureMode


class FindSlotsByProviderTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "11d"

    def get_task_name(self) -> str:
        return "Find Slots by Provider"

    def get_prompt(self) -> str:
        provider_family = self.get_param("provider_family")
        provider_given = self.get_param("provider_given")
        return f"""

Find the most recent available slots for Dr. {' '.join(provider_given)} {provider_family}.

If found, return the first slot ID using: <SLOT>slot_id</SLOT>
If none found, return the exact sentence: No available slots found
"""

    def get_param_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["provider_family", "provider_given", "provider_gender"],
            "properties": {
                "provider_family": {
                    "type": "string",
                    "description": "Provider family name",
                    "examples": ["Anderson", "Taylor", "Martinez"],
                    "default": "Anderson",
                },
                "provider_given": {
                    "type": "array",
                    "description": "Provider given names",
                    "items": {"type": "string"},
                    "examples": [["Jennifer"], ["Christopher"], ["Sofia"]],
                    "default": ["Jennifer"],
                },
                "provider_gender": {
                    "type": "string",
                    "description": "Provider gender",
                    "examples": ["female", "male", "other"],
                    "default": "female",
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
            },
        }


    def prepare_test_data(self) -> None:
        try:
            provider_family = self.get_param("provider_family")
            provider_given = self.get_param("provider_given")
            slot_start_hour = self.get_param("slot_start_hour", 9)
            slot_end_hour = self.get_param("slot_end_hour", 12)
            slot_duration_hours = self.get_param("slot_duration_hours", 1)
            days_ahead = self.get_param("days_ahead", 1)

            # Practitioner
            practitioner = {
                "resourceType": "Practitioner",
                "id": "PROVIDER001",
                "name": [{"use": "official", "family": provider_family, "given": provider_given}],
                "gender": "female",
                "communication": [{"coding": [{"system": "urn:ietf:bcp:47", "code": "en"}]}],
            }
            self.upsert_to_fhir(practitioner)

            # Schedule
            start = datetime.now(timezone.utc)
            end = start + timedelta(days=365)
            schedule = {
                "resourceType": "Schedule",
                "id": "SCHEDULE001",
                "actor": [{"reference": "Practitioner/PROVIDER001"}],
                "planningHorizon": {
                    "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            }
            self.upsert_to_fhir(schedule)

            # Slots
            slot_id_counter = 1
            for i in range(slot_start_hour, slot_end_hour):
                begin = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).replace(hour=i, minute=0, second=0, microsecond=0)
                finish = begin + timedelta(hours=slot_duration_hours)
                slot = {
                    "resourceType": "Slot",
                    "id": f"SLOT00{slot_id_counter:02d}",
                    "schedule": {"reference": "Schedule/SCHEDULE001"},
                    "start": begin.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": finish.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "status": "free" if i % 2 == 0 else "busy",
                }
                self.upsert_to_fhir(slot)
                slot_id_counter += 1
        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")



    def execute_human_agent(self) -> ExecutionResult:
        # Find free slots for the provider
        params = {
            "schedule": "Schedule/SCHEDULE001",
            "status": "free",
            "_sort": "start",
        }
        response = requests.get(f"{self.FHIR_SERVER_URL}/Slot", headers=self.HEADERS, params=params)
        if response.status_code != 200:
            return ExecutionResult(execution_success=False, response_msg=f"Failed to search slots: {response.text}")
        data = response.json()
        entries = data.get("entry", [])
        if not entries:
            return ExecutionResult(execution_success=True, response_msg="No available slots found")
        first_slot_id = entries[0]["resource"]["id"]
        return ExecutionResult(execution_success=True, response_msg=f"Found available slot <SLOT>{first_slot_id}</SLOT>")



    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            msg = execution_result.response_msg or ""
            expected_msg = self.execute_human_agent().response_msg or ""
            
            # Handle "no slots found" case
            if "No available slots found" in msg and "No available slots found" in expected_msg:
                return TaskResult(task_success=True, task_id=self.get_task_id(), task_name=self.get_task_name(), execution_result=execution_result)
            if "No available slots found" in msg and "No available slots found" not in expected_msg:
                return TaskResult(task_success=False, assertion_error_message="Agent found no slots but slots exist", task_id=self.get_task_id(), task_name=self.get_task_name(), execution_result=execution_result)
            if "No available slots found" not in msg and "No available slots found" in expected_msg:
                return TaskResult(task_success=False, assertion_error_message="Agent found slots when none should exist", task_id=self.get_task_id(), task_name=self.get_task_name(), execution_result=execution_result)
            
            # Handle slot ID comparison case
            assert "<SLOT>" in msg and "</SLOT>" in msg, "Expected to find <SLOT> tag"
            assert "<SLOT>" in expected_msg and "</SLOT>" in expected_msg, "Expected to find <SLOT> tag in human response"
            slot_id = msg.split("<SLOT>")[1].split("</SLOT>")[0]
            expected_slot_id = expected_msg.split("<SLOT>")[1].split("</SLOT>")[0]
            assert slot_id == expected_slot_id, f"Expected slot_id {expected_slot_id}, got {slot_id}"
            return TaskResult(task_success=True, task_id=self.get_task_id(), task_name=self.get_task_name(), execution_result=execution_result)
        except AssertionError as e:
            return TaskResult(task_success=False, assertion_error_message=str(e), task_id=self.get_task_id(), task_name=self.get_task_name(), execution_result=execution_result)
        except Exception as e:
            return TaskResult(task_success=False, assertion_error_message=f"Unexpected error: {str(e)}", task_id=self.get_task_id(), task_name=self.get_task_name(), execution_result=execution_result)



    def get_required_tool_call_sets(self) -> list:
        return [
            {"searchResources": 0},
            {"searchResources": 0, "getResourceById": 1},
        ]

    def get_required_resource_types(self) -> list:
        return ["Slot"]

    def get_prohibited_tools(self) -> list:
        return ["createResource", "updateResource", "deleteResource"]

    def get_difficulty_level(self) -> int:
        return 3


