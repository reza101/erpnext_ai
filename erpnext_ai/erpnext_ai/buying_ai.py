# Copyright (c) 2026, Plus Care and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import today


@frappe.whitelist()
def summarize_scorecard(scorecard: str) -> dict:
	"""Plain-language narrative over a Supplier Scorecard's period history.

	Pure read — computes nothing new, just narrates the scoring ERPNext
	already produces via Supplier Scorecard Period.
	"""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import check_ai_access
	from erpnext_ai.llm import chat_completion

	settings = get_cached_settings()
	check_ai_access(settings)

	periods = frappe.get_all(
		"Supplier Scorecard Period",
		filters={"scorecard": scorecard},
		fields=["name", "total_score", "start_date", "end_date"],
		order_by="start_date desc",
		limit=12,
	)
	if not periods:
		frappe.throw(_("No scorecard periods found yet for {0}").format(scorecard))

	lines = []
	for p in periods[:6]:
		criteria = frappe.get_all(
			"Supplier Scorecard Scoring Criteria",
			filters={"parent": p["name"], "parenttype": "Supplier Scorecard Period"},
			fields=["criteria_name", "score", "weight"],
		)
		crit_text = ", ".join(f"{c['criteria_name']}={c['score']}% (weight {c['weight']}%)" for c in criteria)
		lines.append(f"{p['start_date']} to {p['end_date']}: total={p['total_score']}% [{crit_text}]")

	supplier = frappe.db.get_value("Supplier Scorecard", scorecard, "supplier")
	messages = [
		{
			"role": "system",
			"content": (
				"You are a procurement analyst. Given a supplier's scorecard history "
				"(most recent period first), write a short plain-language summary: the "
				"overall trend, what's driving it, and one actionable recommendation. "
				"Max 5 sentences."
			),
		},
		{"role": "user", "content": f"Supplier: {supplier}\n" + "\n".join(lines)},
	]
	summary = chat_completion(messages, settings=settings)
	return {"summary": summary, "periods_considered": len(periods)}


@frappe.whitelist()
def price_trend(item_code: str, supplier: str | None = None) -> dict:
	"""Narrative over historical purchase rates for an item (optionally one supplier)."""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import check_ai_access
	from erpnext_ai.llm import chat_completion

	settings = get_cached_settings()
	check_ai_access(settings)

	po_condition = "and po.supplier = %(supplier)s" if supplier else ""
	pi_condition = "and pi.supplier = %(supplier)s" if supplier else ""
	# Pulls from both Purchase Order and Purchase Invoice — some businesses go
	# straight to Purchase Invoice without ever raising a Purchase Order.
	rows = frappe.db.sql(
		f"""
		select transaction_date, supplier, rate, qty from (
			select po.transaction_date as transaction_date, po.supplier as supplier,
				poi.rate as rate, poi.qty as qty
			from `tabPurchase Order Item` poi
			inner join `tabPurchase Order` po on po.name = poi.parent
			where poi.item_code = %(item_code)s and po.docstatus = 1
			{po_condition}
			union all
			select pi.posting_date as transaction_date, pi.supplier as supplier,
				pii.rate as rate, pii.qty as qty
			from `tabPurchase Invoice Item` pii
			inner join `tabPurchase Invoice` pi on pi.name = pii.parent
			where pii.item_code = %(item_code)s and pi.docstatus = 1
			{pi_condition}
		) combined
		order by transaction_date desc
		limit 30
		""",
		{"item_code": item_code, "supplier": supplier},
		as_dict=True,
	)
	if not rows:
		frappe.throw(_("No purchase history found for {0}").format(item_code))

	lines = [f"{r['transaction_date']}: {r['supplier']} @ {r['rate']} (qty {r['qty']})" for r in rows]
	messages = [
		{
			"role": "system",
			"content": (
				"You are a buying analyst. Given historical purchase rates for one item "
				"(most recent first), summarize the price trend (rising/falling/stable), "
				"flag any supplier charging notably more or less than others, and suggest "
				"one negotiation angle. Max 5 sentences."
			),
		},
		{"role": "user", "content": f"Item: {item_code}\n" + "\n".join(lines)},
	]
	summary = chat_completion(messages, settings=settings)
	return {"summary": summary, "data_points": len(rows)}


@frappe.whitelist()
def draft_rfq(material_request: str) -> dict:
	"""Pre-fill a draft Request for Quotation from a submitted Material Request.

	Candidate suppliers are ranked by actual purchase history for these items;
	the LLM only picks a shortlist from that real candidate list (never invents
	a supplier). The RFQ is left as an editable draft — never auto-submitted.
	"""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import check_ai_access, extract_json_list
	from erpnext_ai.llm import chat_completion

	settings = get_cached_settings()
	check_ai_access(settings)

	mr = frappe.get_doc("Material Request", material_request)
	if not mr.items:
		frappe.throw(_("This Material Request has no items"))

	item_codes = [d.item_code for d in mr.items]
	# Same dual-source logic as price_trend: some businesses never raise a
	# Purchase Order and go straight to Purchase Invoice.
	supplier_rows = frappe.db.sql(
		"""
		select supplier, sum(cnt) as cnt from (
			select po.supplier as supplier, count(*) as cnt
			from `tabPurchase Order Item` poi
			inner join `tabPurchase Order` po on po.name = poi.parent
			where poi.item_code in %(item_codes)s and po.docstatus = 1
			group by po.supplier
			union all
			select pi.supplier as supplier, count(*) as cnt
			from `tabPurchase Invoice Item` pii
			inner join `tabPurchase Invoice` pi on pi.name = pii.parent
			where pii.item_code in %(item_codes)s and pi.docstatus = 1
			group by pi.supplier
		) combined
		group by supplier
		""",
		{"item_codes": item_codes},
		as_dict=True,
	)
	if not supplier_rows:
		frappe.throw(
			_("No purchase history found for any item in this Material Request — add suppliers manually")
		)

	candidates = sorted(supplier_rows, key=lambda r: -r["cnt"])[:8]
	candidate_names = [c["supplier"] for c in candidates]

	messages = [
		{
			"role": "system",
			"content": (
				"You are a procurement assistant. From the candidate supplier list "
				"(with how many times each was purchased from for these items), pick the "
				'3 best suppliers to send this RFQ to. Reply with a strict JSON array of '
				'supplier names only, e.g. ["Supplier A", "Supplier B"]. Only use names '
				"from the candidate list, copied exactly."
			),
		},
		{
			"role": "user",
			"content": "Items: "
			+ ", ".join(item_codes)
			+ "\nCandidates (name: purchase_count): "
			+ ", ".join(f"{c['supplier']}: {c['cnt']}" for c in candidates),
		},
	]
	chosen = [s for s in extract_json_list(chat_completion(messages, settings=settings)) if s in candidate_names]
	if not chosen:
		chosen = candidate_names[:3]

	from erpnext.stock.get_item_details import get_conversion_factor

	rfq = frappe.new_doc("Request for Quotation")
	rfq.naming_series = "PUR-RFQ-.YYYY.-"
	rfq.company = mr.company
	rfq.transaction_date = today()
	for supplier in chosen:
		rfq.append("suppliers", {"supplier": supplier})
	for item in mr.items:
		rfq.append(
			"items",
			{
				"item_code": item.item_code,
				"qty": item.qty,
				"uom": item.uom,
				"stock_uom": frappe.db.get_value("Item", item.item_code, "stock_uom"),
				"conversion_factor": get_conversion_factor(item.item_code, item.uom).get("conversion_factor", 1),
				"warehouse": item.warehouse,
				"schedule_date": item.schedule_date or today(),
				"material_request": mr.name,
				"material_request_item": item.name,
			},
		)
	rfq.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"rfq": rfq.name, "suppliers": chosen}
