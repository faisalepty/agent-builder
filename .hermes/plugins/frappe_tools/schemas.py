# agent_builder/.hermes/plugins/frappe_tools/schemas.py

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
                "description": "Fields to return e.g. [\"name\", \"status\", \"grand_total\"]. Defaults to [\"name\"]. Use [\"*\"] to fetch all fields.",
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
        "Create a new Frappe document or update an existing one. eg Doctype, Workspace, Dashboard, Charts, etc. "
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

FRAPPE_EXECUTE_ACTION = {
    "name": "frappe_execute_action",
    "description": (
        "Transition a document's state via Submission, Cancellation, or Frappe Workflows. "
        "Use this tool when you need to submit, cancel, approve, or reject a document."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
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
                "description": "The name of the Skill document to fetch",
            },
        },
        "required": ["skill_name"],
    },
}

LIST_SKILLS = {
    "name": "list_skills",
    "description": (
        "List Skill documents with optional limit. "
        "Returns name and description of each Skill."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of Skill documents to return. Defaults to 20.",
            },
        },
        "required": [],
    },
}

FRAPPE_EXECUTE_REPORT = {
    "name": "frappe_execute_report",
    "description": (
        "Execute a Frappe Report (Standard or Custom). "
        "Use this to get aggregated data, financials, or analytics like Profit and Loss, Sales, or Outstanding Balances. "
        "Returns the report's result rows and columns."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "report_name": {
                "type": "string",
                "description": "The name of the Report e.g. 'Profit and Loss Statement', 'Accounts Receivable'",
            },
            "filters": {
                "type": "object",
                "description": "Key-value filters to apply to the report (e.g. {\"company\": \"My Company\", \"from_date\": \"2023-01-01\"}). If the user does not specify dates or company, leave this empty or omit the filters, and the system will automatically use the current fiscal year and default company.",
            },
        },
        "required": ["report_name"],
    },
}

FRAPPE_GET_META = {
    "name": "frappe_get_meta",
    "description": (
        "Fetch the metadata (schema) for a given DocType. "
        "Use this to understand what fields, fieldtypes, and child tables are available "
        "before querying or inserting data. This prevents guessing field names."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "The DocType name e.g. 'Item', 'Sales Order'",
            },
        },
        "required": ["doctype"],
    },
}

FRAPPE_RUN_SQL = {
    "name": "frappe_run_sql",
    "description": (
        "Execute a read-only SQL query against the MariaDB database. "
        "Use this for complex aggregations, joins, or when you need data across multiple tables. "
        "Only SELECT statements are allowed. Table names must be prefixed with 'tab' e.g. 'tabItem'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The SELECT SQL query to execute",
            },
        },
        "required": ["query"],
    },
}