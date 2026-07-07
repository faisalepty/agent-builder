# tools/frappe_tools/schema.py

CREATE_DOCUMENT = {
    "name": "create_document",
    "description": ("Create new Frappe documents with proper validation and child table support. Supports all DocTypes including those with child tables. WORKFLOW: First use get_doctype_info to understand the DocType structure, identify required fields and child tables, then create the document with proper field values. Child tables must be provided as arrays of objects. Referenced records (customers, items, warehouses, etc.) must already exist in the system. Use exact field names as shown in DocType metadata. Error responses include specific guidance for resolution. Common use cases: creating Sales Orders with line items, Purchase Orders with items and taxes, customer records, inventory transactions."),
    "parameters": {
            "type": "object",
            "properties": {
                "doctype": {
                    "type": "string",
                    "description": "The Frappe DocType name (e.g., 'Customer', 'Sales Invoice', 'Item', 'User'). Must match exact DocType name in system.",
                },
                "data": {
                    "type": "object",
                    "description": "Document field data as key-value pairs. Include all required fields for the doctype. Example: {'customer_name': 'ABC Corp', 'customer_type': 'Company'}",
                },
                "submit": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to submit the document after creation (for submittable doctypes like Sales Invoice). Use true only when explicitly requested.",
                },
                "validate_only": {
                    "type": "boolean",
                    "default": False,
                    "description": "Only validate the document without saving it. Use this to test data format and required fields before actual creation.",
                },
            },
            "required": ["doctype", "data"],
        },
}

UPDATE_DOCTYPE = {
    "name": "update_document",
    "description": (
        "Update/modify an existing Frappe document. Use when users want to change field values "
        "in an existing record. Always fetch the document first to understand current values. "
        "Supports child tables: send a list of row dicts under the table fieldname. If any row "
        "has a 'name' key, patch mode is used (rows matched by 'name' are updated, rows without "
        "'name' are appended, rows with '_delete': true are removed). If no row has a 'name', "
        "the entire child table is replaced. "
        "IMPORTANT: do NOT call this tool with a child-table doctype (e.g. 'Sales Order Item', "
        "'Purchase Order Item') directly — that bypasses the parent's recalculation and leaves "
        "totals stale. Always call it on the parent doctype (e.g. 'Sales Order') and pass the "
        "child row updates under the table fieldname (e.g. 'items')."
    ),
    "parameters": {
            "type": "object",
            "properties": {
                "doctype": {
                    "type": "string",
                    "description": "The Frappe DocType name (e.g., 'Customer', 'Sales Invoice', 'Item')",
                },
                "name": {
                    "type": "string",
                    "description": "The document name/ID to update (e.g., 'CUST-00001', 'SINV-00001')",
                },
                "data": {
                    "type": "object",
                    "description": (
                        "Field updates as key-value pairs. Only include fields that need to be changed. "
                        "For top-level scalar fields: {'customer_name': 'Updated Corp Name'}. "
                        "For child tables, pass a list of row dicts under the table fieldname. "
                        "Patch mode (any row has 'name'): matched rows are updated, unmatched rows are "
                        "appended, rows with '_delete': true are removed; existing rows not mentioned "
                        "are left untouched. Replace mode (no row has 'name'): the table is cleared and "
                        "refilled. Example patch: {'items': [{'name': 'abc-123', 'qty': 5}, "
                        "{'item_code': 'NEW', 'qty': 1}, {'name': 'old-1', '_delete': true}]}."
                    ),
                },
            },
            "required": ["doctype", "name", "data"],
        },
}


DELETE_DOCUMENT = {
    "name": "delete_document",
    "description": ("Delete an existing Frappe document. Use when users want to remove a record from the system. Always check for dependencies before deletion"),
    "parameters": {
            "type": "object",
            "properties": {
                "doctype": {
                    "type": "string",
                    "description": "The Frappe DocType name (e.g., 'Customer', 'Sales Invoice', 'Item')",
                },
                "name": {
                    "type": "string",
                    "description": "The document name/ID to delete (e.g., 'CUST-00001', 'SINV-00001')",
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "Force deletion even if there are dependencies. Use with caution.",
                },
            },
            "required": ["doctype", "name"],
        },
}

GENERATE_REPORT = {
    "name": "generate_report",
    "description": "Execute a Frappe report. IMPORTANT: Always call report_requirements(report_name) FIRST to get mandatory filters and valid options, then call this tool with explicit filters. Missing filters are auto-defaulted (dates, company) which often returns empty data. Supports Script Reports, Query Reports, and Custom Reports. Report Builder reports are not supported. Large/prepared reports are handled automatically with polling.",
    "parameters": {
            "type": "object",
            "properties": {
                "report_name": {
                    "type": "string",
                    "description": "Exact name of the Frappe report to execute (e.g., 'Accounts Receivable Summary', 'Sales Analytics', 'Stock Balance'). Use report_list to find available reports.",
                },
                "filters": {
                    "type": "object",
                    "default": {},
                    "description": "Filter key-value pairs. Get valid keys and values from report_requirements first. Dates: YYYY-MM-DD. Link fields (company, customer) must be exact DB names. Select fields must match allowed options exactly.",
                },
                "format": {
                    "type": "string",
                    "enum": ["json", "csv", "excel"],
                    "default": "json",
                    "description": "Output format. Use 'json' for data analysis, 'csv' for exports, 'excel' for spreadsheet files.",
                },
            },
            "required": ["report_name"],
        }
}

LIST_DOCTYPES = {
    "name": "list_doctypes",
    "description": "Search and list Frappe documents with optional filtering. Use this when users want to find records, get lists of documents, or search for data. This is the primary tool for data exploration and discovery.",
    "parameters": {
            "type": "object",
            "properties": {
                "doctype": {
                    "type": "string",
                    "description": "The Frappe DocType to search (e.g., 'Customer', 'Sales Invoice', 'Item', 'User'). Must match exact DocType name.",
                },
                "filters": {
                    "type": "object",
                    "default": {},
                    "description": "Search filters as key-value pairs. Examples: {'status': 'Active'}, {'customer_type': 'Company'}, {'creation': ['>', '2024-01-01']}. Use empty {} to get all records.",
                },
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific fields to retrieve. Examples: ['name', 'customer_name', 'email'], ['name', 'item_name', 'item_code']. Leave empty to get standard fields.",
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "maximum": 1000,
                    "description": "Maximum number of records to return. Default is 20, maximum is 1000.",
                },
                "order_by": {
                    "type": "string",
                    "description": "Order results by field. Examples: 'creation desc', 'name asc', 'modified desc'. Default is 'creation desc'.",
                },
            },
            "required": ["doctype"],
        },
}

