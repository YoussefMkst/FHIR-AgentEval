"""
Soft Validator - LLM-based companion validator for FHIR tasks.

This module provides an independent judgment of task success based on execution logs,
comparing it to the official validator to identify evaluation quality issues like:
- validator_too_strict: Agent succeeded but validator failed (false negatives)
- validator_too_loose: Agent failed but validator passed (false positives)

The soft validator judges based only on server evidence (HTTP responses, resource IDs)
rather than deterministic checks, helping identify when validators are misconfigured.
"""

from __future__ import annotations

import os
import json
import inspect
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, Literal, Type

from dotenv import load_dotenv
from openai import OpenAI

# Load .env file from environment directory at module import
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / "environment" / ".env"
load_dotenv(ENV_PATH)


@dataclass
class SoftValidationResult:
    """Result from soft validation with judgment flag and explanation."""
    
    flag: Literal[
        "agreement_success",      # Both validator and soft judge agree: task succeeded
        "agreement_failure",      # Both validator and soft judge agree: task failed
        "validator_too_strict",   # Validator failed but soft judge passed (false negative)
        "validator_too_loose",    # Validator passed but soft judge failed (false positive)
        "unclear"                 # Insufficient evidence to make judgment
    ]
    justification: str           # Explanation of the judgment
    validator_result: bool       # Official validator result for reference

     # New fields:
    last_tool_error_type: Literal[
        "none",          # last FHIR tool call looks fine / appropriate
        "syntax_error",  # FHIR-level syntax / schema / parameter issues
        "logical_error", # syntactically ok, but wrong for the task logic
        "unclear"        # not enough info
    ]
    last_tool_error_explanation: str


def soft_validate(
    task_class: Type,
    execution_log: Dict[str, Any],
    model: str = "o3"
) -> SoftValidationResult:
    """
    Judge task success based on execution logs using an LLM.
    
    Args:
        task_class: The task class with get_prompt() and validate_response() methods
        execution_log: The JSON execution log containing tool_calls, final_text, task_result
        model: OpenAI model to use for judgment (default: gpt-4o-mini)
    
    Returns:
        SoftValidationResult with flag, justification, and validator result
    """
    # Extract validator result from logs
    validator_result = execution_log.get('task_result', {}).get('task_success', False)
    
    # Get task source code
    task_source = inspect.getsource(task_class)
    
    # Extract last tool call for error analysis
    last_tool = _extract_last_tool_call(execution_log)
    
    # Build the prompt for the LLM judge
    prompt = _build_judge_prompt(task_source, execution_log, validator_result, last_tool)
    
    # Get LLM judgment
    print("Calling LLM judge...")
    llm_response = _call_llm_judge(prompt, model)
    
    # Map LLM judgment + validator result to flag
    flag = _determine_flag(llm_response['judgment'], validator_result)
    
    return SoftValidationResult(
        flag=flag,
        justification=llm_response['justification'],
        validator_result=validator_result,
        last_tool_error_type=llm_response.get('last_tool_error_type', 'unclear'),
        last_tool_error_explanation=llm_response.get('last_tool_error_explanation', 'No explanation provided')
    )


def _extract_last_tool_call(execution_log: Dict[str, Any]) -> Dict[str, Any] | None:
    """Extract the last FHIR MCP tool call from raw_logs for error analysis.
    
    Only considers FHIR MCP tools: listResourceTypes, getResourceById, searchResources,
    createResource, updateResource, deleteResource.
    
    Returns the tool call dict or None if no FHIR tool calls found.
    """
    # FHIR MCP tools from fhir_mcp_server.py
    FHIR_TOOLS = {
        'getResourceById', 
        'searchResources',
        'createResource',
        'updateResource',
        'deleteResource'
    }
    
    raw_logs = execution_log.get('raw_logs', {})
    tools = raw_logs.get('tools', [])
    
    # Filter for FHIR tools only and get the last one
    fhir_tools = [t for t in tools if t.get('name') in FHIR_TOOLS]
    
    if not fhir_tools:
        return None
    
    # Return the last FHIR tool call (already sorted by 'order' field)
    return fhir_tools[-1]


def _build_judge_prompt(task_source: str, execution_log: Dict[str, Any], validator_result: bool, last_tool: Dict[str, Any] | None) -> str:
    """Build the prompt for LLM judge with task code and execution logs."""
    
    validator_status = "PASSED" if validator_result else "FAILED"
    
    # Format last tool call section
    if last_tool:
        last_tool_section = f"""
LAST FHIR TOOL CALL:
Tool: {last_tool.get('name')}
Input: {last_tool.get('input')}
Output: {last_tool.get('output')}
Error: {last_tool.get('error')}
"""
    else:
        last_tool_section = "\nLAST FHIR TOOL CALL: None found (agent may not have called any FHIR tools)"
    
    return f"""Judge if the agent completed this FHIR task based on server evidence.

TASK SOURCE CODE:
{task_source}

EXECUTION LOG:
{json.dumps(execution_log, indent=2)}
{last_tool_section}

OFFICIAL VALIDATOR RESULT: {validator_status}

Based ONLY on the server responses in the execution log (HTTP status codes, resource IDs, OperationOutcomes):
1. Did the agent successfully complete the task?
2. Why does your judgment agree or disagree with the official validator?
3. Analyze the LAST FHIR tool call for errors:
   - "syntax_error": Invalid FHIR schema, wrong parameter types, missing required fields, malformed JSON
   - "logical_error": Valid FHIR syntax but wrong for the task (e.g., searching wrong resource type, using wrong patient ID)
   - "none": Tool call appears correct
   - "unclear": Insufficient information or no FHIR tool calls

Return JSON with:
{{
  "judgment": "YES" | "NO" | "UNCLEAR",
  "justification": "One paragraph explaining the evidence and reasoning",
  "last_tool_error_type": "none" | "syntax_error" | "logical_error" | "unclear",
  "last_tool_error_explanation": "Brief explanation of any error found in the last tool call"
}}"""


def _call_llm_judge(prompt: str, model: str) -> Dict[str, str]:
    """Call OpenAI API to get LLM judgment."""
    
    # Load system prompt from file
    prompts_dir = Path(__file__).parent.parent / "prompts"
    system_prompt_path = prompts_dir / "soft_validator_system_prompt.txt"
    
    with open(system_prompt_path, 'r') as f:
        system_prompt = f.read()
    
    # Initialize OpenAI client with API key from environment
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment/.env file or environment variables")
    client = OpenAI(api_key=api_key)
    
    # Call API with JSON mode
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        #temperature=0.0  # Deterministic for consistency
    )
    
    #print(prompt)
    # Parse JSON response
    result = json.loads(response.choices[0].message.content)
    
    return {
        'judgment': result.get('judgment', 'UNCLEAR'),
        'justification': result.get('justification', 'No justification provided'),
        'last_tool_error_type': result.get('last_tool_error_type', 'unclear'),
        'last_tool_error_explanation': result.get('last_tool_error_explanation', 'No explanation provided')
    }


def _determine_flag(
    llm_judgment: str,
    validator_result: bool
) -> Literal["agreement_success", "agreement_failure", "validator_too_strict", "validator_too_loose", "unclear"]:
    """Map LLM judgment + validator result to final flag."""
    
    if llm_judgment == "UNCLEAR":
        return "unclear"
    
    soft_success = (llm_judgment == "YES")
    
    # Both agree on success
    if validator_result and soft_success:
        return "agreement_success"
    
    # Both agree on failure
    if not validator_result and not soft_success:
        return "agreement_failure"
    
    # Validator failed but soft judge passed (false negative)
    if not validator_result and soft_success:
        return "validator_too_strict"
    
    # Validator passed but soft judge failed (false positive)
    if validator_result and not soft_success:
        return "validator_too_loose"
    
    # Fallback (should not reach here)
    return "unclear"

