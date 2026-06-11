---
name: frappe-ui
description: Generate production-grade HTML UI fragments for Frappe Desk agents that render directly inside chat responses.
version: 1.0.0
author: Agent Builder
license: MIT
metadata:
  hermes:
    tags:
      - Frappe
      - ERPNext
      - UI
      - Dashboard
      - Forms
      - Tables
      - Chat Rendering
    related_skills: []
---

# Frappe UI

Generate clean, production-grade HTML interfaces that render directly inside a Frappe Desk chat widget.

The generated output is intended for inline rendering inside agent conversations, not standalone web pages.

## When to Use

Load this skill when the user requests:

- Dashboards
- Reports
- Data tables
- Forms
- KPI cards
- CRM views
- ERP workflows
- Admin panels
- List views
- Business application interfaces

## Quick Reference

### Allowed

- Bootstrap 5 classes
- Tailwind utility classes
- Semantic HTML
- Responsive layouts
- Cards
- Tables
- Forms
- Alerts
- Badges

### Forbidden

- `<style>`
- Inline styles
- Custom CSS

## Procedure

1. Understand the workflow being presented.
2. Identify the primary actions and information.
3. Organize content using cards, tables, forms, and badges.
4. Keep layouts compact and business-focused.
5. Generate valid HTML only.
6. Ensure the result can render inside a bounded chat container.
7. Prefer Bootstrap components unless otherwise requested.

## Pitfalls

Avoid:

- Marketing-style landing pages
- Hero sections
- Full-screen layouts
- Fixed positioning
- Modals
- Excessive whitespace
- Decorative elements that reduce usability
- Assumptions about page-level navigation

The UI must feel native to Frappe Desk.

## Verification

Before returning HTML, verify:

- HTML is valid
- No inline styles exist
- Only Bootstrap or Tailwind classes are used
- Layout works inside a chat message container
- Primary actions are obvious
- Information hierarchy is clear
