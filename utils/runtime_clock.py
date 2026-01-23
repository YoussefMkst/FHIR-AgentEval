from datetime import datetime, timezone

additional_instructions = "When searching by a person’s name in FHIR or creating a resource, never use a single name='First Last'; always split into family=<last> and given=<first> (or name=<first>&name=<last>)."


def _build_clock_block() -> str:
    now_utc = datetime.now(timezone.utc)
    utc_now = now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    weekday = now_utc.strftime('%A')

    return (
        "## Runtime clock\n"
        f"- UTC now: {utc_now} (weekday: {weekday})\n"
        "Note: Use ISO-8601 instants with timezone for FHIR times (e.g., 2025-10-13T09:00:00Z).\n"
        "You must always stick to FHIR R4 specifications for all requests to the FHIR server.\n"
    )