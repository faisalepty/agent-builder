# agent_builder/native_api/verify.py
import logging
import re

import frappe
import asyncio

from agent_builder.native_api.agent.conversation import Conversation, StoppedByUser
from agent_builder.native_api.agent.agent import Agent, MaxTurnsError


_SKILL_CMD_RE = re.compile(r'(?:^|\s)/([a-zA-Z][a-zA-Z0-9-]*)')


def _extract_skill_commands(message: str):
    """Extract /skill-name invocations from a user message.

    Returns (skill_slugs, cleaned_message) where:
      - skill_slugs: list of lowercased slug strings (e.g. ["customer-onboarding"])
      - cleaned_message: the original message with /commands removed
    """
    if not message:
        return [], message

    slugs = []
    for m in _SKILL_CMD_RE.finditer(message):
        slugs.append(m.group(1).lower())

    # Strip the slash commands from the visible message
    cleaned = _SKILL_CMD_RE.sub('', message)
    cleaned = re.sub(r' {2,}', ' ', cleaned).strip()

    return slugs, cleaned


def _load_invoked_skills(skill_slugs: list):
    """Load full content for skills matching the given slugs.

    Queries all enabled Skills, slugifies each name_, and matches against
    the requested slugs. Returns (found_skills, not_found_slugs).

    found_skills: [{slug, label, content, description}, ...]
    not_found_slugs: ["some-slug", ...]
    """
    if not skill_slugs:
        return [], []

    all_skills = frappe.get_all(
        "Skill",
        fields=["name_", "content", "description"],
        filters={"is_enabled": True},
    )

    found = []
    found_slugs = set()

    for s in all_skills:
        raw_name = s.get("name_")
        if not raw_name:
            continue

        slug = _slugify(raw_name)
        if slug in skill_slugs and slug not in found_slugs:
            found.append({
                "slug": slug,
                "label": raw_name,
                "content": s.get("content") or "",
                "description": s.get("description") or "",
            })
            found_slugs.add(slug)

    not_found = [s for s in skill_slugs if s not in found_slugs]
    return found, not_found


def _build_skill_injection(skills: list):
    """Build a system message string from loaded skill contents.

    Returns None if skills is empty.
    """
    if not skills:
        return None

    sections = [
        "# Skill Invocation",
        "The user has explicitly invoked the following skill(s) via slash command. "
        "Follow these instructions precisely for this request.\n",
    ]

    for skill in skills:
        sections.append(f"## {skill['label']}")
        if skill["description"]:
            sections.append(f"_{skill['description']}_\n")
        if skill["content"]:
            sections.append(skill["content"])
        else:
            sections.append(
                "_(No content defined for this skill. "
                "Use the `skill_view` tool if available.)_"
            )
        sections.append("")  # blank-line separator

    return "\n".join(sections)

@frappe.whitelist()
def get_messages(chat_id, limit=50, start=0):
    """Load display messages for a chat — paginated."""
    TOOL_CALL_DOCTYPE = "Agent Tool Call"
    if not frappe.db.exists("Agent session", chat_id):
        frappe.throw("Chat not found", frappe.DoesNotExistError)

    user = frappe.db.get_value("Agent session", chat_id, "user")
    if user != frappe.session.user:
        frappe.throw("Not authorised", frappe.PermissionError)

    title = frappe.db.get_value("Agent session", chat_id, "title")

    limit = int(limit)
    start = int(start)

    rows = frappe.get_list(
        "Agent Message",
        filters={"parent": chat_id, "parenttype": "Agent session"},
        fields=["name", "message_id", "role", "content", "timestamp",
                "attachments", "is_error"],
        order_by="timestamp asc, idx asc",
        limit_page_length=limit,
        start=start,
        ignore_permissions=True,
    )

    message_ids = [r.message_id for r in rows if r.message_id]

    tool_calls_by_parent = {}
    if message_ids:
        tc_rows = frappe.get_list(
            TOOL_CALL_DOCTYPE,
            filters={
                "parent": chat_id,
                "parenttype": "Agent session",
                "parent_message": ["in", message_ids],
            },
            fields=["parent_message", "call_id", "tool_name", "arguments",
                    "status", "result", "error", "elapsed_ms"],
            order_by="idx asc",
            ignore_permissions=True,
        )
        for tc in tc_rows:
            tool_calls_by_parent.setdefault(tc.parent_message, []).append({
                "tool": tc.tool_name,
                "args": _safe_json(tc.arguments),
                "status": tc.status,
                "elapsed_ms": tc.elapsed_ms,
                "result": tc.result,
                "error": tc.error,
            })

    messages = []
    pending_reasoning = None

    for row in rows:
        if row.role == "reasoning":
            pending_reasoning = {"text": row.content, "elapsed_ms": None}
            continue

        if row.role == "assistant":
            messages.append({
                "role": "assistant",
                "content": row.content,
                "is_error": row.is_error,
                "tool_calls": tool_calls_by_parent.get(row.message_id, []),
                "reasoning": pending_reasoning,
            })
            pending_reasoning = None

        elif row.role == "user":
            messages.append({
                "role": "user",
                "content": row.content,
                "attachments": row.attachments,
            })

    return {"messages": messages, "title": title}


def _safe_json(value):
    if not value:
        return None
    try:
        return frappe.parse_json(value)
    except Exception:
        return value
    
    
def _slugify(value):
	"""Turn a skill's display name into a clean /slash-command token."""
	if not value:
		return ""

	return re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")


_MODEL_OPTIONS_CACHE_KEY = "agent_builder:model_options"


@frappe.whitelist()
def get_model_options():
	"""Model catalog for the chat widget's model/reasoning picker.

	Scoped to whichever provider is currently configured on Agent Setup
	(a model_override only makes sense for a model the active provider —
	or an OpenRouter passthrough — can actually serve, so there's no
	point showing models from other providers). Returns active
	(is_active=1) Model Pricing rows with pricing + capability fields,
	plus the site's current defaults so the widget can show what "Auto"
	(no override) actually resolves to.

	Cached for 5 minutes per site: this list changes rarely (a handful of
	manual Model Pricing edits at most) but the chat widget may call it
	every time it opens, across many users — caching avoids a DB round
	trip per widget open for data that's effectively static.
	"""
	cached = frappe.cache().get_value(_MODEL_OPTIONS_CACHE_KEY)
	if cached is not None:
		return cached

	provider = frappe.db.get_single_value("Agent Setup", "provider")
	default_model = frappe.db.get_single_value("Agent Setup", "model")

	# reasoning_effort is an optional field — Agent Setup may not have it
	# (see agent_setup.json history); guard rather than assume.
	setup_meta = frappe.get_meta("Agent Setup")
	default_effort = (
		frappe.db.get_single_value("Agent Setup", "reasoning_effort")
		if setup_meta.has_field("reasoning_effort")
		else None
	)

	rows = frappe.get_all(
		"Model Pricing",
		filters={"provider": provider, "active": 1},
		fields=[
			"model",
			"context_window",
			"max_output_tokens",
			"supports_tools",
			"supports_vision",
			"supports_reasoning",
			"reasoning_efforts",
			"input_price_per_million",
			"output_price_per_million",
			"cached_price_per_million",
		],
		order_by="model asc",
	)

	payload = {
		"provider": provider,
		"default_model": default_model,
		"default_reasoning_effort": default_effort,
		"models": rows,
	}
	frappe.cache().set_value(_MODEL_OPTIONS_CACHE_KEY, payload, expires_in_sec=300)
	return payload


def clear_model_options_cache():
	"""Call from doc_events (Model Pricing / Agent Setup on_update/on_trash
	in hooks.py) so a manual edit is reflected immediately instead of
	waiting out the 5-minute TTL. E.g. in hooks.py:

	    doc_events = {
	        "Model Pricing": {"on_update": "...clear_model_options_cache", "on_trash": "...clear_model_options_cache"},
	        "Agent Setup": {"on_update": "...clear_model_options_cache"},
	    }
	"""
	frappe.cache().delete_value(_MODEL_OPTIONS_CACHE_KEY)


@frappe.whitelist()
def get_skills():
    """Return all skills available to the agent for the frontend."""
    try:
        native_skills = frappe.get_all(
            "Skill",
            fields=[
                "name_",
                "description"
            ],
            filters={"is_enabled": True},
            order_by="name_ asc"
        )

        formatted_skills = []

        for s in native_skills:
            raw_name = s.get("name_")

            if not raw_name:
                continue

            formatted_skills.append({
                "name": _slugify(raw_name),
                "label": raw_name.replace("-", " ").title().replace(" Ui", " UI"),
                "description": s.get("description", "")
            })

        return {"skills": formatted_skills}

    except Exception:
        frappe.log_error(
            title="Skills Extraction Failed",
            message=frappe.get_traceback()
        )
        return {"skills": []}
    


@frappe.whitelist()
def get_agents():
    """Return all enabled Agent Definitions, for the Agent Builder page and
    any agent-picker UI in the chat widget."""
    agents = frappe.get_all(
        "Agent Definition",
        fields=["agent_name", "description", "icon", "is_default", "model"],
        filters={"is_enabled": 1},
        order_by="is_default desc, agent_name asc",
    )
    return {"agents": agents}


@frappe.whitelist()
def get_chats():
    """Return the current user's chat list."""
    chats = frappe.get_list(
        "Agent session",
        filters={"user": frappe.session.user, "status": "Active"},
        fields=["name", "title", "last_active", "message_count"],
        order_by="last_active desc",
        limit_page_length=50,
    )
    return {"chats": chats}


@frappe.whitelist()
def chat(message, chat_id=None, attachments=None, agent_name=None, model=None, reasoning_effort=None):
	"""API Endpoint: Queues the message for background processing.

	agent_name: optional name of an Agent Definition (Agent Builder) to run
	this turn with, instead of the default Omnis agent. The chat widget
	doesn't need to pass this — omit it and behavior is unchanged.
	model: optional explicit model id for this turn only (e.g. a model
	    picker in the chat widget), overriding the Agent Definition's own
	    model, which itself overrides the Agent Setup default. Omit for
	    unchanged behavior.
	reasoning_effort: optional explicit reasoning effort for this turn
	    only — this is the "enable thinking" toggle. Pass "none" to
	    explicitly disable reasoning for this turn even if Agent Setup
	    has an effort configured; omit to use the Agent Setup default.
	"""
	user = frappe.session.user
	attachments = frappe.parse_json(attachments) if attachments else []

    if not chat_id:
        chat_id = Conversation(user=user).session_id

    Conversation.clear_stop_flag(chat_id)

	job = frappe.enqueue(
		method="agent_builder.native_api.verify.process_agent_chat",
		queue="short",
		timeout=300,
		now=frappe.flags.in_test,
		message=message,
		chat_id=chat_id,
		attachments=attachments,
		user=user,
		agent_name=agent_name,
		model_override=model,
		reasoning_effort=reasoning_effort,
	)

    job_id = getattr(job, "id", None)

    return {"status": "queued", "chat_id": chat_id, "job_id": job_id}


@frappe.whitelist()
def stop_chat(chat_id, job_id=None):
    """Signal the running background job for this chat to stop — and stop
    it *now*, not "whenever the loop next checks a flag".

    Conversation.request_stop does two things: sets the cooperative Redis
    flag (kept as a fallback for jobs still queued rather than executing),
    and — the part that actually gives an immediate stop — hard-kills the
    RQ work-horse via job_id, the same mechanism as Desk's RQ Job "Stop
    Job" button.

    Because that kill can land mid-turn (mid-LLM-call, mid-tool-call),
    the killed process's own exception handling in process_agent_chat
    never gets to run. So this endpoint does the cleanup itself,
    synchronously, right here — the session is marked ended and any
    tool_calls left "pending"/"running" are marked "cancelled" before
    this call returns, rather than depending on a process that was just
    killed to tidy up after itself.
    """
    if not chat_id:
        frappe.throw("chat_id required")

    user = frappe.db.get_value("Agent session", chat_id, "user")
    if user != frappe.session.user:
        frappe.throw("Not authorised", frappe.PermissionError)

    Conversation.request_stop(chat_id, job_id)

    try:
        conversation = Conversation(session_id=chat_id)
        conversation.cancel_pending_tool_calls(
            reason="Cancelled: the user stopped the run."
        )
        conversation.save(ended_reason="EndedByUser")
    except Exception:
        # Don't let bookkeeping failure stop the stop — the job kill above
        # already fired, which is the part the user actually needed.
        frappe.log_error("stop_chat cleanup failed", frappe.get_traceback())

    frappe.db.commit()
    return {"status": "stopping"}


def _safe_error_message(e: Exception) -> str:
	"""Short, safe-to-display error summary for the chat widget.

	Always includes the exception type and a truncated message — enough
	to tell "rate limited" from "unknown model" from "a tool crashed"
	apart without asking the user to screenshot a blank "something went
	wrong" and guess. Capped short and intentionally NOT the full
	traceback (that only ever goes to frappe.log_error, via
	frappe.get_traceback(), never to the frontend) so nothing like a
	file path or internal detail leaks into the UI.
	"""
	msg = str(e).strip()
	if len(msg) > 300:
		msg = msg[:300] + "…"
	label = type(e).__name__
	return f"{label}: {msg}" if msg else label


def process_agent_chat(
    message,
    chat_id,
    attachments,
    user,
    agent_name=None,
    model_override=None,
    reasoning_effort=None,
):
    """Background Job: Executes the agent loop.

    agent_name: name of an Agent Definition to run this session's turn
    with. None -> the default Omnis agent (unchanged behavior).

    model_override / reasoning_effort: per-turn overrides forwarded from
    the chat() endpoint's model/reasoning_effort params — see chat()'s
    docstring and Agent.__init__ for precedence and the "none" tri-state.

    Deliberately one big try/except around the ENTIRE body, not just the
    agent run: this is a background job (frappe.enqueue), so any
    exception here — including one raised while just building the
    Conversation or rendering skill text, before the agent even starts —
    needs to (a) always be logged via frappe.log_error with the full
    traceback, and (b) always reach the frontend as *something*
    meaningful, not silently vanish into the job queue.
    """

    conversation = None

    try:
        conversation = (
            Conversation(session_id=chat_id, user=user)
            if chat_id
            else None
        )

        # ── Extract slash-command skill invocations ──────────────────────
        skill_slugs, cleaned_message = _extract_skill_commands(message)
        invoked_skills, not_found = _load_invoked_skills(skill_slugs)

        # Use the cleaned message unless the slash command consumed the
        # entire message (e.g. "/summarize"), in which case preserve the
        # original message.
        agent_message = cleaned_message if cleaned_message else message

        # Tell the model which requested skills could not be found.
        if not_found:
            missing = ", ".join(f"/{slug}" for slug in not_found)
            agent_message = (
                f"{agent_message}\n\n[Skills not found: {missing}]"
            )

        # Attachments are passed separately and converted into multimodal
        # content by Conversation.get_messages().

        skill_injection = None
        if invoked_skills:
            skill_injection = _build_skill_injection(invoked_skills)

        provenance = SessionProvenance(
            trigger_type="Chat",
            trigger_source="Chat",
            trigger_ref=chat_id,
        )

        result = run_headless_agent_streaming(
            agent_name=agent_name or "",
            input_message=agent_message,
            provenance=provenance,
            user=user,
            session_id=chat_id,
            on_token=conversation.emit_token if conversation else None,
            on_reasoning=conversation.emit_reasoning if conversation else None,
            skill_injection=skill_injection,
            model_override=model_override,
            reasoning_effort=reasoning_effort,
            attachments=attachments,
        )

        frappe.db.commit()

        if conversation:
            conversation.emit_done(result.response)

    except MaxTurnsError as e:
        frappe.db.rollback()

        frappe.log_error(
            title="Agent Max Turns",
            message=frappe.get_traceback(),
        )

        if conversation:
            conversation.emit_error(
                f"The agent ran too many turns without finishing ({e})."
            )

    except StoppedByUser:
        frappe.db.rollback()

        if conversation:
            conversation.emit_done("")

    except Exception as e:
        frappe.db.rollback()

        error_text = _safe_error_message(e)

        try:
            frappe.log_error(
                title="Agent Chat Error",
                message=frappe.get_traceback(),
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "frappe.log_error failed while handling process_agent_chat error"
            )

        if conversation:
            conversation.emit_error(error_text)
        else:
            logger = logging.getLogger(__name__)

            logger.error(
                "process_agent_chat failed before Conversation "
                "was created (chat_id=%s user=%s): %s",
                chat_id,
                user,
                error_text,
            )

            try:
                frappe.publish_realtime(
                    event="agent_error",
                    message={
                        "session_id": chat_id,
                        "response": error_text,
                    },
                    user=user,
                )
            except Exception:
                logger.exception(
                    "publish_realtime failed while handling "
                    "process_agent_chat error"
                )