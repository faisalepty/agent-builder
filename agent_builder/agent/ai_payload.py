# agent_builder/agent/ai_payload.py
import json
import frappe
import requests
import time
import os

# --- OpenRouter Configuration ---
OPENROUTER_API_KEY = "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"  # set in env in prod
MODEL = "deepseek/deepseek-chat-v3.1:free"  # free/open model

# --- Prompt Templates (kept simple to avoid format brace conflicts) ---
PROMPT_TEMPLATES = {
    "DocType": (
        "You are an expert Frappe/ERPNext developer.\n"
        "Generate a JSON payload for creating a valid Frappe DocType.\n\n"
        "### Rules:\n"
        "1. Output strictly valid JSON only (no markdown, no explanations).\n"
        "2. JSON must include these top-level keys:\n"
        "   - doctype = \"DocType\"\n"
        "   - name = DocType name (Title Case)\n"
        "   - module = Module name (Title Case)\n"
        "   - custom = 1\n"
        "   - autoname (e.g., \"field:<fieldname>\" or \"naming_series\")\n"
        "   - naming_rule (if relevant)\n"
        "   - fields = [array of field objects]\n"
        "   - permissions = [array of role permissions]\n"
        "3. Each field object must include:\n"
        "   - fieldname, label, fieldtype\n"
        "   - reqd (0 or 1)\n"
        "   - in_list_view (0 or 1 if relevant)\n"
        "   - in_standard_filter (0 or 1 if relevant)\n"
        "   - default (if applicable)\n"
        "   - options (required for Select, Link, Table, Data-with-validator)\n"
        "   - precision/width/depends_on if applicable\n"
        "4. Special fieldtype rules:\n"
        "   - Link: must include 'options' with target DocType\n"
        "   - Select: 'options' must be newline-separated values\n"
        "   - Table: 'options' must be the child DocType name\n"
        "   - Data: may use 'options' for validators like Email, Phone\n"
        "5. If the DocType represents a transactional record (like invoices, orders, service records), include:\n"
        "   - is_submittable = 1\n"
        "   - permissions may include submit, cancel, amend.\n"
        "6. Always include a 'permissions' list with System Manager having full rights (read, write, create, delete, submit, cancel, amend, report, import, export, email, print).\n"
        "7. Do not add explanations, comments, or text outside the JSON.\n\n"
        "User Description: {description}"
    ),
    "Dashboard": (
        "You are an expert Frappe developer.\n"
        "Generate a JSON payload for a Frappe Dashboard.\n"
        "The JSON must include: doctype = \"Dashboard\", dashboard_name, module, custom = 1.\n"
        "Return strictly valid JSON only.\n\n"
        "User Description: {description}"
    ),
    "Dashboard Chart": (
        "You are an expert Frappe developer.\n"
        "Generate a JSON payload for a Frappe Dashboard Chart.\n"
        "The JSON must include: doctype = \"Dashboard Chart\", chart_name, chart_type, module, custom = 1.\n"
        "Return strictly valid JSON only.\n\n"
        "User Description: {description}"
    ),
}

# --- Improved prompt for missing doctypes ---
MISSING_DOCTYPE_PROMPT = (
    "You are an expert Frappe developer.\n"
    "The user originally requested: \"{original_description}\".\n\n"
    "The generated DocType \"{parent_doctype}\" references a missing DocType \"{missing_doctype}\".\n\n"
    "Generate a complete JSON payload for the missing DocType \"{missing_doctype}\" with these rules:\n"
    " - doctype = \"DocType\"\n"
    " - name = \"{missing_doctype}\"\n"
    " - module = same as parent (\"{module}\")\n"
    " - custom = 1\n"
    " - autoname = \"field:name\" unless specified otherwise\n"
    " - fields must include at least one identifying field (e.g., name or title)\n"
    " - if any field is Link, include 'options' = target DocType\n"
    " - do not create additional references to unknown DocTypes\n"
    " - permissions: always include System Manager with full rights\n"
    "Return strictly valid JSON only (no extra text)."
)


# --- GPT Call using OpenRouter ---
def openrouter_generate(prompt_text: str, timeout: int = 30) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt_text}],
        "temperature": 0.2
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            data=json.dumps(data),
            timeout=timeout
        )
        result = response.json()
    except Exception as e:
        print(f"[ERROR] OpenRouter API call failed: {e}")
        return json.dumps({"error": "OpenRouter API call failed", "detail": str(e)})

    if not isinstance(result, dict):
        return json.dumps({"error": "Unexpected response", "raw": str(result)})

    if "error" in result:
        return json.dumps({"error": "OpenRouter API returned error", "detail": result["error"]})

    choices = result.get("choices")
    if not choices or not isinstance(choices, list):
        return json.dumps({"error": "OpenRouter returned no choices", "raw": result})

    first = choices[0]
    content = None
    if isinstance(first, dict):
        message = first.get("message") or {}
        content = message.get("content")
        if content is None:
            content = first.get("text") or first.get("content")

    if content is None:
        return json.dumps({"error": "Missing content in OpenRouter response", "raw_choice": first})

    return content


# --- Utility: extract JSON block from a string robustly ---
def extract_json_block(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0 or end <= start:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    return json.loads(text[start:end])


# --- Pre-validation for link fields ---
def find_missing_linked_doctypes(payload: dict) -> list:
    missing = []
    for f in payload.get("fields", []):
        if f.get("fieldtype") == "Link":
            opts = f.get("options")
            if opts and not frappe.db.exists("DocType", opts):
                if opts not in missing:
                    missing.append(opts)
    return missing


# --- Fix AI payloads (sanitize) ---
def sanitize_payload(payload: dict) -> dict:
    for f in payload.get("fields", []):
        if f.get("fieldtype") == "Check":
            default = str(f.get("default", "0")).strip()
            if default not in ["0", "1"]:
                f["default"] = "0"
            else:
                f["default"] = default
    return payload


# --- Generate payload for a missing DocType ---
def generate_missing_doctype_payload(original_prompt: str, parent_doctype: str, missing_doctype: str, module: str, max_retries: int = 2) -> dict:
    prompt_text = MISSING_DOCTYPE_PROMPT.format(
        original_description=original_prompt,
        parent_doctype=parent_doctype,
        missing_doctype=missing_doctype,
        module=module
    )

    attempt = 0
    last_raw = ""
    while attempt <= max_retries:
        raw = openrouter_generate(prompt_text)
        last_raw = raw
        if isinstance(raw, str) and raw.startswith("{") and '"error"' in raw:
            attempt += 1
            time.sleep(0.5)
            continue

        try:
            payload = extract_json_block(raw)
            return sanitize_payload(payload)
        except json.JSONDecodeError:
            attempt += 1
            prompt_text += "\n\nIMPORTANT: Only return the JSON payload object, with no surrounding text."
            time.sleep(0.5)
            continue

    raise json.JSONDecodeError(f"Failed to generate JSON for missing DocType '{missing_doctype}'. Last raw: {last_raw}", last_raw, 0)


# --- Recursively resolve missing doctypes ---
def resolve_missing_doctypes(original_prompt: str, parent_doctype: str, module: str, missing_doctypes: list, resolved: dict) -> dict:
    for missing_dt in missing_doctypes:
        if missing_dt in resolved:
            continue

        linked_payload = generate_missing_doctype_payload(
            original_prompt=original_prompt,
            parent_doctype=parent_doctype,
            missing_doctype=missing_dt,
            module=module,
            max_retries=2
        )
        resolved[missing_dt] = linked_payload

        further_missing = find_missing_linked_doctypes(linked_payload)
        if further_missing:
            resolve_missing_doctypes(
                original_prompt=original_prompt,
                parent_doctype=missing_dt,
                module=linked_payload.get("module", module),
                missing_doctypes=further_missing,
                resolved=resolved
            )
    return resolved


# --- Main AI Payload Generator ---
def ai_payload(user_prompt: str, doc_type: str = "DocType", max_retries: int = 3) -> dict:
    template = PROMPT_TEMPLATES.get(doc_type, PROMPT_TEMPLATES["DocType"])
    prompt_text = template.format(description=user_prompt)

    attempt = 0
    last_raw = ""
    while attempt <= max_retries:
        raw = openrouter_generate(prompt_text)
        last_raw = raw
        if isinstance(raw, str) and raw.startswith("{") and '"error"' in raw:
            attempt += 1
            time.sleep(0.5)
            continue

        try:
            payload = extract_json_block(raw)
        except json.JSONDecodeError:
            attempt += 1
            prompt_text += "\n\nIMPORTANT: Only return the JSON payload object, with no surrounding text."
            time.sleep(0.5)
            continue

        # Fix missing options in Link fields
        invalid_links = [f["fieldname"] for f in payload.get("fields", []) if f.get("fieldtype") == "Link" and not f.get("options")]
        if invalid_links:
            attempt += 1
            prompt_text += "\n\nIMPORTANT: For every field with fieldtype = 'Link', you must include an 'options' key with the target DocType name."
            time.sleep(0.5)
            continue

        # Ensure required keys
        required = ["doctype", "name", "module", "fields"]
        missing_keys = [k for k in required if k not in payload]
        if missing_keys:
            attempt += 1
            prompt_text += f"\n\nThe JSON must include these keys: {', '.join(required)}."
            time.sleep(0.5)
            continue

        # Resolve missing linked doctypes recursively
        missing_links = find_missing_linked_doctypes(payload)
        generated_linked = {}
        if missing_links:
            generated_linked = resolve_missing_doctypes(
                original_prompt=user_prompt,
                parent_doctype=payload.get("name"),
                module=payload.get("module", "Custom"),
                missing_doctypes=missing_links,
                resolved={}
            )

        payload = sanitize_payload(payload)
        for k, v in generated_linked.items():
            generated_linked[k] = sanitize_payload(v)

        return {
            "payload": payload,
            "missing_linked_doctypes": list(generated_linked.keys()),
            "generated_linked_payloads": generated_linked,
            "raw": last_raw
        }

    frappe.log_error(frappe.get_traceback(), "AI Payload Generation Failed")
    raise RuntimeError(f"AI generation failed after {max_retries} attempts. Last raw: {last_raw}")
