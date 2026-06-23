---
name: frappe-native-ui
description: Generate native ERPNext/Frappe Desk UI fragments that render directly inside Hermes chat while preserving the visual hierarchy, spacing, and interaction patterns of Frappe Desk, Workspace, Reports, Quick Entry, and Form views.
version: 3.0.0
author: agent_builder
metadata:
  hermes:
    tags: [frappe, erpnext, ui, html, frontend, desk, workspace]
    category: frappe
---

# Frappe Native UI v3

## Purpose

Generate UI that looks and feels like native ERPNext/Frappe Desk.

Do not invent a design language.

Prefer:

* Workspace Cards
* Form Views
* Section Breaks
* Quick Entry Forms
* Report Tables
* Dashboard Metrics
* Sidebar Panels
* Approval Dialogs

The generated UI should resemble ERPNext rather than a generic SaaS dashboard.

---

# Output Rules

Return raw HTML inside:

```html
...
```

The Hermes renderer will render the fragment directly.

---

# Critical Rules

## Always Use Fallbacks

Every token must include a fallback.

Good:

```css
background: var(--surface-base, #ffffff);
```

Bad:

```css
background: var(--surface-base);
```

This prevents broken styling when chat history is restored before frappe-ui variables are available.

---

## Never Hardcode Design Colors

Allowed:

```css
var(--surface-*)
var(--ink-*)
var(--outline-*)
```

Not Allowed:

```css
#ffffff
#000000
#0d8ef8
rgb(...)
hsl(...)
```

except as fallbacks.

---

## Typography

Always use:

```css
font-family:
InterVar,
system-ui,
sans-serif;
```

Base text:

```css
font-size:14px;
```

---

# Approved Design Tokens

## Surface

```css
--surface-base
--surface-gray-1
--surface-gray-2
--surface-gray-3

--surface-blue-2
--surface-green-2
--surface-red-2
--surface-amber-2

--surface-elevation-1
--surface-elevation-2
```

---

## Ink

```css
--ink-gray-5
--ink-gray-7
--ink-gray-8
--ink-gray-9

--ink-blue-8
--ink-green-8
--ink-red-7
--ink-amber-8
```

---

## Outline

```css
--outline-gray-1
--outline-gray-2
--outline-gray-3

--outline-blue-5
--outline-green-3
--outline-red-3
--outline-amber-3
```

---

## Radius

```css
--radius-4
--radius-6
--radius-9
```

---

## Elevation

```css
--elevation-sm
--elevation-md
```

---

# Native Layout Hierarchy

Every generated page should follow:

```text
Page Title

Actions

Filters

Metrics

Section Break

Content

Footer Actions
```

This mirrors ERPNext Desk.

---

# Workspace Metric Card

```html
<div style="
background:var(--surface-base,#fff);
border:1px solid var(--outline-gray-2,#e2e2e2);
border-radius:var(--radius-6,12px);
padding:16px;
">

<div style="
font-size:24px;
font-weight:700;
color:var(--ink-gray-9,#0f0f0f);
">
142
</div>

<div style="
margin-top:4px;
font-size:12px;
font-weight:500;
color:var(--ink-gray-5,#7c7c7c);
">
Total Customers
</div>

</div>
```

---

# Native Section Break

ERPNext uses Section Breaks extensively.

```html
<div style="
margin:20px 0 12px;
padding-bottom:8px;
border-bottom:1px solid var(--outline-gray-1,#ededed);
">

<div style="
font-size:15px;
font-weight:600;
color:var(--ink-gray-9,#0f0f0f);
">
Customer Details
</div>

</div>
```

---

# Native Field Pattern

```html
<div style="
display:flex;
flex-direction:column;
gap:4px;
">

<label style="
font-size:12px;
font-weight:500;
color:var(--ink-gray-5,#7c7c7c);
">
Customer Name
</label>

<input
id="customer_name"
type="text"
style="
height:28px;
padding:0 8px;
border:1px solid var(--outline-gray-2,#e2e2e2);
border-radius:var(--radius-4,8px);
background:var(--surface-base,#fff);
color:var(--ink-gray-8,#171717);
font-size:13px;
font-family:inherit;
"
/>

</div>
```

---

# Native Form Section

```html
<div style="
background:var(--surface-base,#fff);
border:1px solid var(--outline-gray-2,#e2e2e2);
border-radius:var(--radius-6,12px);
padding:16px;
">

<!-- section break -->

<!-- fields -->

</div>
```

Avoid shadows unless representing dialogs.

---

# Native Report Table

```html
<div style="
overflow-x:auto;
border:1px solid var(--outline-gray-2,#e2e2e2);
border-radius:var(--radius-6,12px);
">

<table style="
width:100%;
border-collapse:collapse;
font-size:13px;
font-family:inherit;
">

<thead>
<tr style="
background:var(--surface-gray-1,#f8f8f8);
border-bottom:1px solid var(--outline-gray-2,#e2e2e2);
">
...
</tr>
</thead>

<tbody>
<tr style="
border-bottom:1px solid var(--outline-gray-1,#ededed);
">
...
</tr>
</tbody>

</table>

</div>
```

---

# Native Status Indicators

Prefer subtle ERPNext style indicators.

Success:

```html
<span style="
font-size:12px;
font-weight:500;
color:var(--ink-green-8,#166534);
">
● Active
</span>
```

Error:

```html
<span style="
font-size:12px;
font-weight:500;
color:var(--ink-red-7,#dc2626);
">
● Failed
</span>
```

Warning:

```html
<span style="
font-size:12px;
font-weight:500;
color:var(--ink-amber-8,#b45309);
">
● Pending
</span>
```

Do not overuse badges.

---

# Native Action Buttons

Primary:

```html
<button
data-action="primary"
style="
height:28px;
padding:0 12px;
border:none;
border-radius:var(--radius-4,8px);
background:var(--surface-blue-6,#0d8ef8);
color:var(--surface-base,#fff);
font-size:13px;
font-weight:500;
font-family:inherit;
cursor:pointer;
">
Save
</button>
```

Secondary:

```html
<button
data-action="secondary"
style="
height:28px;
padding:0 12px;
border:1px solid var(--outline-gray-2,#e2e2e2);
border-radius:var(--radius-4,8px);
background:var(--surface-base,#fff);
color:var(--ink-gray-8,#171717);
font-size:13px;
font-weight:500;
font-family:inherit;
cursor:pointer;
">
Cancel
</button>
```

---

# Form Submission Standard

All forms must:

1. Assign IDs to inputs.
2. Collect values into a payload.
3. Send payload via Hermes.

```javascript
function submitForm() {
  const payload = {
    customer_name:
      document.getElementById("customer_name").value
  };

  window.parent.postMessage({
    type: "hermes_submit",
    data: payload
  }, "*");

  if (typeof sendPrompt === "function") {
    sendPrompt(JSON.stringify(payload, null, 2));
  }
}
```

---

# Dark Mode

Never create separate dark mode styles.

Always rely on:

```css
--surface-*
--ink-*
--outline-*
```

Frappe automatically swaps values when theme changes.

---

# Forbidden Patterns

Never generate:

* Tailwind classes
* Bootstrap classes
* External CSS
* External JS
* CDN imports
* Glassmorphism
* Gradients
* Neon effects
* Animated backgrounds
* Custom design systems
* Material UI styling
* Shadcn styling
* Generic SaaS dashboard styling

---

# Preferred Layout Types

When generating UI choose one of:

1. Workspace
2. Form View
3. Quick Entry
4. Report View
5. Dashboard
6. Sidebar Panel
7. Approval Dialog
8. Wizard

Prefer the closest ERPNext layout instead of inventing a new one.
