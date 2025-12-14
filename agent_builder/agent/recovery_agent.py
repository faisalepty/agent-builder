from .ai_payload import openrouter_generate
import json
def attempt_recovery(payload, errors):
    """
    Attempts to fix a broken payload using AI.
    Returns a dict: {"fixed_payload": {...}} if successful, else {}.
    """
    print(f"[RecoveryAgent] Attempting fix for errors: {errors}")
    
    # TODO: integrate with AI client (like OpenAI)
    # For now, just log the error context
    OPENROUTER_API_KEY = "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"  # set in env in prod
    MODEL = "openai/gpt-oss-20b:free"  # free/open model
    RECOVERY_PROMPT_TEMPLATE = """
    You are an expert Frappe/ERPNext developer tasked with fixing validation errors in a DocType payload.
    ### Original Payload:
    {payload}
    ### Validation Errors Found:
    {errors}
    ### Your Task:
    Fix the payload to resolve ALL validation errors while maintaining the original intent.
    ### Rules:
    Output strictly valid JSON only (no markdown, no explanations).
    Keep the original structure and intent of the DocType.
    Fix validation errors by:
    - Adding missing required fields
    - Correcting invalid fieldtypes to valid Frappe fieldtypes
    - Adding missing 'options' for Link fields (use sensible DocType names)
    - Fixing invalid field values (e.g., Check fields should have '0' or '1' defaults)
    - Adding missing permissions if needed
    For Link fields missing options, use common DocType names like 'Customer', 'Item', 'User', etc.
    Ensure all fieldnames are valid (lowercase, underscore-separated).
    Maintain the original doctype name, module, and core functionality.
    Return the corrected JSON payload:
    """
    prompt_text = RECOVERY_PROMPT_TEMPLATE.format(payload=payload, errors=errors)
    raw = openrouter_generate(prompt_text)
    if isinstance(raw, str) and raw.startswith("{") and '"error"' in raw:
        return {"fixed_payload": payload}
    try:
        fixed_payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"fixed_payload": payload}
    return {"fixed_payload": fixed_payload}
