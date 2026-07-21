# omnis_hermes/tools/decorator.py
from collections.abc import Callable
from typing import Any, Dict


def tool(schema_name: str) -> Callable:
	"""
	Marks a function as a tool and links it to its schema name.
	The schema MUST be defined as a variable in the group's schema.py file.
	"""

	def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
		func.__is_tool__ = True
		func.__schema_name__ = schema_name
		return func

	return decorator


class ToolRegistry:
	def __init__(self) -> None:
		self._tools: dict[str, dict[str, Any]] = {}
		self.executors: dict[str, Callable] = {}

	def load_schemas(self, schemas: dict[str, dict]) -> None:
		"""Injects hand-crafted JSON schemas from schema.py files."""
		for name, schema in schemas.items():
			self._tools[name] = {
				"type": "function",
				"function": {
					"name": schema["name"],
					"description": schema.get("description", ""),
					"parameters": schema.get("parameters", {"type": "object", "properties": {}}),
				},
			}

	def register_tool(self, func: Callable) -> None:
		"""Wires a python function to its pre-loaded schema."""
		name = func.__schema_name__
		if name not in self._tools:
			raise ValueError(
				f"Schema '{name}' not found in registry. Did you define it in the group's schema.py?"
			)
		self.executors[name] = func

	def get_tool_schemas(self) -> list:
		return list(self._tools.values())
