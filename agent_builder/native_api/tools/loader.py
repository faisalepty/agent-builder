# omnis_hermes/tools/loader.py
import importlib.util
import logging
from pathlib import Path

from agent_builder.native_api.tools.decorator import ToolRegistry

logger = logging.getLogger(__name__)


def load_tools(registry: ToolRegistry, tools_dir: str | Path) -> None:
	base = Path(tools_dir)

	# tool_name -> tool_group_dir name, accumulated across every group as we
	# load it. Passed to sync_tool_registry() at the end so the Tool
	# Group / Agent Tool doctypes can be kept in step with what's actually
	# on disk, without every tool file having to know or care about Frappe.
	tool_to_group: dict[str, str] = {}

	# Iterate through all sub-directories in the tools/ folder
	for tool_group_dir in base.iterdir():
		if not tool_group_dir.is_dir() or tool_group_dir.name.startswith("_"):
			continue

		# 1. Load schemas first
		schema_file = tool_group_dir / "schema.py"
		if schema_file.exists():
			loaded_names = _load_schemas(schema_file, registry)
			for name in loaded_names:
				tool_to_group[name] = tool_group_dir.name
		else:
			logger.warning(f"Skipping {tool_group_dir.name}: missing schema.py")

		# 2. Load and wire implementations
		for py_file in tool_group_dir.glob("*.py"):
			if py_file.name.startswith("_") or py_file.name == "schema.py":
				continue
			_load_implementations(py_file, registry)

	# 3. Reconcile the DB-backed on/off switches (Tool Group / Agent Tool)
	# against what actually got loaded. Best-effort: this must never be
	# able to take the whole registry build down (e.g. running outside a
	# Frappe request context, such as isolated tests).
	try:
		from agent_builder.native_api.tools.tool_sync import sync_tool_registry

		sync_tool_registry(registry, tool_to_group)
	except Exception as exc:
		logger.error(f"Tool registry sync (Tool Group / Agent Tool) failed: {exc}")


def _load_schemas(schema_file: Path, registry: ToolRegistry) -> list[str]:
	"""Dynamically finds all dict variables in schema.py and loads them.

	Returns the list of tool names it loaded, so the caller can attribute
	them to this group for sync_tool_registry.
	"""
	module_name = f"tools.{schema_file.parent.name}.schema"
	spec = importlib.util.spec_from_file_location(module_name, schema_file)
	module = importlib.util.module_from_spec(spec)

	try:
		spec.loader.exec_module(module)

		# Auto-discover any variable that looks like a tool schema
		schemas = {
			val["name"]: val
			for val in vars(module).values()
			if isinstance(val, dict) and "name" in val and "parameters" in val
		}

		if schemas:
			registry.load_schemas(schemas)
			logger.info(f"Loaded {len(schemas)} schemas from {schema_file.parent.name}/schema.py")

		return list(schemas.keys())

	except Exception as exc:
		logger.error(f"Failed to load schemas from {schema_file}: {exc}")
		return []


def _load_implementations(py_file: Path, registry: ToolRegistry) -> None:
	"""Finds @tool decorated functions and wires them to the pre-loaded schemas."""
	module_name = f"tools.{py_file.parent.name}.{py_file.stem}"
	spec = importlib.util.spec_from_file_location(module_name, py_file)
	module = importlib.util.module_from_spec(spec)

	try:
		spec.loader.exec_module(module)
	except Exception as exc:
		logger.error(f"Failed to load tool file {py_file}: {exc}")
		return

	for attr_name in dir(module):
		obj = getattr(module, attr_name)
		if callable(obj) and getattr(obj, "__is_tool__", False):
			try:
				registry.register_tool(obj)
				logger.debug(f"Wired executor '{obj.__schema_name__}' from {py_file.name}")
			except Exception as exc:
				logger.error(f"Failed to wire {attr_name}: {exc}")