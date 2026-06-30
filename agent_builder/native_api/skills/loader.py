# omnis_hermes/skills/loader.py
#
# SkillManager is a pure filesystem reader.
#
# It is NOT injected into the Agent. It exists only as a backend
# for the skill_list and skill_view tools which close over it in
# the caller's setup code (see verify.py).
#
# Skill directory convention:
#   skills/
#     my_skill/
#       skill.md       ← YAML frontmatter + body (full spec)
#       execute.py     ← optional; owns its own @tool-decorated functions
#                        which the caller registers on ToolRegistry separately
#
import re
from pathlib import Path
from typing import Dict, List, Union


class SkillManager:
    """
    Reads skill.md files from the filesystem and exposes two surfaces:

    list_skills()       — formatted string of name + one-line description.
                          Returned verbatim by the skill_list tool.

    get_skill_detail()  — full skill.md body for a named skill.
                          Returned verbatim by the skill_view tool so the
                          model gets the complete spec, parameter contract,
                          and usage examples before acting.
    """

    def __init__(self) -> None:
        self._manifest: List[Dict[str, str]] = []
        self._docs: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_skills_from_dir(self, directory_path: Union[str, Path]) -> None:
        """
        Recursively scans directory_path for skill.md files and registers
        each valid skill.
        """
        base_path = Path(directory_path)
        if not base_path.exists():
            return
        for config_file in sorted(base_path.rglob("skill.md")):
            self._load_single_skill(config_file)

    def _load_single_skill(self, config_file: Path) -> None:
        skill_dir = config_file.parent

        with open(config_file, "r", encoding="utf-8") as f:
            raw = f.read()

        # ---- Parse YAML frontmatter ----------------------------------------
        metadata: Dict[str, str] = {}
        body = raw.strip()

        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", raw, re.DOTALL)
        if match:
            for line in match.group(1).splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    metadata[k.strip()] = v.strip().strip("'\"")
            body = match.group(2).strip()

        # Prefer metadata name over directory name for consistency
        skill_name = metadata.get("name") or skill_dir.name
        description = metadata.get("description", "No description provided.")

        self._manifest.append({"name": skill_name, "description": description})
        self._docs[skill_name] = body

    # ------------------------------------------------------------------
    # Retrieval (called by skill_list / skill_view tool closures)
    # ------------------------------------------------------------------

    def list_skills(self) -> str:
        if not self._manifest:
            return "No skills are currently loaded."
        lines = [f"- {s['name']}: {s['description']}" for s in self._manifest]
        return "\n".join(lines)

    def get_skill_detail(self, skill_name: str) -> str:
        doc = self._docs.get(skill_name)
        if doc is None:
            available = ", ".join(self._docs) or "none"
            return (
                f"Skill '{skill_name}' not found. "
                f"Available skills: {available}"
            )
        return doc