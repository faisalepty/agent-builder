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
    print("PROCESS: Attempting to extract JSON from LLM text.")
    if not text:
        print("PROCESS: No text provided to extract JSON from.")
        return None, text

    raw = text.strip()
    # 1. direct
    try:
        parsed = json.loads(raw)
        print("PROCESS: JSON extracted by direct json.loads.")
        return parsed, raw
    except Exception:
        print("PROCESS: Direct json.loads failed; trying fenced code blocks.")

    # 2. fenced blocks
    blocks = re.findall(r"```(?:json)?\s*(.*?)```", raw, flags=re.S)
    if blocks:
        print(f"PROCESS: Found {len(blocks)} fenced block(s); attempting to parse each.")
    else:
        print("PROCESS: No fenced blocks found; will attempt substring search.")

    for b in blocks:
        try:
            parsed = json.loads(b.strip())
            print("PROCESS: JSON extracted from fenced block.")
            return parsed, raw
        except Exception:
            print("PROCESS: Failed to parse a fenced block; continuing to next.")

    # 3. find first {...} substring (balanced braces)
    start = raw.find("{")
    if start != -1:
        print("PROCESS: Found a '{' in text; attempting balanced-brace substring extraction.")
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
                        parsed = json.loads(candidate)
                        print("PROCESS: JSON extracted from substring with balanced braces.")
                        return parsed, raw
                    except Exception:
                        print("PROCESS: Substring matched braces but json.loads failed on candidate.")
                        break
    else:
        print("PROCESS: No '{' found in text; cannot attempt substring extraction.")

    print("PROCESS: JSON extraction failed; returning None and raw text.")
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

        print("PROCESS: Starting payload generation via LLM.")
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        msg = resp.choices[0].message
        raw = getattr(msg, "content", "") or ""
        print("PROCESS: LLM returned raw payload text.")
        payload, raw = extract_json_from_text(raw)
        if payload is not None:
            print("PROCESS: Payload JSON extracted successfully from LLM output.")
        else:
            print("PROCESS: Failed to extract JSON payload from LLM output; raw text saved.")
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
        print(f"PROCESS: Executing {len(tool_calls)} tool call(s) from assistant message.")
        tool_messages = []
        executions = []
        for call in tool_calls:
            fname = call.function.name
            raw_args = call.function.arguments or "{}"
            print(f"PROCESS: Preparing to run tool '{fname}' with raw args: {raw_args}")
            try:
                args = json.loads(raw_args)
                print(f"PROCESS: Parsed args for tool '{fname}' as JSON.")
            except Exception:
                try:
                    args = eval(raw_args)  # trusted env fallback only
                    print(f"PROCESS: Parsed args for tool '{fname}' via eval fallback.")
                except Exception:
                    args = {}
                    print(f"PROCESS: Failed to parse args for tool '{fname}'; using empty args.")

            tool_fn = self.tool_map.get(fname)
            if not tool_fn:
                result = {
                    "status": "tool_error",
                    "message": f"Unknown tool: {fname}",
                    "errors": [f"Unknown tool: {fname}"]
                }
                print(f"PROCESS: Tool '{fname}' not found in tool map.")
            else:
                try:
                    print(f"PROCESS: Calling tool function '{fname}'.")
                    result = tool_fn(**args)
                    # ensure result follows standard schema
                    if not isinstance(result, dict):
                        result = {"status": "ok", "result": result}
                    print(f"PROCESS: Tool '{fname}' executed; result captured.")
                except Exception as e:
                    result = {
                        "status": "tool_error",
                        "message": str(e),
                        "errors": [str(e)]
                    }
                    print(f"PROCESS: Exception while executing tool '{fname}': {e}")

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
            print(f"PROCESS: Recorded execution for tool '{fname}'; error={is_error}.")

        print("PROCESS: Completed executing tool calls; returning tool messages and executions.")
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

        print("PROCESS: Starting a tool-enabled loop.")
        # fresh messages for this phase
        messages = [{"role": "system", "content": system_prompt}]
        if context_messages:
            for m in context_messages:
                # copy only non-system messages to avoid re-adding system prompts
                if m.get("role") != "system":
                    messages.append(m)
        messages.append({"role": "user", "content": user_content})

        print("PROCESS: Initial messages prepared for loop.")
        tool_executions = []
        assistant_history = []

        for turn in range(max_turns):
            print(f"PROCESS: Loop turn {turn + 1}/{max_turns} — sending messages to LLM.")
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=allowed_tools,
                tool_choice="auto",
                temperature=self.temperature,
            )

            msg = resp.choices[0].message
            assistant_history.append(msg)
            print("PROCESS: Received assistant message from LLM.")

            # if no tool calls => final assistant output
            if not getattr(msg, "tool_calls", None):
                assistant_text = getattr(msg, "content", "") or ""
                print("PROCESS: Assistant did not request any tool calls; finishing loop with final assistant output.")
                return {
                    "status": "final",
                    "assistant": assistant_text,
                    "assistant_message_obj": msg,
                    "tool_executions": tool_executions,
                    "messages": messages + [{"role": "assistant", "content": assistant_text}],
                }

            # else execute tool calls
            print("PROCESS: Assistant requested tool call(s); executing them now.")
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
            print("PROCESS: Appended tool results to messages for next LLM turn; continuing loop.")

            # continue loop; LLM will see the appended function messages and decide next action

        # max turns reached
        print("PROCESS: Max turns reached in tool loop without finalizing.")
        return {
            "status": "error",
            "error": "max_turns_exceeded",
            "assistant_history": assistant_history,
            "tool_executions": tool_executions,
            "messages": messages
        }

    # ---------- Run full pipeline ----------
    def run(self, user_prompt: str, auto_create: bool = True, dry_run: bool = True) -> dict:
        print("PROCESS: Orchestrator run started.")
        summary = {
            "generated": None,
            "generated_raw": None,
            "validation": None,
            "creation": None,
            "errors": [],
            "tool_executions": []
        }

        # 1) Generate payload
        print("PROCESS: === Phase 1: Payload Generation ===")
        payload, raw = self.generate_payload(user_prompt)
        summary["generated_raw"] = raw
        if payload is None:
            print("PROCESS: Payload generation failed or produced invalid JSON.")
            summary["errors"].append({"phase": "generate", "message": "invalid_json_from_model", "raw": raw})
            print("PROCESS: Returning summary due to generation error.")
            return summary
        summary["generated"] = payload
        print("PROCESS: Payload generation completed and stored in summary.")

        # 2) VALIDATION
        print("PROCESS: === Phase 2: Validation ===")
        validate_system = (
            "You are the Validator Agent. You MUST call tool_validate_payload on the JSON payload provided. "
            "If the tool returns an error, produce a corrected JSON payload and call the tool again. "
            "When the payload is valid, return a simple JSON object: {\"status\":\"valid\",\"payload\": <sanitized_json>}. "
            "If you cannot fix it, return {\"status\":\"fatal_error\",\"message\":\"...\"}."
        )
        validate_user = f"Validate this payload: {json.dumps(payload)}"
        print("PROCESS: Starting validation tool loop.")
        validate_res = self._run_tool_loop(
            system_prompt=validate_system,
            user_content=validate_user,
            allowed_tools=self.tool_defs,
            context_messages=[{"role": "user", "content": user_prompt}],
            max_turns=self.max_turns
        )

        summary["validation"] = validate_res
        summary["tool_executions"].extend(validate_res.get("tool_executions", []))
        print("PROCESS: Validation loop finished; analyzing result.")

        if validate_res.get("status") != "final":
            print("PROCESS: Validation failed or did not finalize within allowed turns.")
            summary["errors"].append({"phase": "validation", "message": "validation_failed_or_max_turns", "detail": validate_res})
            return summary

        # Attempt to parse assistant content as JSON response from validator
        assistant_text = validate_res.get("assistant", "") or ""
        parsed, raw = extract_json_from_text(assistant_text)
        if not parsed:
            print("PROCESS: Validator assistant did not return JSON directly; checking tool executions for validation result.")
            # maybe validator used tool outputs; check tool_executions for a validation result
            v_execs = [e for e in summary["tool_executions"] if e.get("tool") == "tool_validate_payload"]
            if v_execs:
                print(f"PROCESS: Found {len(v_execs)} tool_validate_payload execution(s); inspecting last one.")
                last = v_execs[-1]["result"]
                # tool_validate_payload is expected to return standard schema
                if last.get("status") in ("ok", "error", "tool_error"):
                    # treat sanitized_payload if present
                    sanitized_payload = last.get("sanitized_payload") or None
                    errors = last.get("errors") or []
                    if last.get("status") == "ok" and (not errors):
                        sanitized = sanitized_payload or payload
                        summary["validation"]["sanitized_payload"] = sanitized
                        print("PROCESS: tool_validate_payload returned ok and no errors; sanitized payload stored.")
                    else:
                        print("PROCESS: tool_validate_payload returned errors; failing validation.")
                        summary["errors"].append({"phase": "validation", "message": "tool_validation_failed", "detail": last})
                        return summary
                else:
                    print("PROCESS: Unexpected result schema from tool_validate_payload; failing.")
                    summary["errors"].append({"phase": "validation", "message": "unexpected_tool_result", "detail": last})
                    return summary
            else:
                print("PROCESS: No tool execution found for validation and no JSON from assistant; failing.")
                summary["errors"].append({"phase": "validation", "message": "validator_no_json_output", "assistant_text": assistant_text})
                return summary
        else:
            print("PROCESS: Parsed JSON returned by validator assistant.")
            status = parsed.get("status")
            if status == "valid":
                sanitized = parsed.get("payload")
                summary["validation"]["sanitized_payload"] = sanitized or payload
                print("PROCESS: Validator reported status 'valid'; sanitized payload recorded.")
            elif status == "fatal_error":
                print("PROCESS: Validator reported fatal_error; aborting.")
                summary["errors"].append({"phase": "validation", "message": "fatal_error", "detail": parsed.get("message")})
                return summary
            else:
                print("PROCESS: Validator returned unknown status; aborting.")
                summary["errors"].append({"phase": "validation", "message": "unknown_validator_status", "detail": parsed})
                return summary

        # 3) CREATION (optional)
        if auto_create:
            print("PROCESS: === Phase 3: Creation ===")
            sanitized = summary["validation"].get("sanitized_payload")
            if sanitized is None:
                print("PROCESS: No sanitized payload available for creation; aborting.")
                summary["errors"].append({"phase": "create", "message": "no_sanitized_payload"})
                return summary

            create_system = (
                "You are the Creator Agent. The input JSON is already validated. "
                "Call tool_agent_create with the sanitized payload. If creation succeeds, return {\"status\":\"ok\",\"created\": [ ... ]}. "
                "If creation fails, return {\"status\":\"error\",\"message\":\"...\",\"errors\":[...]}."
            )
            create_user = f"Create this sanitized payload (dry_run={str(dry_run)}): {json.dumps(sanitized)}"
            print("PROCESS: Starting creation tool loop (dry_run=" + str(dry_run) + ").")
            create_res = self._run_tool_loop(
                system_prompt=create_system,
                user_content=create_user,
                allowed_tools=self.tool_defs,
                context_messages=[{"role": "user", "content": user_prompt}],
                max_turns=self.max_turns
            )
            summary["creation"] = create_res
            summary["tool_executions"].extend(create_res.get("tool_executions", []))
            print("PROCESS: Creation loop finished; analyzing result.")

            if create_res.get("status") != "final":
                print("PROCESS: Creation did not finalize successfully within allowed turns.")
                summary["errors"].append({"phase": "create", "message": "create_failed_or_max_turns", "detail": create_res})
                return summary

            # parse create output
            c_parsed, rawc = extract_json_from_text(create_res.get("assistant","") or "")
            if c_parsed:
                if c_parsed.get("status") == "ok":
                    summary["created"] = c_parsed.get("created", [])
                    print("PROCESS: Creator assistant returned status 'ok'; created items recorded.")
                else:
                    print("PROCESS: Creator assistant returned an error status; aborting.")
                    summary["errors"].append({"phase": "create", "message": "create_tool_reported_error", "detail": c_parsed})
                    return summary
            else:
                # maybe tool_agent_create execution exists
                c_execs = [e for e in summary["tool_executions"] if e.get("tool") == "tool_agent_create"]
                if c_execs:
                    print(f"PROCESS: Found {len(c_execs)} tool_agent_create execution(s); inspecting last one.")
                    lastc = c_execs[-1].get("result", {})
                    if lastc.get("status") == "ok":
                        summary["created"] = lastc.get("created", [])
                        print("PROCESS: tool_agent_create reported success; created items recorded.")
                    else:
                        print("PROCESS: tool_agent_create reported failure; aborting.")
                        summary["errors"].append({"phase":"create", "message":"tool_create_failed", "detail": lastc})
                        return summary
                else:
                    print("PROCESS: No tool_agent_create output found and creator assistant returned no JSON; aborting.")
                    summary["errors"].append({"phase":"create", "message":"no_create_tool_output","assistant_text": create_res.get("assistant","")})
                    return summary

        print("PROCESS: Orchestration completed; returning final summary.")
        return summary
