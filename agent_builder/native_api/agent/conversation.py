# omnis_hermes/agent/conversation.py
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

import frappe
from frappe.realtime import get_user_room
from frappe.utils import now_datetime
from frappe.utils.background_jobs import get_redis_conn

# `attachments.py` is a NEW module (agent_builder/native_api/agent/attachments.py)
# added alongside this file to support image/file uploads to vision-capable
# models. Imported defensively: if it's missing (e.g. not yet deployed
# alongside this file) or fails for any other reason, plain-text chat —
# the vast majority of traffic and something that has nothing to do with
# attachments — must keep working exactly as before. build_content_parts
# is None in that case and get_messages() below falls back to plain text.
try:
	from agent_builder.native_api.agent.attachments import build_content_parts
except Exception:
	build_content_parts = None
	logging.getLogger(__name__).exception(
		"agent.attachments could not be imported — attachments will be "
		"sent as plain-text references only until this is fixed. Check "
		"that attachments.py was deployed to agent_builder/native_api/agent/ "
		"alongside conversation.py, and that workers were restarted."
	)

SESSION_DOCTYPE = "Agent session"

_STOP_FLAG_PREFIX = "agent_stop:"
_STOP_FLAG_TTL = 600  # seconds — well beyond any realistic single-turn runtime


class StoppedByUser(Exception):
	"""Raised inside Agent.run()'s loop when a user-initiated stop is
	detected via Conversation.is_stop_requested()."""

	pass


class ChainBrokenError(Exception):
	"""Raised when the model stops unexpectedly mid-chain.

	The partial_message contains whatever the model produced before
	the break, so callers can decide whether to surface it or retry.
	"""

	def __init__(self, reason: str, partial_message: dict[str, Any]):
		self.reason = reason
		self.partial_message = partial_message
		super().__init__(f"Chain broken: {reason}")


# Simple process-lifetime cache — pricing rows change rarely, and hitting the
# DB on every single assistant message would be wasteful. Call
# _invalidate_pricing_cache() from a Model Pricing on_update hook if you want
# changes to take effect without a worker restart.
_pricing_cache: dict[str, dict] = {}


def _get_pricing(model: str) -> dict | None:
	if not model:
		return None
	if model not in _pricing_cache:
		row = frappe.db.get_value(
			"Model Pricing",
			model,
			["input_price_per_million", "output_price_per_million", "cached_price_per_million"],
			as_dict=True,
		)
		_pricing_cache[model] = row or {}
	return _pricing_cache[model] or None


def _invalidate_pricing_cache():
	_pricing_cache.clear()


def _compute_cost(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float | None:
	pricing = _get_pricing(model)
	if not pricing:
		return None
	# Cached tokens are billed at the cheaper cached rate and should not
	# also be double-counted at the full input rate.
	billable_input = max((input_tokens or 0) - (cached_tokens or 0), 0)
	cost = 0.0
	cost += billable_input * (pricing.get("input_price_per_million") or 0) / 1_000_000
	cost += (output_tokens or 0) * (pricing.get("output_price_per_million") or 0) / 1_000_000
	cost += (cached_tokens or 0) * (pricing.get("cached_price_per_million") or 0) / 1_000_000
	return round(cost, 6)


def _gen_id() -> str:
	return frappe.generate_hash(length=16)


def _safe_tool_arguments(raw: str | None) -> str:
	"""Guarantee the string we replay as tool_calls[].function.arguments is
	valid JSON.

	A malformed arguments string (bad JSON the model emitted, e.g. a stray
	double comma) is caught and reported at execution time — the tool
	executor returns a parse-error result and the turn completes normally.
	But that raw broken string is what's persisted on the Agent Tool Call
	row, and get_messages() replays it verbatim into every future request's
	history. Some OpenRouter backends (observed: Novita) validate every
	tool_call.function.arguments in the whole message array, not just the
	newest one, and 400 the *entire* request the moment any historical call
	has unparseable arguments — even though that call already failed
	cleanly and is done.

	Falling back to "{}" here only changes what gets replayed as history;
	the tool-result row already on record (the "could not parse arguments"
	error) is untouched, so nothing the user or model sees changes.
	"""
	raw = raw or "{}"
	try:
		json.loads(raw)
		return raw
	except (TypeError, ValueError):
		return "{}"


class Conversation:
	def __init__(self, session_id=None, user=None):
		self.user = user or frappe.session.user or "Guest"
		self.room = get_user_room(self.user)

		if session_id and frappe.db.exists(SESSION_DOCTYPE, session_id):
			self.doc = frappe.get_doc(SESSION_DOCTYPE, session_id)
		else:
			self.doc = frappe.new_doc(SESSION_DOCTYPE)
			self.doc.user = self.user
			if session_id:
				self.doc.name = session_id
			self.doc.insert(ignore_permissions=True)

		self.session_id = self.doc.name
		self.system_prompt = None
		self._reasoning_buffer = ""
		self._last_message_id = None
		# Track recent tool calls for loop detection.
		# The Agent can override _max_repeated_calls to tune sensitivity.
		self._recent_tool_calls: list[str] = []
		self._max_repeated_calls: int = 3

	# ── Loop detection ───────────────────────────────────

	def _detect_tool_loop(self, tool_name: str, arguments: str) -> bool:
		"""Detect if we're calling the same tool with the same args repeatedly.

		Returns True if the same (tool_name, arguments) pair has been seen
		_max_repeated_calls times consecutively at the tail of the history.
		"""
		call_signature = f"{tool_name}:{arguments}"
		self._recent_tool_calls.append(call_signature)

		# Keep only the last N*2 calls so the window doesn't grow unbounded.
		window = self._max_repeated_calls * 2
		if len(self._recent_tool_calls) > window:
			self._recent_tool_calls = self._recent_tool_calls[-window:]

		# Count consecutive identical calls from the tail.
		consecutive = 0
		for call in reversed(self._recent_tool_calls):
			if call == call_signature:
				consecutive += 1
			else:
				break

		return consecutive >= self._max_repeated_calls

	# ── History reconstruction ───────────────────────────

	def get_messages(
		self,
		reasoning_replay=None,
		max_turns: int | None = None,
		allow_image_attachments: bool = True,
	):
		"""Rebuild the OpenAI-style message list from the two normalized tables.

		       reasoning_replay: optional callable(meta, had_tool_calls, msg) — see
		       OpenAIProvider.replay_reasoning. When given, it decides how (or
		       whether) each assistant row's stored reasoning_meta gets reattached
		       to the outgoing message for this specific provider/model. When
		       omitted, falls back to the old universal behavior of merging
		       buffered plain-text reasoning into a  </thinking>
		block inside content —
		       safe for simple open-weight deployments, but NOT correct for
		       providers with strict replay requirements (DeepSeek V4, OpenRouter
		       reasoning models with tool calls). Always pass the provider's bound
		       replay_reasoning when one is available.

		       max_turns: optional limit on the number of assistant turns to include
		       in the rebuilt history. When set, only the *last* max_turns assistant
		       messages are sent to the provider (older ones are dropped from the
		       request but remain in the DB for the timeline UI). This prevents
		       context-window overflow on very long sessions. The system prompt
		       and the user message that triggered the first kept assistant turn
		       are always preserved.

		       allow_image_attachments: whether the resolved model advertises
		       vision support (Model Pricing.supports_vision) for this run. When
		       True (default — preserves old callers' behavior), user-turn image
		       attachments are inlined as base64 image_url content parts. When
		       False, image attachments are skipped and referenced by filename
		       in the text instead, so we don't send bytes a text-only model
		       will 400 on. PDF attachments are unaffected by this flag — see
		       agent.attachments.build_content_parts.
		"""
		messages = []
		if self.system_prompt:
			messages.append({"role": "system", "content": self.system_prompt})

		# Index tool calls by their parent message_id, preserving insertion order.
		tool_calls_by_parent: dict[str, list] = {}
		for tc in self.doc.tool_calls:
			tool_calls_by_parent.setdefault(tc.parent_message, []).append(tc)

		# Buffer to accumulate reasoning so we can attach it to the next
		# assistant turn — only used in the no-strategy fallback path.
		pending_reasoning = []

		# Collect all rows so we can slice by turn count if needed.
		all_rows = list(self.doc.messages)

		# If max_turns is set, find the cut point: we want the LAST
		# max_turns assistant messages, plus any user/system messages that
		# fall after the assistant message just before the first kept one
		# (so we don't lose the user prompt that triggered it).
		if max_turns is not None:
			assistant_indices = [i for i, r in enumerate(all_rows) if r.role == "assistant"]
			if len(assistant_indices) > max_turns:
				# Index of the first assistant message we want to keep.
				first_keep_idx = assistant_indices[-max_turns]
				# Index of the assistant message just before it (if any).
				prev_assistant_idx = (
					assistant_indices[-max_turns - 1] if len(assistant_indices) > max_turns else -1
				)
				# Keep everything from prev_assistant+1 onward so we
				# capture the user message that preceded the first kept
				# assistant turn.
				cut = prev_assistant_idx + 1 if prev_assistant_idx >= 0 else 0
				all_rows = all_rows[cut:]

		for row in all_rows:
			if row.role == "reasoning":
				if reasoning_replay is None and row.content:
					pending_reasoning.append(row.content.strip())
				continue

			if row.role == "assistant":
				content = row.content or ""
				tc_rows = tool_calls_by_parent.get(row.message_id, [])
				had_tool_calls = bool(tc_rows)

				if reasoning_replay is None:
					# Fallback: re-attach preceding reasoning into the
					# assistant's content block as a  </thinking> tag. Fine for
					# providers that just want text; not correct for
					# providers with structural replay requirements.
					if pending_reasoning:
						reasoning_text = "\n\n".join(pending_reasoning)
						if content:
							content = f" </thinking>\n{reasoning_text}\n</thinking>\n\n{content}"
						else:
							content = f" </thinking>\n{reasoning_text}\n</thinking>"
						pending_reasoning = []

				msg = {"role": "assistant", "content": content}

				if tc_rows:
					msg["tool_calls"] = [
						{
							"id": tc.call_id,
							"type": "function",
							"function": {
								"name": tc.tool_name,
								"arguments": _safe_tool_arguments(tc.arguments),
							},
						}
						for tc in tc_rows
					]
				messages.append(msg)

				if reasoning_replay is not None:
					reasoning_meta = None
					stored = getattr(row, "reasoning_meta", None)
					if stored:
						try:
							reasoning_meta = json.loads(stored)
						except (TypeError, ValueError):
							reasoning_meta = None
					reasoning_replay(reasoning_meta, had_tool_calls, msg)

				# OpenAI's Chat Completions API strictly requires that every
				# tool_call_id in an assistant message be immediately followed
				# by a matching tool-role reply — with NO exceptions, unlike
				# OpenRouter/NVIDIA which tolerate gaps. If a tool call got
				# stuck in "pending"/"running" (crash, restart, interrupted
				# turn) and never resolved, we must still emit a synthetic
				# tool reply for it, or every subsequent request to OpenAI
				# will 400 with "did not have response messages: call_xxx".
				for tc in tc_rows:
					if tc.status in ("success", "error"):
						result_content = (tc.error if tc.status == "error" else tc.result) or ""
					elif tc.status == "cancelled":
						result_content = tc.error or "Cancelled by user before execution."
					else:
						result_content = (
							"Error: tool execution was interrupted and no "
							"result was recorded. Please retry the operation "
							"if needed."
						)
					messages.append(
						{
							"role": "tool",
							"tool_call_id": tc.call_id,
							"name": tc.tool_name,
							"content": result_content,
						}
					)
			elif row.role == "user":
				# For User messages, clear reasoning buffer if out of order
				pending_reasoning = []
				content = row.content or ""
				row_attachments = getattr(row, "attachments", None)
				if row_attachments and build_content_parts is not None:
					try:
						attachments = frappe.parse_json(row_attachments)
						content = build_content_parts(
							row.content or "",
							attachments,
							allow_images=allow_image_attachments,
						)
					except Exception:
						# Never let a bad attachment (unreadable file,
						# malformed stored JSON, etc.) break the whole
						# turn — fall back to plain text for this message
						# and log it so it's actually diagnosable.
						logging.getLogger(__name__).exception(
							"build_content_parts failed for message %s in session %s — "
							"sending as plain text instead.",
							getattr(row, "message_id", "?"),
							self.session_id,
						)
						content = row.content or ""
				messages.append({"role": "user", "content": content})
			else:
				# System messages (or any other role) — unchanged.
				pending_reasoning = []
				messages.append({"role": row.role, "content": row.content or ""})

		return messages

	# ── Mutators ─────────────────────────────────────────

	def set_system(self, text):
		self.system_prompt = text

	def _checkpoint(self):
		"""Persist whatever's accumulated in memory right now.

		Called after each completed unit of work (an assistant turn, a
		finished tool call) rather than relying solely on the one big
		save() at the end of Agent.run(). This is what makes a stop (or any
		hard kill) safe — everything up to the last completed step is
		already in the DB, so only the currently in-flight step is ever at
		risk of being lost, not the whole session.
		"""
		self.doc.last_active = now_datetime()
		self.doc.message_count = len(self.doc.messages)
		self.doc.tool_call_count = len(self.doc.tool_calls)
		self.doc.save(ignore_permissions=True)
		frappe.db.commit()

	def add_system_message(self, text, skill_name: str | None = None):
		"""Append a system-scoped message at this point in the conversation.

		Unlike set_system() — which sets the global session-level prompt that
		gets prepended as the very first message — this inserts a system
		message inline, right before the next user/assistant message.

		Used for per-turn skill injections: when a user types /skill-name,
		the skill's content is loaded and inserted here so the agent sees
		it as contextual instructions scoped to that specific request.

		Also used by Agent._inject_system_nudge() to steer a broken chain
		back on track without replacing the top-level system prompt.

		skill_name: pass the invoking skill's name (e.g. from the slash
		command) to stamp skill_invoked + skill_content_hash on the session.
		The hash lets eval scores be joined back to the exact skill content
		version that was active, so a later content edit doesn't silently
		get credited/blamed for an older run's score.
		"""
		msg_id = _gen_id()
		self.doc.append(
			"messages",
			{
				"message_id": msg_id,
				"role": "system",
				"content": text,
				"timestamp": now_datetime(),
			},
		)
		self._last_message_id = msg_id

		if skill_name:
			if not self.doc.skill_invoked:
				self.doc.skill_invoked = skill_name
			self.doc.skill_content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

	def add_user_message(self, text, attachments: list[dict[str, Any]] | None = None):
		"""Append a user turn. `text` is stored as plain text regardless of
		attachments — the multimodal content-parts array (image_url/file)
		is built lazily in get_messages(), once we know whether the
		resolved model for this run supports vision. This keeps the stored
		row provider-agnostic and avoids re-persisting base64 blobs.

		attachments: [{"file_name": ..., "file_url": ..., "mime_type": ...}, ...]
		as produced by the chat widget's upload_file step (verify.chat).
		"""
		if not self.doc.title:
			self.doc.title = (text or "")[:72]
		msg_id = _gen_id()
		self.doc.append(
			"messages",
			{
				"message_id": msg_id,
				"role": "user",
				"content": text,
				"attachments": json.dumps(attachments) if attachments else None,
				"timestamp": now_datetime(),
			},
		)
		self._last_message_id = msg_id
		self._emit("user", text)

	def add_assistant_message(self, message_obj, streamed=False, latency_ms=None):
		"""Persist an assistant turn (content, reasoning, tool calls, usage).

		Raises ChainBrokenError AFTER persisting the partial message if the
		provider signaled an unexpected termination (e.g. stopped mid-reasoning,
		stream ended without finish_reason). The caller can catch this to
		attempt recovery or surface the partial content.
		"""
		self._flush_reasoning()

		content = message_obj.get("content") or ""
		tool_calls = message_obj.get("tool_calls") or []
		reasoning_meta = message_obj.get("reasoning_meta")
		reasoning_text = message_obj.get("reasoning")
		chain_break = message_obj.get("chain_break")
		# Populated by OpenAIProvider.generate() — see openai_api.py. Handles
		# both Chat Completions (prompt_tokens/completion_tokens) and
		# Anthropic/Responses-style (input_tokens/output_tokens) usage shapes
		# so this layer stays provider-agnostic.
		usage = message_obj.get("usage") or {}
		model = message_obj.get("model")
		input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
		output_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
		cached_tokens = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
		reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
		turn_cost = _compute_cost(model, input_tokens, output_tokens, cached_tokens or 0)

		self._turn_index = getattr(self, "_turn_index", 0) + 1

		# If this call wasn't streamed, reasoning text never went through
		# emit_reasoning()/_flush_reasoning() above, so it would otherwise
		# be silently dropped. Persist it now as its own reasoning-role row
		# so UI/timeline reconstruction still works for non-streamed turns.
		if reasoning_text and not streamed:
			self.doc.append(
				"messages",
				{
					"message_id": _gen_id(),
					"role": "reasoning",
					"content": reasoning_text,
					"timestamp": now_datetime(),
				},
			)

		msg_id = _gen_id()
		self.doc.append(
			"messages",
			{
				"message_id": msg_id,
				"role": "assistant",
				"content": content,
				"is_error": bool(message_obj.get("is_error")),
				# Raw, provider-specific reasoning payload (reasoning_details,
				# signatures, etc.) — kept verbatim so it can be replayed back
				# correctly later. Requires a "reasoning_meta" Long Text/JSON
				# field on the Agent Message child table.
				"reasoning_meta": json.dumps(reasoning_meta) if reasoning_meta else None,
				# Store chain break info for debugging and analytics.
				"chain_break": json.dumps(chain_break) if chain_break else None,
				"turn_index": self._turn_index,
				"model": model,
				"input_tokens": input_tokens,
				"output_tokens": output_tokens,
				"cached_tokens": cached_tokens,
				"reasoning_tokens": reasoning_tokens,
				"latency_ms": latency_ms,
				"estimated_cost": turn_cost,
				"timestamp": now_datetime(),
			},
		)
		self._last_message_id = msg_id

		# Denormalize onto the session doc for cheap dashboard queries —
		# avoids a child-table aggregation just to plot cost/turns per session.
		if model and not self.doc.model:
			self.doc.model = model
		self.doc.total_input_tokens = (self.doc.total_input_tokens or 0) + input_tokens
		self.doc.total_output_tokens = (self.doc.total_output_tokens or 0) + output_tokens
		self.doc.turn_count = self._turn_index
		if turn_cost is not None:
			self.doc.estimated_cost = (self.doc.estimated_cost or 0) + turn_cost

		# Add tool call rows — with loop detection.
		for tc in tool_calls:
			fn = tc.get("function", {})
			# Keep the raw string for loop-detection fingerprinting (below)
			# and for whatever diagnostic value the exact malformed text
			# has, but store a JSON-safe version on the row itself so
			# get_messages() never has to repair it on every future read.
			args_str = fn.get("arguments") or "{}"
			stored_args_str = _safe_tool_arguments(args_str)

			# Detect and short-circuit tool loops.
			if self._detect_tool_loop(fn.get("name", ""), args_str):
				import logging

				logging.getLogger(__name__).warning(
					"Tool loop detected: %s called %d times consecutively with same args in session %s",
					fn.get("name", ""),
					self._max_repeated_calls,
					self.session_id,
				)
				self.doc.append(
					"tool_calls",
					{
						"call_id": tc.get("id") or _gen_id(),
						"parent_message": msg_id,
						"tool_name": fn.get("name", ""),
						"arguments": stored_args_str,
						"status": "error",
						"error": (
							"Error: Tool loop detected — the same tool was called "
							"repeatedly with identical arguments. Please try a "
							"different approach or provide your final answer with "
							"the information already available."
						),
						"started_at": now_datetime(),
						"completed_at": now_datetime(),
						"elapsed_ms": 0,
						"was_loop_strike": True,
					},
				)
				continue

			self.doc.append(
				"tool_calls",
				{
					"call_id": tc.get("id") or _gen_id(),
					"parent_message": msg_id,
					"tool_name": fn.get("name", ""),
					"arguments": stored_args_str,
					"status": "pending",
					"started_at": now_datetime(),
				},
			)

		if content and not streamed:
			self._emit("assistant", content)

		self._checkpoint()

		# Raise chain break error AFTER persisting, so the partial message
		# is safely in the DB for debugging and potential recovery.
		if chain_break:
			raise ChainBrokenError(chain_break.get("reason", "Unknown"), message_obj)

	# ── Streaming hooks ──────────────────────────────────

	def emit_token(self, delta):
		if not delta:
			return
		frappe.publish_realtime(
			event="agent_token",
			message={"session_id": self.session_id, "delta": delta},
			room=self.room,
		)

	def emit_reasoning(self, delta):
		if not delta:
			return
		self._reasoning_buffer += delta
		frappe.publish_realtime(
			event="agent_reasoning",
			message={"session_id": self.session_id, "delta": delta},
			room=self.room,
		)

	# ── Tool lifecycle ───────────────────────────────────

	def emit_tool_start(self, tool_call_id, tool_name, args):
		self._flush_reasoning()

		# Persist the transition pending → running.
		for tc in self.doc.tool_calls:
			if tc.call_id == tool_call_id and tc.status == "pending":
				tc.status = "running"
				tc.started_at = now_datetime()
				break

		self._publish_event(
			{
				"type": "tool_start",
				"tool": tool_name,
				"args": json.dumps(args) if isinstance(args, dict) else str(args),
				"call_id": tool_call_id,
			}
		)

	def add_tool_result(self, tool_call_id, name, content, elapsed_ms=None, was_loop_strike=False):
		is_error = isinstance(content, str) and content.startswith("Error:")
		now = now_datetime()

		for tc in self.doc.tool_calls:
			if tc.call_id != tool_call_id:
				continue

			tc.status = "error" if is_error else "success"
			tc.completed_at = now
			tc.was_loop_strike = was_loop_strike

			if is_error:
				tc.error = content
			else:
				tc.result = content

			if elapsed_ms is None and tc.started_at:
				elapsed_ms = int((now - tc.started_at).total_seconds() * 1000)
			tc.elapsed_ms = elapsed_ms
			break

		payload = {
			"type": "tool_done",
			"tool": name,
			"call_id": tool_call_id,
			"elapsed_ms": elapsed_ms,
		}
		payload["error" if is_error else "result"] = content[:500] if is_error else str(content)[:500]
		self._publish_event(payload)
		self._checkpoint()

	# ── Terminal events ──────────────────────────────────

	def emit_done(self, response):
		frappe.publish_realtime(
			event="agent_done",
			message={"session_id": self.session_id, "response": response},
			room=self.room,
		)

	def emit_error(self, error_text):
		frappe.publish_realtime(
			event="agent_error",
			message={"session_id": self.session_id, "response": error_text},
			room=self.room,
		)

	# ── Feedback & eval-adjacent fields ──────────────────

	def set_user_feedback(self, feedback: str, note: str | None = None):
		"""feedback: '👍' | '👎' | 'none'. Called from the Hermes frontend
		when a user reacts to a reply — the highest-signal, lowest-cost
		quality data you can collect, since it's real users rather than an
		LLM judge or manual review.
		"""
		if feedback not in ("👍", "👎", "none"):
			frappe.throw(f"Invalid feedback value: {feedback}")
		self.doc.user_feedback = feedback
		if note:
			self.doc.user_feedback_note = note
		self.doc.save(ignore_permissions=True)
		frappe.db.commit()

	def set_outcome(self, outcome: str):
		"""outcome: 'Success' | 'Partial' | 'Failure' | 'Unclear'. Distinct
		from ended_reason — ended_reason is the technical exit path
		(Completed/Error/LoopDetected/MaxTurnsError), outcome is a
		human/judge call on whether the user's actual goal was met.
		"""
		valid = {"Success", "Partial", "Failure", "Unclear"}
		if outcome not in valid:
			frappe.throw(f"Invalid outcome: {outcome}. Must be one of {valid}")
		self.doc.outcome = outcome
		self.doc.save(ignore_permissions=True)
		frappe.db.commit()

	@staticmethod
	def set_user_feedback_by_session_id(session_id: str, feedback: str, note: str | None = None):
		"""Lightweight path for the frontend's thumbs up/down handler —
		avoids reconstructing a full Conversation (and its message history)
		just to flip one field.
		"""
		if feedback not in ("👍", "👎", "none"):
			frappe.throw(f"Invalid feedback value: {feedback}")
		if not frappe.db.exists(SESSION_DOCTYPE, session_id):
			frappe.throw(f"No such session: {session_id}")
		updates = {"user_feedback": feedback}
		if note:
			updates["user_feedback_note"] = note
		frappe.db.set_value(SESSION_DOCTYPE, session_id, updates)
		frappe.db.commit()

	# ── Stop control ──────────────────────────────────────

	@staticmethod
	def request_stop(session_id: str, job_id: str | None = None):
		"""Stop button entry point. Does two things:

		1. Sets the cooperative Redis flag (unchanged) — belt-and-braces
		   for the (rare) case the hard-kill below can't reach the job
		   in time, e.g. it's still queued rather than executing yet.
		2. Immediately kills the RQ work-horse via job_id, the same
		   mechanism Desk's "Stop Job" button on the RQ Job list uses
		   (rq.command.send_stop_job_command). Unlike the cooperative
		   flag — which is only ever checked at loop boundaries (before
		   a new LLM turn, before a tool-call batch) and can therefore
		   sit for the full duration of an in-flight LLM/tool call before
		   it's noticed — this interrupts the work-horse process itself,
		   right now, regardless of what it's doing.

		Trade-off: because the process is killed rather than asked to
		exit, Agent.run()'s `finally: conversation.save(...)` does NOT
		reliably run afterwards. Callers of request_stop that also have
		DB access (see verify.stop_chat) should follow up with their own
		synchronous cleanup — marking the session ended, cancelling any
		"pending"/"running" tool_call rows — rather than assuming the
		killed process will do it.
		"""
		conn = get_redis_conn()
		conn.set(f"{_STOP_FLAG_PREFIX}{session_id}", "1", ex=_STOP_FLAG_TTL)
		if job_id:
			Conversation.hard_kill(job_id)

	@staticmethod
	def hard_kill(job_id: str) -> bool:
		"""Immediately interrupt the RQ work-horse running `job_id`, the
		same call Desk's RQ Job "Stop Job" button makes. Best-effort:
		returns False (never raises) if the job has already finished,
		was never dispatched to a worker, or Redis/RQ otherwise rejects
		the command — all of which are fine to just ignore here, since
		the cooperative flag set alongside this is still in place as a
		fallback for those cases.
		"""
		try:
			from rq.command import send_stop_job_command

			send_stop_job_command(get_redis_conn(), job_id)
			return True
		except Exception:
			import logging

			logging.getLogger(__name__).info(
				"hard_kill: could not stop job %s (already finished, not yet running, "
				"or not currently executing) — cooperative stop flag still applies",
				job_id,
			)
			return False

	@staticmethod
	def clear_stop_flag(session_id: str):
		get_redis_conn().delete(f"{_STOP_FLAG_PREFIX}{session_id}")

	def is_stop_requested(self) -> bool:
		"""Cooperative check — call at loop boundaries (before a new LLM
		turn, before dispatching a tool call), not per-token."""
		return bool(get_redis_conn().get(f"{_STOP_FLAG_PREFIX}{self.session_id}"))

	def cancel_pending_tool_calls(self, reason: str = "Cancelled by user before execution.") -> int:
		"""Give any still-"pending" tool_calls a terminal status instead of
		leaving them stuck forever.

		This matters for the specific race in Agent.run(): the assistant's
		tool_calls are persisted as "pending" (via add_assistant_message)
		*before* is_stop_requested() is checked a second time right before
		dispatch. If the stop lands in that window, those rows would
		otherwise sit as "pending" permanently — indistinguishable, to the
		anomaly detectors, from a worker crash or a genuinely abandoned
		call. Marking them "cancelled" here keeps that distinction honest:
		- get_last_incomplete_state / abandoned_pending only look at
		  "pending"/"running", so a "cancelled" row is correctly excluded
		  from both future retry-recovery and the abandoned_pending
		  detector.
		- get_messages() still emits a synthetic tool-role reply for
		  "cancelled" rows (same as it already does for pending/running),
		  so a resumed conversation stays valid for providers that require
		  a reply for every tool_call_id.

		Returns the number of rows cancelled.
		"""
		count = 0
		now = now_datetime()
		for tc in self.doc.tool_calls:
			if tc.status in ("pending", "running"):
				tc.status = "cancelled"
				tc.error = reason
				tc.completed_at = now
				if tc.started_at:
					tc.elapsed_ms = int((now - tc.started_at).total_seconds() * 1000)
				count += 1
		if count:
			self._checkpoint()
		return count

	# ── Persistence ──────────────────────────────────────

	def save(self, ended_reason=None):
		self._flush_reasoning()
		if ended_reason:
			self.doc.ended_reason = ended_reason
		self._checkpoint()

	# ── Recovery helpers ─────────────────────────────────

	def get_last_incomplete_state(self) -> dict[str, Any]:
		"""Analyze the conversation to find any incomplete state that needs
		recovery (e.g. after a crash or interrupted turn).

		Returns a dict with:
		  - has_pending_tool_calls: bool — True if any tool calls are stuck
		    in "pending" or "running" status.
		  - pending_call_ids: list[str] — IDs of the stuck tool calls.
		  - last_assistant_message_id: Optional[str] — The most recent
		    assistant message (may be None if the session has no turns yet).
		  - last_assistant_had_tool_calls: bool — True if the last assistant
		    message has unresolved (pending/running) tool calls.
		"""
		pending_calls: list[str] = []
		last_assistant_id: str | None = None
		last_assistant_had_tools = False

		for row in reversed(self.doc.messages):
			if row.role == "assistant":
				last_assistant_id = row.message_id
				# Check if any tool calls from this assistant message are
				# still pending or running (never got a result).
				last_assistant_had_tools = any(
					tc.parent_message == row.message_id and tc.status in ("pending", "running")
					for tc in self.doc.tool_calls
				)
				break

		# Collect all pending tool calls regardless of parent.
		for tc in self.doc.tool_calls:
			if tc.status == "pending":
				pending_calls.append(tc.call_id)

		return {
			"has_pending_tool_calls": bool(pending_calls),
			"pending_call_ids": pending_calls,
			"last_assistant_message_id": last_assistant_id,
			"last_assistant_had_tool_calls": last_assistant_had_tools,
		}

	def can_retry_from_last_state(self) -> bool:
		"""Check if it's safe to retry from the last state.

		It's safe to retry if:
		- There are pending tool calls (we can inject error results so the
		  model knows to retry or try a different approach).
		- The last assistant message had unresolved tool calls.
		"""
		state = self.get_last_incomplete_state()
		return state["has_pending_tool_calls"] or state["last_assistant_had_tool_calls"]

	def inject_recovery_tool_results(self) -> int:
		"""Inject error results for any pending tool calls so the model can
		continue on the next turn instead of getting stuck waiting for
		results that will never arrive.

		Returns the number of tool results injected.
		"""
		state = self.get_last_incomplete_state()
		if not state["has_pending_tool_calls"]:
			return 0

		count = 0
		for tc in self.doc.tool_calls:
			if tc.status == "pending":
				self.add_tool_result(
					tool_call_id=tc.call_id,
					name=tc.tool_name,
					content=(
						"Error: Previous execution was interrupted and no "
						"result was recorded. Please retry the operation "
						"if needed."
					),
					was_loop_strike=False,
				)
				count += 1

		return count

	# ── Private ──────────────────────────────────────────

	def _flush_reasoning(self):
		if not self._reasoning_buffer:
			return
		self.doc.append(
			"messages",
			{
				"message_id": _gen_id(),
				"role": "reasoning",
				"content": self._reasoning_buffer,
				"timestamp": now_datetime(),
			},
		)
		self._reasoning_buffer = ""

	def _emit(self, role, content, **kwargs):
		if not content:
			return
		frappe.publish_realtime(
			event="agent_message",
			message={"session_id": self.session_id, "role": role, "content": content, **kwargs},
			room=self.room,
		)

	def _publish_event(self, payload):
		frappe.publish_realtime(
			event="agent_event",
			message={"session_id": self.session_id, **payload},
			room=self.room,
		)