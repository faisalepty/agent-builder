# omnis_hermes/tools/internal/skill_view.py
import os
import re
from pathlib import Path
from agent_builder.native_api.tools.decorator import tool


@tool(
    name="skill_view",
    description=(
        "Read the full specification of a skill — its purpose, instructions, "
        "parameter contract, and usage examples. "
        "Call this before acting on a skill so you have the complete spec in context."
    ),
    param_descriptions={
        "skill_name": "Exact skill name as shown by skill_list.",
    },
)
def skill_view(skill_name: str) -> str:
    """Finds and returns the full skill.md body for the named skill."""
    skills_dir = Path(os.environ["SKILLS_DIR"])
    if not skills_dir.exists():
        return f"Skills directory not found: {skills_dir}"

    for skill_md in skills_dir.rglob("skill.md"):
        with open(skill_md, "r", encoding="utf-8") as f:
            content = f.read()

        metadata = _parse_frontmatter(content)
        name = metadata.get("name") or skill_md.parent.name

        if name == skill_name:
            return _extract_body(content)

    # Build available list for helpful error
    available = _list_skill_names(skills_dir)
    return (
        f"Skill '{skill_name}' not found. "
        f"Available skills: {', '.join(available) or 'none'}"
    )


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


def _extract_body(content: str) -> str:
    match = re.match(r"^---\s*\n.*?\n---\s*\n?(.*)", content, re.DOTALL)
    return match.group(1).strip() if match else content.strip()


def _list_skill_names(skills_dir: Path) -> list:
    names = []
    for skill_md in sorted(skills_dir.rglob("skill.md")):
        with open(skill_md, "r", encoding="utf-8") as f:
            content = f.read()
        metadata = _parse_frontmatter(content)
        names.append(metadata.get("name") or skill_md.parent.name)
    return names