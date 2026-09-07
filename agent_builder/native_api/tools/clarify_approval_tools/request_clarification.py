# agent_builder/native_api/tools/chat_tools/request_clarification.py

import json

import frappe
from frappe.realtime import get_user_room

from agent_builder.native_api.agent.conversation import CLARIFICATION_PENDING_KEY, current_session_id
from agent_builder.native_api.tools.decorator import tool

# CLARIFICATION_PENDING_KEY and current_session_id live in conversation.py,
# not agent.py — agent.py needs this constant too, and this tool needs
# current_session_id, so keeping either in the other file creates a
# circular import. conversation.py has no dependency on agent.py or this
# tool, and agent.py already depends on conversation.py one-way, so both
# sides importing shared state from there adds nothing new to the
# dependency graph.


@tool(schema_name="request_clarification")
def request_clarification(args: dict, **kwargs) -> str:
	"""Pause the current turn to ask the user a genuine clarifying question
	before continuing — the same pattern as Claude's own clarify tool.

	Call this only when you're actually blocked by ambiguity you can't
	resolve with a tool call: which of two same-named records, what date
	range "recently" means here, which of several plausible interpretations
	of the request is correct. Do not call this for anything a
	frappe_get_list/frappe_get_doc/frappe_get_doctype_info call could
	settle on its own — see the "Avoid" section of the system prompt.

	args:
	    question (str, required): the actual question, in plain language.
	    options (list[str], optional): 2-5 short, concrete answers the
	        user can tap instead of typing — offer these whenever the
	        ambiguity has a genuinely small set of resolutions (e.g. two
	        matching Customers). Omit entirely for open-ended questions.
	    allow_free_text (bool, optional): whether a typed answer is also
	        accepted alongside/instead of the options. Defaults to True
	        when `options` is omitted, False when options are given and
	        this isn't set — set it True explicitly if the options are
	        just shortcuts and a different typed answer should still work.

	This does not block — it returns immediately with a pause marker.
	The turn resumes once the user answers, and their answer arrives as
	this tool's result on the next turn: read it and continue.
	"""
	question = (args.get("question") or "").strip()
	if not question:
		return "Error: request_clarification requires a non-empty 'question'."

	raw_options = args.get("options") or []
	options = [str(o).strip() for o in raw_options if str(o).strip()][:5]

	allow_free_text = args.get("allow_free_text")
	if allow_free_text is None:
		allow_free_text = not options
	else:
		allow_free_text = bool(allow_free_text)

	session_id = current_session_id.get()
	clarification_id = f"clar_{frappe.generate_hash(length=10)}"

	frappe.publish_realtime(
		event="agent_clarification_request",
		message={
			"session_id": session_id,
			"clarification_id": clarification_id,
			"question": question,
			"options": options,
			"allow_free_text": allow_free_text,
		},
		room=get_user_room(frappe.session.user),
	)

	return json.dumps(
		{
			CLARIFICATION_PENDING_KEY: True,
			"clarification_id": clarification_id,
			"question": question,
		}
	)