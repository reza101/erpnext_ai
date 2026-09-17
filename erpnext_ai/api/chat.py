# Copyright (c) 2026, Plus Care and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from erpnext_ai.erpnext_ai.utils import check_ai_access


def extend_boot_session(bootinfo):
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings

	settings = get_cached_settings()
	can_use = bool(settings.enabled and settings.allowed_role in frappe.get_roles())
	bootinfo.erpnext_ai = {
		"can_use": can_use,
		"show_widget": can_use and bool(settings.enable_chat_widget),
	}


@frappe.whitelist()
def ask(message: str):
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.llm import chat_completion

	message = (message or "").strip()
	if not message:
		frappe.throw(_("Message cannot be empty"))

	settings = get_cached_settings()
	check_ai_access(settings)

	system_prompt = settings.system_prompt or ""
	policy_context = _get_hr_policy_context(settings)
	if policy_context:
		system_prompt += (
			"\n\nInternal HR policy reference (use this to answer policy questions):\n" + policy_context
		)

	messages = [
		{"role": "system", "content": system_prompt},
		{"role": "user", "content": message},
	]
	reply, usage = chat_completion(messages, settings=settings, with_usage=True)

	frappe.get_doc(
		{
			"doctype": "AI Chat Log",
			"user": frappe.session.user,
			"model": settings.model,
			"prompt": message,
			"response": reply,
			"prompt_tokens": usage["prompt_tokens"],
			"completion_tokens": usage["completion_tokens"],
		}
	).insert(ignore_permissions=True)

	return {"reply": reply}


def _get_hr_policy_context(settings) -> str:
	"""Extracted text of the configured HR policy document, cached for an hour.

	Only surfaced to HR User/HR Manager — everyone else's chat requests are
	unaffected, keeping the base assistant's prompt size unchanged.
	"""
	if not settings.hr_policy_document:
		return ""
	if not ({"HR User", "HR Manager"} & set(frappe.get_roles())):
		return ""

	from erpnext_ai.erpnext_ai.utils import extract_text_from_file

	cache_key = f"erpnext_ai_hr_policy_text::{settings.hr_policy_document}"
	cached = frappe.cache().get_value(cache_key)
	if cached is not None:
		return cached

	file_doc = frappe.get_doc("File", {"file_url": settings.hr_policy_document})
	text = extract_text_from_file(file_doc)[:6000]
	frappe.cache().set_value(cache_key, text, expires_in_sec=3600)
	return text
