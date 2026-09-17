# Copyright (c) 2026, Plus Care and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, flt, nowdate


@frappe.whitelist()
def suggest_item_details(item_code: str) -> dict:
	"""Propose a description and item group for an Item based on its name.

	Returned for review — the caller decides whether to save it, never
	written automatically.
	"""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import check_ai_access, extract_json_object
	from erpnext_ai.llm import chat_completion

	settings = get_cached_settings()
	check_ai_access(settings)

	item = frappe.get_doc("Item", item_code)
	item_groups = frappe.get_all("Item Group", pluck="name", limit=200)

	messages = [
		{
			"role": "system",
			"content": (
				"You help catalog products in an ERP. Given an item's name (and any "
				"existing description), write a concise 1-2 sentence product description, "
				"and pick the single best-fit item group from the provided list (copy the "
				'name exactly). Reply with strict JSON only: {"description": "...", '
				'"item_group": "..."}'
			),
		},
		{
			"role": "user",
			"content": (
				f"Item name: {item.item_name}\n"
				f"Existing description: {item.description or '(none)'}\n"
				f"Available item groups: {', '.join(item_groups)}"
			),
		},
	]
	data = extract_json_object(chat_completion(messages, settings=settings))

	suggested_group = data.get("item_group")
	if suggested_group not in item_groups:
		suggested_group = item.item_group  # keep current rather than write a made-up group

	return {"description": data.get("description", ""), "item_group": suggested_group}


@frappe.whitelist()
def suggest_reorder_levels(item_code: str) -> dict:
	"""Suggest a reorder level/qty per warehouse from 90-day consumption.

	Purely advisory — returns suggestions for the user to review via
	`apply_reorder_levels`; never writes anything itself.
	"""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import check_ai_access, extract_json_list
	from erpnext_ai.llm import chat_completion

	settings = get_cached_settings()
	check_ai_access(settings)

	since = add_days(nowdate(), -90)
	consumption = frappe.db.sql(
		"""
		select warehouse, sum(-actual_qty) as consumed
		from `tabStock Ledger Entry`
		where item_code = %(item_code)s and actual_qty < 0
			and is_cancelled = 0 and posting_date >= %(since)s
		group by warehouse
		""",
		{"item_code": item_code, "since": since},
		as_dict=True,
	)
	if not consumption:
		frappe.throw(_("No outgoing stock movement found for {0} in the last 90 days").format(item_code))

	bins = {
		b.warehouse: b.actual_qty
		for b in frappe.get_all("Bin", filters={"item_code": item_code}, fields=["warehouse", "actual_qty"])
	}

	lines = []
	for row in consumption:
		daily_avg = flt(row["consumed"]) / 90
		current_stock = bins.get(row["warehouse"], 0)
		lines.append(
			f"{row['warehouse']}: consumed {row['consumed']} over 90 days "
			f"(~{daily_avg:.2f}/day), current stock {current_stock}"
		)

	messages = [
		{
			"role": "system",
			"content": (
				"You are an inventory planner. Given 90-day consumption and current stock "
				"per warehouse, suggest a reorder_level (trigger point) and reorder_qty "
				"(order size) per warehouse — assume a 14-day lead time and a small safety "
				"buffer. Reply with strict JSON only: a list of objects like "
				'[{"warehouse": "...", "reorder_level": 0, "reorder_qty": 0, "reason": "..."}]'
			),
		},
		{"role": "user", "content": "\n".join(lines)},
	]
	suggestions = extract_json_list(chat_completion(messages, settings=settings))
	valid_warehouses = set(bins.keys()) | {r["warehouse"] for r in consumption}
	suggestions = [s for s in suggestions if s.get("warehouse") in valid_warehouses]

	if not suggestions:
		frappe.throw(_("Could not generate reorder suggestions — try again"))

	return {"suggestions": suggestions}


@frappe.whitelist()
def apply_reorder_levels(item_code: str, suggestions) -> dict:
	"""Write accepted reorder suggestions into the Item's existing Item Reorder rows.

	`suggestions` is a list of {warehouse, reorder_level, reorder_qty}. Updates
	the row for a warehouse if one already exists, otherwise appends a new one
	— never touches warehouses not included in `suggestions`.
	"""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import check_ai_access

	check_ai_access(get_cached_settings())

	if isinstance(suggestions, str):
		import json

		suggestions = json.loads(suggestions)

	item = frappe.get_doc("Item", item_code)
	existing = {row.warehouse: row for row in item.reorder_levels}

	for s in suggestions:
		warehouse = s.get("warehouse")
		if not warehouse:
			continue
		if warehouse in existing:
			existing[warehouse].warehouse_reorder_level = flt(s.get("reorder_level"))
			existing[warehouse].warehouse_reorder_qty = flt(s.get("reorder_qty"))
		else:
			item.append(
				"reorder_levels",
				{
					"warehouse": warehouse,
					"warehouse_reorder_level": flt(s.get("reorder_level")),
					"warehouse_reorder_qty": flt(s.get("reorder_qty")),
					"material_request_type": "Purchase",
				},
			)

	item.save(ignore_permissions=True)
	frappe.db.commit()
	return {"item_code": item_code, "warehouses_updated": len(suggestions)}


def detect_stock_anomalies():
	"""Scheduled (daily): flag item/warehouse stock movements that are
	statistically unusual vs. the item's own recent history, and log an
	`AI Stock Alert` with a short LLM-written explanation.

	A cheap statistical pre-filter (z-score) runs first so the LLM is only
	called for the (typically few) rows that are actually flagged — keeps
	cost proportional to actual anomalies, not total ledger volume.
	"""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.llm import chat_completion

	settings = get_cached_settings()
	if not settings.enabled:
		return

	yesterday = add_days(nowdate(), -1)
	moved_rows = frappe.db.sql(
		"""
		select item_code, warehouse, voucher_type, voucher_no, posting_date,
			sum(abs(actual_qty)) as qty_moved
		from `tabStock Ledger Entry`
		where posting_date = %(yesterday)s and is_cancelled = 0
		group by item_code, warehouse, voucher_type, voucher_no, posting_date
		""",
		{"yesterday": yesterday},
		as_dict=True,
	)

	for row in moved_rows:
		try:
			_check_one_movement(row, yesterday, settings, chat_completion)
		except Exception:
			frappe.log_error(title=f"erpnext_ai stock anomaly check failed for {row.get('item_code')}")

	frappe.db.commit()


def _check_one_movement(row, yesterday, settings, chat_completion):
	history = frappe.db.sql(
		"""
		select posting_date, sum(abs(actual_qty)) as qty_moved
		from `tabStock Ledger Entry`
		where item_code = %(item_code)s and warehouse = %(warehouse)s
			and is_cancelled = 0 and posting_date < %(yesterday)s and posting_date >= %(since)s
		group by posting_date
		""",
		{
			"item_code": row["item_code"],
			"warehouse": row["warehouse"],
			"yesterday": yesterday,
			"since": add_days(yesterday, -60),
		},
		as_dict=True,
	)
	if len(history) < 5:
		return  # not enough history to judge what's "normal" for this item/warehouse

	values = [flt(h["qty_moved"]) for h in history]
	mean = sum(values) / len(values)
	variance = sum((v - mean) ** 2 for v in values) / len(values)
	stddev = variance**0.5

	if stddev == 0:
		# No historical variation at all — z-score is undefined, but a stable
		# pattern makes any large deviation meaningful. Fall back to a flat multiple.
		threshold = max(mean * 2, mean + 1)
	else:
		threshold = mean + 3 * stddev

	if flt(row["qty_moved"]) <= threshold:
		return  # within normal range

	messages = [
		{
			"role": "system",
			"content": (
				"You are a stock analyst. In one short sentence, explain why this quantity "
				"movement looks unusual compared to recent history, and suggest what to check."
			),
		},
		{
			"role": "user",
			"content": (
				f"Item {row['item_code']} in warehouse {row['warehouse']}: moved "
				f"{row['qty_moved']} units on {row['posting_date']} via "
				f"{row['voucher_type']} {row['voucher_no']}. Recent daily average is "
				f"{mean:.1f} (std dev {stddev:.1f})."
			),
		},
	]
	message = chat_completion(messages, settings=settings)
	severity = "High" if flt(row["qty_moved"]) > mean + 5 * stddev else "Medium"

	frappe.get_doc(
		{
			"doctype": "AI Stock Alert",
			"item_code": row["item_code"],
			"warehouse": row["warehouse"],
			"severity": severity,
			"posting_date": row["posting_date"],
			"voucher_type": row["voucher_type"],
			"voucher_no": row["voucher_no"],
			"actual_qty": row["qty_moved"],
			"message": message,
		}
	).insert(ignore_permissions=True)
