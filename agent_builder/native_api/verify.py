# agent_builder/native_api/verify.py
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
    """Load display messages for a chat — paginated.

    Reshapes the two normalized child tables (Agent Message, Agent Tool
    Call) back into the turn-based shape the widget's history renderer
    expects — the same shape the *live* renderer builds turn-by-turn
    while streaming:

        { role: "assistant", content, is_error,
          tool_calls: [{tool, args, status, elapsed_ms, result|error}],
          reasoning: {text, elapsed_ms} | null }

    "reasoning" and legacy "tool" rows are never sent back as their own
    message entries — the frontend only renders user/assistant rows;
    everything else is folded into the assistant row it belongs to.
    """
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

    # Group tool calls by the assistant message that requested them.
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
                "status": tc.status,            # "pending" | "running" | "success" | "error"
                "elapsed_ms": tc.elapsed_ms,
                "result": tc.result,
                "error": tc.error,
            })

    # Walk rows in write order and pair each reasoning row with the very
    # next assistant row — that's the order Conversation writes them in
    # (_flush_reasoning() runs right before add_assistant_message()'s
    # append, and again before each emit_tool_start()).
    #
    # Caveat: if a reasoning row lands as the very last row of a page and
    # its assistant row falls on the next page, this pairing breaks across
    # the page boundary. Only matters once conversations exceed `limit`
    # messages — fine for now, flag if you start paginating mid-turn.
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

        # Any other role (e.g. a legacy "tool" row from before the
        # migration) is intentionally skipped — the new schema never
        # produces a standalone tool-result message; results live on the
        # tool call row itself and are attached to their parent assistant
        # message above.

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

    

@frappe.whitelist()
def get_skills():
    """Return all skills available to the agent for the frontend.

    Reads from the new Skill schema (name_, description) and returns a
    slugified name for routing and a clean label for display.
    """
    try:
        native_skills = frappe.get_all(
            "Skill",
            fields=[
                "name_",   # display name (Data, hidden, unique)
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
def chat(message, chat_id=None, attachments=None):
    """API Endpoint: Queues the message for background processing."""
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
        user=user
    )

    # frappe.enqueue returns the RQ Job object (None in `now=True` sync-test
    # mode, since there's nothing to cancel by then anyway).
    job_id = getattr(job, "id", None)

    return {"status": "queued", "chat_id": chat_id, "job_id": job_id}


@frappe.whitelist()
def stop_chat(chat_id, job_id=None):
    """Signal the running background job for this chat to stop.

    See Conversation.request_stop for the two-layer mechanism (cooperative
    Redis flag + best-effort RQ interrupt).
    """
    if not chat_id:
        frappe.throw("chat_id required")

    user = frappe.db.get_value("Agent session", chat_id, "user")
    if user != frappe.session.user:
        frappe.throw("Not authorised", frappe.PermissionError)

    Conversation.request_stop(chat_id, job_id)
    return {"status": "stopping"}


def process_agent_chat(message, chat_id, attachments, user):
    """Background Job: Executes the agent loop."""
    # ── Extract slash-command skill invocations ──
    skill_slugs, cleaned_message = _extract_skill_commands(message)
    invoked_skills, not_found = _load_invoked_skills(skill_slugs)

    # Use cleaned message; fall back to original if slash commands
    # were the entire message (e.g. user typed only "/summarize")
    agent_message = cleaned_message if cleaned_message else message

    # If some skills weren't found, append a note so the model
    # can inform the user rather than silently ignoring
    if not_found:
        missing = ", ".join(f"/{s}" for s in not_found)
        agent_message = f"{agent_message}\n\n[Skills not found: {missing}]"

    if attachments:
        file_lines = "\n".join(
            f"- {a.get('file_name', 'file')}: {a.get('file_url', '')}"
            for a in attachments
        )
        agent_message = f"{agent_message}\n\n[Attached files]\n{file_lines}".strip()

    conversation = Conversation(session_id=chat_id, user=user)

    try:
        agent = Agent()

        # Inject skill content as a per-turn system message,
        # positioned right before the user message in the child table.
        # This is separate from the global system prompt (set by Agent
        # via conversation.set_system) and won't be overwritten.
        if invoked_skills:
            skill_injection = _build_skill_injection(invoked_skills)
            if skill_injection:
                conversation.add_system_message(skill_injection)

        conversation.add_user_message(agent_message)
        

        final_response = asyncio.run(
            agent.run(
                conversation,
                on_token=conversation.emit_token,
                on_reasoning=conversation.emit_reasoning,
            )
        )

        frappe.db.commit()
        conversation.emit_done(final_response)

    except MaxTurnsError as e:
        frappe.db.commit()
        conversation.emit_error("Agent took too long.")
        frappe.log_error("Agent Max Turns", str(e))

    except StoppedByUser:
        # Frontend already finalized the bubble locally in onStop() (see
        # chat_messages.js) and set its own _stopped flag, so we deliberately
        # emit_done with an empty string here rather than any real content —
        # onDone() treats an empty response as a no-op (no new bubble
        # appended). We still commit so partial tool-call rows / assistant
        # content written before the interrupt aren't lost.
        frappe.db.commit()
        conversation.emit_done("")

    except Exception as e:
        frappe.db.commit()
        error_text = str(e) if frappe.conf.get("developer_mode") else "Sorry, something went wrong."
        conversation.emit_error(error_text)
        frappe.log_error("Agent Chat Error", frappe.get_traceback())