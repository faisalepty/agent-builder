# tools.py
import json
import frappe
from .validator import ValidationService, ValidationError

validator = ValidationService()
DENYLIST = {"User","Role","DocType","Email Queue"}


def tool_validate_payload(payload: dict, strict: bool=True):
    sanitized, errors = validator.validate_doc(payload)
    return {
        "sanitized_payload": sanitized,
        "errors": [e.as_dict() for e in errors],
        "status": "ok" if not errors else "error"
    }

def tool_doctype_exists(name: str):
    return {"exists": bool(frappe.db.exists("DocType", name))}

def tool_role_exists(role: str):
    return {"exists": bool(frappe.db.exists("Role", role))}

def tool_agent_create(payload: dict, dry_run: bool=False):
    name = payload.get("name")
    if name in DENYLIST:
        return {"status_tool_agent_create":"error", "error": "Denied doctype name"}
    sanitized, errs = validator.validate_doc(payload)
    if errs:
        return {"status_tool_agent_create":"error", "errors":[e.as_dict() for e in errs]}
    if dry_run:
        return {"status_tool_agent_create":"ok", "created": [], "dry_run": True}
    try:
        d = frappe.get_doc(sanitized)
        d.insert(ignore_permissions=True)
        frappe.db.commit()
        return {"status_tool_agent_create":"ok", "created":[{"doctype":d.doctype, "name":d.name}]}
    except Exception as e:
        return {"status_tool_agent_create":"error", "error": str(e)}
