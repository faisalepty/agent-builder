---
name: doctype_creation
description: >
  Create structured document type definitions and metadata from user requirements.
  Produce implementation-ready schema definitions, field details, and validation guidance.
---

## Purpose

Define new doctypes by translating user needs into:
- schema name and description
- field definitions
- field types and validation rules
- sample instances
- metadata for implementation

## When to use

Use this skill when a request asks to:
- create a new document type
- design schema fields and constraints
- define document metadata for ingestion or storage
- validate the structure of a new document type

## Behavior

- Ask clarifying questions if requirements are incomplete.
- Avoid inventing unspecified fields or behaviors.
- Keep output precise, consistent, and implementation-ready.
- Prefer explicit evidence from the user's request.
- Provide examples and validation notes when useful.

## Output format

Return a clear, structured doctype definition:
- `doctype_name`
- `description`
- `fields` list with:
  - `name`
  - `type`
  - `description`
  - `required`
  - `example`
  - `constraints`
- sample JSON instance
- validation guidance
