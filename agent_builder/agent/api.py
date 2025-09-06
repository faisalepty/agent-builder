import frappe
import json
from agent_builder.agent.services import ValidationService, normalize_payload


# ============================================================
# Main API
# ============================================================
@frappe.whitelist()
def agent_create(payload_json: str, dry_run=False):
    """
    Create DocTypes, Dashboards, Charts, etc. from AI-generated JSON.
    Returns structured result: {status, created, errors}
    dry_run can be truthy string to validate only (no DB inserts).
    """
    service = ValidationService()
    dry_run = str(dry_run).lower() in ("1", "true", "yes")

    created, errors = [], []

    try:
        try:
            payload = json.loads(payload_json)
        except Exception as e:
            return {
                "status": "error",
                "created": [],
                "errors": [{"doctype": None, "name": None, "error": f"Invalid JSON: {e}"}]
            }

        docs = payload if isinstance(payload, list) else [payload]

        for doc in docs:
            doc = normalize_payload(doc)
            sanitized_doc, v_errors = service.validate_doc(doc)
            if v_errors:
                for err in v_errors:
                    errors.append({
                        "doctype": doc.get("doctype"),
                        "name": doc.get("name"),
                        "error": err.message,
                        "severity": err.severity,
                        "suggestion": err.suggestion
                    })
                continue

            try:
                if dry_run:
                    created.append({"doctype": sanitized_doc.get("doctype"), "name": sanitized_doc.get("name")})
                    continue

                d = frappe.get_doc(sanitized_doc)
                d.insert(ignore_permissions=True)
                created.append({"doctype": d.doctype, "name": d.name})
            except Exception as inner:
                errors.append({
                    "doctype": sanitized_doc.get("doctype"),
                    "name": sanitized_doc.get("name"),
                    "error": str(inner),
                    "severity": "error"
                })

        if created and not dry_run:
            frappe.db.commit()

        if created and errors:
            status = "partial"
        elif created:
            status = "success"
        elif errors:
            status = "error"
        else:
            status = "error"

        return {"status": status, "created": created, "errors": errors}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Agent Create Failed")
        return {
            "status": "error",
            "created": created,
            "errors": [{"doctype": None, "name": None, "error": str(e)}]
        }
