# agent_builder/native_api/tools/clarify_approval_tools/notify.py
"""User-facing notifications for triggered agent runs.

Three channels, each covering the others' blind spots:

1. Realtime toast (notify_run_started) — the "something is happening
   right now" signal. Zero DB writes, fire-and-forget. Missed by
   offline users, which is fine: for DocType Event triggers it's sent
   in the SAME request as the user's save — the one moment they are
   guaranteed to be online.

2. Notification Log row (notify_run_complete) — the persistent outcome
   record. Survives offline users, updates the Desk bell badge live
   (Frappe publishes on Notification Log insert), and click-throughs
   to the Agent session of the run.

3. Timeline comment (add_agent_comment) — the contextual record. A run
   fired by SO-0042 leaves its outcome on SO-0042, where every future
   viewer of that document finds it.

The toast channel requires agent_notifications.js (app_include_js);
the bell and comment channels are pure server-side and need no client
code.
"""

import frappe

# Optional but recommended: create this as a disabled-login User so
# timeline comments render with a friendly name/avatar instead of a raw
# email. Everything still works if it doesn't exist — Frappe will show
# the email as the comment author.
AGENT_BOT_EMAIL = "agent@example.com"
AGENT_BOT_NAME = "Agent"


def excerpt_text(text: str, limit: int = 280) -> str:
    """First ~`limit` chars of a run's response, cut on a word boundary.
    Keeps bell entries and doc comments scannable — the full response is
    always one click away on the linked Agent session."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " …"


def dedupe_users(users) -> list:
    """Drop None/empty, duplicates, and system accounts — a Notification
    Log row for Administrator or Guest is noise nobody reads, and the
    start toast shouldn't fire for system-driven saves either."""
    seen, out = set(), []
    for u in users or []:
        if u and u not in ("Guest", "Administrator") and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def system_managers() -> list:
    """Enabled System Managers — the fallback audience for FAILED
    unattended runs (scheduled/webhook triggers with no run_as_user),
    so failures are never silent. Only queried on that failure path."""
    try:
        names = frappe.get_all(
            "Has Role",
            filters={"role": "System Manager", "parenttype": "User"},
            pluck="parent",
        )
        return dedupe_users(
            frappe.get_all(
                "User",
                filters={"enabled": 1, "name": ["in", names]},
                pluck="name",
            )
        )
    except Exception:
        frappe.log_error("agent_builder system_managers lookup failed", frappe.get_traceback())
        return []


def notify_run_started(users, message: str, doctype: str | None = None, docname: str | None = None):
    """Ephemeral 'an agent run just queued' toast.

    Called from fire_trigger inside the user's own request (DocType
    Event path), so latency is ~zero and nothing is written to the DB on
    the request path. Users are deduped; system accounts dropped.
    Never raises — a notification failure must never break the trigger.
    """
    for user in dedupe_users(users):
        try:
            frappe.publish_realtime(
                "agent_builder_progress",
                {"message": message, "doctype": doctype, "docname": docname},
                user=user,
            )
        except Exception:
            frappe.log_error("agent_builder start toast failed", frappe.get_traceback())


def notify_run_complete(
    user: str,
    subject: str,
    message: str,
    success: bool = True,
    link_doctype: str | None = None,
    link_name: str | None = None,
):
    """Persistent outcome notification: one Notification Log row (Desk
    bell, survives offline users, click-through to link_doctype/link_name
    — pass the Agent session) plus a best-effort live toast for users
    who happen to be online right now.

    Signature is a superset of the old msgprint-based version — existing
    callers passing (user, subject, message, success) keep working.
    `message` is excerpted here, so callers may pass the full response.
    """
    # ── Persistent channel: the bell ─────────────────────────────────
    try:
        frappe.get_doc(
            {
                "doctype": "Notification Log",
                "for_user": user,
                "type": "Alert",  # if your Notification Log Select lacks "Alert", use "Action"
                "subject": subject,
                "email_content": excerpt_text(message),
                "document_type": link_doctype,
                "document_name": link_name,
            }
        ).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error("agent_builder completion notification failed", frappe.get_traceback())

    # ── Ephemeral channel: live toast if they're at a Desk right now ─
    try:
        frappe.publish_realtime(
            "agent_builder_run_complete",
            {
                "message": subject,
                "success": success,
                "doctype": link_doctype,
                "docname": link_name,
            },
            user=user,
        )
        # TEMP DEBUG — confirms the call was reached and what args it used.
        # Remove once the toast is confirmed working again.
        frappe.log_error(
            f"agent_builder DEBUG: publish_realtime fired for user={user!r} success={success}",
            "agent_builder realtime debug",
        )
    except Exception:
        # TEMP DEBUG — was silently swallowed before; now logged so we can
        # actually see why. Revert to bare `except: pass` once fixed.
        frappe.log_error("agent_builder realtime publish failed", frappe.get_traceback())


def add_agent_comment(doctype: str, docname: str, content: str):
    """Timeline comment on the triggering document — the contextual
    record. Callers skip delete events themselves (the doc may be gone);
    this also just logs and moves on if the insert fails for any reason.
    """
    if not (doctype and docname):
        return
    try:
        frappe.get_doc(
            {
                "doctype": "Comment",
                "comment_type": "Comment",
                "reference_doctype": doctype,
                "reference_name": docname,
                "comment_email": AGENT_BOT_EMAIL,
                "comment_by": AGENT_BOT_NAME,
                "content": content,
            }
        ).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error("agent_builder doc comment failed", frappe.get_traceback())


def notify_progress(user: str, message: str, run_id: str | None = None):
    """Back-compat shim for existing callers (workflow engine). Maps the
    old one-user progress ping onto the batched toast channel."""
    notify_run_started([user], message)