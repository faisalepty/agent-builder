---
name: frappe-chart
description: Create standalone Frappe Dashboard Charts for use in Dashboards or Workspaces. Load before creating any chart.
version: 1.0.0
author: agent_builder
metadata:
  hermes:
    tags: [frappe, chart, analytics, visualization]
    category: frappe
---

# Frappe Dashboard Chart

## When to Use
Creating a Dashboard Chart that visualises DocType data over time or by group.
Charts are standalone documents — they can live in a Dashboard or be embedded
directly in a Workspace.

## Key Knowledge

### chart_type options
| Type | Use for |
|---|---|
| `Count` | Number of records over time |
| `Sum` | Total of a numeric field over time |
| `Average` | Average of a numeric field over time |
| `Group By` | Distribution by a category field |

### time_interval options
`Yearly`, `Quarterly`, `Monthly`, `Weekly`, `Daily`

### timespan options
`Last Year`, `Last Quarter`, `Last Month`, `Last Week`

### Chart document full structure
```json
{
  "doctype": "Dashboard Chart",
  "chart_name": "Monthly Revenue",
  "document_type": "Sales Invoice",
  "chart_type": "Sum",
  "based_on": "posting_date",
  "value_based_on": "grand_total",
  "timespan": "Last Year",
  "time_interval": "Monthly",
  "filters_json": "[]",
  "is_public": 1,
  "type": "bar"
}
```

### type (visual style)
`bar`, `line`, `pie`, `donut`, `percentage`

### Group By chart
When `chart_type` is `Group By`:
- Set `group_by_based_on` to the field to group by (e.g. `"status"`, `"customer"`)
- Set `group_by_type` to `"Count"` or `"Sum"`
- `based_on` (date field) is NOT required for Group By

```json
{
  "doctype": "Dashboard Chart",
  "chart_name": "Invoices by Status",
  "document_type": "Sales Invoice",
  "chart_type": "Group By",
  "group_by_based_on": "status",
  "group_by_type": "Count",
  "filters_json": "[]",
  "is_public": 1,
  "type": "pie"
}
```

## Procedure

1. Confirm the target DocType exists — `frappe_get_doc` on `"DocType"` with the target name.
2. Confirm `based_on` field is Date or Datetime type if using time-series chart types.
3. For Sum/Average — confirm `value_based_on` is a numeric field (Int, Float, Currency).
4. Save the chart using `frappe_save_doc`.
5. Confirm by fetching back and checking `chart_name` and `document_type`.

## Pitfalls
- `based_on` must be a Date or Datetime field — using a non-date field breaks the chart silently.
- `value_based_on` is required for Sum and Average — missing it returns zeros.
- `filters_json` must be a valid JSON string — use `"[]"` for no filters, not `null` or `""`.
- `is_public: 0` hides the chart from all users except the creator.
- Chart names must be unique across all Dashboard Charts.