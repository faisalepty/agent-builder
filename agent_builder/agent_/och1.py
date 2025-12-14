# orchestrator_v2.py
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from .ai_client import Client  # your wrapper
from .tools_plugin import agent_tools as TOOL_DEFS
from .tools import (
    tool_validate_payload,
    tool_agent_create,
    tool_doctype_exists,
    tool_role_exists,
)

# Standardized tool map - tool name -> callable
TOOL_MAP = {
    "tool_validate_payload": tool_validate_payload,
    "tool_agent_create": tool_agent_create,
    "tool_doctype_exists": tool_doctype_exists,
    "tool_role_exists": tool_role_exists,
}


def extract_json_from_text(text: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    Try to extract JSON from text returned by LLM. Return (dict or None, raw_text).
    Attempts:
      1. direct json.loads(text)
      2. find first ```json ... ``` block
      3. find first ``` ... ``` block
      4. fallback: try to find {...} substring and json.loads
    """
    if not text:
        return None, text

    raw = text.strip()
    # 1. direct
    try:
        return json.loads(raw), raw
    except Exception:
        pass

    # 2. fenced blocks
    blocks = re.findall(r"```(?:json)?\s*(.*?)```", raw, flags=re.S)
    for b in blocks:
        try:
            return json.loads(b.strip()), raw
        except Exception:
            continue

    # 3. find first {...} substring (balanced braces)
    # rudimentary but often helpful
    start = raw.find("{")
    if start != -1:
        # attempt to find matching brace - simple incremental parse
        cnt = 0
        for i in range(start, len(raw)):
            if raw[i] == "{":
                cnt += 1
            elif raw[i] == "}":
                cnt -= 1
                if cnt == 0:
                    candidate = raw[start:i+1]
                    try:
                        return json.loads(candidate), raw
                    except Exception:
                        break

    return None, raw


class OrchestratorV2:
    def __init__(self,
                 client=Client,
                 tool_defs: list = TOOL_DEFS,
                 tool_map: dict = TOOL_MAP,
                 model: str = "x-ai/grok-4.1-fast:free",
                 max_turns: int = 6,
                 max_retries: int = 2,
                 temperature: float = 0.2):
        self.client = client
        self.tool_defs = tool_defs
        self.tool_map = tool_map
        self.model = model
        self.max_turns = max_turns
        self.max_retries = max_retries
        self.temperature = temperature

    # ---------- Phase 1 ----------
    def generate_payload(self, user_prompt: str) -> Tuple[Optional[dict], str]:
        system = (
            "You are an expert Frappe/ERPNext developer. Generate STRICT JSON only (no prose). "
            "The JSON should be a valid DocType payload with keys: doctype='DocType', name, module, custom, fields, permissions, autoname (if needed)."
            " If you cannot produce valid JSON, return an error object as JSON: {\"status\":\"error\",\"message\":\"...\"}."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        msg = resp.choices[0].message
        raw = getattr(msg, "content", "") or ""
        payload, raw = extract_json_from_text(raw)
        return payload, raw

    # ---------- tool execution ----------
    def _execute_tool_calls(self, msg) -> Tuple[List[dict], List[dict]]:
        """
        Execute any tool calls present in `msg` (LLM assistant message).
        Returns:
          - tool_messages: list of dict {role:function, tool_call_id, content} to append to conversation
          - executions: list of execution metadata for logging
        """
        tool_calls = getattr(msg, "tool_calls", None) or []
        tool_messages = []
        executions = []
        for call in tool_calls:
            fname = call.function.name
            raw_args = call.function.arguments or "{}"
            try:
                args = json.loads(raw_args)
            except Exception:
                try:
                    args = eval(raw_args)  # trusted env fallback only
                except Exception:
                    args = {}

            tool_fn = self.tool_map.get(fname)
            if not tool_fn:
                result = {
                    "status": "tool_error",
                    "message": f"Unknown tool: {fname}",
                    "errors": [f"Unknown tool: {fname}"]
                }
            else:
                try:
                    result = tool_fn(**args)
                    # ensure result follows standard schema
                    if not isinstance(result, dict):
                        result = {"status": "ok", "result": result}
                except Exception as e:
                    result = {
                        "status": "tool_error",
                        "message": str(e),
                        "errors": [str(e)]
                    }

            # mark error flag
            is_error = result.get("status") in ("error", "tool_error")
            tool_msg_content = json.dumps(result)

            # create the message that we append to messages to return to LLM
            # we append as role "function" with tool_call_id to mimic function responses
            tool_message = {
                "role": "function",
                "tool_call_id": call.id,
                "name": fname,
                "content": tool_msg_content,
                "is_error": is_error
            }

            tool_messages.append(tool_message)
            executions.append({"tool": fname, "args": args, "result": result})
        return tool_messages, executions

    # ---------- Generic tool loop runner ----------
    def _run_tool_loop(self,
                       system_prompt: str,
                       user_content: str,
                       allowed_tools: list,
                       context_messages: Optional[List[dict]] = None,
                       max_turns: Optional[int] = None) -> dict:
        """
        Runs a tool-enabled loop with the LLM:
          - builds a fresh message list with system_prompt + context_messages (non-system)
          - sends to LLM; if assistant makes tool calls, execute them and append function messages; repeat until assistant produces no tool_calls or max_turns.
        Returns structured dict:
          {status: 'final'|'error', assistant: "<text>", assistant_obj: msg, tool_executions: [...], messages: [...]}
        """
        if max_turns is None:
            max_turns = self.max_turns

        # fresh messages for this phase
        messages = [{"role": "system", "content": system_prompt}]
        if context_messages:
            for m in context_messages:
                # copy only non-system messages to avoid re-adding system prompts
                if m.get("role") != "system":
                    messages.append(m)
        messages.append({"role": "user", "content": user_content})

        tool_executions = []
        assistant_history = []

        for turn in range(max_turns):
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=allowed_tools,
                tool_choice="auto",
                temperature=self.temperature,
            )

            msg = resp.choices[0].message
            assistant_history.append(msg)

            # if no tool calls => final assistant output
            if not getattr(msg, "tool_calls", None):
                assistant_text = getattr(msg, "content", "") or ""
                return {
                    "status": "final",
                    "assistant": assistant_text,
                    "assistant_message_obj": msg,
                    "tool_executions": tool_executions,
                    "messages": messages + [{"role": "assistant", "content": assistant_text}],
                }

            # else execute tool calls
            tool_msgs, executions = self._execute_tool_calls(msg)
            tool_executions.extend(executions)

            # append tool/function messages into conversation (so LLM sees results)
            for tm in tool_msgs:
                # only append function messages content (we use the function role as LLM expects)
                messages.append({
                    "role": "function",
                    "tool_call_id": tm["tool_call_id"],
                    "content": tm["content"],
                    "name": tm.get("name"),
                    # is_error is descriptive but LLM also sees content JSON
                })

            # continue loop; LLM will see the appended function messages and decide next action

        # max turns reached
        return {
            "status": "error",
            "error": "max_turns_exceeded",
            "assistant_history": assistant_history,
            "tool_executions": tool_executions,
            "messages": messages
        }

    # ---------- Run full pipeline ----------
    def run(self, user_prompt: str, auto_create: bool = True, dry_run: bool = True) -> dict:
        summary = {
            "generated": None,
            "generated_raw": None,
            "validation": None,
            "creation": None,
            "errors": [],
            "tool_executions": []
        }

        # 1) Generate payload
        payload, raw = self.generate_payload(user_prompt)
        summary["generated_raw"] = raw
        if payload is None:
            summary["errors"].append({"phase": "generate", "message": "invalid_json_from_model", "raw": raw})
            return summary
        summary["generated"] = payload

        # 2) VALIDATION
        validate_system = (
            "You are the Validator Agent. You MUST call tool_validate_payload on the JSON payload provided. "
            "If the tool returns an error, produce a corrected JSON payload and call the tool again. "
            "When the payload is valid, return a simple JSON object: {\"status\":\"valid\",\"payload\": <sanitized_json>}. "
            "If you cannot fix it, return {\"status\":\"fatal_error\",\"message\":\"...\"}."
        )
        validate_user = f"Validate this payload: {json.dumps(payload)}"
        validate_res = self._run_tool_loop(
            system_prompt=validate_system,
            user_content=validate_user,
            allowed_tools=self.tool_defs,
            context_messages=[{"role": "user", "content": user_prompt}],
            max_turns=self.max_turns
        )

        summary["validation"] = validate_res
        summary["tool_executions"].extend(validate_res.get("tool_executions", []))

        if validate_res.get("status") != "final":
            summary["errors"].append({"phase": "validation", "message": "validation_failed_or_max_turns", "detail": validate_res})
            return summary

        # Attempt to parse assistant content as JSON response from validator
        assistant_text = validate_res.get("assistant", "") or ""
        parsed, raw = extract_json_from_text(assistant_text)
        if not parsed:
            # maybe validator used tool outputs; check tool_executions for a validation result
            v_execs = [e for e in summary["tool_executions"] if e.get("tool") == "tool_validate_payload"]
            if v_execs:
                last = v_execs[-1]["result"]
                # tool_validate_payload is expected to return standard schema
                if last.get("status") in ("ok", "error", "tool_error"):
                    # treat sanitized_payload if present
                    sanitized_payload = last.get("sanitized_payload") or None
                    errors = last.get("errors") or []
                    if last.get("status") == "ok" and (not errors):
                        sanitized = sanitized_payload or payload
                        summary["validation"]["sanitized_payload"] = sanitized
                    else:
                        summary["errors"].append({"phase": "validation", "message": "tool_validation_failed", "detail": last})
                        return summary
                else:
                    summary["errors"].append({"phase": "validation", "message": "unexpected_tool_result", "detail": last})
                    return summary
            else:
                summary["errors"].append({"phase": "validation", "message": "validator_no_json_output", "assistant_text": assistant_text})
                return summary
        else:
            # parsed JSON from assistant
            status = parsed.get("status")
            if status == "valid":
                sanitized = parsed.get("payload")
                summary["validation"]["sanitized_payload"] = sanitized or payload
            elif status == "fatal_error":
                summary["errors"].append({"phase": "validation", "message": "fatal_error", "detail": parsed.get("message")})
                return summary
            else:
                # unknown status - fail safe
                summary["errors"].append({"phase": "validation", "message": "unknown_validator_status", "detail": parsed})
                return summary

        # 3) CREATION (optional)
        if auto_create:
            sanitized = summary["validation"].get("sanitized_payload")
            if sanitized is None:
                summary["errors"].append({"phase": "create", "message": "no_sanitized_payload"})
                return summary

            create_system = (
                "You are the Creator Agent. The input JSON is already validated. "
                "Call tool_agent_create with the sanitized payload. If creation succeeds, return {\"status\":\"ok\",\"created\": [ ... ]}. "
                "If creation fails, return {\"status\":\"error\",\"message\":\"...\",\"errors\":[...]}."
            )
            create_user = f"Create this sanitized payload (dry_run={str(dry_run)}): {json.dumps(sanitized)}"
            create_res = self._run_tool_loop(
                system_prompt=create_system,
                user_content=create_user,
                allowed_tools=self.tool_defs,
                context_messages=[{"role": "user", "content": user_prompt}],
                max_turns=self.max_turns
            )
            summary["creation"] = create_res
            summary["tool_executions"].extend(create_res.get("tool_executions", []))

            if create_res.get("status") != "final":
                summary["errors"].append({"phase": "create", "message": "create_failed_or_max_turns", "detail": create_res})
                return summary

            # parse create output
            c_parsed, rawc = extract_json_from_text(create_res.get("assistant","") or "")
            if c_parsed:
                if c_parsed.get("status") == "ok":
                    summary["created"] = c_parsed.get("created", [])
                else:
                    summary["errors"].append({"phase": "create", "message": "create_tool_reported_error", "detail": c_parsed})
                    return summary
            else:
                # maybe tool_agent_create execution exists
                c_execs = [e for e in summary["tool_executions"] if e.get("tool") == "tool_agent_create"]
                if c_execs:
                    lastc = c_execs[-1].get("result", {})
                    if lastc.get("status") == "ok":
                        summary["created"] = lastc.get("created", [])
                    else:
                        summary["errors"].append({"phase":"create", "message":"tool_create_failed", "detail": lastc})
                        return summary
                else:
                    summary["errors"].append({"phase":"create", "message":"no_create_tool_output","assistant_text": create_res.get("assistant","")})
                    return summary

        return summary
