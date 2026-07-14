"""Tool schemas for MCP function definitions."""

FRAPPE_CREATE_DOC = {
    "name": "frappe_create_doc",
    "description": (
        "Create a new Frappe document, with support for child tables. "
        "Fails clearly if a document with the given name already exists — use "
        "frappe_save_doc to update it instead. Referenced records (customers, items, "
        "warehouses, etc.) must already exist in the system. "
        "Set validate_only=true to check the data against Frappe's validation without "
        "saving, or submit=true to submit immediately after creation (for submittable doctypes)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doc": {
                "type": "object",
                "description": (
                    "Document data as a dict. Must include 'doctype'. Include 'module' to specify "
                    "the module, use \"Agent Builder\" for default. Child table fields must be lists "
                    "of row dicts. Example: {\"doctype\": \"ToDo\", \"description\": \"Follow up\"}"
                ),
            },
            "submit": {
                "type": "boolean",
                "default": False,
                "description": "Submit the document right after creation. Only use when explicitly requested.",
            },
            "validate_only": {
                "type": "boolean",
                "default": False,
                "description": "If true, validate the data without persisting the document.",
            },
        },
        "required": ["doc"],
    },
}

FRAPPE_UPDATE_DOC = {
    "name": "frappe_update_doc",
    "description": (
        "Update field values on an existing Frappe document. Cannot be called on a "
        "child-table doctype directly (e.g. 'Sales Order Item') — always target the "
        "parent doctype and pass child-row changes under the table fieldname. "
        "Child tables support patch mode (any row includes 'name': matched rows updated, "
        "unmatched rows appended, rows with '_delete': true removed, other existing rows "
        "left untouched) or replace mode (no row has 'name': table cleared and refilled)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "The Frappe DocType name of the document to update (e.g. 'Sales Order').",
            },
            "name": {
                "type": "string",
                "description": "The document name/ID to update (e.g. 'SO-00001').",
            },
            "data": {
                "type": "object",
                "description": (
                    "Field updates as key-value pairs — only include fields that need to change. "
                    "For child tables, pass a list of row dicts under the table fieldname. "
                    "Example: {\"items\": [{\"name\": \"abc-123\", \"qty\": 5}, "
                    "{\"item_code\": \"NEW\", \"qty\": 1}, {\"name\": \"old-1\", \"_delete\": true}]}"
                ),
            },
        },
        "required": ["doctype", "name", "data"],
    },
}

FRAPPE_DELETE_DOC = {
    "name": "frappe_delete_doc",
    "description": (
        "Delete an existing Frappe document. Checks that the document exists and that "
        "the current user has delete permission before removing it. "
        "If the document is linked to other records, deletion fails unless force=true is set."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "The Frappe DocType name (e.g., 'ToDo', 'Sales Invoice', 'Item').",
            },
            "name": {
                "type": "string",
                "description": "The document name/ID to delete (e.g., 'CUST-00001').",
            },
            "force": {
                "type": "boolean",
                "default": False,
                "description": "Force deletion even if the document is linked to other documents. Use with caution — this can break referential integrity.",
            },
        },
        "required": ["doctype", "name"],
    },
}

FRAPPE_GET_LIST = {
    "name": "frappe_get_list",
    "description": (
        "Search and list Frappe documents with optional filtering. Use this to find records, "
        "browse a doctype, or discover data before creating/updating documents. "
        "For aggregated queries (SUM, COUNT, GROUP BY), use frappe_aggregate instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "The Frappe DocType to search (e.g. 'Customer', 'Sales Invoice', 'Item').",
            },
            "filters": {
                "type": "object",
                "default": {},
                "description": (
                    "Search filters as key-value pairs. Examples: {\"status\": \"Active\"}, "
                    "{\"creation\": [\">\", \"2024-01-01\"]}. Use {} to get all records."
                ),
            },
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Fields to retrieve, e.g. ['name', 'customer_name']. Defaults to ['name', 'creation', 'modified'].",
            },
            "parent_doctype": {
                "type": "string",
                "description": (
                    "Required when doctype is a child table (e.g. 'Agent Tool Call'). Without it, "
                    "Frappe's permission layer silently returns only the 'name' field for every "
                    "row. If unsure whether a doctype is a child table, check frappe_get_doctype_info "
                    "first — it reports is_child_table."
                ),
            },
            "limit": {
                "type": "integer",
                "default": 20,
                "maximum": 1000,
                "description": "Maximum records to return. Default 20, max 1000.",
            },
            "order_by": {
                "type": "string",
                "description": "Sort order, e.g. 'creation desc', 'name asc'. Default 'creation desc'.",
            },
        },
        "required": ["doctype"],
    },
}

FRAPPE_GET_DOC = {
    "name": "frappe_get_doc",
    "description": (
        "Retrieve full details of a specific Frappe document. Use when the user asks about "
        "a particular record and you already know its doctype and name/ID."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "The Frappe DocType name (e.g. 'Customer', 'Sales Invoice', 'Item').",
            },
            "name": {
                "type": "string",
                "description": "The document name/ID (e.g. 'CUST-00001', 'SINV-00001').",
            },
        },
        "required": ["doctype", "name"],
    },
}

FRAPPE_GET_DOCTYPE_INFO = {
    "name": "frappe_get_doctype_info",
    "description": (
        "Get a DocType's field structure: fieldnames, types, required/read-only flags, "
        "link fields, and child-table field definitions. Call this before "
        "frappe_create_doc or frappe_save_doc when the exact field shape is unknown."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "The DocType name to inspect, e.g. 'Sales Order'.",
            },
        },
        "required": ["doctype"],
    },
}

FRAPPE_SUBMIT_DOC = {
    "name": "frappe_submit_doc",
    "description": (
        "Submit a draft document to finalize it. Only works on documents in draft state "
        "(docstatus=0) and on doctypes that support submission (e.g. Sales Invoice, "
        "Purchase Order). Submitted documents become read-only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "The Frappe DocType name (e.g. 'Sales Invoice', 'Purchase Order').",
            },
            "name": {
                "type": "string",
                "description": "The document name/ID to submit (e.g. 'SINV-00001').",
            },
        },
        "required": ["doctype", "name"],
    },
}

FRAPPE_GENERATE_REPORT = {
    "name": "frappe_generate_report",
    "description": (
        "Execute any Frappe report (Query Report, Script Report, or Report Builder) "
        "and return its data. This calls frappe.desk.query_report.run() directly — "
        "the same function the Frappe web UI uses. Missing filters are auto-defaulted "
        "(fiscal-year dates, default company) which often returns 0 rows — pass "
        "explicit filters when known. "
        "NOTE: financial-statement reports (Balance Sheet, Profit and Loss, Gross and Net "
        "Profit, Cash Flow, etc.) often require 'filter_based_on': 'Date Range' in "
        "addition to from_date/to_date. If you encounter 'mandatory' errors, the tool will "
        "return the exact filters it passed. If it still fails, use frappe_get_list on the "
        "underlying doctype (e.g., GL Entry) to fetch data directly."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "report_name": {
                "type": "string",
                "description": "Exact report name, e.g. 'Accounts Receivable Summary', 'Sales Analytics'.",
            },
            "filters": {
                "type": "object",
                "default": {},
                "description": (
                    "Filter key-value pairs, e.g. {\"company\": \"your company name\", \"from_date\": \"2026-01-01\", "
                    "\"to_date\": \"2026-12-31\"}. Financial reports may also need "
                    "\"filter_based_on\": \"Date Range\" — check frappe_get_report_filters if unsure."
                ),
            },
        },
        "required": ["report_name"],
    },
}

FRAPPE_LIST_REPORTS = {
    "name": "frappe_list_reports",
    "description": (
        "List available Frappe reports, optionally filtered by module, report type, "
        "or name substring. Use this to discover report names before calling frappe_generate_report."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "module": {
                "type": "string",
                "description": "Filter to reports in a specific module, e.g. 'Accounts', 'Selling'.",
            },
            "report_type": {
                "type": "string",
                "enum": ["Query Report", "Script Report", "Report Builder"],
                "description": "Filter to a specific report type.",
            },
            "name_contains": {
                "type": "string",
                "description": "Filter to reports whose name contains this text (case-insensitive). Example: 'downtime' finds 'Downtime Analysis'.",
            },
        },
        "required": [],
    },
}

FRAPPE_AGGREGATE = {
    "name": "frappe_aggregate",
    "description": (
        "Run an aggregated GROUP BY query on a doctype — SUM, COUNT, AVG, MIN, MAX. "
        "Use this for any analytical question: 'total sales per customer', 'downtime hours "
        "per machine', 'count of orders by status'. Do NOT fetch raw rows with frappe_get_list "
        "and try to sum them manually — use this tool instead for reliable results. "
        "Aliases can be any valid name (letters, digits, underscores) — they are output "
        "column names you define, not existing doctype fields."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "The doctype to query, e.g. 'Sales Invoice', 'Downtime Entry'.",
            },
            "group_by": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Fields to group by. These must be real fields on the doctype. "
                    "Use [] for an overall aggregate with no grouping."
                ),
            },
            "aggregations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {
                            "type": "string",
                            "description": "The doctype field to aggregate (must exist on the doctype).",
                        },
                        "function": {
                            "type": "string",
                            "enum": ["sum", "count", "avg", "min", "max"],
                            "description": "Aggregation function.",
                        },
                        "alias": {
                            "type": "string",
                            "description": (
                                "Output column name you choose — any valid identifier "
                                "(letters, digits, underscores). Examples: 'total_mins', "
                                "'total_sales', 'entry_count'. Do not use spaces or hyphens."
                            ),
                        },
                    },
                    "required": ["field", "function", "alias"],
                },
                "description": (
                    "Aggregations to compute. Example: "
                    '[{"field": "downtime", "function": "sum", "alias": "total_mins"}, '
                    '{"field": "name", "function": "count", "alias": "entry_count"}]'
                ),
            },
            "filters": {
                "type": "object",
                "default": {},
                "description": (
                    "WHERE filters on real doctype fields. "
                    "Examples: {\"company\": \"Apex Steel\", \"docstatus\": 1}, "
                    "{\"from_time\": [\">\", \"2025-01-01\"]}. "
                    "Do NOT put aliases or aggregate fields here — only real doctype fields."
                ),
            },
            "having": {
                "type": "object",
                "default": {},
                "description": (
                    "Filter on aggregate results using aliases. "
                    "Example: {\"total_mins\": [\">\", 500]}. "
                    "Only supports simple comparison operators: >, >=, <, <=, =, !="
                ),
            },
            "order_by": {
                "type": "string",
                "description": (
                    "Sort results. Can use group_by fields or aggregate aliases. "
                    "Examples: 'total_mins desc', 'workstation asc'. "
                    "Append 'desc' or 'asc' for direction."
                ),
            },
            "limit": {
                "type": "integer",
                "default": 100,
                "description": "Max group rows to return.",
            },
        },
        "required": ["doctype", "group_by", "aggregations"],
    },
}

FRAPPE_GET_WORKFLOW_INFO = {
    "name": "frappe_get_workflow_info",
    "description": (
        "Get the workflow states and transitions defined for a DocType, if one exists. "
        "Use before attempting frappe_save_doc/frappe_submit_doc on a doctype whose "
        "records are workflow-gated (e.g. approval flows), to see valid next actions "
        "and which field tracks state (workflow_state_field)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "The DocType to check, e.g. 'Purchase Order', 'Leave Application'.",
            },
        },
        "required": ["doctype"],
    },
}

FRAPPE_RUN_WORKFLOW = {
    "name": "frappe_run_workflow",
    "description": (
        "Execute a workflow action on a document (e.g. 'Approve', 'Reject', 'Submit for Review'). "
        "Use for any business-process action beyond a plain field update or raw submit — this "
        "correctly applies workflow permissions, state transitions, and side effects (like "
        "notifications). Do not set workflow_state directly via frappe_save_doc; use this instead. "
        "If unsure of the exact action name, call frappe_get_workflow_info first, or retry after "
        "this tool returns the available_actions for the document's current state."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "Document type, e.g. 'Purchase Order', 'Leave Application'.",
            },
            "name": {
                "type": "string",
                "description": "Document name/ID, e.g. 'PO-00001'.",
            },
            "action": {
                "type": "string",
                "description": "Exact workflow action name, case-sensitive (e.g. 'Approve', 'Reject').",
            },
        },
        "required": ["doctype", "name", "action"],
    },
}

FRAPPE_GET_PENDING_APPROVALS = {
    "name": "frappe_get_pending_approvals",
    "description": (
        "Get documents currently pending the logged-in user's approval, via the Workflow "
        "Action system (not Todos or Notifications). Use when the user asks about pending "
        "approvals, items awaiting review, or their approval queue. Pair with "
        "frappe_run_workflow to act on the returned available_actions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "Optional: restrict to a specific doctype, e.g. 'Purchase Order'.",
            },
            "limit": {
                "type": "integer",
                "default": 50,
                "maximum": 200,
                "description": "Maximum pending actions to return.",
            },
            "include_actions": {
                "type": "boolean",
                "default": True,
                "description": "Include available workflow actions per document. Set false for faster results on large lists.",
            },
        },
        "required": [],
    },
}

FRAPPE_SEARCH_DOCUMENTS = {
    "name": "frappe_search_documents",
    "description": (
        "Search by name across doctypes. Defaults to common doctypes (Customer, Item, Sales Order, etc.). "
        "Use the 'doctypes' parameter to search specific doctypes. Prefer frappe_get_list when "
        "you know the exact doctype."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Text to search for in document names."},
            "doctypes": {
                "type": "string",
                "description": "Comma-separated list of doctypes to search. Overrides defaults. Example: 'Customer,Supplier'.",
            },
            "limit": {"type": "integer", "default": 20, "description": "Maximum results across all doctypes."},
        },
        "required": ["query"],
    },
}

FRAPPE_SEARCH_LINK = {
    "name": "frappe_search_link",
    "description": (
        "Resolve a fuzzy/partial name to a valid document reference for a link field, "
        "using Frappe's native relevance-ranked search. Use before frappe_create_doc or "
        "frappe_save_doc when you have an approximate name (e.g. a customer or item) but "
        "not its exact record name — this reduces 'does not exist' validation failures."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doctype": {
                "type": "string",
                "description": "Target DocType being linked to, e.g. 'Customer', 'Item'.",
            },
            "query": {
                "type": "string",
                "description": "Partial or fuzzy name to search for.",
            },
            "filters": {
                "type": "object",
                "default": {},
                "description": "Optional additional filters to narrow results, e.g. {\"disabled\": 0}.",
            },
        },
        "required": ["doctype", "query"],
    },
}