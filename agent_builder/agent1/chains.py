from .ai_client import client
from .utils import clean_state




def generate_doctype_payload_agent(state, tools=None):
    
    messages = state.messages

    generate_payload_system_prompt = (
            "You are an expert Frappe/ERPNext developer. Generate STRICT JSON only (no prose). "
            "The JSON should be a valid DocType payload with keys: doctype='DocType', name, module, custom, fields, permissions, autoname (if needed)."
            " If you cannot produce valid JSON, return an error object as JSON: {\"status\":\"error\",\"message\":\"...\"}."
            " you have access to the validate function to check the validity of the generated JSON."
            " You must use the validate function to ensure the generated JSON is valid before returning it."
)
    
    messages.insert(0, {"role": "system", "content": generate_payload_system_prompt})
    response = client(
        tools=tools,
        messages=messages
    )

    return response

def validate_doctype_payload_agent(state, tools=None):
    
    messages = state.messages
    ### UPDATE SYTEM PROMPT TO MIRROR AGENT
    generate_payload_system_prompt = (
            "You are an expert Frappe/ERPNext developer. Generate STRICT JSON only (no prose). "
            "The JSON should be a valid DocType payload with keys: doctype='DocType', name, module, custom, fields, permissions, autoname (if needed)."
            " If you cannot produce valid JSON, return an error object as JSON: {\"status\":\"error\",\"message\":\"...\"}."
            " you have access to the validate function to check the validity of the generated JSON."
            " You must use the validate function to ensure the generated JSON is valid before returning it."
)
    
    messages.insert(0, {"role": "system", "content": generate_payload_system_prompt})
    response = client(
        tools=tools,
        messages=messages
    )

    return response

def create_doctype_agent(state, tools=None):
    
    messages = state.messages

    # create and validate, "mirror -> regenerate -> create" agent
    generate_doctype_system_prompt = (
         "You are the Creator Agent. The input JSON is already validated. "
         "Call tool_agent_create with the sanitized payload. If creation succeeds, return {\"status\":\"ok\",\"created\": [ ... ]}. "
         "If creation fails, return {\"status\":\"error\",\"message\":\"...\",\"errors\":[...]}."

    )
    messages.insert(0, generate_doctype_system_prompt)


    response = client(
        tools=tools,
        messages=messages
    )

    return response

    
