import frappe
from frappe.desk.query_report import run

def test_report():
    import sys
    sys.path.insert(0, '/home/frappe/benches/school/apps/agent_builder/.hermes/plugins/frappe_tools')
    from tools import frappe_execute_report
    try:
        # Get active fiscal year for Apex Piping
        today = frappe.utils.today()
        fiscal_years = frappe.db.sql("""
            select name, year_start_date, year_end_date 
            from `tabFiscal Year` 
            where %s between year_start_date and year_end_date
            order by year_start_date desc limit 1
        """, (today,), as_dict=True)
        fy = fiscal_years[0]
        
        args = {
            "report_name": "Profit and Loss Statement",
            "filters": {
                "company": "Apex Piping Systems",
                "from_date": str(fy.year_start_date),
                "to_date": str(fy.year_end_date)
            }
        }
        res_json = frappe_execute_report(args)
        import json
        res = json.loads(res_json)
        if "error" in res:
            print("ERROR RETURNED:", res["error"])
        else:
            print("SUCCESS WITH CUSTOM DATES! Keys:", list(res.keys()))
    except Exception as e:
        import traceback
        traceback.print_exc()

