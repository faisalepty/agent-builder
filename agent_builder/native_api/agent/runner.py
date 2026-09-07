# agent_builder/native_api/agent/runner.py
"""Unified headless agent runner.

Single entry point for: triggers, workflow steps, manual agent runs.
All paths converge here — chat endpoint (verify.chat) is the only
separate interactive path, but it also uses Agent.run underneath.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional
import frappe

from agent_builder.native_api.agent.agent import Agent, MaxTurnsError, StoppedByUser
from agent_builder.native_api.agent.conversation import ChainBrokenError, ClarificationPending, Conversation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionProvenance:
	"""How/why this agent session was started."""

	trigger_type: (
		str  # "Chat" | "DocType Event" | "Scheduled" | "Workflow Step" | "Manual" | "MCP" | "Webhook"
	)
	trigger_source: str  # e.g. "Sales Order", "daily-cron", "AR Collection Workflow / verify-payments"
	trigger_ref: str = ""  # e.g. "SO-0042", "", "step-3"


@dataclass
class RunResult:
	"""Result of a headless agent run."""

	session_id: str
	response: str
	ended_reason: str  # Completed | MaxTurnsError | LoopDetected | Error | EndedByUser | ChainBroken
	chain_break: dict | None = None


async def _run_agent_loop(
	conversation: Conversation,
	agent: Agent,
	stream_callbacks: bool = False,
	on_token=None,
	on_reasoning=None,
) -> RunResult:
	"""Core loop — runs Agent.run with proper exception handling.

	Returns RunResult with outcome. Never raises.
	"""
	chain_break_info: dict | None = None
	ended_reason = "Error"
	response = ""
	token_cb = on_token if on_token is not None else (conversation.emit_token if stream_callbacks else None)
	reasoning_cb = (
		on_reasoning
		if on_reasoning is not None
		else (conversation.emit_reasoning if stream_callbacks else None)
	)

	try:
		response = await agent.run(
			conversation,
			on_token=token_cb,
			on_reasoning=reasoning_cb,
		)
		ended_reason = "Completed"
		
	

	except MaxTurnsError as e:
		frappe.log_error(f"Agent max turns exceeded: {e}")
		ended_reason = "MaxTurnsError"
		response = ""

	except StoppedByUser:
		frappe.log_error("Agent stopped by user")
		ended_reason = "EndedByUser"
		response = ""

	except ClarificationPending:
		# Deliberate, expected pause — not an error and not worth a log
		# entry (unlike the other branches here, which all represent
		# something going wrong). request_clarification already published
		# agent_clarification_request to the frontend; the run resumes
		# later via verify.resume_agent_chat, not from here.
		ended_reason = "AwaitingClarification"
		response = ""

	except ChainBrokenError as e:
		frappe.log_error(f"Chain broken: {e.reason}")
		ended_reason = "ChainBroken"
		chain_break_info = e.partial_message.get("chain_break")
		# The partial message is already persisted by Conversation.add_assistant_message
		# Use whatever content was produced as the response
		response = e.partial_message.get("content", "")

	except Exception:
		frappe.log_error("Agent run failed", frappe.get_traceback())
		ended_reason = "Error"
		response = ""

	finally:
		conversation.save(ended_reason=ended_reason)
	

	return RunResult(
		session_id=conversation.session_id,
		response=response,
		ended_reason=ended_reason,
		chain_break=chain_break_info,
	)


def create_conversation(
	user: str = "Administrator",
	session_id: str | None = None,
	agent_name: str | None = None,
	provenance: SessionProvenance | None = None,
) -> Conversation:
	"""Create a Conversation and stamp provenance/agent metadata once."""
	conversation = Conversation(session_id=session_id, user=user)
	if agent_name is not None:
		conversation.doc.agent_name = agent_name
	if provenance is not None:
		conversation.doc.trigger_type = provenance.trigger_type
		conversation.doc.trigger_source = provenance.trigger_source
		conversation.doc.trigger_ref = provenance.trigger_ref
	return conversation


def run_agent_conversation(
	conversation: Conversation,
	agent_name: str | None = None,
	stream_callbacks: bool = False,
	on_token=None,
	on_reasoning=None,
	model_override: str | None = None,
	reasoning_effort: str | None = None,
) -> RunResult:
	"""Run an existing Conversation through the shared agent loop.

	model_override / reasoning_effort: per-call overrides forwarded to
	Agent — see Agent.__init__ for precedence rules.
	"""
	agent = Agent(agent_name=agent_name, model_override=model_override, reasoning_effort=reasoning_effort)
	return asyncio.run(
		_run_agent_loop(
			conversation,
			agent,
			stream_callbacks=stream_callbacks,
			on_token=on_token,
			on_reasoning=on_reasoning,
		)
	)


def run_headless_agent(
	agent_name: str,
	input_message: str,
	provenance: SessionProvenance,
	user: str = "Administrator",
	session_id: str | None = None,
	skill_injection: str | None = None,
	model_override: str | None = None,
	reasoning_effort: str | None = None,
	attachments: list[dict] | None = None,
) -> RunResult:
	"""Run a single agent headlessly (no streaming callbacks).

	This is the canonical way to run an agent outside the chat widget.
	Creates a Conversation, stamps provenance, runs the agent loop,
	returns the final response and session metadata.

	NOTE: wraps the loop in asyncio.run() and therefore must only be
	called from *synchronous* code with no event loop already running
	(e.g. a background job's top-level function, like trigger.py's
	run_triggered_agent). Calling it from inside an already-running loop
	(e.g. a tool executed mid Agent.run(), such as delegate_task) raises
	"asyncio.run() cannot be called from a running event loop" — use
	run_headless_agent_async for that case instead.

	Args:
	    agent_name: Name of Agent Definition record.
	    input_message: First user message (already rendered from template).
	    provenance: SessionProvenance — why this run happened.
	    user: Frappe user to run as (for permissions).
	    session_id: Optional existing session to continue.
	    skill_injection: Optional skill content to inject as system message.
	    model_override: explicit model id for this run — see Agent.__init__.
	    reasoning_effort: explicit reasoning effort for this run ("none" to
	        disable, or a provider-valid effort string) — see Agent.__init__.
	    attachments: optional [{"file_name", "file_url", "mime_type"}, ...]
	        for this user turn — see Conversation.add_user_message. Whether
	        images in here actually reach the model as vision content
	        depends on the resolved model's Model Pricing.supports_vision;
	        PDFs are always sent (OpenRouter parses them server-side).

	Returns:
	    RunResult with session_id, response, ended_reason.
	"""
	conversation = create_conversation(
		user=user,
		session_id=session_id,
		agent_name=agent_name,
		provenance=provenance,
	)
	if skill_injection:
		conversation.add_system_message(skill_injection)
	conversation.add_user_message(input_message, attachments=attachments)
	return run_agent_conversation(
		conversation,
		agent_name=agent_name,
		stream_callbacks=False,
		model_override=model_override,
		reasoning_effort=reasoning_effort,
	)


async def run_headless_agent_async(
	agent_name: str,
	input_message: str,
	provenance: SessionProvenance,
	user: str = "Administrator",
	session_id: str | None = None,
	skill_injection: str | None = None,
	model_override: str | None = None,
	reasoning_effort: str | None = None,
	attachments: list[dict] | None = None,
) -> RunResult:
	"""Same as run_headless_agent, but awaited directly instead of wrapping
	in asyncio.run() — safe to call from code already running inside an
	event loop, i.e. a tool dispatched mid Agent.run() (delegate_task).
	This is the version delegate_task must use; the sync version would
	nest asyncio.run() inside the parent's already-running loop and crash.

	model_override / reasoning_effort: same per-call overrides as
	run_headless_agent — see Agent.__init__ for precedence rules.
	attachments: see run_headless_agent.
	"""
	conversation = create_conversation(
		user=user,
		session_id=session_id,
		agent_name=agent_name,
		provenance=provenance,
	)
	if skill_injection:
		conversation.add_system_message(skill_injection)
	conversation.add_user_message(input_message, attachments=attachments)
	agent = Agent(agent_name=agent_name, model_override=model_override, reasoning_effort=reasoning_effort)
	return await _run_agent_loop(conversation, agent, stream_callbacks=False)


def run_headless_agent_streaming(
	agent_name: str,
	input_message: str,
	provenance: SessionProvenance,
	user: str = "Administrator",
	session_id: str | None = None,
	on_token=None,
	on_reasoning=None,
	skill_injection: str | None = None,
	model_override: str | None = None,
	reasoning_effort: str | None = None,
	attachments: list[dict] | None = None,
) -> RunResult:
	"""Run a single agent headlessly WITH streaming callbacks.

	Used by the chat widget (verify.py) and any caller that wants
	real-time token/reasoning events. Core loop is identical; only
	the streaming callbacks differ.

	model_override / reasoning_effort: per-call overrides — e.g. a
	"thinking mode" toggle or model picker in the chat widget passes
	these straight through from the frontend request. See Agent.__init__
	for precedence against the Agent Definition and Agent Setup defaults.
	attachments: see run_headless_agent. The chat widget passes through
	whatever it received from verify.chat()'s own `attachments` param.
	"""
	conversation = create_conversation(
		user=user,
		session_id=session_id,
		agent_name=agent_name,
		provenance=provenance,
	)
	if skill_injection:
		conversation.add_system_message(skill_injection)
	conversation.add_user_message(input_message, attachments=attachments)
	
	return run_agent_conversation(
		conversation,
		agent_name=agent_name,
		stream_callbacks=True,
		on_token=on_token,
		on_reasoning=on_reasoning,
		model_override=model_override,
		reasoning_effort=reasoning_effort,
	)