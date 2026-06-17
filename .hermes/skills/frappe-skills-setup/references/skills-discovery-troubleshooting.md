# Skills Discovery — Troubleshooting Log

## Symptoms
- `skills_list()` returns empty despite valid skill files existing
- `skill_view(name)` returns "Skill not found"
- Skills disappear after agent restart

## Root Causes Found

### 1. Filename Case Sensitivity
- `SKILL.MD` (uppercase) → **NOT recognized**
- `skill.md` (lowercase) → **Correct**
- The skills scanner is case-sensitive on the filename

### 2. plugin.yaml Name Mismatch
The `provides_skills` list must use the frontmatter `name` field, NOT the directory name:

```yaml
# WRONG — uses directory names
provides_skills:
  - frontend-skill    # directory name
  - frappe-doctype    # directory name

# CORRECT — uses frontmatter name
provides_skills:
  - frappe-ui         # name from frontend-skill/skill.md frontmatter
  - frappe-tools      # name from frappe-doctype/skill.md frontmatter
```

### 3. Snapshot Cache
`.skills_prompt_snapshot.json` is a startup cache. Editing it manually does NOT register new skills — must restart the agent.

### 4. Registration Happens at Startup
Skills are registered when the agent initializes. File changes after startup won't be picked up until restart.

## Verification Steps

1. Check filename case: `find .hermes/skills -name "*.md" | grep -i skill`
2. Compare frontmatter names to plugin.yaml: `grep "^name:" .hermes/skills/*/skill.md`
3. Restart agent after any changes
4. Call `skills_list()` to verify

## Files Involved
- `<app>/.hermes/skills/<dir>/skill.md` — skill definition
- `<app>/.hermes/plugins/<plugin>/plugin.yaml` — skill registration
- `<app>/.hermes/.skills_prompt_snapshot.json` — startup cache (auto-generated)
