# omnis_hermes/tools/loader.py
#
# Auto-discovers and registers all @tool-decorated functions from
# tools/internal/ and tools/external/ onto the ToolRegistry.
#
# This means adding a new tool is just:
#   1. Create tools/internal/my_tool.py with a @tool-decorated function
#   2. That's it — no manual registration needed
#
import importlib.util
import logging
from pathlib import Path

from agent_builder.native_api.tools.decorator import ToolRegistry

logger = logging.getLogger(__name__)


def load_tools(registry: ToolRegistry, tools_dir: str | Path) -> None:
    """
    Scans tools/internal/ and tools/external/ for Python files,
    imports each one, and registers any @tool-decorated functions found.
    Skips __init__.py and this file itself.
    """
    base = Path(tools_dir)
    for subdir in ("internal", "external"):
        target = base / subdir
        if not target.exists():
            continue
        for py_file in sorted(target.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            _register_from_file(py_file, registry)


def _register_from_file(py_file: Path, registry: ToolRegistry) -> None:
    module_name = f"tools.{py_file.parent.name}.{py_file.stem}"
    spec = importlib.util.spec_from_file_location(module_name, py_file)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        logger.error("Failed to load tool file '%s': %s", py_file, exc)
        return

    for attr_name in dir(module):
        obj = getattr(module, attr_name)
        if callable(obj) and getattr(obj, "__is_tool__", False):
            try:
                registry.register_native_tool(obj)
                logger.debug("Registered tool '%s' from %s", obj.__tool_name__, py_file.name)
            except Exception as exc:
                logger.error(
                    "Failed to register tool '%s' from '%s': %s",
                    attr_name, py_file, exc,
                )