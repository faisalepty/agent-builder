---
name: frappe-dashboard
description: Create Frappe Dashboards with number cards and charts. Load before creating or modifying any Dashboard.
version: 1.0.0
author: agent_builder
metadata:
  hermes:
    tags: [frappe, dashboard, number card, analytics]
    category: frappe
---

# Frappe Dashboard Management

## When to Use
Creating a new Dashboard, adding Number Cards or Dashboard Charts to it,
or linking a Dashboard to a Workspace.

## Key Knowledge

### Dashboard hierarchy
Dashboard
└── Dashboard Chart (one or more)
└── Number Card (one or more)
Charts and Number Cards are separate documents — create them first,
then link them to the Dashboard.

### Dashboard document
doctype: "Dashboard"
dashboard_name: display name
module: owning module
is_standard: 0
cards: array of {card} links
charts: array of {chart} links

### Number Card document
doctype: "Number Card"
name: unique name
label: display label
document_type: DocType to count/aggregate
function: "Count" | "Sum" | "Average" | "Minimum" | "Maximum"
aggregate_function_based_on: fieldname for Sum/Average/Min/Max
filters_json: JSON string of filters
color: hex color string e.g. "#4287f5"
is_public: 1

Example — count open Sales Orders:
```json
{
  "doctype": "Number Card",
  "label": "Open Orders",
  "document_type": "Sales Order",
  "function": "Count",
  "filters_json": "[{\"status\": \"To Deliver and Bill\"}]",
  "color": "#5e64ff",
  "is_public": 1
}
```

### Dashboard Chart document
doctype: "Dashboard Chart"
chart_name: display name
document_type: DocType to aggregate
chart_type: "Count" | "Sum" | "Average" | "Group By"
based_on: date field for time-series (e.g. "posting_date")
value_based_on: numeric field for Sum/Average
timespan: "Last Year" | "Last Quarter" | "Last Month" | "Last Week"
time_interval: "Yearly" | "Quarterly" | "Monthly" | "Weekly" | "Daily"
filters_json: JSON string
is_public: 1

## Procedure

1. Create Number Cards first — one `frappe_save_doc` per card.
2. Create Dashboard Charts — one `frappe_save_doc` per chart.
3. Create the Dashboard document, linking cards and charts by name.
4. Optionally link the Dashboard to a Workspace shortcut.
5. Confirm by fetching the Dashboard back and checking linked cards and charts.

## Pitfalls
- `filters_json` must be valid JSON string — double-encode if needed.
- `based_on` must be a Date or Datetime field on the target DocType.
- `is_public: 0` means only the creator can see it — always set `1` for shared dashboards.
- Dashboard Chart `chart_type: "Group By"` requires `group_by_based_on` field set.
- Number Card `function: "Sum"` without `aggregate_function_based_on` set will error silently.
- **Dashboard `charts` field is `reqd: 1`** — you MUST create at least one Dashboard Chart and link it in the `charts` array before saving the Dashboard. An empty `charts: []` will fail validation. Always create a chart first, even a simple one.
- **Dashboard Chart `type` is case-sensitive** — valid values are `"Line"`, `"Bar"`, `"Percentage"`, `"Pie"`, `"Donut"`, `"Heatmap"`. Lowercase `"pie"` will fail with a validation error.