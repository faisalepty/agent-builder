# Page Doctype — Required Fields & Pattern

## Required Fields
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `page_name` | Data | Yes | Unique identifier, also the route |
| `standard` | Select | Yes | `"Yes"` or `"No"` |
| `module` | Link (Module Def) | Yes | Must match existing Module Def |
| `title` | Data | No | Display title |

## Minimal Create
```json
{
  "doctype": "Page",
  "page_name": "my-custom-page",
  "standard": "No",
  "module": "Stock",
  "title": "My Custom Page"
}
```

## Common Errors
- **`'NoneType' object has no attribute 'lower'`** → missing `standard` field
- **`expected string or bytes-like object, got 'NoneType'`** → missing `page_name` field

## When to Use Page vs Custom DocType
- **Page**: static content, simple HTML display, no data entry
- **Custom DocType + child table**: interactive forms, data entry, workflow, submissions
