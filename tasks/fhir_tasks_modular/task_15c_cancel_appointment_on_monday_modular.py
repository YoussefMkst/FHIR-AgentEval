# task_15c_cancel_appointment_on_monday_modular.py

import requests
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from tasks.fhir_tasks_modular.task_interface_modular import TaskInterfaceModular, TaskResult, ExecutionResult, TaskFailureMode


class CancelAppointmentOnMondayTaskModular(TaskInterfaceModular):
    def get_task_id(self) -> str:
        return "15c"

    def get_task_name(self) -> str:
        return "Cancel Appointment On Monday"


    def get_prompt(self) -> str:
        patient_family = self.get_param("patient_family", "Doe")
        patient_given = self.get_param("patient_given", ["John"])
        return f"""
        Cancel the next Monday appointment for patient {' '.join(patient_given)} {patient_family} and free its slot.

        Return the cancelled appointment ID and freed slot ID using:
        <APPOINTMENT>appointment_id</APPOINTMENT>
        <SLOT_ID>slot_id</SLOT_ID>
        """.strip()

    def get_param_schema(self) -> Dict[str, Any]:
        return {
        "type": "object",
        "required": ["patient_family", "patient_given"],
        "properties": {
            # From YAML
            "patient_family": {"type": "string", "default": "Doe"},
            "patient_given": {"type": "array", "items": {"type": "string"}, "default": ["John"]},
            "patient_birth_date": {"type": "string", "default": "1990-06-15"},
            "patient_phone": {"type": "string", "default": "555-111-2222"},
            "practitioner_family": {"type": "string", "default": "Smith"},
            "practitioner_given": {"type": "array", "items": {"type": "string"}, "default": ["John"]},
            "practitioner_gender": {"type": "string", "default": "male", "enum": ["male","female","other","unknown"]},
            "first_appointment_day": {
                "type": "string",
                "default": "Monday",
                "enum": ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],
            },
            "first_appointment_hour": {"type": "integer", "default": 9, "minimum": 0, "maximum": 23},
            "second_appointment_day_offset": {"type": "integer", "default": 1, "minimum": 0, "maximum": 7},

            # Existing task options
            "appointment_hour": {"type": "integer", "default": 9, "minimum": 0, "maximum": 23},
            "duration_hours": {"type": "integer", "default": 1, "minimum": 1, "maximum": 8},
        },
        }


    def prepare_test_data(self) -> None:
        try:
            # YAML params
            pf = self.get_param("patient_family")
            pg = self.get_param("patient_given")
            pbd = self.get_param("patient_birth_date", "1990-06-15")
            pphone = self.get_param("patient_phone", "555-111-2222")

            prf = self.get_param("practitioner_family", "Smith")
            prg = self.get_param("practitioner_given", ["John"])
            pr_gender = self.get_param("practitioner_gender", "male")

            first_day = self.get_param("first_appointment_day", "Monday")
            first_hour = self.get_param("first_appointment_hour", 9)
            dur = self.get_param("duration_hours", 1)
            offset_days = self.get_param("second_appointment_day_offset", 1)

            # Upsert Patient/Practitioner
            patient = {
                "resourceType": "Patient",
                "id": "PAT001",
                "name": [{"family": pf, "given": pg}],
                "birthDate": pbd,
                "telecom": [{"system": "phone", "value": pphone}],
            }
            self.upsert_to_fhir(patient)

            practitioner = {
                "resourceType": "Practitioner",
                "id": "PROVIDER001",
                "name": [{"family": prf, "given": prg}],
                "gender": pr_gender,
            }
            self.upsert_to_fhir(practitioner)

            # Schedule (UTC)
            now = datetime.now(timezone.utc)
            schedule = {
                "resourceType": "Schedule",
                "id": "SCHEDULE001",
                "actor": [{"reference": "Practitioner/PROVIDER001"}],
                "planningHorizon": {
                    "start": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": (now + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            }
            self.upsert_to_fhir(schedule)

            # Compute next target weekday (UTC)
            day_map = {"Monday":0,"Tuesday":1,"Wednesday":2,"Thursday":3,"Friday":4,"Saturday":5,"Sunday":6}
            target_wd = day_map.get(first_day, 0)
            base = now + timedelta(days=(target_wd - now.weekday()) % 7)
            if base.date() == now.date():  # ensure strictly NEXT Monday if the cript is ran on a monday
                base += timedelta(days=7)
            base = base.replace(hour=first_hour, minute=0, second=0, microsecond=0)

            # First (Monday) busy slot + appointment
            slot1 = {
                "resourceType": "Slot",
                "id": "SLOT001",
                "schedule": {"reference": "Schedule/SCHEDULE001"},
                "start": base.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": (base + timedelta(hours=dur)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "busy",
            }
            self.upsert_to_fhir(slot1)

            appt1 = {
                "resourceType": "Appointment",
                "id": "APPOINTMENT001",
                "status": "booked",
                "slot": [{"reference": "Slot/SLOT001"}],
                "participant": [
                    {"actor": {"reference": "Patient/PAT001"}, "status": "accepted"},
                    {"actor": {"reference": "Practitioner/PROVIDER001"}, "status": "accepted"},
                ],
                "start": slot1["start"],
                "end": slot1["end"],
            }
            self.upsert_to_fhir(appt1)

            # Second booked appointment (to ensure logic chooses Monday specifically)
            base2 = base + timedelta(days=offset_days)
            slot2 = {
                "resourceType": "Slot",
                "id": "SLOT002",
                "schedule": {"reference": "Schedule/SCHEDULE001"},
                "start": base2.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": (base2 + timedelta(hours=dur)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "busy",
            }
            self.upsert_to_fhir(slot2)

            appt2 = {
                "resourceType": "Appointment",
                "id": "APPOINTMENT002",
                "status": "booked",
                "slot": [{"reference": "Slot/SLOT002"}],
                "participant": [
                    {"actor": {"reference": "Patient/PAT001"}, "status": "accepted"},
                    {"actor": {"reference": "Practitioner/PROVIDER001"}, "status": "accepted"},
                ],
                "start": slot2["start"],
                "end": slot2["end"],
            }
            self.upsert_to_fhir(appt2)

        except Exception as e:
            raise Exception(f"Failed to prepare test data: {str(e)}")

# ------------------------------------------------------------------------------------------------

    # def execute_human_agent(self) -> ExecutionResult:
    #     try:
    #         # Inputs
    #         pf = self.get_param("patient_family", "Doe")
    #         pg = self.get_param("patient_given", ["John"])
    #         hour = self.get_param("first_appointment_hour", 9)
    #         dur = self.get_param("duration_hours", 1)

    #         # Resolve Patient ID by name
    #         p = requests.get(
    #             f"{self.FHIR_SERVER_URL}/Patient",
    #             headers=self.HEADERS,
    #             params={"family": pf, "given": pg[0]},
    #         )
    #         if p.status_code != 200 or not p.json().get("entry"):
    #             return ExecutionResult(False, f"Patient {' '.join(pg)} {pf} not found")
    #         patient_id = p.json()["entry"][0]["resource"]["id"]

    #         # Compute next Monday window (UTC)
    #         now = datetime.now(timezone.utc)
    #         target_wd = 0  # Monday
    #         monday = now + timedelta(days=(target_wd - now.weekday()) % 7)
    #         if monday.date() == now.date():  # ensure strictly next Monday
    #             monday += timedelta(days=7)
    #         start_dt = monday.replace(hour=hour, minute=0, second=0, microsecond=0)
    #         end_dt = start_dt + timedelta(hours=dur)

    #         # Search booked Appointment for that patient within window
    #         params = [
    #             ("actor", f"Patient/{patient_id}"),
    #             ("status", "booked"),
    #             ("date", f"ge{start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}"),
    #             ("date", f"lt{end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}"),
    #         ]
    #         a = requests.get(f"{self.FHIR_SERVER_URL}/Appointment", headers=self.HEADERS, params=params)
    #         if a.status_code != 200:
    #             return ExecutionResult(
    #                 execution_success=False,
    #                 response_msg=f"Failed to search appointments: {a.text}",
    #             )
    #         entries = a.json().get("entry", [])
    #         if not entries:
    #             return ExecutionResult(
    #                 execution_success=False,
    #                 response_msg="No Monday appointment to cancel",
    #             )

    #         appt = entries[0]["resource"]
    #         appt_id = appt["id"]
    #         slot_ref = appt["slot"][0]["reference"]
    #         slot_id = slot_ref.split("/")[-1]

    #         # Cancel appointment
    #         appt["status"] = "cancelled"
    #         put_appt = requests.put(f"{self.FHIR_SERVER_URL}/Appointment/{appt_id}", headers=self.HEADERS, json=appt)
    #         if put_appt.status_code not in (200, 201):
    #             return ExecutionResult(
    #                 execution_success=False,
    #                 response_msg=f"Failed to cancel appointment: {put_appt.text}",
    #             )

    #         # Free slot
    #         s = requests.get(f"{self.FHIR_SERVER_URL}/Slot/{slot_id}", headers=self.HEADERS)
    #         if s.status_code != 200:
    #             return ExecutionResult(
    #                 execution_success=False,
    #                 response_msg=f"Failed to read slot: {s.text}",
    #             )
    #         slot = s.json()
    #         slot["status"] = "free"
    #         put_slot = requests.put(f"{self.FHIR_SERVER_URL}/Slot/{slot_id}", headers=self.HEADERS, json=slot)
    #         if put_slot.status_code not in (200, 201):
    #             return ExecutionResult(
    #                 execution_success=False,
    #                 response_msg=f"Failed to free slot: {put_slot.text}",
    #             )

    #         return ExecutionResult(
    #             execution_success=True,
    #             response_msg=(
    #                 "Successfully cancelled appointment "
    #                 f"<APPOINTMENT>{appt_id}</APPOINTMENT> and freed slot "
    #                 f"<SLOT_ID>{slot_id}</SLOT_ID>"
    #             ),
    #         )
    #     except Exception as e:
    #         return ExecutionResult(
    #             execution_success=False,
    #             response_msg=f"Error: {str(e)}",
    #         )


    # ------------------------------------------------------------------------------------------------
    def execute_human_agent(self) -> ExecutionResult:
        try:
            # --- Inputs from params
            hour = self.get_param("first_appointment_hour", 9)

            # --- Compute the next Monday at the configured hour (UTC, strictly NEXT)
            now = datetime.now(timezone.utc)
            target_wd = 0  # Monday
            monday = now + timedelta(days=(target_wd - now.weekday()) % 7)
            if monday.date() == now.date():  # if today is Monday, move to the following Monday
                monday += timedelta(days=7)
            start_dt = monday.replace(hour=hour, minute=0, second=0, microsecond=0)

            # --- 1) Find the exact Slot on the provider's schedule
            slot_q = {
                "schedule": "Schedule/SCHEDULE001",
                "start": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            s = requests.get(f"{self.FHIR_SERVER_URL}/Slot", headers=self.HEADERS, params=slot_q)
            if s.status_code != 200:
                return ExecutionResult(False, f"Failed to find Monday slot: {s.text}")
            slot_entries = s.json().get("entry", [])
            if not slot_entries:
                return ExecutionResult(False, "No Monday slot found at the expected time")
            slot_id = slot_entries[0]["resource"]["id"]

            # --- 2) Fetch the booked Appointment via that slot
            a = requests.get(
                f"{self.FHIR_SERVER_URL}/Appointment",
                headers=self.HEADERS,
                params=[("slot", f"Slot/{slot_id}"), ("status", "booked")],
            )
            if a.status_code != 200:
                return ExecutionResult(False, f"Failed to search appointment by slot: {a.text}")
            entries = a.json().get("entry", [])
            if not entries:
                return ExecutionResult(False, "No Monday appointment to cancel")

            appt = entries[0]["resource"]
            appt_id = appt["id"]

            # --- 3) Cancel the appointment
            appt["status"] = "cancelled"
            put_appt = requests.put(f"{self.FHIR_SERVER_URL}/Appointment/{appt_id}", headers=self.HEADERS, json=appt)
            if put_appt.status_code not in (200, 201):
                return ExecutionResult(False, f"Failed to cancel appointment: {put_appt.text}")

            # --- 4) Free the slot
            slot_resp = requests.get(f"{self.FHIR_SERVER_URL}/Slot/{slot_id}", headers=self.HEADERS)
            if slot_resp.status_code != 200:
                return ExecutionResult(False, f"Failed to read slot: {slot_resp.text}")
            slot = slot_resp.json()
            slot["status"] = "free"
            put_slot = requests.put(f"{self.FHIR_SERVER_URL}/Slot/{slot_id}", headers=self.HEADERS, json=slot)
            if put_slot.status_code not in (200, 201):
                return ExecutionResult(False, f"Failed to free slot: {put_slot.text}")

            # --- 5) Return tagged IDs for validator
            return ExecutionResult(
                True,
                f"Successfully cancelled appointment <APPOINTMENT>{appt_id}</APPOINTMENT> "
                f"and freed slot <SLOT_ID>{slot_id}</SLOT_ID>"
            )

        except Exception as e:
            return ExecutionResult(False, f"Error: {str(e)}")



    def validate_response(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            msg = (execution_result.response_msg or "").strip()
            assert "<APPOINTMENT>" in msg and "</APPOINTMENT>" in msg, "Missing <APPOINTMENT> tag"
            assert "<SLOT_ID>" in msg and "</SLOT_ID>" in msg, "Missing <SLOT_ID> tag"
            appt_id = msg.split("<APPOINTMENT>")[1].split("</APPOINTMENT>")[0]
            slot_id = msg.split("<SLOT_ID>")[1].split("</SLOT_ID>")[0]

            a = requests.get(f"{self.FHIR_SERVER_URL}/Appointment/{appt_id}", headers=self.HEADERS)
            assert a.status_code == 200 and a.json().get("status") == "cancelled", "Appointment not cancelled"
            s = requests.get(f"{self.FHIR_SERVER_URL}/Slot/{slot_id}", headers=self.HEADERS)
            assert s.status_code == 200 and s.json().get("status") == "free", "Slot not freed"

            return TaskResult(task_success=True, task_id=self.get_task_id(), task_name=self.get_task_name(), execution_result=execution_result)
        except AssertionError as e:
            return TaskResult(task_success=False, assertion_error_message=str(e), task_id=self.get_task_id(), task_name=self.get_task_name(), execution_result=execution_result)
        except Exception as e:
            return TaskResult(task_success=False, assertion_error_message=f"Unexpected error: {str(e)}", task_id=self.get_task_id(), task_name=self.get_task_name(), execution_result=execution_result)


    def validate_response_light(self, execution_result: ExecutionResult) -> TaskResult:
        try:
            msg = (execution_result.response_msg or "").strip()
            assert "<APPOINTMENT>" in msg and "</APPOINTMENT>" in msg, "Missing <APPOINTMENT> tag"
            assert "<SLOT_ID>" in msg and "</SLOT_ID>" in msg, "Missing <SLOT_ID> tag"
            appt_id = msg.split("<APPOINTMENT>")[1].split("</APPOINTMENT>")[0]
            slot_id = msg.split("<SLOT_ID>")[1].split("</SLOT_ID>")[0]

            a = requests.get(f"{self.FHIR_SERVER_URL}/Appointment/{appt_id}", headers=self.HEADERS)
            assert a.status_code == 200, "Appointment not found"
            assert a.json().get("status"), "Appointment must have status"
            
            s = requests.get(f"{self.FHIR_SERVER_URL}/Slot/{slot_id}", headers=self.HEADERS)
            assert s.status_code == 200, "Slot not found"
            assert s.json().get("status"), "Slot must have status"

            return TaskResult(task_success=True, task_id=self.get_task_id(), task_name=self.get_task_name(), execution_result=execution_result)
        except AssertionError as e:
            return TaskResult(task_success=False, assertion_error_message=f"Light validation failed: {str(e)}", task_id=self.get_task_id(), task_name=self.get_task_name(), execution_result=execution_result)
        except Exception as e:
            return TaskResult(task_success=False, assertion_error_message=f"Light validation error: {str(e)}", task_id=self.get_task_id(), task_name=self.get_task_name(), execution_result=execution_result)


    def get_required_tool_call_sets(self) -> list:
        return [
            {"searchResources": 0, "searchResources": 1, "updateResource": 2, "getResourceById": 3, "updateResource": 4},
            {"searchResources": 0, "updateResource": 1, "getResourceById": 2, "updateResource": 3},
            {"searchResources": 0, "searchResources": 1, "getResourceById": 2, "updateResource": 3, "getResourceById": 4, "updateResource": 5},
            {"searchResources": 0, "updateResource": 1, "updateResource": 2},
        ]

    def get_required_resource_types(self) -> list:
        return ["Appointment", "Slot"]

    def get_prohibited_tools(self) -> list:
        return ["createResource", "deleteResource"]

    def get_difficulty_level(self) -> int:
        return 3


