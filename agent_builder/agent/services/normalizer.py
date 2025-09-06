import copy

def normalize_payload(payload: dict) -> dict:
    """
    Normalize AI-generated payload so it becomes Frappe-compliant.
    Handles fields, permissions, and DocType-level corrections.
    """
    payload = copy.deepcopy(payload)  # avoid mutating original

    # --- DocType Level ---
    payload.setdefault("doctype", "DocType")
    payload.setdefault("custom", 1)
    payload.setdefault("fields", [])
    payload.setdefault("permissions", [])

    # --- Field Level ---
    for f in payload["fields"]:
        f.setdefault("in_list_view", 0)
        f.setdefault("in_standard_filter", 0)
        f.setdefault("reqd", 0)

        if f.get("fieldtype") == "Link":
            if not f.get("options"):
                f["options"] = f.get("label")

        elif f.get("fieldtype") == "Select":
            opts = f.get("options")
            if isinstance(opts, list):
                f["options"] = "\n".join(opts)

        elif f.get("fieldtype") == "Check":
            if f.get("default") in ("0", "1", 0, 1, None):
                f["default"] = int(f["default"])

        elif f.get("fieldtype") in ("Currency", "Float"):
            if "precision" not in f:
                f["precision"] = "2"

    # --- Permissions ---
    if not payload["permissions"]:
        payload["permissions"].append({
            "role": "System Manager",
            "read": 1, "write": 1, "create": 1, "delete": 1
        })

    for p in payload["permissions"]:
        if p.get("submit", 0) and not payload.get("is_submittable"):
            p["submit"] = 0

        # remove unsupported flags
        if "import" in p and not payload.get("is_importable"):
            p.pop("import")

    return payload
