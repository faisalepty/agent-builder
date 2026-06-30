# omnis_hermes/tools/internal/skill_list.py
import os
import re
from pathlib import Path
from agent_builder.native_api.tools.decorator import tool


@tool(
    name="skill_list",
    description=(
        "List all available skills with their names and one-line descriptions. "
        "Call this to discover which skills are available before deciding to use one."
    ),
)
def skill_list() -> str:
    """Scans SKILLS_DIR and returns a name+description manifest."""
    skills_dir = Path("/home/faisa/Desktop/mft/manufacturing/apps/agent_builder/agent_builder/native_api/skills")
    if not skills_dir.exists():
        return f"Skills directory not found: {skills_dir}"

    results = []
    for skill_md in sorted(skills_dir.rglob("skill.md")):
        with open(skill_md, "r", encoding="utf-8") as f:
            content = f.read()

        metadata = _parse_frontmatter(content)
        skill_dir = skill_md.parent
        name = metadata.get("name") or skill_dir.name
        description = metadata.get("description", "No description provided.")
        results.append(f"- {name}: {description}")

    return "\n".join(results) if results else "No skills currently available."


def _parse_frontmatter(content: str) -> dict:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", content, re.DOTALL)
    if not match:
        return {}
    metadata = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            metadata[k.strip()] = v.strip().strip("'\"")
    return metadata