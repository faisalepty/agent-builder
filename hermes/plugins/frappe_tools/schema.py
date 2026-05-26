# agent_builder/hermes/plugins/frappe_tools/schemas.py

FRAPPE_GET_DOC = {
    "name": "frappe_get_doc",
    "description": (
        "Fetch a single Frappe document by DocType and name. "
        "Use this when you need the full details of a specific record. "
        "Returns all fields including child tables."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "The DocType name e.g. 'Customer', 'Sales Order', 'Item'",
            },
            "name": {
                "type": "string",
                "description": "The document name/ID e.g. 'CUST-00001'",
            },
        },
        "required": ["doctype", "name"],
    },
}

FRAPPE_GET_LIST = {
    "name": "frappe_get_list",
    "description": (
        "List Frappe documents of a given DocType with optional filters and fields. "
        "Use this to search, browse, or count records. "
        "Filters use key-value pairs e.g. {\"status\": \"Open\"}."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "The DocType name e.g. 'Customer', 'Sales Order'",
            },
            "filters": {
                "type": "object",
                "description": "Key-value filters e.g. {\"status\": \"Open\", \"customer\": \"CUST-00001\"}",
            },
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Fields to return e.g. [\"name\", \"status\", \"grand_total\"]. Defaults to [\"name\"].",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of records to return. Defaults to 20.",
            },
        },
        "required": ["doctype"],
    },
}

FRAPPE_SAVE_DOC = {
    "name": "frappe_save_doc",
    "description": (
        "Create a new Frappe document or update an existing one. "
        "To create: provide doctype and fields, omit name. "
        "To update: include the name field of the existing document. "
        "Child table rows must include their own doctype field."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doc": {
                "type": "object",
                "description": (
                    "Document data as a dict. Must include 'doctype'. "
                    "Include 'name' to update an existing document. "
                    "Example: {\"doctype\": \"ToDo\", \"description\": \"Follow up\"}"
                ),
            },
        },
        "required": ["doc"],
    },
}

FRAPPE_DELETE_DOC = {
    "name": "frappe_delete_doc",
    "description": (
        "Permanently delete a Frappe document by DocType and name. "
        "Use with caution — this cannot be undone. "
        "Only works on documents the current user has delete permission for."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "The DocType name e.g. 'ToDo'",
            },
            "name": {
                "type": "string",
                "description": "The document name/ID to delete",
            },
        },
        "required": ["doctype", "name"],
    },
}