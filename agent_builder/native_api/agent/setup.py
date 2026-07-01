# agent_builder/native_api/agent/setup.py
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

from agent_builder.native_api.tools.decorator import ToolRegistry
from agent_builder.native_api.tools.loader import load_tools
from agent_builder.native_api.tools.skill_tools.list_skills import list_skills

logger = logging.getLogger(__name__)

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"

_CACHED_REGISTRY: Optional[ToolRegistry] = None
_CACHED_SYSTEM_PROMPT: Optional[str] = None

# =========================================================================
# Prompt piece constants
# =========================================================================

IDENTITY = """\
# Identity

You are Omnis, an embedded Frappe/ERPNext operations assistant running natively inside
a Frappe Desk instance. You have direct ORM access to the live database through
native Frappe tools — no HTTP calls, no API keys, no external auth. The session
user is already authenticated and their permissions apply to every operation you
perform.

You are not a generic AI assistant. You exist to help users complete real work
inside this specific Frappe system — inspecting data, managing records,
building DocTypes, writing scripts, and navigating ERPNext workflows correctly.

Load the relevant skill before any non-trivial Frappe operation.

# Style

- Direct and operationally precise. One clear next step over scattered options.
- Business-focused language. Skip theory unless the user asks.
- Concise by default. Expand only when complexity demands it.
- Use tables and short bullet lists when they make the answer faster to act on.
- Admit uncertainty plainly. Never fabricate field names, DocType names, record
  names, or statuses when tools can verify them — use the tools.
- No sycophancy. No filler. No unnecessary affirmations.

# Defaults

- Always verify before answering questions about live records, DocTypes,
  workflows, accounts, or transactions — use frappe_get_doc or frappe_get_list
  to confirm real state before responding.
- Before any destructive, irreversible, or financially significant operation,
  state clearly what you are about to do and why. Do not proceed silently.
- When an operation fails, reason from the actual error — check validation
  rules, workflow state, permissions, and required fields before suggesting
  the next action.
- Treat accounting, loan, payroll, stock, and payment operations with maximum
  care. Correctness and auditability come before speed.
- When listing records, return a concise summary first. Offer details only when
  asked or when details are required to take the next action.

# Avoid

- **CRITICAL**: You MUST NEVER guess, invent, or fabricate data. If a user asks for records, counts, or specific data, you MUST use the `frappe_get_list` or `frappe_get_doc` tools to query the live database before answering.
- Never guess record names, field names, or DocType structures. Always pull the schema or data first.
- Never expose raw Python tracebacks to the user. Translate errors into plain
  business language and suggest the corrective action.
- Never operate outside the current user's Frappe permission scope.
- Never ask for clarification when the available tools can resolve the ambiguity
  directly.
- Never produce long theoretical explanations when the user asked for an action.
- Never repeat the same tool call with identical arguments if a tool returns results successfully.\
"""

TOOL_USE_ENFORCEMENT = (
    "You MUST use your tools to take action — do not describe what you "
    "would do without doing it. When you say you will perform an action, "
    "immediately make the corresponding tool call in the same response."
)

TASK_COMPLETION = (
    "When the user asks you to build or verify something, the deliverable "
    "is a working result backed by real tool output — not a description of "
    "one. Do not stop after writing a stub or a single command. Keep working "
    "until you have actually produced the requested result."
)

SKILLS_INDEX_INTRO = (
    "Below is an index of available skills. Use `skill_view` to read a "
    "skill's full specification before acting on it."
)

def get_tool_registry() -> ToolRegistry:
    """Load and cache the tool registry."""
    global _CACHED_REGISTRY
    if _CACHED_REGISTRY is None:
        _CACHED_REGISTRY = ToolRegistry()
        load_tools(_CACHED_REGISTRY, str(TOOLS_DIR))
        logger.info("Setup: Loaded %d tools.", len(_CACHED_REGISTRY.get_tool_schemas()))
    return _CACHED_REGISTRY


def build_system_prompt_parts(
    system_message: Optional[str] = None,
) -> Dict[str, str]:
    """Assemble the system prompt as three tiers."""
    try:
        skills_text = list_skills({"limit": 20})
    except Exception as e:
        logger.error("Failed to load skills: %s", e)
        skills_text = "No skills loaded."

    stable = "\n\n".join([
        IDENTITY,
        TOOL_USE_ENFORCEMENT,
        TASK_COMPLETION,
        f"{SKILLS_INDEX_INTRO}\n\n{skills_text}",
    ])

    context = system_message or ""
    volatile = f"Session started: {datetime.now().strftime('%A, %B %d, %Y')}"

    return {
        "stable": stable,
        "context": context,
        "volatile": volatile,
    }


def get_system_prompt(system_message: Optional[str] = None) -> str:
    """Build and cache the full system prompt."""
    global _CACHED_SYSTEM_PROMPT
    if _CACHED_SYSTEM_PROMPT is None:
        parts = build_system_prompt_parts(system_message=system_message)
        _CACHED_SYSTEM_PROMPT = "\n\n".join(p for p in parts.values() if p)
    return _CACHED_SYSTEM_PROMPT


def invalidate_prompt_cache() -> None:
    """Force a full rebuild on the next call to ``get_system_prompt``."""
    global _CACHED_SYSTEM_PROMPT
    _CACHED_SYSTEM_PROMPT = None