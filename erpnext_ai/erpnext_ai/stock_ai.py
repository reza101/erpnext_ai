# Copyright (c) 2026, Plus Care and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, flt, nowdate


@frappe.whitelist()
def suggest_item_details(item_code: str) -> dict:
	"""Propose a description, item group, and usage guidance for an Item based on its name.

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
				"pick the single best-fit item group from the provided list (copy the "
				"name exactly), and write short, practical usage guidance: how to use "
				"the product, and when it should not be used (contraindications, "
				"warnings, people who should avoid it). Write the text fields in the "
				"same language as the item name. If you are not sure about a safety "
				"detail, say so rather than guess. Reply with strict JSON only: "
				'{"description": "...", "item_group": "...", "how_to_use": "...", '
				'"when_not_to_use": "..."}'
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

	return {
		"description": data.get("description", ""),
		"item_group": suggested_group,
		"how_to_use": data.get("how_to_use", ""),
		"when_not_to_use": data.get("when_not_to_use", ""),
	}


@frappe.whitelist()
def suggest_item_images(item_code: str) -> list:
	"""Find candidate product images on the web for an Item.

	Chat models cannot browse, so the model is only used to locate real product
	pages (OpenAI web search); the image URLs are then read from those pages
	(og:image etc.) rather than taken from the model's text, which would be
	made up. Advisory only — see `apply_item_image` for saving one.
	"""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import check_ai_access, extract_json_list, extract_page_images

	settings = get_cached_settings()
	check_ai_access(settings)
	if settings.provider == "Ollama":
		frappe.throw(_("Finding images on the web needs the OpenAI provider (web search)"))

	item = frappe.get_doc("Item", item_code)
	barcodes = ", ".join(row.barcode for row in item.get("barcodes") or [] if row.barcode)
	query = (
		f"Product: {item.item_name}\n"
		f"Brand: {item.brand or '(unknown)'}\n"
		f"Barcode: {barcodes or '(none)'}\n"
		f"Description: {item.description or '(none)'}\n\n"
		"Search the web for pages that show this exact product: the manufacturer's "
		"site first, then reputable retailers. Reply with a JSON array of at most 5 "
		"page URLs, nothing else."
	)

	# Plain HTTP: the pinned openai SDK (~=1.54) predates the Responses API.
	import requests

	api_key = settings.get_password("api_key", raise_exception=False)
	if not api_key:
		frappe.throw(_("OpenAI API Key is not configured in AI Settings"))
	try:
		res = requests.post(
			"https://api.openai.com/v1/responses",
			headers={"Authorization": f"Bearer {api_key}"},
			json={
				"model": settings.model or "gpt-4o-mini",
				"tools": [{"type": "web_search"}],
				"input": query,
			},
			timeout=90,
		)
		res.raise_for_status()
		response = res.json()
	except requests.RequestException as e:
		frappe.throw(_("OpenAI request failed: {0}").format(str(e)))

	# Citations are URLs the search tool really visited; the model's own list
	# only adds to them.
	pages = []
	answer = ""
	for output in response.get("output") or []:
		for part in output.get("content") or []:
			answer += part.get("text") or ""
			for ann in part.get("annotations") or []:
				if ann.get("type") == "url_citation" and ann.get("url") not in pages:
					pages.append(ann["url"])
	for url in extract_json_list(answer):
		if isinstance(url, str) and url not in pages:
			pages.append(url)

	candidates = []
	for page in pages[:8]:
		for image_url in extract_page_images(page):
			if all(c["image_url"] != image_url for c in candidates):
				candidates.append({"image_url": image_url, "page_url": page})
		if len(candidates) >= 6:
			break

	return candidates[:6]


@frappe.whitelist()
def apply_item_image(item_code: str, image_url: str) -> str:
	"""Download the chosen image and attach it to the Item; returns its file_url.

	Saved server-side so the item doesn't depend on a third-party link staying
	alive. The Item's `image` field is set by the caller, who still has to save.
	"""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import check_ai_access, download_image

	check_ai_access(get_cached_settings())
	frappe.has_permission("Item", "write", item_code, throw=True)

	content, file_name = download_image(image_url)
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"attached_to_doctype": "Item",
			"attached_to_name": item_code,
			"attached_to_field": "image",
			"is_private": 0,
			"content": content,
		}
	).insert()
	return file_doc.file_url


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
