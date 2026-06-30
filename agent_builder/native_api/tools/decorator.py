# omnis_hermes/tools/decorator.py
#
# Single canonical ToolRegistry.
# A tool is a tool — primitives, external wrappers, skill-specific tools,
# and meta-tools (skill_list, skill_view) all register here identically.
#
import inspect
from typing import Any, Callable, Dict, List, Optional


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    param_descriptions: Optional[Dict[str, str]] = None,
) -> Callable:
    """
    Decorator to mark a Python function as an LLM-callable tool.

    Args:
        name:               Override the tool name (defaults to function name).
        description:        Tool description shown to the model.
        param_descriptions: Per-parameter descriptions injected into the schema
                            so the model understands each argument.

    Example:
        @tool(
            name="fetch_transaction_status",
            description="Look up a transaction in the remote ledger.",
            param_descriptions={"tx_id": "Unique transaction ID, e.g. TX_001"},
        )
        def fetch_transaction_status(tx_id: str) -> str: ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func.__is_tool__ = True
        func.__tool_name__ = name or func.__name__
        func.__tool_desc__ = description or func.__doc__ or "No description provided."
        func.__param_descs__ = param_descriptions or {}
        return func
    return decorator


class ToolRegistry:
    """
    Central registry for all LLM-callable tools.

    Two registration paths — same output shape:
      register_native_tool()   — @tool-decorated Python function.
                                 Schema is introspected from the signature.
      register_explicit_tool() — Hand-authored schema + executor callable.
                                 Used for complex tools where the parameter
                                 contract cannot be inferred from a signature.

    Both paths produce the same {"type": "function", "function": {...}} envelope
    with strict: true and additionalProperties: false enforced, so
    get_tool_schemas() always returns a uniform list regardless of how
    each tool was registered.
    """

    def __init__(self) -> None:
        # Full OpenAI-compatible tool schemas keyed by name
        self._tools: Dict[str, Dict[str, Any]] = {}
        # Callable executors keyed by name
        self.executors: Dict[str, Callable] = {}
        # Lightweight name/description index for system-prompt discovery block
        self._skills_manifest: List[Dict[str, str]] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_native_tool(self, func: Callable) -> None:
        """
        Registers a @tool-decorated function.

        Introspects the signature to build the JSON schema parameter block.
        Supports str, int, float, bool annotations.

        Strict-mode requirements (OpenAI docs):
          - additionalProperties: false on every object
          - ALL fields must appear in required[]
          - Optional fields use {"type": ["string", "null"]} union, not omission
        """
        if not getattr(func, "__is_tool__", False):
            raise ValueError(
                f"Function '{func.__name__}' must be decorated with @tool "
                "before registration."
            )

        name: str = func.__tool_name__
        param_descs: Dict[str, str] = getattr(func, "__param_descs__", {})
        sig = inspect.signature(func)
        properties: Dict[str, Any] = {}
        required: List[str] = []

        for param_name, param in sig.parameters.items():
            ann = param.annotation

            # Map Python annotations to JSON Schema types
            if ann in (int, float):
                ptype: Any = "number"
            elif ann == bool:
                ptype = "boolean"
            elif ann == list:
                ptype = "array"
            elif ann == dict:
                ptype = "object"
            else:
                ptype = "string"

            # Optional param (has a default) → nullable union in strict mode
            if param.default is not inspect.Parameter.empty:
                prop: Dict[str, Any] = {"type": [ptype, "null"]}
            else:
                prop = {"type": ptype}
                required.append(param_name)

            if param_name in param_descs:
                prop["description"] = param_descs[param_name]

            properties[param_name] = prop

        self._tools[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": func.__tool_desc__,
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
        }
        self.executors[name] = func

    def register_explicit_tool(
        self,
        schema: Dict[str, Any],
        executor: Callable,
    ) -> None:
        """
        Registers a tool whose parameter schema is hand-authored.

        schema must be the inner function descriptor:
            {
                "name": "my_tool",
                "description": "...",
                "parameters": {
                    "type": "object",
                    "properties": { ... },
                    "required": [...],
                }
            }

        strict: true and additionalProperties: false are injected
        automatically so callers don't have to remember them.

        If the tool represents a high-level skill, also adds it to the
        skills manifest so it appears in the discovery block.
        """
        name: str = schema["name"]
        description: str = schema.get("description", "No description provided.")

        params = dict(schema.get("parameters", {}))
        params.setdefault("additionalProperties", False)

        self._tools[name] = {
            "type": "function",
            "function": {
                **schema,
                "strict": True,
                "parameters": params,
            },
        }
        self.executors[name] = executor
        self._skills_manifest.append({"name": name, "description": description})

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Returns all OpenAI-compatible tool schemas."""
        return list(self._tools.values())

    def get_skills_context(self) -> List[Dict[str, str]]:
        """
        Returns the lightweight name/description manifest for tools registered
        via register_explicit_tool() — these are typically high-level skills
        whose names are surfaced in the system-prompt discovery block.
        """
        return list(self._skills_manifest)