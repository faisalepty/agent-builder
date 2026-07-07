from typing import Dict, Any

import frappe
from frappe import _


def get_doctype_info(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute DocType info retrieval"""
    try:
        # Import the metadata implementation
        from .metadata_tools import MetadataTools

        # Execute metadata retrieval using existing implementation
        return MetadataTools.get_doctype_metadata(doctype=arguments.get("doctype"))

    except Exception as e:
        frappe.log_error(
            title=_("Get DocType Info Error"), message=f"Error getting DocType info: {str(e)}"
        )

        return {"success": False, "error": str(e)}