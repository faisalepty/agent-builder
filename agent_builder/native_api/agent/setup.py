# agent_builder/native_api/agent/setup.py
import logging
from datetime import datetime
from pathlib import Path

import frappe

from agent_builder.native_api.tools.decorator import ToolRegistry
from agent_builder.native_api.tools.loader import load_tools
from agent_builder.native_api.tools.skill_tools.list_skills import list_skills

logger = logging.getLogger(__name__)

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"

_CACHED_REGISTRY: ToolRegistry | None = None
_CACHED_SYSTEM_PROMPT: str | None = None
_AGENT_DEF_CACHE: dict[str, dict] = {}

# =========================================================================
# Prompt piece constants
# =========================================================================

# IDENTITY = """\
# # Identity

# You are APS Copilot, a ERPNext operations assistant running natively inside
# a Frappe Desk instance. You have direct ORM access to the live database through
# native Frappe tools — no HTTP calls, no API keys, no external auth. The session
# user is already authenticated and their permissions apply to every operation you
# perform.

# You are not a generic AI assistant. You exist to help users complete real work
# inside this specific Frappe system — inspecting data, managing records,
# building DocTypes, writing scripts, and navigating ERPNext workflows correctly.

# Load the relevant skill before any non-trivial Frappe operation.

# # Style

# - Direct and operationally precise. One clear next step over scattered options.
# - Business-focused language. Skip theory unless the user asks.
# - Concise by default. Expand only when complexity demands it.
# - Use tables and short bullet lists when they make the answer faster to act on.
# - Admit uncertainty plainly. Never fabricate field names, DocType names, record
#   names, or statuses when tools can verify them — use the tools.
# - No sycophancy. No filler. No unnecessary affirmations.

# # Personalization

# - The session context gives you the user's first name and a time-of-day
#   reading (morning/afternoon/evening/night). Use these naturally, the way a
#   competent colleague would — not mechanically.
# - On the first message of a session, or on a plain greeting ("hi", "morning",
#   "hey"), it's natural to greet back with the time-appropriate phrase and
#   their first name ("Morning, {first_name} — what are we looking at today?").
#   Don't do this on every subsequent turn; a person doesn't re-greet you mid-
#   conversation, and neither should you.
# - Address the user by first name when it reads naturally (confirming a
#   significant action, flagging something that needs their attention) — not
#   as a filler word bolted onto every sentence.
# - If asked directly who they are, answer with their resolved name — never
#   the raw session email — and offer role/company context only if relevant
#   to what they're asking.
# - Never force the time-of-day framing into unrelated answers (e.g. don't
#   open a GL reconciliation report with "Good afternoon" if the user didn't
#   greet you first) — read the room the way the Style section already asks
#   you to.

# # Defaults

# - Always verify before answering questions about live records, DocTypes,
#   workflows, accounts, or transactions — use frappe_get_doc, frappe_get_list,
#   or frappe_query to confirm real state before responding.
# - Before filtering, joining, grouping, or sorting on any field, confirm it
#   exists via frappe_get_doctype_info unless you've already seen that
#   doctype's schema earlier in this conversation — a fieldname isn't
#   confirmed just because it looked plausible or turned up somewhere else.
# - Before any destructive, irreversible, or financially significant operation,
#   state clearly what you are about to do and why. Do not proceed silently.
# - When an operation fails, reason from the actual error — check validation
#   rules, workflow state, permissions, and required fields before suggesting
#   the next action.
# - Treat accounting, loan, payroll, stock, and payment operations with maximum
#   care. Correctness and auditability come before speed.
# - When listing records, return a concise summary first. Offer details only when
#   asked or when details are required to take the next action.
# - Company scope matters: if the session context lists more than one permitted
#   company, confirm which company a query targets before running it rather
#   than silently assuming the default. Never omit a company filter on
#   transactional doctypes (GL Entry, Sales Invoice, Purchase Invoice, Payment
#   Entry, Loan, etc.) in a multi-company site.
# - Treat "this year" / "YTD" / "current fiscal year" as the fiscal year given
#   in the session context, not a value memorized from an earlier turn —
#   recompute-sensitive language should defer to that context each time.

# # Avoid

# - **CRITICAL**: You MUST NEVER guess, invent, or fabricate data. If a user asks for records, counts, or specific data, you MUST use the `frappe_get_list`, `frappe_query`, or `frappe_get_doc` tools to query the live database before answering.
# - Never guess record names, field names, DocType structures, or filter/join fields. Always pull the schema (frappe_get_doctype_info) or data first.
# - Never expose raw Python tracebacks to the user. Translate errors into plain
#   business language and suggest the corrective action.
# - Never operate outside the current user's Frappe permission scope.
# - Never ask for clarification when the available tools can resolve the ambiguity
#   directly.
# - Never produce long theoretical explanations when the user asked for an action.
# - Never repeat the same tool call with identical arguments if a tool returns results successfully.
# - Never explain a trend, comparison, or breakdown in prose alone when a
#   ```chart block is warranted.\
# """

IDENTITY = frappe.get_doc("Skill", "Identity").content or ""

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

QUERY_TOOL_GUIDANCE = """\
# Querying data: which tool

- `frappe_get_list`: simple, single-doctype listing/search, no join or aggregation.
- `frappe_query`: filtering plus up to 3 joined doctypes, and/or grouped
  aggregation (sum/count/avg/min/max) — use this instead of frappe_get_list
  whenever the question needs a linked field alongside source rows, or needs
  totals/counts by group. Do not sum or group raw rows by hand.
- `frappe_generate_report`: use an existing Frappe report (financial
  statements, analytics reports) instead of reconstructing its logic by hand.

If frappe_query or frappe_generate_report errors on an unknown field, don't
retry with another guess — call frappe_get_doctype_info, confirm the real
fieldname, then retry once.\
"""

CHART_INSTRUCTIONS = """\
# Charts

Emit a fenced ```chart block whenever the answer involves a trend, a \
comparison across categories, a breakdown by dimension, or a proportion of \
a whole. This is a default, not a suggestion — skip it only for a single \
scalar, a single record's detail, or >12 categories/series. A table does \
not substitute for a chart when one is warranted; use both if both help.

or if you generate a report and it can be visualised using a chart, you should generate a chart block for it.

The block must contain ONLY valid JSON — no comments, no trailing commas, \
nothing before or after the fence. The JSON is passed directly to \
frappe.Chart, so it must match that constructor's options object:

```chart
{
  "title": "Revenue by Region",
  "type": "bar",
  "data": {
    "labels": ["Nairobi", "Mombasa", "Kisumu"],
    "datasets": [{ "name": "Q2 2026", "values": [420000, 210000, 98000] }]
  }
}
```

Rules:
- `type` must be one of: bar, line, scatter, pie, percentage, axis-mixed, heatmap.
- Pull labels/values from real tool output (frappe_get_list / frappe_get_doc / \
frappe_query / frappe_generate_report) — never invent numbers to fill a chart.
- One ```chart block per chart. For multiple charts, use multiple blocks with \
prose between them.
- Never wrap the block in ```json — it must be ```chart exactly, or it will \
render as a code sample instead of a live chart.
- If the data has too many series or points to read as a chart (e.g. >12 \
categories), prefer a table instead.\
"""

SKILLS_INDEX_INTRO = (
	"Below is an index of available skills. Use `view_skill` to read a "
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


# =========================================================================
# Session context — company / currency / fiscal year / installed apps /
# roles / user identity. Must be computed fresh per request; never baked
# into the cached stable system prompt, since it varies per user and per
# session.
# =========================================================================


def get_session_context() -> dict:
	"""Snapshot of session-scoped facts the model needs to ground its
	queries.

	Notes on sourcing, from things that have bitten real ERPNext deployments:
	- User identity: frappe.session.user is a login id (email), not a name
	  a human would recognize themselves by — never surface it alone as
	  "who the user is". Resolve the display name from the User doctype's
	  full_name, falling back to first_name/last_name, then the email
	  localpart, then the raw email if nothing else is populated (can
	  happen for freshly-created or system accounts). A separate casual
	  first name is resolved too, since "Good morning, Faiz Ahmed" reads
	  stiffer than "Good morning, Faiz" — fall back to the first token of
	  the display name if first_name isn't set.
	- Time-of-day: compute the greeting period (morning/afternoon/evening/
	  night) server-side from the resolved System Settings time_zone rather
	  than handing the model a bare timestamp and expecting correct
	  chronological reasoning about greeting conventions — that's a job for
	  code, not inference.
	- Company: frappe.defaults.get_user_default requires the capitalized key
	  "Company" — the lowercase "company" silently returns the site-wide
	  Global Defaults value instead of the user's actual default, which is a
	  long-standing footgun. Even with the right casing, a user restricted
	  via User Permission rather than a plain default can get no value back,
	  so we fall back to Global Defaults, and separately surface the full set
	  of permitted companies so the agent can tell when scope is ambiguous.
	- Currency: prefer the resolved company's currency over the bare system
	  default, since multi-company Kenyan deployments frequently mix KES and
	  USD entities.
	- Fiscal year: derived from today's date against the Fiscal Year
	  doctype's date range rather than trusting a stored "default fiscal
	  year" value, since that concept is unreliable/version-dependent
	  (ERPNext v15 removed the UI to set one explicitly).
	- Installed apps: not every client site runs every module (e.g. Frappe
	  Lending isn't installed everywhere), so the agent should check this
	  before assuming a doctype exists.
	"""
	user = frappe.session.user

	user_details = (
		frappe.db.get_value(
			"User", user, ["full_name", "first_name", "last_name"], as_dict=True
		)
		or {}
	)
	display_name = (
		user_details.get("full_name")
		or " ".join(
			filter(None, [user_details.get("first_name"), user_details.get("last_name")])
		)
		or (user.split("@")[0] if user and "@" in user else user)
		or user
	)
	first_name = (
		user_details.get("first_name")
		or display_name.split(" ")[0]
	)

	timezone = frappe.db.get_single_value("System Settings", "time_zone")
	try:
		local_now = (
			frappe.utils.now_datetime().astimezone(frappe.utils.get_timezone(timezone))
			if timezone
			else datetime.now()
		)
	except Exception as e:
		logger.warning("Could not resolve session timezone %r: %s", timezone, e)
		local_now = datetime.now()

	hour = local_now.hour
	if 5 <= hour < 12:
		time_of_day = "morning"
	elif 12 <= hour < 17:
		time_of_day = "afternoon"
	elif 17 <= hour < 21:
		time_of_day = "evening"
	else:
		time_of_day = "night"

	company = frappe.defaults.get_user_default("Company")
	if not company:
		company = frappe.db.get_single_value("Global Defaults", "default_company")

	permitted_companies = frappe.db.get_list(
		"User Permission",
		filters={"user": user, "allow": "Company"},
		pluck="for_value",
	) or ([company] if company else [])

	company_currency = None
	if company:
		company_currency = frappe.db.get_value("Company", company, "default_currency")
	currency = company_currency or frappe.db.get_single_value(
		"Global Defaults", "default_currency"
	)

	today = frappe.utils.today()
	fiscal_year = frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ("<=", today), "year_end_date": (">=", today)},
		["name", "year_start_date", "year_end_date"],
		as_dict=True,
	)

	try:
		installed_apps = frappe.get_installed_apps()
	except Exception as e:
		logger.warning("Could not fetch installed apps: %s", e)
		installed_apps = []

	try:
		roles = frappe.get_roles(user)
	except Exception as e:
		logger.warning("Could not fetch roles for %s: %s", user, e)
		roles = []

	return {
		"user": user,
		"user_display_name": display_name,
		"user_first_name": first_name,
		"time_of_day": time_of_day,
		"roles": roles,
		"default_company": company,
		"permitted_companies": permitted_companies,
		"currency": currency,
		"fiscal_year": fiscal_year,
		"installed_apps": installed_apps,
		"timezone": timezone,
		"date_format": frappe.db.get_single_value("System Settings", "date_format"),
		"number_format": frappe.db.get_single_value("System Settings", "number_format"),
	}


def format_session_context(ctx: dict) -> str:
	"""Render session context as compact prose for the volatile prompt tier."""
	lines = []

	role_list = ctx["roles"]
	shown_roles = ", ".join(role_list[:6]) + ("..." if len(role_list) > 6 else "")
	lines.append(
		f"Session user: {ctx['user_display_name']} ({ctx['user']}), "
		f"first name: {ctx['user_first_name']} — roles: {shown_roles}"
	)
	lines.append(f"Time of day for greeting purposes: {ctx['time_of_day']}")

	if ctx["default_company"]:
		companies = ctx["permitted_companies"]
		if len(companies) > 1:
			lines.append(
				f"Default company: {ctx['default_company']} — user is permitted on "
				f"multiple companies ({', '.join(companies)}); confirm scope before "
				f"running company-scoped queries."
			)
		else:
			lines.append(f"Default company: {ctx['default_company']}")
	else:
		lines.append(
			"No default company set for this user — confirm or infer scope "
			"from context before running company-scoped queries."
		)

	if ctx["currency"]:
		lines.append(f"Currency: {ctx['currency']}")

	fy = ctx["fiscal_year"]
	if fy:
		lines.append(
			f"Current fiscal year: {fy['name']} "
			f"({fy['year_start_date']} to {fy['year_end_date']})"
		)
	else:
		lines.append(
			"No Fiscal Year record covers today's date — verify before "
			"answering any 'this year' / YTD question."
		)

	if ctx["installed_apps"]:
		lines.append(f"Installed apps: {', '.join(ctx['installed_apps'])}")

	if ctx["timezone"]:
		lines.append(f"Timezone: {ctx['timezone']}")

	return "\n".join(lines)


def _safe_session_context_block() -> str:
	"""Session context is best-effort: if it fails for any reason (e.g. no
	Frappe request context available, such as in isolated tests), degrade
	to just the date rather than breaking prompt assembly."""
	try:
		return format_session_context(get_session_context())
	except Exception as e:
		logger.error("Failed to build session context: %s", e)
		return ""


def build_system_prompt_parts(
	system_message: str | None = None,
) -> dict[str, str]:
	"""Assemble the system prompt as three tiers."""
	try:
		skills_text = list_skills({"limit": 20})
	except Exception as e:
		logger.error("Failed to load skills: %s", e)
		skills_text = "No skills loaded."

	stable = "\n\n".join(
		[
			IDENTITY,
			TOOL_USE_ENFORCEMENT,
			QUERY_TOOL_GUIDANCE,
			CHART_INSTRUCTIONS,
			TASK_COMPLETION,
			f"{SKILLS_INDEX_INTRO}\n\n{skills_text}",
		]
	)

	context = system_message or ""

	volatile_parts = [f"The current date and time is and the Session started at: {datetime.now().strftime('%A, %B %d, %Y')}"]
	session_block = _safe_session_context_block()
	if session_block:
		volatile_parts.append(session_block)
	volatile = "\n\n".join(volatile_parts)

	return {
		"stable": stable,
		"context": context,
		"volatile": volatile,
	}


def get_system_prompt(system_message: str | None = None) -> str:
	"""Build and cache the full system prompt.

	NOTE: session context lives in `volatile` and is fetched fresh every
	call to build_system_prompt_parts — but get_system_prompt itself caches
	the *joined* result on first call. If per-session freshness is required
	here (recommended, since company/roles/fiscal-year/user identity are
	user-specific), callers should prefer build_system_prompt_parts()
	directly instead of relying on this cached wrapper, or invalidate_prompt_cache()
	per session.
	"""
	global _CACHED_SYSTEM_PROMPT
	if _CACHED_SYSTEM_PROMPT is None:
		parts = build_system_prompt_parts(system_message=system_message)
		_CACHED_SYSTEM_PROMPT = "\n\n".join(p for p in parts.values() if p)
	return _CACHED_SYSTEM_PROMPT


def invalidate_prompt_cache() -> None:
	"""Force a full rebuild on the next call to ``get_system_prompt``."""
	global _CACHED_SYSTEM_PROMPT
	_CACHED_SYSTEM_PROMPT = None
	_AGENT_DEF_CACHE.clear()


# =========================================================================
# Agent Definition support — user-created agents (Agent Builder)
# =========================================================================


def get_agent_definition(agent_name: str) -> dict:
	"""Load an ``Agent Definition`` record, cached per process.

	Raises frappe.DoesNotExistError if the name isn't found; throws if
	disabled.
	"""
	if agent_name not in _AGENT_DEF_CACHE:
		doc = frappe.get_doc("Agent Definition", agent_name)
		if not doc.is_enabled:
			frappe.throw(f"Agent '{agent_name}' is disabled.")
		_AGENT_DEF_CACHE[agent_name] = {
			"agent_name": doc.agent_name,
			"instructions": doc.instructions or "",
			"model": doc.model or None,
			"temperature": doc.temperature,
			"max_turns": doc.max_turns or 40,
			"tool_mode": doc.tool_mode or "All",
			"allowed_tools": [t.strip() for t in (doc.allowed_tools or "").split(",") if t.strip()],
		}
	return _AGENT_DEF_CACHE[agent_name]


def get_default_agent_name() -> str | None:
	"""Return the Agent Definition flagged is_default, if any (used by the
	chat widget when no explicit agent is requested). None -> fall back to
	the hardcoded Omnis identity, for backward compatibility."""
	return frappe.db.get_value("Agent Definition", {"is_default": 1, "is_enabled": 1}, "agent_name")


def get_agent_system_prompt(agent_name: str | None) -> str:
	"""Build the system prompt for a specific Agent Definition, layering its
	instructions on top of the same stable Identity/Style/Chart/Skills
	scaffold every agent shares. Falls back to the default Omnis prompt when
	agent_name is None."""
	if not agent_name:
		return get_system_prompt()

	agent_def = get_agent_definition(agent_name)
	parts = build_system_prompt_parts(system_message=agent_def["instructions"])
	return "\n\n".join(p for p in parts.values() if p)


def get_tool_schemas_for(agent_name: str | None) -> list:
	"""Return the tool schema list a given agent is allowed to see.

	This is a *soft* restriction: it narrows what the model is offered, not
	what ToolRegistry can execute. Good enough to scope an agent's
	behavior; it is not a hard permission boundary (Frappe's own doc
	permissions still apply underneath every tool call).
	"""
	all_schemas = get_tool_registry().get_tool_schemas()
	if not agent_name:
		return all_schemas

	agent_def = get_agent_definition(agent_name)
	mode = agent_def["tool_mode"]
	allowed = set(agent_def["allowed_tools"])
	if mode == "All" or not allowed:
		return all_schemas

	def _name(schema):
		return schema.get("function", {}).get("name") or schema.get("name")

	if mode == "Allow List":
		return [s for s in all_schemas if _name(s) in allowed]
	if mode == "Block List":
		return [s for s in all_schemas if _name(s) not in allowed]
	return all_schemas