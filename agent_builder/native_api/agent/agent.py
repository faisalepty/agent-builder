# agent_builder/native_api/agent/agent.py
import asyncio
import json
import logging
import random
import time
from collections.abc import Callable
from typing import Any, List, Optional, Tuple

import frappe

from agent_builder.native_api.agent.conversation import (
	CLARIFICATION_PENDING_KEY,
	ClarificationPending,
	Conversation,
	StoppedByUser,
	current_delegate_depth,
	current_session_id,
)
from agent_builder.native_api.agent.setup import (
	get_agent_definition,
	get_agent_system_prompt,
	get_system_prompt,
	get_tool_registry,
	get_tool_schemas_for,
)
from agent_builder.native_api.providers.openai_api import OpenAIProvider
from agent_builder.native_api.tools.executor import ToolExecutor

logger = logging.getLogger(__name__)

# current_session_id / current_delegate_depth / CLARIFICATION_PENDING_KEY
# live in conversation.py, not here — this module used to define the two
# ContextVars directly, but agent.py needing CLARIFICATION_PENDING_KEY from
# the tool module while the tool module needed current_session_id from
# here is a circular import. conversation.py is already a one-way
# dependency of this file (agent.py imports Conversation/StoppedByUser
# from it, never the reverse), so putting shared, tool-visible state there
# instead adds nothing new to the dependency graph — no extra module
# needed. Re-exported at this module's top level via the import above, so
# `from agent.agent import current_session_id` still works for any
# existing tool that imports it that way (e.g. delegate_task) — nothing
# else needs to change.


class MaxTurnsError(Exception):
	pass


class Agent:
	"""
	Standalone Agent.

	Handles its own tool loading, system prompt generation, and provider setup
	internally via setup.py. The caller only needs to provide the model name.

	Supports parallel tool calling: when the model returns multiple tool calls
	in a single response, they are executed concurrently for improved performance.
	"""

	def __init__(
		self,
		agent_name: str | None = None,
		max_turns: int | None = None,
		max_retries: int = 2,
		max_context_chars: int = 1000000,
		model_override: str | None = None,
		reasoning_effort: str | None = None,
	):
		"""
		agent_name: name of an ``Agent Definition`` record (Agent Builder).
		    When given, the agent's instructions are layered onto the shared
		    identity/style scaffold, its tool list is narrowed per its
		    tool_mode/allowed_tools, and its own model/max_turns are used
		    unless explicitly overridden. When omitted, behaves exactly as
		    before (the hardcoded default Omnis agent) — existing callers
		    (the chat widget) are unaffected.
		model_override: explicit model id for this run, taking precedence
		    over the Agent Definition's own `model` field, which itself
		    takes precedence over Agent Setup's saved default. Lets a
		    single call site (e.g. a "thinking mode" toggle in the chat
		    widget, or a workflow step wanting a specific model) pick a
		    model without editing the Agent Definition or Agent Setup.
		reasoning_effort: explicit reasoning effort for this run — same
		    precedence idea, forwarded to OpenAIProvider as a tri-state
		    override (None = use Agent Setup default, "none" = explicitly
		    disable, any other value = use it). This is the "enable
		    thinking" knob.
		"""
		self.agent_name = agent_name
		agent_def = get_agent_definition(agent_name) if agent_name else None

		# 1. Bootstrap internal dependencies via setup.py, scoped to this agent
		self.registry = get_tool_registry()
		self.system_prompt = get_agent_system_prompt(agent_name)
		self.available_tool_schemas = get_tool_schemas_for(agent_name)

		# 2. Resolve model: explicit override > Agent Definition's model >
		# OpenAIProvider's own Agent Setup fallback (leave as None to let
		# OpenAIProvider read Agent Setup directly, same as before).
		resolved_model = model_override or (agent_def.get("model") if agent_def else None)

		# 3. Initialize provider and executor
		self.provider = OpenAIProvider(
			model_override=resolved_model,
			reasoning_effort_override=reasoning_effort,
		)
		self.executor = ToolExecutor(self.registry)

		# Whether this run's resolved model advertises vision support —
		# looked up post-resolution (self.provider.model, not
		# resolved_model) so it reflects whatever OpenAIProvider actually
		# settled on, including its own Agent Setup fallback when neither
		# model_override nor the Agent Definition supplied one. Passed to
		# Conversation.get_messages() so image attachments are only
		# inlined for models that can actually use them — see
		# agent.attachments.build_content_parts.
		#
		# Defensive: this is a plain lookup with no reason to fail under
		# normal operation, but it must never be able to take an entire
		# run down (e.g. Model Pricing not yet migrated with this field
		# on some sites) — fail to "no vision" rather than erroring, same
		# fail-closed default the frontend uses (see chat_ui.js's
		# _attachEnabled).
		try:
			self.supports_vision = bool(
				frappe.db.get_value("Model Pricing", self.provider.model, "supports_vision")
			)
		except Exception:
			frappe.log_error(
				f"supports_vision lookup failed for model {self.provider.model} — defaulting to False",
				frappe.get_traceback(),
			)
			self.supports_vision = False

		# 3. Store config — explicit args win, then Agent Definition, then default
		self.max_turns = max_turns or (agent_def["max_turns"] if agent_def else 40)
		self.max_retries = max_retries
		self.max_context_chars = max_context_chars

	async def run(
		self,
		conversation: Conversation,
		on_token: Callable[[str], None] | None = None,
		on_reasoning: Callable[[str], None] | None = None,
	) -> str:
		
		available_tools = self.available_tool_schemas
		conversation.set_system(self.system_prompt)
		
		# Defensive reset: clear_stop_flag() is only ever called when a stop
		# is actually consumed below, and the Redis flag carries a 600s TTL.
		# If a *previous* run on this same session_id was stopped and the
		# caller starts a new run within that TTL window, is_stop_requested()
		# would otherwise read the stale flag as True on the very first
		# check and kill this brand-new run before it does anything — which
		# is exactly the "EndedByUser with pending tool calls the user never
		# actually stopped" anomaly. A fresh run can't legitimately have a
		# stop request queued against it yet, so it's always safe to clear
		# here before the loop starts.
		conversation.clear_stop_flag(conversation.session_id)
		

		# Set once per run — copied automatically into any child task this
		# coroutine spawns (e.g. the tool-call tasks in
		# _execute_tool_calls_parallel's asyncio.gather), so delegate_task
		# can read it no matter which parallel branch it's called from.
		current_session_id.set(conversation.session_id)
		last_fp: tuple[str, str] | None = None
		loop_strikes = 0
		turns = 0
		ended_reason = "Completed"
		
		

		try:
			while turns < self.max_turns:
				
				turns += 1

				if conversation.is_stop_requested():
					ended_reason = "EndedByUser"
					raise StoppedByUser()

				messages = self._trim_context(
					conversation.get_messages(
						reasoning_replay=self.provider.replay_reasoning,
						allow_image_attachments=self.supports_vision,
					)
				)
				t0 = time.monotonic()
				response, tool_calls = await self._retry_llm(
					messages, available_tools, on_token=on_token, on_reasoning=on_reasoning
				)
				latency_ms = int((time.monotonic() - t0) * 1000)
				conversation.add_assistant_message(
					response,
					streamed=on_token is not None or on_reasoning is not None,
					latency_ms=latency_ms,
				)

				if not tool_calls:
					return response.get("content", "")

				# Loop detection: check the first tool call pattern
				fp = (tool_calls[0].function.name, tool_calls[0].function.arguments)
				is_loop_strike = fp == last_fp
				if is_loop_strike:
					loop_strikes += 1
					if loop_strikes >= 3:
						ended_reason = "LoopDetected"
						raise MaxTurnsError(f"Stuck calling '{fp[0]}'")
				else:
					last_fp = fp
					loop_strikes = 0

				# Execute all tool calls in parallel. Only the fingerprinted
				# call (tool_calls[0]) is flagged as the loop strike here —
				# the other calls in this same batch aren't what's being
				# detected as stuck.
				if conversation.is_stop_requested():
					ended_reason = "EndedByUser"
					raise StoppedByUser()

				await self._execute_tool_calls_parallel(
					tool_calls, conversation, is_loop_strike=is_loop_strike
				)

			ended_reason = "MaxTurnsError"
			raise MaxTurnsError(f"Exceeded {self.max_turns}-turn budget.")

		except MaxTurnsError:
			raise
		except ClarificationPending:
			# Orderly pause, not an interruption — nothing to cancel or
			# clean up. Exactly one tool_call was already left in
			# "awaiting_clarification" by pause_for_clarification() before
			# this was raised. Just record why the run ended and let the
			# frontend's already-rendered question card do its job.
			ended_reason = "AwaitingClarification"
			raise
		except StoppedByUser:
			# The tool_calls for the turn that was in flight (if any) were
			# already checkpointed as "pending" by add_assistant_message
			# before this stop was detected. Give them a terminal
			# "cancelled" status now instead of leaving them "pending"
			# forever — that's what let the abandoned_pending detector
			# mistake an intentional, clean stop for a crash/abandonment.
			conversation.cancel_pending_tool_calls(
				reason="Cancelled: the user stopped the run before this tool call executed."
			)
			# Consume the flag now (not just defensively at the top of the
			# next run) so an immediate retry/continue on this same session
			# isn't blocked, and so is_stop_requested() can't be read as
			# True again by anything else still polling it.
			conversation.clear_stop_flag(conversation.session_id)
			raise
		except Exception:
			ended_reason = "Error"
			raise
		finally:
			conversation.save(ended_reason=ended_reason)
			# Non-blocking post-run anomaly analysis
			try:
				from frappe.utils.background_jobs import enqueue

				enqueue(
					"agent_builder.native_api.anomaly.analyzer.analyze_session",
					session_id=conversation.session_id,
					queue="short",
					timeout=300,
				)
			except Exception:
				# Never let analysis failure affect the agent response
				frappe.log_error(
					f"Failed to enqueue post-run anomaly analysis for {conversation.session_id}",
					frappe.get_traceback(),
				)

	async def _execute_tool_calls_parallel(
		self,
		tool_calls: list[Any],
		conversation: Conversation,
		is_loop_strike: bool = False,
	) -> None:
		"""
		Execute multiple tool calls concurrently using asyncio.gather.

		This provides significant performance improvements when the model
		returns multiple independent tool calls (e.g., fetching data from
		multiple sources simultaneously).
		"""
		pending_pause: dict[str, str] = {}  # holds at most one — first pause wins

		async def execute_single_tool(tc: Any, flag_as_strike: bool) -> None:
			"""Execute a single tool call with proper event emission."""
			name = tc.function.name
			try:
				args = json.loads(tc.function.arguments)
			except json.JSONDecodeError:
				args = tc.function.arguments

			# Emit tool start event
			conversation.emit_tool_start(tc.id, name, args)

			# Execute the tool and measure time
			t0 = time.monotonic()
			result = await self.executor._dispatch(name, tc.function.arguments)
			elapsed_ms = int((time.monotonic() - t0) * 1000)

			# request_clarification doesn't return a normal result — it
			# returns a pause marker (see request_clarification.py).
			# Detect it here rather than inside the tool itself: tool
			# dispatch is a stateless request/response call by convention
			# (see workflow_tools/human_approval.py's docstring), so the
			# actual state transition belongs at this level.
			#
			# Deliberately NOT raised here. gather() re-raises the moment
			# any one task raises, without waiting for the others — so if
			# request_clarification (no DB I/O before its own write) wins
			# the race against a slower sibling tool call still mid-flight
			# in this same batch, that sibling would still be holding a
			# reference to this same conversation.doc and could still be
			# mid-add_tool_result()/save() after we've already moved on.
			# Two writers, same document, overlapping — that's exactly
			# what produces a TimestampMismatchError. Recording the pause
			# and only raising after every task in this gather has
			# actually finished (see below) guarantees nothing else is
			# still writing to conversation.doc when we act on it.
			pause = self._detect_clarification_pause(result)
			if pause:
				if "clarification_id" in pending_pause:
					# A second clarification in the same batch — only one
					# pause can be acted on per turn. Resolve this one as
					# an ordinary (skipped) result instead of leaving its
					# tool_call row stuck in "running" forever with
					# nothing ever calling add_tool_result on it.
					conversation.add_tool_result(
						tc.id,
						name,
						"Skipped: another clarification is already pending this turn. "
						"Ask this question again after the first one is answered.",
						elapsed_ms=elapsed_ms,
						was_loop_strike=False,
					)
					return
				pending_pause["clarification_id"] = pause["clarification_id"]
				pending_pause["tool_call_id"] = tc.id
				return

			# Add result to conversation. Only the fingerprinted call (index 0,
			# the one run.py's loop-detection actually matched against
			# last_fp) is marked was_loop_strike=True.
			conversation.add_tool_result(
				tc.id, name, result, elapsed_ms=elapsed_ms, was_loop_strike=flag_as_strike
			)

		# Execute all tool calls concurrently — gather() with its default
		# return_exceptions=False is safe here specifically because
		# nothing inside execute_single_tool raises anymore for the pause
		# case; it always returns normally, so gather always waits for
		# every task before this line continues.
		await asyncio.gather(
			*[execute_single_tool(tc, is_loop_strike and idx == 0) for idx, tc in enumerate(tool_calls)]
		)

		if pending_pause:
			# Safe now: every tool call in this batch — including any
			# slower sibling of the one that paused — has already
			# finished its own add_tool_result()/save(). This is the only
			# writer left standing.
			conversation.pause_for_clarification(
				tool_call_id=pending_pause["tool_call_id"],
				clarification_id=pending_pause["clarification_id"],
			)

	@staticmethod
	def _detect_clarification_pause(result: Any) -> dict | None:
		"""result is whatever executor._dispatch returned — normally a
		plain string, but request_clarification returns a JSON string
		carrying CLARIFICATION_PENDING_KEY. Anything that isn't exactly
		that shape (including ordinary tool output that merely happens to
		look JSON-ish) is treated as a normal result — only an exact,
		well-formed marker triggers the pause.
		"""
		if not isinstance(result, str) or not result.startswith("{"):
			return None
		try:
			parsed = json.loads(result)
		except Exception:
			return None
		if not isinstance(parsed, dict) or not parsed.get(CLARIFICATION_PENDING_KEY):
			return None
		if not parsed.get("clarification_id"):
			return None
		return parsed

	async def _retry_llm(self, messages, tools, on_token=None, on_reasoning=None):
		last_err = None
		for attempt in range(self.max_retries + 1):
			try:
				return await self.provider.generate(
					messages=messages,
					tools=tools or None,
					on_token=on_token,
					on_reasoning=on_reasoning,
				)
			except Exception as e:
				last_err = e
				if attempt < self.max_retries:
					await asyncio.sleep(min(2**attempt, 8) + random.uniform(0, 1))
		raise last_err

	@staticmethod
	def _content_char_len(content) -> int:
		"""Approximate char length of a message's `content`.

		Usually a plain string, but user turns with attachments carry a
		content-parts list (see Conversation.get_messages /
		agent.attachments.build_content_parts). Base64 image/file bytes
		there don't map to text-context tokens the way string length
		does for the rest of this heuristic, so they're excluded — only
		the text part counts. This keeps _trim_context's budget about
		actual conversation text, not attachment payload size.
		"""
		if isinstance(content, str):
			return len(content)
		if isinstance(content, list):
			return sum(len(p.get("text", "")) for p in content if isinstance(p, dict) and p.get("type") == "text")
		return 0

	def _trim_context(self, messages):
		total_chars = sum(self._content_char_len(m.get("content", "")) for m in messages)
		if total_chars <= self.max_context_chars:
			return messages

		has_system = messages and messages[0]["role"] == "system"
		kept = [messages[0]] if has_system else []
		limit = self.max_context_chars

		for msg in reversed(messages[1:] if has_system else messages):
			limit -= self._content_char_len(msg.get("content", ""))
			if limit < 0:
				break
			kept.insert(1 if has_system else 0, msg)

		return kept