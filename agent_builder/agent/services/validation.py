import frappe
from typing import List

# ============================================================
# Schema Registry (expandable)
# ============================================================
SCHEMA = {
    "DocType": ["name", "module", "fields"],
    "Dashboard": ["dashboard_name", "module"],
    "Dashboard Chart": ["chart_name", "chart_type", "module"],
    # add more as needed
}

# ============================================================
# Utility Validators
# ============================================================
def _get_all_fieldtypes():
    try:
        from frappe.model.meta import all_fieldtypes
        return all_fieldtypes
    except Exception:
        # fallback minimal set
        return [
    "Attach",
    "Attach Image",
    "Autocomplete",
    "Barcode",
    "Button",
    "Check",
    "Code",
    "Color",
    "Currency",
    "Data",
    "Date",
    "Datetime",
    "Duration",
    "Dynamic Link",
    "Float",
    "Geolocation",
    "Heading",
    "HTML",
    "HTML Editor",
    "Icon",
    "Image",
    "Int",
    "JSON",
    "Link",
    "Long Text",
    "Markdown Editor",
    "Password",
    "Percent",
    "Phone",
    "Rating",
    "Read Only",
    "Select",
    "Signature",
    "Small Text",
    "Table",
    "Table MultiSelect",
    "Text",
    "Text Editor",
    "Time"
]


def validate_fieldtype(fieldtype: str):
    valid_types = _get_all_fieldtypes()
    if fieldtype not in valid_types:
        return f"Invalid fieldtype '{fieldtype}'. Valid types: {', '.join(valid_types[:10])}..."
    return None

def validate_link_field(field: dict):
    if field.get("fieldtype") == "Link":
        target = field.get("options")
        if not target:
            return f"Link field '{field.get('fieldname')}' missing 'options' (target DocType)."
        if not frappe.db.exists("DocType", target):
            return f"Link field '{field.get('fieldname')}' references non-existent DocType '{target}'."
    return None

def sanitize_fieldname(fieldname: str) -> str:
    RESERVED = {
        "name","owner","creation","modified","modified_by",
        "parent","parentfield","parenttype","idx","docstatus"
    }
    if not isinstance(fieldname, str):
        fieldname = str(fieldname or "")
    fieldname = fieldname.strip().lower().replace(" ", "_")
    if fieldname in RESERVED:
        return f"custom_{fieldname}"
    return fieldname

# ============================================================
# Structured Error (for AI consumption)
# ============================================================
class ValidationError:
    def __init__(self, message: str, severity: str = "error", suggestion: str = None):
        self.message = message
        self.severity = severity  # "error" | "warning"
        self.suggestion = suggestion

    def as_dict(self):
        return {
            "message": self.message,
            "severity": self.severity,
            "suggestion": self.suggestion
        }

# ============================================================
# Validation Service (Basic + Advanced)
# ============================================================
class ValidationService:
    def __init__(self):
        pass

    # ------------------ Field Validation ------------------
    def validate_fields(self, fields: list):
        sanitized, errors = [], []
        for i, f in enumerate(fields or []):
            if not isinstance(f, dict):
                errors.append(ValidationError(f"Field at index {i} is not an object: {f!r}"))
                continue

            if not f.get("fieldname"):
                errors.append(ValidationError(f"Field at index {i} missing 'fieldname'."))
            if not f.get("fieldtype"):
                errors.append(ValidationError(f"Field '{f.get('fieldname') or ('index '+str(i))}' missing 'fieldtype'."))
            if not f.get("label"):
                errors.append(ValidationError(f"Field '{f.get('fieldname') or ('index '+str(i))}' missing 'label'."))

            # sanitize name
            fieldname = sanitize_fieldname(f.get("fieldname", f"field_{i}"))
            f["fieldname"] = fieldname

            # validate type
            if f.get("fieldtype"):
                err = validate_fieldtype(f["fieldtype"])
                if err:
                    errors.append(ValidationError(err))

            # link-specific
            link_err = validate_link_field(f)
            if link_err:
                errors.append(ValidationError(link_err))

            sanitized.append(f)
        return sanitized, errors

    # ------------------ Permission Validation ------------------
    def validate_permissions(self, perms: list):
        valid, errors = [], []
        for i, p in enumerate(perms or []):
            if not isinstance(p, dict):
                errors.append(ValidationError(f"Permission at index {i} is not an object."))
                continue
            role = p.get("role")
            if not role:
                errors.append(ValidationError(f"Permission at index {i} missing 'role'."))
                continue
            if not frappe.db.exists("Role", role):
                errors.append(ValidationError(f"Permission references non-existent role '{role}'."))
                continue
            valid.append(p)
        return valid, errors

    # # ------------------ Advanced Validation ------------------
    # def validate_cross_field_logic(self, doc: dict):
    #     errors = []
    #     if doc.get("doctype") == "DocType":
    #         for f in doc.get("fields", []):
    #             if f.get("fieldtype") == "Check" and f.get("default") not in ("0", "1", None):
    #                 errors.append(
    #                     ValidationError(
    #                         f"Field '{f['fieldname']}' is a Check but has invalid default '{f.get('default')}'.",
    #                         suggestion="Use '0' or '1' for default."
    #                     )
    #                 )
    #     return errors

    def validate_cross_entity_logic(self, doc: dict):
        errors = []
        if doc.get("doctype") == "Dashboard Chart":
            dataset = doc.get("dataset")
            if dataset and not frappe.db.exists("DocType", dataset):
                errors.append(
                    ValidationError(
                        f"Dashboard Chart references unknown dataset '{dataset}'.",
                        suggestion="Ensure dataset DocType exists before linking."
                    )
                )
        return errors

    # ------------------ Top-level Doc Validation ------------------
    def validate_doc(self, doc: dict):
        errors: List[ValidationError] = []
        if not isinstance(doc, dict):
            return None, [ValidationError("Payload item is not an object/dict.")]

        doctype = doc.get("doctype")
        if not doctype:
            return None, [ValidationError("Missing 'doctype' in document.")]

        required = SCHEMA.get(doctype, [])
        for field in required:
            if field not in doc:
                errors.append(ValidationError(f"Missing required field '{field}' for {doctype}."))

        sanitized = dict(doc)

        if doctype == "DocType":
            if "fields" in doc:
                sanitized_fields, field_errors = self.validate_fields(doc.get("fields", []))
                sanitized["fields"] = sanitized_fields
                errors.extend(field_errors)
            if "permissions" in doc:
                valid_perms, perm_errors = self.validate_permissions(doc.get("permissions", []))
                sanitized["permissions"] = valid_perms
                errors.extend(perm_errors)

        # run advanced checks
        errors.extend(self.validate_cross_entity_logic(sanitized))

        return sanitized, errors