# Copyright (c) 2026, Plus Care and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def _check_access(settings):
	"""Server-side gate for every AI feature, not just the chat widget.

	The client-side widget hides itself based on boot info, but that's a UX
	nicety — this is the actual permission boundary, so any future feature
	module that calls the LLM should route through here (or duplicate this
	check) rather than trusting the client.
	"""
	if not settings.enabled:
		frappe.throw(_("The AI assistant is not enabled"), frappe.PermissionError)

	if settings.allowed_role not in frappe.get_roles():
		frappe.throw(_("You are not permitted to use the AI assistant"), frappe.PermissionError)


def extend_boot_session(bootinfo):
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings

	settings = get_cached_settings()
	can_use = bool(settings.enabled and settings.allowed_role in frappe.get_roles())
	bootinfo.erpnext_ai = {
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
	_check_access(settings)

	messages = [
		{"role": "system", "content": settings.system_prompt or ""},
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
