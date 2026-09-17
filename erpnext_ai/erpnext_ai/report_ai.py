# Copyright (c) 2026, Plus Care and contributors
# For license information, please see license.txt

import frappe
from frappe import _

# A short, curated schema hint — enough for common reporting questions without
# dumping the full (huge) ERPNext schema into every prompt.
SCHEMA_HINT = """Common tables you may query (MariaDB, Frappe naming: `tabDocType Name`):
- `tabSales Invoice` (name, customer, posting_date, grand_total, status, company, outstanding_amount)
- `tabPurchase Invoice` (name, supplier, posting_date, grand_total, status, company, outstanding_amount)
- `tabSales Invoice Item` (parent, item_code, item_name, qty, rate, amount)
- `tabPurchase Invoice Item` (parent, item_code, item_name, qty, rate, amount)
- `tabItem` (name, item_code, item_name, item_group, stock_uom)
- `tabCustomer` (name, customer_name, customer_group, territory)
- `tabSupplier` (name, supplier_name, supplier_group)
- `tabGL Entry` (account, debit, credit, posting_date, voucher_type, voucher_no, party, party_type, company)
- `tabBin` (item_code, warehouse, actual_qty)
- `tabStock Ledger Entry` (item_code, warehouse, posting_date, actual_qty, qty_after_transaction, voucher_type)
"""


def _strip_code_fence(text: str) -> str:
	text = text.strip()
	if not text.startswith("```"):
		return text
	text = text.strip("`")
	if text.lower().startswith("sql"):
		text = text[3:]
	return text.strip()


@frappe.whitelist()
def generate_query(prompt: str) -> dict:
	"""Turn a natural-language question into a read-only SQL query.

	The query is validated with Frappe's own `check_safe_sql_query` (the same
	guard core Query Reports use) before being returned — it is never executed
	here, just generated and validated.
	"""
	from frappe.utils.safe_exec import check_safe_sql_query

	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import check_ai_access
	from erpnext_ai.llm import chat_completion

	prompt = (prompt or "").strip()
	if not prompt:
		frappe.throw(_("Describe the report you want"))

	settings = get_cached_settings()
	check_ai_access(settings)

	messages = [
		{
			"role": "system",
			"content": (
				"You write a single read-only MariaDB SQL query (SELECT only) for a "
				"Frappe/ERPNext database, based on the user's question. Only use the "
				"tables/columns listed below. Reply with the raw SQL only — no markdown "
				"fences, no explanation.\n" + SCHEMA_HINT
			),
		},
		{"role": "user", "content": prompt},
	]
	query = _strip_code_fence(chat_completion(messages, settings=settings))

	check_safe_sql_query(query, throw=True)
	return {"query": query}


@frappe.whitelist()
def run_query(query: str) -> dict:
	"""Re-validate and execute a query the user reviewed (e.g. after hand-editing it)."""
	from frappe.utils.safe_exec import check_safe_sql_query

	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import check_ai_access

	check_ai_access(get_cached_settings())
	check_safe_sql_query(query, throw=True)

	rows = frappe.db.sql(query, as_dict=True)
	columns = list(rows[0].keys()) if rows else []
	return {"columns": columns, "rows": rows}


@frappe.whitelist()
def save_as_report(report_name: str, query: str, ref_doctype: str = "User") -> dict:
	"""Persist a validated query as a standard Frappe Query Report."""
	from frappe.utils.safe_exec import check_safe_sql_query

	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import check_ai_access

	check_ai_access(get_cached_settings())
	check_safe_sql_query(query, throw=True)

	if frappe.db.exists("Report", report_name):
		frappe.throw(_("A report named {0} already exists").format(report_name))

	report = frappe.get_doc(
		{
			"doctype": "Report",
			"report_name": report_name,
			"ref_doctype": ref_doctype,
			"report_type": "Query Report",
			"is_standard": "No",
			"query": query,
		}
	).insert()
	return {"report": report.name}


@frappe.whitelist()
def summarize(rows: list | None = None, columns: list | None = None) -> dict:
	"""Ask the LLM for exactly 3 bullet points summarizing tabular results."""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import check_ai_access
	from erpnext_ai.llm import chat_completion

	settings = get_cached_settings()
	check_ai_access(settings)

	rows = rows or []
	if not rows:
		frappe.throw(_("No data to summarize"))

	# Cap what we send to the model — this is a summary, not a data dump.
	sample = rows[:200]
	table_text = "\n".join(", ".join(f"{k}={v}" for k, v in row.items()) for row in sample)

	messages = [
		{
			"role": "system",
			"content": (
				"You summarize tabular business report data for an ERP user. Reply with "
				"exactly 3 bullet points, each one line, no preamble."
			),
		},
		{
			"role": "user",
			"content": f"Columns: {columns}\nRows ({len(rows)} total, showing {len(sample)}):\n{table_text}",
		},
	]
	summary = chat_completion(messages, settings=settings)
	return {"summary": summary}
