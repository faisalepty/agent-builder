---
name: frappe-workspace
description: Create and configure Frappe Workspaces — the role-based home pages in Frappe Desk. Load before creating or modifying any Workspace.
version: 1.0.0
author: agent_builder
metadata:
  hermes:
    tags: [frappe, workspace, desk, navigation]
    category: frappe
---

# Frappe Workspace Management

## When to Use
Creating a new Workspace, adding shortcuts, number cards, charts, or quick lists
to an existing Workspace, or configuring role-based visibility.

## Key Knowledge

### What a Workspace is
A Workspace is a Frappe Desk home page. It appears in the left sidebar.
Each Workspace belongs to a module and can be restricted to specific roles.
Users see only Workspaces their roles allow.

### Workspace DocType structure
doctype: "Workspace"
name: unique slug (auto or set)
label: display name shown in sidebar
module: module it belongs to
is_standard: 0 for custom, 1 for standard (avoid setting 1)
public: 1 makes it visible to all users with module access
roles: array of role objects controlling visibility
content: JSON string — the page layout (blocks)
shortcuts: array of shortcut objects
cards: array of card link objects

### Roles array
```json
[{"role": "Sales Manager"}, {"role": "Sales User"}]
```
Empty roles array = visible to everyone with module access.

### Visibility rules
Workspace visibility depends on TWO things:
1. User has the roles listed in the Workspace `roles` array
2. User has access to the module (Module access in User settings)
Both must be true. If a user cannot see a Workspace, check module access first.

### Shortcuts array
Each shortcut links to a DocType, Page, Report, or URL:
```json
{
  "label": "Sales Invoice",
  "type": "DocType",
  "link_to": "Sales Invoice",
  "color": "#4287f5",
  "icon": "invoice"
}
```
Types: `DocType`, `Page`, `Report`, `URL`

### Cards (Link groups)
Cards are grouped navigation links shown as tiles:
```json
{
  "label": "Transactions",
  "links": [
    {"label": "Sales Invoice", "type": "DocType", "link_to": "Sales Invoice"},
    {"label": "Payment Entry", "type": "DocType", "link_to": "Payment Entry"}
  ]
}
```

## Procedure

1. Fetch the target module name — confirm it matches an installed Module Def.
2. Build the Workspace document with `label`, `module`, `public`, `roles`.
3. Add `shortcuts` for the most important daily actions.
4. Save using `frappe_save_doc`.
5. Confirm by fetching back and checking `name` and `shortcuts` count.

## Pitfalls
- `is_standard: 1` workspaces are overwritten on bench migrate — never set this on custom ones.
- `module` must exactly match an existing Module Def name — case sensitive.
- If roles array is set but user still cannot see it, check their Module access under User settings.
- `content` JSON must be valid — an invalid content string breaks the Workspace page silently.
- Two Workspaces with the same `label` in the same module will cause confusion — names must be unique.