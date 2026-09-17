# Copyright (c) 2026, Plus Care and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_months, flt, nowdate

EXTRACTION_INSTRUCTION = (
	"Extract this purchase invoice into strict JSON only, keys: "
	'"supplier_name", "bill_no", "bill_date" (YYYY-MM-DD), "grand_total" (number), '
	'"items": [{"description": "...", "qty": number, "rate": number, "amount": number}]. '
	"Use null for anything you can't find. No other text."
)


@frappe.whitelist()
def scan_purchase_invoice(file_url: str) -> dict:
	"""OCR/extract structured data from an uploaded purchase invoice file.

	Images go through the vision model directly. Text-based PDFs go through
	the same text-extraction + text-model path used for resumes (most
	supplier invoices are digitally generated, not scanned). Pure image-only
	PDFs aren't supported without a PDF-rendering dependency this environment
	doesn't have — the caller gets a clear error in that case rather than a
	silent bad extraction.

	Returned for review; never writes to any document itself — the caller
	pre-fills a draft form and the user confirms before saving.
	"""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import check_ai_access, extract_json_object, extract_text_from_file
	from erpnext_ai.llm import chat_completion, extract_from_image

	settings = get_cached_settings()
	check_ai_access(settings)

	file_doc = frappe.get_doc("File", {"file_url": file_url})
	filename = (file_doc.file_name or "").lower()

	if filename.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
		ext = filename.rsplit(".", 1)[-1]
		mime = "image/jpeg" if ext == "jpg" else f"image/{ext}"
		reply = extract_from_image(file_doc.get_content(), mime, EXTRACTION_INSTRUCTION, settings=settings)
	elif filename.endswith(".pdf"):
		text = extract_text_from_file(file_doc)[:8000]
		if not text.strip():
			frappe.throw(
				_(
					"Could not read any text from this PDF — it looks like a scanned/image-only "
					"PDF, which isn't supported yet. Upload a photo (JPG/PNG) instead."
				)
			)
		reply = chat_completion(
			[
				{"role": "system", "content": EXTRACTION_INSTRUCTION},
				{"role": "user", "content": text},
			],
			settings=settings,
		)
	else:
		frappe.throw(_("Unsupported file type — upload a PDF or an image (JPG/PNG)"))

	data = extract_json_object(reply)
	if not data:
		frappe.throw(_("Could not extract structured data from this file"))

	# Best-effort match against real records — never invent a Link value.
	supplier = None
	if data.get("supplier_name"):
		supplier = frappe.db.get_value(
			"Supplier", {"supplier_name": ["like", f"%{data['supplier_name']}%"]}, "name"
		)

	items = data.get("items") or []
	for item in items:
		item["item_code"] = None
		if item.get("description"):
			item["item_code"] = frappe.db.get_value(
				"Item", {"item_name": ["like", f"%{item['description']}%"]}, "name"
			)

	return {
		"supplier": supplier,
		"supplier_name_raw": data.get("supplier_name"),
		"bill_no": data.get("bill_no"),
		"bill_date": data.get("bill_date"),
		"grand_total": data.get("grand_total"),
		"items": items,
	}


@frappe.whitelist()
def financial_trend_summary(company: str | None = None, months: int = 6) -> dict:
	"""Narrative over recent monthly income/expense totals from GL Entry.

	Reuses the same "aggregate then ask for a short narrative" shape as
	report_ai.summarize() and buying_ai.price_trend() rather than inventing a
	new pattern.
	"""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import check_ai_access
	from erpnext_ai.llm import chat_completion

	settings = get_cached_settings()
	check_ai_access(settings)

	months = int(months) or 6
	since = add_months(nowdate(), -months)
	condition = "and gle.company = %(company)s" if company else ""

	rows = frappe.db.sql(
		f"""
		select date_format(gle.posting_date, '%%Y-%%m') as month, acc.root_type as root_type,
			sum(gle.debit - gle.credit) as net
		from `tabGL Entry` gle
		inner join `tabAccount` acc on acc.name = gle.account
		where gle.is_cancelled = 0 and gle.posting_date >= %(since)s
			and acc.root_type in ('Income', 'Expense')
			{condition}
		group by month, acc.root_type
		order by month
		""",
		{"since": since, "company": company},
		as_dict=True,
	)
	if not rows:
		frappe.throw(_("No GL Entry data found for the last {0} months").format(months))

	lines = []
	for r in rows:
		# Income accounts are credit-normal, so debit-credit is negative for revenue — flip sign for readability.
		amount = -flt(r["net"]) if r["root_type"] == "Income" else flt(r["net"])
		lines.append(f"{r['month']} {r['root_type']}: {amount:,.2f}")

	messages = [
		{
			"role": "system",
			"content": (
				"You are a financial analyst. Given monthly income and expense totals, "
				"summarize the trend (growing/shrinking/volatile), flag anything unusual, "
				"and note the overall trajectory. Max 5 sentences."
			),
		},
		{"role": "user", "content": "\n".join(lines)},
	]
	summary = chat_completion(messages, settings=settings)
	return {"summary": summary, "months_considered": months}
