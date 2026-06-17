---
name: frappe-skills-setup
description: Troubleshooting guide for Hermes skill discovery and registration in Frappe apps. Load when skills_list returns empty or skill_view can't find a skill.
version: 1.0.0
author: agent_builder
metadata:
  hermes:
    tags: [frappe, hermes, skills, setup, troubleshooting]
    category: frappe-operations
---

# Frappe Skills Setup & Troubleshooting

## When to Use
- `skills_list()` returns empty despite skill files existing
- `skill_view(name)` returns "Skill not found"
- Skills work in one session but disappear after restart
- Debugging why a skill isn't being recognized

## How Skill Discovery Works

Skills are stored under `<app>/.hermes/skills/<directory>/skill.md`. Each skill needs:
1. A directory under `.hermes/skills/`
2. A file named exactly `skill.md` (**lowercase** — `SKILL.MD` will NOT be recognized)
3. Valid YAML frontmatter with at least a `name` field
4. The `plugin.yaml` in the providing plugin must list the skill's frontmatter `name` (not directory name) under `provides_skills`

## Skill File Format

```yaml
---
name: my-skill
description: What this skill does
metadata:
  hermes:
    tags: [frappe, relevant, tags]
    category: frappe
---
```

**Critical:** The `name` in frontmatter is the canonical identifier. Directory names are irrelevant to the scanner.

## plugin.yaml Registration

The plugin that provides the skills must declare them in `provides_skills`:

```yaml
provides_skills:
  - my-skill        # must match frontmatter `name`, NOT directory name
  - another-skill
```

Mismatches between `plugin.yaml` and frontmatter `name` cause the skill to not appear.

## Complete Skill Library

| Skill | Frontmatter Name | Directory | Purpose |
|---|---|---|---|
| Frappe Tools | `frappe-tools` | `frappe-doctype/` | CRUD tool reference |
| Frappe Chart | `frappe-chart` | `frappe-chart/` | Dashboard Chart creation |
| Frappe Dashboard | `frappe-dashboard` | `frappe-dashboard/` | Dashboard & Number Cards |
| Frappe Workspace | `frappe-workspace` | `frappe-workspace/` | Workspace management |
| Frappe UI | `frappe-ui` | `frontend-skill/` | HTML UI generation |
| Skills Setup | `frappe-skills-setup` | `frappe-skills-setup/` | This skill |

**Note:** Directory names and frontmatter names differ for `frappe-doctype/` (contains `frappe-tools`) and `frontend-skill/` (contains `frappe-ui`). plugin.yaml must use frontmatter names.

## Diagnostics Checklist

When `skills_list()` returns empty:

1. **Check file naming**: `find .hermes/skills -name "skill.md"` — ensure files are lowercase
2. **Check frontmatter name matches plugin.yaml**: Compare `grep "^name:" .hermes/skills/*/skill.md` vs `grep provides_skills -A20 .hermes/plugins/*/plugin.yaml`
3. **Check plugin.yaml names**: `provides_skills` entries must match frontmatter `name` field exactly
4. **Check snapshot cache**: `.skills_prompt_snapshot.json` may be stale — delete or reset it
5. **Restart the agent**: Skills are registered at agent startup; changes require a bench/agent restart
6. **Remove stale snapshot**: If `.skills_prompt_snapshot.json` has stale entries, reset it to `{"version":1,"manifest":{},"skills":[],"category_descriptions":{}}`

## Common Pitfalls

- **Uppercase filenames**: `SKILL.MD` or `Skill.md` won't work — must be `skill.md`
- **Name mismatch**: Directory `frontend-skill/` contains skill with `name: frappe-ui` — plugin.yaml must list `frappe-ui`, not `frontend-skill`
- **Duplicate names**: Two directories with skills sharing the same frontmatter `name` — only one loads
- **Invalid YAML frontmatter**: Missing `name` field or malformed YAML prevents registration
- **Snapshot cache**: `.skills_prompt_snapshot.json` is a startup cache; editing it manually is not sufficient to register new skills — must restart

## Verification

After fixing and restarting:
1. Call `skills_list()` — should return all registered skills
2. Call `skill_view(name=<skill-name>)` — should return the SKILL.md content
3. If still empty, check logs at `.hermes/logs/agent.log` for skill registration errors

## See Also

- `references/skills-discovery-troubleshooting.md` — detailed troubleshooting log with root cause analysis
