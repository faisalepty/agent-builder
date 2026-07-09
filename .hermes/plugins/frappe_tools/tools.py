# agent_builder/.hermes/plugins/frappe_tools/tools.py

import json
import frappe
import frappe.desk.query_report

def frappe_get_doc(args: dict, **kwargs) -> str:
    try:
        doc = frappe.get_doc(args["doctype"], args["name"])
        doc.check_permission("read")

        return json.dumps(doc.as_dict(), default=str)

    except frappe.DoesNotExistError:
        return json.dumps({
            "error": f"{args['doctype']} '{args['name']}' does not exist"
        })

    except frappe.PermissionError:
        return json.dumps({
            "error": f"No permission to read {args['doctype']} '{args['name']}'"
        })

    except Exception as e:
        return json.dumps({"error": str(e)})


def frappe_get_list(args: dict, **kwargs) -> str:
    try:
        result = frappe.get_list(
            args["doctype"],
            filters=args.get("filters", {}),
            fields=args.get("fields", ["name"]),
            limit_page_length=args.get("limit", 20),
        )

        return json.dumps(result, default=str)

    except frappe.PermissionError:
        return json.dumps({
            "error": f"No permission to read {args['doctype']}"
        })

    except Exception as e:
        return json.dumps({"error": str(e)})


_GUARDED_FIELDS = {
    "disabled": (1, True, "1"),
}
_GUARDED_STATUSES = {"disabled", "inactive", "cancelled", "blocked"}

def _check_disable_guard(data: dict, existing_doc=None) -> str | None:
    """
    Return a guardrail error message if the payload is attempting to
    disable, deactivate, or inactivate a record.
    Returns None if the operation is allowed.
    """
    # Guard: setting disabled = 1 / True / "1"
    disabled_val = data.get("disabled")
    if disabled_val is not None and str(disabled_val) in ("1", "true", "True"):
        # If the record is already disabled, allow saving other fields
        if existing_doc and getattr(existing_doc, "disabled", None) in (1, True, "1"):
            pass  # already disabled — not our concern
        else:
            return (
                "guardrail_blocked: Disabling records via the agent is not permitted. "
                "Please inform the user how they can disable the record themselves "
                "through the Frappe UI (open the record, tick the 'Disabled' checkbox, and save)."
            )

    # Guard: setting status to a disabled-equivalent value
    status_val = str(data.get("status", "")).strip().lower()
    if status_val and status_val in _GUARDED_STATUSES:
        if existing_doc:
            current_status = str(getattr(existing_doc, "status", "") or "").strip().lower()
            if current_status == status_val:
                pass  # already in that status — unrelated save
            else:
                return (
                    f"guardrail_blocked: Setting a record's status to '{data.get('status')}' via the agent is not permitted. "
                    f"Please inform the user how they can update the status themselves through the Frappe UI."
                )

    return None


def frappe_save_doc(args: dict, **kwargs) -> str:
    
    try:
        data = args["doc"]
        doctype = data.get("doctype")
        name = data.get("name")

        if name and frappe.db.exists(doctype, name):
            # Update existing
            doc = frappe.get_doc(doctype, name)
            doc.check_permission("write")

            # --- Guardrail: block disable/inactivate attempts ---
            guard_error = _check_disable_guard(data, existing_doc=doc)
            if guard_error:
                return json.dumps({"error": guard_error})

            for key, value in data.items():
                if key in ("name", "doctype", "modified", "creation", "owner", "docstatus", "idx"):
                    continue
                df = doc.meta.get_field(key)
                if df and (df.read_only or df.hidden or df.fieldtype == "Read Only"):
                    continue
                doc.set(key, value)

            doc.save()
        else:
            # Create new — guard still applies (e.g. someone creating a doc in a disabled state)
            guard_error = _check_disable_guard(data)
            if guard_error:
                return json.dumps({"error": guard_error})

            doc = frappe.get_doc(data)
            doc.check_permission("create")
            doc.insert(ignore_permissions=False)

        frappe.db.commit()
        return json.dumps({"name": doc.name, "doctype": doc.doctype, "status": "saved"})
    except frappe.PermissionError:
        return json.dumps({"error": "No permission to save this document"})
    except frappe.ValidationError as e:
        return json.dumps({"error": f"Validation failed: {str(e)}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

def frappe_execute_action(args: dict, **kwargs) -> str:
    try:
        doctype = args.get("doctype")
        name = args.get("name")
        action = args.get("action")

        if not (doctype and name and action):
            return json.dumps({"error": "doctype, name, and action are required."})

        doc = frappe.get_doc(doctype, name)
        
        active_workflow = frappe.get_all("Workflow", filters={"document_type": doctype, "is_active": 1})
        
        if active_workflow:
            import frappe.model.workflow
            frappe.model.workflow.apply_workflow(doc, action)
            frappe.db.commit()
            return json.dumps({"doctype": doctype, "name": name, "status": "action_executed", "action": action})
        else:
            if action.lower() == "submit":
                doc.submit()
            elif action.lower() == "cancel":
                doc.cancel()
            else:
                return json.dumps({"error": f"Invalid action '{action}' for doctype without workflow."})
            
            frappe.db.commit()
            return json.dumps({"doctype": doctype, "name": name, "status": "action_executed", "action": action})

    except frappe.PermissionError:
        return json.dumps({"error": f"No permission to perform '{args.get('action')}' on {args.get('doctype')} '{args.get('name')}'"})
    except frappe.ValidationError as e:
        return json.dumps({"error": f"Validation failed: {str(e)}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

def view_skill(args: dict, **kwargs) -> str:
    try:
        skill_name = args.get("skill_name")
        if not skill_name:
            return json.dumps({"error": "Skill name is required"})

        skill_doc = frappe.get_doc("Skill", skill_name)
        skill_description = skill_doc.get("description", "")
        skill_content = skill_doc.get("content", "")
        return json.dumps({
            "name": skill_doc.name,
            "description": skill_description,
            "content": skill_content
        }, default=str)


    except frappe.DoesNotExistError:
        return json.dumps({"error": f"Skill '{skill_name}' does not exist"})
    except frappe.PermissionError:
        return json.dumps({"error": f"No permission to view skill '{skill_name}'"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def list_skills(args: dict, **kwargs) -> str:
    try:
        skills = frappe.get_list("Skill", fields=["name", "description"], limit_page_length=args.get("limit", 20))
        return json.dumps(skills, default=str)

    except frappe.PermissionError:
        return json.dumps({"error": "No permission to list skills"})
    except Exception as e:
        return json.dumps({"error": str(e)})
def frappe_execute_report(args: dict, **kwargs) -> str:
    try:
        report_name = args.get("report_name")
        filters = args.get("filters") or {}
        
        if not report_name:
            return json.dumps({"error": "report_name is required"})
            
        # Try to inject sensible defaults for missing filters (especially for ERPNext)
        try:
            if "company" not in filters:
                default_company = frappe.defaults.get_user_default("Company")
                if default_company:
                    filters["company"] = default_company
            
            # Map from_date / to_date to period_start_date / period_end_date for financial reports
            if "from_date" in filters and "period_start_date" not in filters:
                filters["period_start_date"] = filters["from_date"]
                filters.setdefault("filter_based_on", "Date Range")
            if "to_date" in filters and "period_end_date" not in filters:
                filters["period_end_date"] = filters["to_date"]
            
            # If dates/periods aren't provided at all, default to current fiscal year
            if "from_date" not in filters and "period_start_date" not in filters and "from_fiscal_year" not in filters:
                # We do this safely without assuming erpnext is installed
                if frappe.get_all("Fiscal Year", limit=1):
                    # We can use frappe.utils to get today, then find the fiscal year that covers it
                    today = frappe.utils.today()
                    fiscal_years = frappe.db.sql("""
                        select name, year_start_date, year_end_date 
                        from `tabFiscal Year` 
                        where %s between year_start_date and year_end_date
                        order by year_start_date desc limit 1
                    """, (today,), as_dict=True)
                    
                    if fiscal_years:
                        fy = fiscal_years[0]
                        filters.setdefault("from_fiscal_year", fy.name)
                        filters.setdefault("to_fiscal_year", fy.name)
                        filters.setdefault("period_start_date", fy.year_start_date)
                        filters.setdefault("period_end_date", fy.year_end_date)
                        filters.setdefault("from_date", fy.year_start_date)
                        filters.setdefault("to_date", fy.year_end_date)
                        filters.setdefault("filter_based_on", "Fiscal Year")
                        filters.setdefault("periodicity", "Yearly")
            
            # Ensure periodicity is set if filter_based_on is Date Range or Fiscal Year
            if filters.get("filter_based_on") in ("Date Range", "Fiscal Year"):
                filters.setdefault("periodicity", "Yearly")
        except Exception:
            pass # Ignore default injection failures

        result = frappe.desk.query_report.run(report_name, filters=filters)
        
        # Try to get system currency
        try:
            system_currency = frappe.defaults.get_user_default("Currency") or frappe.db.get_default("currency") or "KES"
            result["system_currency"] = system_currency
        except Exception:
            pass

        # Head & Tail truncation for large result sets
        if isinstance(result.get("result"), list):
            data = result["result"]
            if len(data) > 50:
                head = data[:20]
                tail = data[-20:]
                omitted_count = len(data) - 40
                truncated_data = head + [{"_omitted": f"... [{omitted_count} rows omitted] ..."}] + tail
                result["result"] = truncated_data

        # Result format is usually {"result": [...], "columns": [...]}
        # We need to serialize this cleanly for the LLM
        return json.dumps(result, default=str)

    except frappe.PermissionError:
        return json.dumps({"error": f"No permission to run report '{args.get('report_name')}'"})
    except frappe.ValidationError as e:
        error_msg = str(e)
        if not error_msg:
            error_msg = "Validation Error"
        return json.dumps({"error": error_msg})
    except Exception as e:
        return json.dumps({"error": str(e)})
