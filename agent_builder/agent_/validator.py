# validator.py
import frappe
from typing import Tuple, List, Dict

RESERVED = {"name","owner","creation","modified","modified_by","parent","parentfield","parenttype","idx","docstatus"}
FALLBACK_TYPES = ["Autocomplete", "Attach", "Attach Image", "Barcode", "Button", "Check", "Code", "Color",
"Currency", "Data", "Date", "Datetime", "Duration", "Dynamic Link", "Float", "Geolocation",
"Heading", "HTML", "HTML Editor", "Icon", "Image", "Int", "JSON", "Link", "Long Text",
"Markdown Editor", "Password", "Percent", "Phone", "Read Only", "Rating", "Select",
"Signature", "Small Text", "Table", "Table MultiSelect", "Text", "Text Editor", "Time"]

class ValidationError:
    def __init__(self, message, field=None, suggestion=None):
        self.message = message
        self.field = field
        self.suggestion = suggestion
    def as_dict(self):
        return {"message": self.message, "field": self.field, "suggestion": self.suggestion}

class ValidationService:
    def _sanitize_fieldname(self, fn: str) -> str:
        if not isinstance(fn, str):
            fn = str(fn or "")
        fn = fn.strip().lower().replace(" ", "_")
        if fn in RESERVED:
            return f"custom_{fn}"
        return fn

    def _valid_fieldtype(self, t: str) -> bool:
        try:
            from frappe.model.meta import all_fieldtypes
            return t in all_fieldtypes
        except Exception:
            return t in FALLBACK_TYPES

    def validate_fields(self, fields) -> (List[dict], List[ValidationError]):
        sanitized = []
        errors = []
        for i, f in enumerate(fields or []):
            if not isinstance(f, dict):
                errors.append(ValidationError(f"Field at index {i} is not an object"))
                continue
            if not f.get("fieldname"):
                errors.append(ValidationError("Missing fieldname", field=f))
            if not f.get("fieldtype"):
                errors.append(ValidationError("Missing fieldtype", field=f.get("fieldname")))
            if not f.get("label"):
                errors.append(ValidationError("Missing label", field=f.get("fieldname")))
            fname = self._sanitize_fieldname(f.get("fieldname","field_%d"%i))
            f["fieldname"] = fname
            if f.get("fieldtype") and not self._valid_fieldtype(f["fieldtype"]):
                errors.append(ValidationError(f"Invalid fieldtype '{f['fieldtype']}'", field=fname, suggestion="Use Data, Text, Int, Float, Link etc."))
            if f.get("fieldtype") == "Link":
                target = f.get("options")
                if not target:
                    errors.append(ValidationError("Link field missing options", field=fname, suggestion="Set options to the target DocType name"))
                elif not frappe.db.exists("DocType", target):
                    errors.append(ValidationError(f"Link target '{target}' not found", field=fname))
            sanitized.append(f)
        return sanitized, errors

    def validate_doc(self, doc) -> (dict, List[ValidationError]):
        errors = []
        if not isinstance(doc, dict):
            return None, [ValidationError("Payload is not an object")]
        if doc.get("doctype") != "DocType":
            errors.append(ValidationError("Currently only DocType creation is supported", field="doctype"))
            return None, errors
        required = ["name","module","fields"]
        for r in required:
            if r not in doc:
                errors.append(ValidationError(f"Missing required '{r}'", field=r))
        sanitized = dict(doc)
        if "fields" in doc:
            s_fields, f_errors = self.validate_fields(doc.get("fields", []))
            sanitized["fields"] = s_fields
            errors.extend(f_errors)
        if "permissions" in doc:
            # validate roles exist
            for p in doc.get("permissions", []):
                if not p.get("role"):
                    errors.append(ValidationError("Permission missing role", field="permissions"))
                elif not frappe.db.exists("Role", p.get("role")):
                    errors.append(ValidationError(f"Role '{p.get('role')}' not found", field="permissions"))
        return sanitized, errors
