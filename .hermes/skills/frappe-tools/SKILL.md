---
name: frappe-tools
description: Exact reference for using Frappe CRUD tools correctly. Load this before any Frappe operation.
version: 1.0.0
---

# Frappe Tools Reference

## Exact Tool Names — Never Deviate
The only available tools are exactly:
- `frappe_get_doc`
- `frappe_get_list`
- `frappe_save_doc`
- `frappe_execute_action`
- `frappe_execute_report`

## Strict Action Adherence
If the user requests an action that you do not have a tool for (e.g., deleting a record), you **MUST** explicitly state that you cannot perform the action. You **MUST NEVER** attempt to substitute it with a workaround (like cancelling or modifying the record) unless the user explicitly asks you to do so. Never perform unrequested mutations.

## Communication Style
When communicating with the user, **DO NOT** mention the technical names of your tools (e.g., `frappe_get_doc`, `frappe_save_doc`). Always explain your capabilities and actions in plain, non-technical language. For example, instead of saying "I don't have the frappe_delete_doc tool", say "I am not able to delete records, but I can read or update them for you." Do not explain your internal rules, procedures, or strict action adherence guidelines. Just respond naturally and concisely.


## frappe_get_doc
```json
{"doctype": "Customer", "name": "CUST-00001"}
```

## frappe_get_list
```json
{
  "doctype": "Item",
  "fields": ["name", "item_name", "stock_uom"],
  "filters": {"disabled": 0},
  "limit": 20
}
```

## frappe_save_doc — Create
Omit `name` to create new:
```json
{"doc": {"doctype": "ToDo", "description": "Follow up"}}
```

## frappe_save_doc — Update
Include `name` to update existing:
```json
{"doc": {"doctype": "Customer", "name": "CUST-00001", "customer_name": "New Name"}}
```

## frappe_execute_action — Submit, Cancel, Approve
Use this tool for all document state transitions instead of trying to modify docstatus or workflow fields manually:
```json
{"doctype": "Sales Invoice", "name": "SINV-0001", "action": "Submit"}
```
For custom workflows, use the action name:
```json
{"doctype": "Leave Application", "name": "HR-LA-0001", "action": "Approve"}
```

## frappe_execute_report
Use this to query standard and custom Frappe reports.
```json
{"report_name": "Accounts Receivable", "filters": {"company": "My Company"}}
```
**Important Note on Currency**: When reporting financial figures from reports or records, ALWAYS use the `system_currency` provided in the tool output (e.g., KES) instead of defaulting to $. Do not assume USD unless explicitly stated.

## DocType Creation — Strict Procedure

1. If the user specifies a module use it exactly as provided.
   If no module is mentioned default to `Agent Builder`.
   Never call `frappe_get_list` on Module Def — just use the module name.
2. Required fields on every DocType doc:
   - `doctype`: "DocType"
   - `name`: DocType name
   - `module`: module name (from user or default "Agent Builder")
   - `fields`: array of field objects
   - `permissions`: at least one role with `read: 1`
3. Every field object requires: `fieldname`, `fieldtype`, `label`

### Page Doctype
See [`references/page-doctype-pattern.md`](references/page-doctype-pattern.md) for required fields and common errors.

## Valid Fieldtypes
'Data', 'Small Text', 'Text', 'Long Text', 'Text Editor', 'Markdown Editor',
'HTML Editor', 'Code', 'HTML', 'Password', 'JSON',
'Link', 'Dynamic Link', 'Table', 'Table MultiSelect',
'Int', 'Float', 'Currency', 'Percent', 'Rating', 'Duration',
'Date', 'Date and Time', 'Time',
'Check', 'Select', 'Autocomplete',
'Attach', 'Attach Image', 'Image',
'Color', 'Barcode', 'Geolocation', 'Signature', 'Phone', 'Icon',
'Read Only', 'Button', 'Heading', 'Fold',
'Section Break', 'Column Break', 'Tab Break'

## Pitfalls
- Link fields need `options` set to the linked DocType name
- Never call `frappe_get_doc` without confirming the record exists first
- **Workspace save fails with `NoneType` error** when `content` field is provided — `frappe_save_doc` has a server-side issue with the Workspace doctype's `content` JSON field. Workaround: create a custom DocType with child table instead for form-like pages, or use a Page doctype.
- **Page doctype requires `page_name` (Data, reqd), `standard` (Select: Yes/No, reqd), and `module` (Link → Module Def, reqd)** — omitting any of these causes a `NoneType` or `lower()` AttributeError or a validation error. Always include all three.
- **`frappe_save_doc` parameter format**: Pass fields flat at top level (`{"doctype": "ToDo", "description": "x"}`), NOT wrapped in a `doc` key. The `doc` wrapper causes `'str' object has no attribute 'get'` errors.
- **Child table DocType must exist before parent** — when creating a DocType with a `Table` field, create the child table DocType first, then reference it in the parent's `options`.