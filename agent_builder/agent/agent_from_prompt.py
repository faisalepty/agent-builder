# agent_builder/agent/agent_from_prompt.py
import json
from agent_builder.agent.ai_payload import ai_payload
from agent_builder.agent.api import agent_create

def create_from_prompt(user_prompt: str, doc_type: str = "DocType", dry_run: bool = False):
    """
    Orchestrates: 
      1. Generate payloads via AI
      2. Create missing linked doctypes first
      3. Then create main payload
    """
    try:
        result = ai_payload(user_prompt, doc_type=doc_type)
    except Exception as e:
        return {"status": "error", "created": [], "errors": [{"error": f"AI failed: {str(e)}"}]}

    created, errors = [], []

    # Create linked doctypes first
    for linked_name, linked_payload in result.get("generated_linked_payloads", {}).items():
        try:
            res = agent_create(json.dumps(linked_payload), dry_run=dry_run)
            if res.get("status") == "success":
                created.extend(res.get("created", []))
            else:
                errors.extend(res.get("errors", []))
        except Exception as e:
            errors.append({"doctype": "DocType", "name": linked_name, "error": str(e)})

    # Create main payload
    try:
        res = agent_create(json.dumps(result["payload"]), dry_run=dry_run)
        if res.get("status") == "success":
            created.extend(res.get("created", []))
        else:
            errors.extend(res.get("errors", []))
    except Exception as e:
        errors.append({"doctype": doc_type, "name": result["payload"].get("name"), "error": str(e)})

    return {
        "status": "success" if not errors else "error",
        "created": created,
        "errors": errors,
        "missing_linked_doctypes": result.get("missing_linked_doctypes", []),
        "raw_ai_output": result.get("raw")
    }
