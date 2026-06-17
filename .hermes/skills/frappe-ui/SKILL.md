---
name: frappe-ui
description: Generate production-grade HTML UI fragments for Frappe Desk agents that render directly inside chat responses using native frappe-ui design tokens.
version: 2.0.0
author: agent_builder
metadata:
  hermes:
    tags: [frappe, ui, html, frontend, chat]
    category: frappe
---

# Frappe UI — Chat-Embedded HTML Fragments (Native Tokens)

## When to Use
The user asks for a form, table, dashboard, or interactive UI rendered directly in the chat
response. Produce a self-contained HTML fragment that renders inline in the Hermes chat widget
using **the same CSS variables that frappe-ui/Desk already injects into the page**. No
hardcoded hex values. No CDN imports.

## Output Format
Output raw HTML inside a fenced code block labeled `html`. The chat client will auto-render it.

---

## Design Token Reference

Frappe Desk's `frappe-ui` stylesheet defines these CSS variables on `:root`.
**Always use these — never hardcode colors.**

### Surface (backgrounds)
```
--surface-base          /* pure white card background */
--surface-gray-1        /* #f8f8f8 — page / app background */
--surface-gray-2        /* #f3f3f3 — subtle input fill, row hover */
--surface-gray-3        /* #ededed — active input fill */
--surface-gray-4        /* #e2e2e2 — dividers, disabled bg */

--surface-blue-2        /* pale blue bg (info badges, highlights) */
--surface-blue-6        /* #0d8ef8 — primary action bg */
--surface-green-2       /* pale green bg (success) */
--surface-green-7       /* saturated green bg */
--surface-red-2         /* pale red bg (error) */
--surface-red-7         /* saturated red bg */
--surface-amber-2       /* pale amber bg (warning) */
--surface-amber-7       /* saturated amber bg */
--surface-violet-2      /* pale violet bg */

--surface-elevation-1   /* elevated card bg (e.g. dropdown, modal) */
--surface-elevation-2
--surface-elevation-3
```

### Ink (text / icon colors)
```
--ink-gray-4            /* #999 — placeholder / disabled text */
--ink-gray-5            /* #7c7c7c — muted / secondary text */
--ink-gray-6            /* #525252 — body text (muted) */
--ink-gray-7            /* #383838 — body text */
--ink-gray-8            /* #171717 — primary text */
--ink-gray-9            /* #0f0f0f — high-contrast headings */

--ink-blue-6            /* #0d8ef8 — link / primary action text */
--ink-blue-8            /* darker blue text */
--ink-green-8           /* success text */
--ink-red-7             /* error text */
--ink-amber-8           /* warning text */
```

### Outline (borders)
```
--outline-gray-1        /* #ededed — very subtle border */
--outline-gray-2        /* #e2e2e2 — default border (cards, inputs) */
--outline-gray-3        /* #c7c7c7 — hover border */
--outline-gray-4        /* #999 — active / focus border */

--outline-blue-3        /* pale blue border */
--outline-blue-5        /* #0d8ef8 — primary border */
--outline-green-3       /* success border */
--outline-red-3         /* error border */
--outline-amber-3       /* warning border */

--outline-elevation-1   /* elevation-aware border for cards */
--outline-elevation-2
```

### Border Radius
```
--radius-1: 4px    --radius-2: 5px    --radius-3: 6px    --radius-4: 8px (DEFAULT)
--radius-5: 10px   --radius-6: 12px   --radius-7: 16px   --radius-9: 999px (pill)
```

### Elevation (box-shadow)
```
--elevation-sm      /* subtle card shadow */
--elevation-base    /* standard card shadow */
--elevation-md      /* popover / dropdown shadow */
--elevation-lg      /* modal shadow */
```

### Typography
Font: `InterVar, system-ui, sans-serif` (Desk loads Inter)
| Token      | Size | Use |
|------------|------|-----|
| `tiny`/`2xs` | 11px | labels, badges |
| `xs`       | 12px | secondary meta |
| `sm`       | 13px | table cells, captions |
| `base`     | 14px | body text (default) |
| `lg`       | 15px | sub-headings |
| `xl`       | 16px | card headings |
| `2xl`+     | 17px+ | page titles |

Font weight: `420` regular · `500` medium · `600` semibold · `700` bold

---

## Component Patterns

### Card Shell
```html
<div style="
  background: var(--surface-base);
  border: 1px solid var(--outline-gray-2);
  border-radius: var(--radius-4);
  box-shadow: var(--elevation-sm);
  padding: 16px;
  font-family: InterVar, system-ui, sans-serif;
">
  <!-- content -->
</div>
```

### Page / Section Wrapper
```html
<div style="
  background: var(--surface-gray-1);
  padding: 20px;
  font-family: InterVar, system-ui, sans-serif;
  color: var(--ink-gray-8);
  font-size: 14px;
">
```

### Button — Solid (Primary)
```html
<button style="
  background: var(--surface-gray-9);
  color: var(--surface-base);
  border: none;
  border-radius: var(--radius-4);
  padding: 0 12px;
  height: 28px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
" onmouseover="this.style.opacity='0.85'" onmouseout="this.style.opacity='1'">
  Save
</button>
```

### Button — Subtle (Secondary)
```html
<button style="
  background: var(--surface-gray-2);
  color: var(--ink-gray-8);
  border: none;
  border-radius: var(--radius-4);
  padding: 0 12px;
  height: 28px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
" onmouseover="this.style.background='var(--surface-gray-3)'" onmouseout="this.style.background='var(--surface-gray-2)'">
  Cancel
</button>
```

### Button — Outline
```html
<button style="
  background: var(--surface-base);
  color: var(--ink-gray-8);
  border: 1px solid var(--outline-gray-2);
  border-radius: var(--radius-4);
  padding: 0 12px;
  height: 28px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
">
  Export
</button>
```

### Button — Danger
```html
<button style="
  background: var(--surface-red-7);
  color: var(--surface-base);
  border: none;
  border-radius: var(--radius-4);
  padding: 0 12px;
  height: 28px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
">
  Delete
</button>
```

### Badge / Pill
```html
<!-- Subtle blue (info) -->
<span style="
  display: inline-flex; align-items: center; gap: 4px;
  background: var(--surface-blue-2);
  color: var(--ink-blue-8);
  border-radius: var(--radius-9);
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
">Active</span>

<!-- Subtle green (success) -->
<span style="background:var(--surface-green-2);color:var(--ink-green-8);border-radius:var(--radius-9);padding:2px 8px;font-size:12px;font-weight:500;">Paid</span>

<!-- Subtle red (error/danger) -->
<span style="background:var(--surface-red-2);color:var(--ink-red-7);border-radius:var(--radius-9);padding:2px 8px;font-size:12px;font-weight:500;">Overdue</span>

<!-- Subtle amber (warning) -->
<span style="background:var(--surface-amber-2);color:var(--ink-amber-8);border-radius:var(--radius-9);padding:2px 8px;font-size:12px;font-weight:500;">Pending</span>

<!-- Subtle gray (neutral) -->
<span style="background:var(--surface-gray-2);color:var(--ink-gray-6);border-radius:var(--radius-9);padding:2px 8px;font-size:12px;font-weight:500;">Draft</span>
```

### Form Input
```html
<div style="display:flex;flex-direction:column;gap:4px">
  <label style="font-size:12px;font-weight:500;color:var(--ink-gray-7)">Field Label</label>
  <input
    type="text"
    placeholder="Enter value…"
    style="
      height: 28px;
      padding: 0 8px;
      border: 1px solid var(--outline-gray-2);
      border-radius: var(--radius-4);
      background: var(--surface-gray-2);
      color: var(--ink-gray-8);
      font-size: 13px;
      font-family: inherit;
      outline: none;
      transition: border-color 0.15s, background 0.15s;
    "
    onfocus="this.style.borderColor='var(--outline-gray-4)';this.style.background='var(--surface-base)'"
    onblur="this.style.borderColor='var(--outline-gray-2)';this.style.background='var(--surface-gray-2)'"
  />
</div>
```

### Select / Dropdown
```html
<select style="
  height: 28px;
  padding: 0 28px 0 8px;
  border: 1px solid var(--outline-gray-2);
  border-radius: var(--radius-4);
  background: var(--surface-gray-2);
  color: var(--ink-gray-8);
  font-size: 13px;
  font-family: inherit;
  appearance: none;
  background-image: url('data:image/svg+xml,<svg xmlns=\"http://www.w3.org/2000/svg\" fill=\"none\" stroke=\"%237C7C7C\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" viewBox=\"0 0 24 24\"><path d=\"m6 9 6 6 6-6\"/></svg>');
  background-repeat: no-repeat;
  background-size: 1.1em;
  background-position: right 6px center;
  cursor: pointer;
">
  <option>Option A</option>
  <option>Option B</option>
</select>
```

### Data Table
```html
<div style="
  background: var(--surface-base);
  border: 1px solid var(--outline-gray-2);
  border-radius: var(--radius-4);
  box-shadow: var(--elevation-sm);
  overflow: hidden;
">
  <table style="width:100%;border-collapse:collapse;font-size:13px;font-family:InterVar,system-ui,sans-serif">
    <thead>
      <tr style="background:var(--surface-gray-1);border-bottom:1px solid var(--outline-gray-2)">
        <th style="padding:8px 12px;text-align:left;color:var(--ink-gray-5);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Name</th>
        <th style="padding:8px 12px;text-align:left;color:var(--ink-gray-5);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Status</th>
        <th style="padding:8px 12px;text-align:right;color:var(--ink-gray-5);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Amount</th>
      </tr>
    </thead>
    <tbody>
      <tr style="border-bottom:1px solid var(--outline-gray-1)" onmouseover="this.style.background='var(--surface-gray-1)'" onmouseout="this.style.background='transparent'">
        <td style="padding:10px 12px;color:var(--ink-gray-8);font-weight:500">INV-0001</td>
        <td style="padding:10px 12px">
          <span style="background:var(--surface-green-2);color:var(--ink-green-8);border-radius:var(--radius-9);padding:2px 8px;font-size:12px;font-weight:500;">Paid</span>
        </td>
        <td style="padding:10px 12px;text-align:right;color:var(--ink-gray-8);font-weight:600">₹12,500</td>
      </tr>
    </tbody>
  </table>
</div>
```

### Summary Stat Cards Row
```html
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px">
  <div style="background:var(--surface-base);border:1px solid var(--outline-gray-2);border-radius:var(--radius-4);box-shadow:var(--elevation-sm);padding:16px">
    <div style="font-size:22px;font-weight:700;color:var(--ink-gray-9)">142</div>
    <div style="font-size:12px;color:var(--ink-gray-5);margin-top:4px;font-weight:500">Total Loans</div>
  </div>
  <div style="background:var(--surface-base);border:1px solid var(--outline-gray-2);border-radius:var(--radius-4);box-shadow:var(--elevation-sm);padding:16px">
    <div style="font-size:22px;font-weight:700;color:var(--ink-green-8)">₹4.2M</div>
    <div style="font-size:12px;color:var(--ink-gray-5);margin-top:4px;font-weight:500">Disbursed</div>
  </div>
  <div style="background:var(--surface-base);border:1px solid var(--outline-gray-2);border-radius:var(--radius-4);box-shadow:var(--elevation-sm);padding:16px">
    <div style="font-size:22px;font-weight:700;color:var(--ink-red-7)">8</div>
    <div style="font-size:12px;color:var(--ink-gray-5);margin-top:4px;font-weight:500">NPA</div>
  </div>
</div>
```

### Section Header (inside a card)
```html
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
  <h3 style="margin:0;font-size:15px;font-weight:600;color:var(--ink-gray-9)">Section Title</h3>
  <span style="font-size:12px;color:var(--ink-gray-5)">Subtitle or count</span>
</div>
<div style="height:1px;background:var(--outline-gray-1);margin-bottom:16px"></div>
```

### Alert / Notice Banner
```html
<!-- Info -->
<div style="display:flex;gap:10px;align-items:flex-start;padding:12px 14px;background:var(--surface-blue-2);border:1px solid var(--outline-blue-3);border-radius:var(--radius-4);font-size:13px;color:var(--ink-blue-8)">
  <span>ℹ️</span>
  <span>This loan is pending disbursement approval.</span>
</div>

<!-- Warning -->
<div style="display:flex;gap:10px;align-items:flex-start;padding:12px 14px;background:var(--surface-amber-2);border:1px solid var(--outline-amber-3);border-radius:var(--radius-4);font-size:13px;color:var(--ink-amber-8)">
  <span>⚠️</span>
  <span>Collateral shortfall detected. Review before disbursement.</span>
</div>

<!-- Error -->
<div style="display:flex;gap:10px;align-items:flex-start;padding:12px 14px;background:var(--surface-red-2);border:1px solid var(--outline-red-3);border-radius:var(--radius-4);font-size:13px;color:var(--ink-red-7)">
  <span>✕</span>
  <span>GL validation failed: account type mismatch.</span>
</div>
```

### Key-Value Detail Row (DocType form style)
```html
<div style="display:grid;grid-template-columns:1fr 1fr;gap:0;font-size:13px;font-family:InterVar,system-ui,sans-serif">
  <div style="padding:10px 12px;border-bottom:1px solid var(--outline-gray-1)">
    <div style="color:var(--ink-gray-5);font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:2px">Borrower</div>
    <div style="color:var(--ink-gray-8);font-weight:500">John Kamau</div>
  </div>
  <div style="padding:10px 12px;border-bottom:1px solid var(--outline-gray-1)">
    <div style="color:var(--ink-gray-5);font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:2px">Loan Amount</div>
    <div style="color:var(--ink-gray-8);font-weight:600">KES 500,000</div>
  </div>
</div>
```

### Tab Bar
```html
<div style="display:flex;gap:2px;border-bottom:1px solid var(--outline-gray-2);margin-bottom:16px">
  <button id="tab-active" style="padding:6px 14px;font-size:13px;font-weight:500;color:var(--ink-gray-8);background:none;border:none;border-bottom:2px solid var(--outline-blue-5);cursor:pointer;font-family:inherit;margin-bottom:-1px">Overview</button>
  <button style="padding:6px 14px;font-size:13px;color:var(--ink-gray-5);background:none;border:none;border-bottom:2px solid transparent;cursor:pointer;font-family:inherit;margin-bottom:-1px">Repayments</button>
  <button style="padding:6px 14px;font-size:13px;color:var(--ink-gray-5);background:none;border:none;border-bottom:2px solid transparent;cursor:pointer;font-family:inherit;margin-bottom:-1px">Documents</button>
</div>
```

---

## Form Submission Pattern
For forms that submit data back to Hermes:
1. Every input gets a unique `id`.
2. The submit handler reads all values into a structured payload.
3. Use `window.parent.postMessage({ type: 'hermes_submit', data: payload }, '*')` — Hermes listens for this message type.
4. Fallback: format values into a human-readable string and call `sendPrompt(text)` if that global is available.

```javascript
function submitForm() {
  const payload = {
    field1: document.getElementById('field1').value,
    field2: document.getElementById('field2').value,
  }
  // Primary: structured postMessage to Hermes
  window.parent.postMessage({ type: 'hermes_submit', data: payload }, '*')
  // Fallback: send as plain text prompt
  if (typeof sendPrompt === 'function') {
    sendPrompt(JSON.stringify(payload, null, 2))
  }
}
```

---

## Dark Mode
All `--surface-*`, `--ink-*`, `--outline-*` variables automatically flip when
Desk switches to `data-theme="dark"` — **no extra effort required** as long as
you use the CSS variables rather than hardcoded hex values.

---

## Pitfalls
- **Never hardcode hex colors** — always use `var(--surface-*)`, `var(--ink-*)`, `var(--outline-*)`.
- No external CDN links — the chat widget may block them.
- Keep HTML self-contained with inline styles only; no `<style>` blocks (they may be stripped).
- Use `max-width` and `overflow-x:auto` on tables to prevent horizontal overflow.
- All `<input>` / `<select>` elements must have `id` attributes for JS interop.
- Avoid `onclick` on submit buttons — use named functions instead.
- Do not use Tailwind class names — they won't resolve inside the rendered iframe.
- Font: reference `InterVar, system-ui, sans-serif` — Inter is already loaded by Desk.