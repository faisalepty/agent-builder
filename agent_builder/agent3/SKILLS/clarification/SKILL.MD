---
name: clarification
description: >
  Enable human-in-the-loop verification by asking targeted follow-up
  questions when requirements are unclear, incomplete, or ambiguous.
---

## Purpose

Pause generation and request clarifying input when:
- requirements are incomplete
- ambiguous fields exist
- business intent is uncertain
- output needs validation before finalization

## Behavior

- Identify missing assumptions and uncertainty in user requests.
- Ask concise, specific questions rather than broad or vague prompts.
- Confirm the target format, required fields, and expected semantics.
- Avoid making decisions when key details are unknown.
- Defer to the user for final decisions on ambiguous or conflicting requirements.

## When to use

Use this skill when:
- a doctype request lacks clear field definitions
- validation rules are not specified
- sample outputs or target systems are unclear
- multiple interpretations are possible

## Output format

Return a short clarification request that includes:
- what is missing
- why it matters
- one or two specific questions

Example:
- “I need the expected data type and required status for the `customer_id` field.”
- “Should this doctype support nested address objects, or do you want a flat address schema?”