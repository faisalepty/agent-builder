import json
from agent_builder.agent.ai_payload import ai_payload
from agent_builder.agent.api import agent_create
from agent_builder.agent.recovery_agent import attempt_recovery


def try_create_with_recovery(user_prompt, payload, name, doc_type, dry_run=False, max_retries=3):
    """
    Attempts to create a document, and if it fails,
    invokes the Recovery Agent to fix and retry creation.
    """
    try:
        print(f"[try_create_with_recovery] Attempting to create {max_retries} times")
        res = agent_create(json.dumps(payload), dry_run=dry_run)
        if res.get("status") == "success":
            return res
        # If there are errors, attempt recovery
        errors = res.get("errors", [])
        recovery_result = attempt_recovery(payload, errors)
        if recovery_result.get("fixed_payload") and max_retries > 0:
            # Retry once with fixed payload
            return try_create_with_recovery(user_prompt, 
                recovery_result["fixed_payload"], name, doc_type, dry_run, max_retries - 1
            )
        return res
    except Exception as e:
        return {"status": "error", "errors": [{"doctype": doc_type, "name": name, "error": str(e)}]}


def create_from_prompt(user_prompt: str, doc_type: str = "DocType", dry_run: bool = False):
    """
    Orchestrates:
      1. Generate payloads via AI
      2. Create missing linked doctypes (with recovery)
      3. Create main payload (with recovery)
    """
    try:
        result = ai_payload(user_prompt, doc_type=doc_type)
    except Exception as e:
        return {
            "status": "error",
            "created": [],
            "errors": [{"error": f"AI failed: {str(e)}"}],
        }

    created, errors = [], []

    # Step 1: Create missing linked doctypes
    for linked_name, linked_payload in result.get("generated_linked_payloads", {}).items():
        res = try_create_with_recovery(user_prompt, linked_payload, linked_name, "DocType", dry_run)
        if res.get("status") == "success":
            created.extend(res.get("created", []))
        else:
            errors.extend(res.get("errors", []))

    # Step 2: Create main payload
    main_payload = result.get("payload")
    res = try_create_with_recovery(user_prompt, main_payload, main_payload.get("name"), doc_type, dry_run)
    if res.get("status") == "success":
        created.extend(res.get("created", []))
    else:
        errors.extend(res.get("errors", []))

    # Step 3: Return unified result
    return {
        "status": "success" if not errors else "error",
        "created": created,
        "errors": errors,
        "missing_linked_doctypes": result.get("missing_linked_doctypes", []),
        "raw_ai_output": result.get("raw"),
    }
