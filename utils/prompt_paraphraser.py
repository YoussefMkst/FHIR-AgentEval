"""
Simple utility to paraphrase task prompts while preserving key details.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

# Load environment variables
env_path = Path(__file__).parent.parent / "environment" / ".env"
load_dotenv(env_path)


def paraphrase_prompt(original_prompt: str) -> str:
    """
    Paraphrase a task prompt while preserving all key details.
    
    Args:
        original_prompt: The original task prompt to paraphrase
        
    Returns:
        A paraphrased version of the prompt with preserved details
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    
    system_prompt = """You are a helpful assistant that paraphrases task prompts to simulate real-world scenario variations.

CRITICAL RULES:
- Preserve ALL specific details: names, dates, times, medical conditions, medications, dosages, IDs, phone numbers, addresses, etc.
- Only rephrase the sentence structure and wording of the task requirement itself
- Keep the same meaning and intent
- Make it sound natural and conversational like a real person would say it
- Preserve all response formatting requirements (e.g. the returned patient id must be returned between <PATIENT_ID></PATIENT_ID> tags...).
- Do NOT add or remove any factual information

Example:
Original: "Schedule an appointment for John Doe on Monday at 2 PM for a checkup"
Paraphrased: "Book John Doe for a checkup appointment Monday at 2 PM"
(Notice: name, day, time, and purpose are all preserved)"""
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Paraphrase this task prompt:\n\n{original_prompt}")
    ]
    
    response = llm.invoke(messages)
    paraphrased = response.content.strip()
    return paraphrased


def main():
    """Test the paraphraser with sample prompts."""
    
    test_prompts = [
        "Schedule an appointment for Jane Smith on next Monday at 2:30 PM with Dr. Johnson for a follow-up consultation.",
        "Enter a new patient named Robert Brown, born on 05/15/1985, phone number 555-0123, living at 123 Main St, Boston MA.",
        "Update the medical history for patient Emily Davis to include diabetes type 2 diagnosed in 2020.",
        "Cancel the appointment for Michael Wilson scheduled for Thursday at 10 AM.",
        """Cancel Patient Michael Smith's next coming appointment with Dr. John Smith.
        After cancellation, return the cancelled appointment ID and freed slot ID using the following format:
        <APPOINTMENT>appointment_id</APPOINTMENT>
        <SLOT_ID>slot_id</SLOT_ID>"""
    ]
    
    print("Testing Prompt Paraphraser")
    print("=" * 80)
    
    for i, prompt in enumerate(test_prompts, 1):
        print(f"\n### Test {i}")
        print(f"Original:\n  {prompt}")
        
        paraphrased = paraphrase_prompt(prompt)
        print(f"\nParaphrased:\n  {paraphrased}")
        print("-" * 80)


if __name__ == "__main__":
    main()

