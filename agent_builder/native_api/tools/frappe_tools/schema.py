# tools/frappe_tools/schema.py

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
        "Create a new Frappe document/doctype or update an existing one. eg Doctype, Workspace, Dashboard, Charts, etc. "
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
                    "Include 'module' to specify the module name. use \"Agent Builder\" for default. "
                    "Include 'name' to update an existing document. "
                    "Example: {\"doctype\": \"ToDo\", \"description\": \"Follow up\"}"
                ),
            },
        },
        "required": ["doc"],
    },
}

FRAPPE_EXECUTE_ACTION = {
    "name": "frappe_execute_action",
FRAPPE_EXECUTE_ACTION = {
    "name": "frappe_execute_action",
    "description": (
        "Transition a document's state via Submission, Cancellation, or Frappe Workflows. "
        "Use this tool when you need to submit, cancel, approve, or reject a document."
        "Transition a document's state via Submission, Cancellation, or Frappe Workflows. "
        "Use this tool when you need to submit, cancel, approve, or reject a document."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "The DocType name e.g. 'Sales Order'",
                "description": "The DocType name e.g. 'Sales Order'",
            },
            "name": {
                "type": "string",
                "description": "The document name/ID e.g. 'SO-00001'",
            },
            "action": {
                "type": "string",
                "description": "The action to execute. Standard actions: 'Submit', 'Cancel'. For workflows, use the action name e.g. 'Approve', 'Reject'.",
            },
        },
        "required": ["doctype", "name", "action"],
    },
}

VIEW_SKILL = {
    "name": "view_skill",
    "description": (
        "Fetch a Skill document by name. "
        "Returns all fields of the Skill document."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "The action to execute. Standard actions: 'Submit', 'Cancel'. For workflows, use the action name e.g. 'Approve', 'Reject'.",
            },
        },
        "required": ["doctype", "name", "action"],
    },
}
