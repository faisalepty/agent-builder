# tools.py
import json
import frappe
from .validator import ValidationService, ValidationError

validator = ValidationService()
DENYLIST = {"User","Role","DocType","Email Queue"}

def tool_get_doctype_metadata(doctype: str):
    """
    Fetch all relevant metadata for a Frappe DocType.
    This is intended to help LLMs generate valid payloads.
    """

    # Check existence
    if not frappe.db.exists("DocType", doctype):
        return {"status": "error", "error": f"DocType '{doctype}' not found"}

    try:
        meta = frappe.get_meta(doctype)

        fields = []
        for f in meta.fields:
            fields.append({
                "fieldname": f.fieldname,
                "label": f.label,
                "fieldtype": f.fieldtype,
                "reqd": bool(f.reqd),
                "unique": bool(f.unique),
                "options": f.options if hasattr(f, "options") else None,
                "in_list_view": bool(getattr(f, "in_list_view", False)),
                "parentfield": getattr(f, "parentfield", None),
            })

        # Mandatory = field.reqd == True
        mandatory_fields = [
            f["fieldname"] for f in fields if f["reqd"]
        ]

        # Child tables
        child_tables = [
            f["fieldname"] for f in fields
            if f["fieldtype"] == "Table"
        ]

        # Unique fields
        unique_fields = [
            f["fieldname"] for f in fields if f["unique"]
        ]

        return {
            "status": "ok",
            "doctype": doctype,
            "is_single": meta.issingle,
            "fields": fields,
            "mandatory_fields": mandatory_fields,
            "unique_fields": unique_fields,
            "child_tables": child_tables,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
   

def tool_validate_doctype_payload(payload: dict, strict: bool = True):
    """
    Validate a DocType payload.
    Returns 'ok' if valid, 'error' if invalid.
    Uses frappe.model.validator.validate_doc.
    """
    # Denylist check
    name = payload.get("name")
    if name in DENYLIST:
        return {"status": "error", "error": f"Denied DocType name '{name}'"}

    try:
        # validate_doc expects a Frappe DocType dict
        sanitized, errors = validator.validate_doc(payload)

        if errors:
            # Convert errors to dicts for readability
            return {
                "status": "error",
                "errors": [e.as_dict() for e in errors]
            }

        if strict:
            # Additional checks: name, module, fields exist
            required_keys = ["doctype", "name", "module", "fields"]
            for key in required_keys:
                if key not in sanitized:
                    return {"status": "error", "error": f"Missing required key: {key}"}

        return {"status": "ok", "sanitized_payload": sanitized}

    except Exception as e:
        return {"status": "error", "error": str(e)}

def tool_validate_dashboard_chart_payload(payload: dict):
    """
    Dashboard Chart semantic validation.
    """
    errors = []

    required_fields = [
        "chart_name",
        "chart_type",
        "document_type",
        "type"
    ]

    for field in required_fields:
        if not payload.get(field):
            errors.append({
                "field": field,
                "message": "Required for Dashboard Chart"
            })

    if payload.get("chart_type") == "Group By":
        if not payload.get("group_by_based_on"):
            errors.append({
                "field": "group_by_based_on",
                "message": "Required when chart_type is 'Group By'"
            })

    if payload.get("timeseries"):
        if not payload.get("timeseries_based_on"):
            errors.append({
                "field": "timeseries_based_on",
                "message": "Missing timeseries field"
            })

    if errors:
        return {
            "status": "error",
            "errors": errors,
            "sanitized_payload": payload
        }

    return {
            "status": "ok",
            "errors": errors,
            "sanitized_payload": payload
        }


def tool_agent_create(payload: dict, dry_run: bool = False):
    """
    Create ANY Frappe document after validation.
    """
    try:
        doctype = payload.get("doctype")
        if not doctype:
            return {"status": "error", "error": "Missing doctype"}

        if dry_run:
            return {
                "status": "ok",
                "dry_run": True,
                "doctype": doctype
            }

        doc = frappe.get_doc(payload)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        return {
            "status": "ok",
            "created": {
                "doctype": doc.doctype,
                "name": doc.name
            }
        }

    except Exception as e:
        frappe.db.rollback()
        return {
            "status": "error",
            "error": str(e)
        }




# def tool_validate_payload(payload: dict, strict: bool=True):
#     sanitized, errors = validator.validate_doc(payload)
#     return {
#         "sanitized_payload": sanitized,
#         "errors": [e.as_dict() for e in errors],
#         "status": "ok" if not errors else "error"
#     }

# def tool_doctype_exists(name: str):
#     return {"exists": bool(frappe.db.exists("DocType", name))}

# def tool_role_exists(role: str):
#     return {"exists": bool(frappe.db.exists("Role", role))}

# import frappe
# from frappe.model.document import Document
# from frappe.exceptions import ValidationError


# DENYLIST = {
#     # optional safety rails
#     # "DocType",
#     # "User",
# }


# def tool_agent_create(payload: dict, dry_run: bool = False):
#     """
#     Generic creation tool for ANY Frappe DocType.

#     payload MUST include:
#       - doctype (str)
#       - other valid fields for that doctype

#     Returns deterministic JSON for supervisor routing.
#     """

#     # -----------------------------
#     # 1️⃣ Basic payload sanity
#     # -----------------------------
#     doctype = payload.get("doctype")

#     if not doctype:
#         return {
#             "status": "error",
#             "error": "Missing required key: doctype"
#         }

#     if doctype in DENYLIST:
#         return {
#             "status": "error",
#             "error": f"Creation of '{doctype}' is denied"
#         }

#     if not frappe.db.exists("DocType", doctype):
#         return {
#             "status": "error",
#             "error": f"DocType '{doctype}' does not exist"
#         }

#     # -----------------------------
#     # 2️⃣ Dry run (used by agents)
#     # -----------------------------
#     if dry_run:
#         return {
#             "status": "ok",
#             "dry_run": True,
#             "created": []
#         }

#     # -----------------------------
#     # 3️⃣ Create document
#     # -----------------------------
#     try:
#         doc: Document = frappe.get_doc(payload)

#         # Let Frappe do full validation:
#         # - field types
#         # - mandatory fields
#         # - permissions (ignored below)
#         # - autoname rules
#         doc.insert(ignore_permissions=True)

#         frappe.db.commit()

#         return {
#             "status": "ok",
#             "created": [
#                 {
#                     "doctype": doc.doctype,
#                     "name": doc.name
#                 }
#             ]
#         }

#     # -----------------------------
#     # 4️⃣ Known validation errors
#     # -----------------------------
#     except ValidationError as e:
#         frappe.db.rollback()
#         return {
#             "status": "error",
#             "error_type": "validation",
#             "error": str(e)
#         }

#     # -----------------------------
#     # 5️⃣ Everything else
#     # -----------------------------
#     except Exception as e:
#         frappe.db.rollback()
#         return {
#             "status": "error",
#             "error_type": "exception",
#             "error": str(e)
#         }

    

# def tool_get_doctype_metadata(doctype: str):
#     if not frappe.db.exists("DocType", doctype):
#         return {"status":"error", "message": f"DocType '{doctype}' does not exist."}
#     docmeta = frappe.get_meta(doctype)
#     fields = []
#     for field in docmeta.fields:
#         fields.append({
#             "fieldname": field.fieldname,
#             "label": field.label,
#             "fieldtype": field.fieldtype,
#             "options": field.options,
#             "mandatory": field.reqd,
#         })
#     return {
#         "status":"ok",
#         "doctype": doctype,
#         "fields": fields
#     }

# class DashboardPayloadValidationError(Exception):
#     pass


# def tool_validate_dashboard_chart_payload(payload: dict):
#     """
#     Validates a Dashboard Chart payload against Frappe rules.

#     Returns:
#         {
#             "status": "ok",
#             "normalized_payload": dict
#         }

#     Raises:
#         DashboardPayloadValidationError
#     """

#     REQUIRED_KEYS = {
#         "chart_name",
#         "chart_type",
#         "type",
#         "document_type",
#         "is_public"
#     }

#     ALLOWED_CHART_TYPES = {"Group By", "Timeseries", "Report"}
#     ALLOWED_VISUAL_TYPES = {"Bar", "Line", "Pie", "Donut", "Percentage"}

#     GROUPABLE_FIELD_TYPES = {
#         "Data", "Select", "Link", "Int", "Check"
#     }

#     TIMESERIES_FIELD_TYPES = {
#         "Date", "Datetime"
#     }

#     # -----------------------------
#     # 1️⃣ Basic structure validation
#     # -----------------------------
#     missing = REQUIRED_KEYS - payload.keys()
#     if missing:
#         raise DashboardPayloadValidationError(
#             f"Missing required keys: {sorted(missing)}"
#         )

#     if payload["chart_type"] not in ALLOWED_CHART_TYPES:
#         raise DashboardPayloadValidationError(
#             f"Invalid chart_type: {payload['chart_type']}"
#         )

#     if payload["type"] not in ALLOWED_VISUAL_TYPES:
#         raise DashboardPayloadValidationError(
#             f"Invalid chart visual type: {payload['type']}"
#         )

#     # -----------------------------
#     # 2️⃣ Validate document_type
#     # -----------------------------
#     doctype = payload["document_type"]

#     if not frappe.db.exists("DocType", doctype):
#         raise DashboardPayloadValidationError(
#             f"DocType '{doctype}' does not exist"
#         )

#     meta: Meta = frappe.get_meta(doctype)

#     field_map = {
#         f.fieldname: f.fieldtype
#         for f in meta.fields
#     }

#     # -----------------------------
#     # 3️⃣ Chart-type specific rules
#     # -----------------------------
#     chart_type = payload["chart_type"]

#     # ---- GROUP BY ----
#     if chart_type == "Group By":
#         required = {"group_by_based_on", "group_by_type"}
#         missing = required - payload.keys()
#         if missing:
#             raise DashboardPayloadValidationError(
#                 f"Group By chart missing: {sorted(missing)}"
#             )

#         group_field = payload["group_by_based_on"]

#         if group_field not in field_map:
#             raise DashboardPayloadValidationError(
#                 f"Field '{group_field}' not found in DocType '{doctype}'"
#             )

#         if field_map[group_field] not in GROUPABLE_FIELD_TYPES:
#             raise DashboardPayloadValidationError(
#                 f"Field '{group_field}' ({field_map[group_field]}) "
#                 f"is not groupable"
#             )

#     # ---- TIMESERIES ----
#     if chart_type == "Timeseries":
#         if not payload.get("timeseries"):
#             raise DashboardPayloadValidationError(
#                 "Timeseries chart requires timeseries=1"
#             )

#         time_field = payload.get("time_series_field")
#         if not time_field:
#             raise DashboardPayloadValidationError(
#                 "Timeseries chart requires time_series_field"
#             )

#         if time_field not in field_map:
#             raise DashboardPayloadValidationError(
#                 f"Time field '{time_field}' not found in DocType '{doctype}'"
#             )

#         if field_map[time_field] not in TIMESERIES_FIELD_TYPES:
#             raise DashboardPayloadValidationError(
#                 f"Field '{time_field}' is not Date/Datetime"
#             )

#     # ---- REPORT CHART ----
#     if chart_type == "Report":
#         if not payload.get("use_report_chart"):
#             raise DashboardPayloadValidationError(
#                 "Report chart requires use_report_chart=1"
#             )

#         if not payload.get("report_name"):
#             raise DashboardPayloadValidationError(
#                 "Report chart requires report_name"
#             )

#         if not frappe.db.exists("Report", payload["report_name"]):
#             raise DashboardPayloadValidationError(
#                 f"Report '{payload['report_name']}' does not exist"
#             )

#     # -----------------------------
#     # 4️⃣ Parent document consistency
#     # -----------------------------
#     if payload.get("parent_document_type"):
#         parent = payload["parent_document_type"]
#         if not frappe.db.exists("DocType", parent):
#             raise DashboardPayloadValidationError(
#                 f"Parent DocType '{parent}' does not exist"
#             )

#     # -----------------------------
#     # 5️⃣ Normalize optional fields
#     # -----------------------------
#     payload.setdefault("filters_json", "[]")
#     payload.setdefault("dynamic_filters_json", "")
#     payload.setdefault("roles", [])
#     payload.setdefault("y_axis", [])

#     return {
#         "status": "ok",
#         "normalized_payload": payload
#     }
