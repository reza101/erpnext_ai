# Copyright (c) 2026, Plus Care and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AISettings(Document):
	def validate(self):
		if self.enabled and not self.get_password("api_key", raise_exception=False):
			frappe.throw(_("Set an OpenAI API Key before enabling the AI assistant"))

	@frappe.whitelist()
	def test_connection(self):
		frappe.only_for("System Manager")
		from erpnext_ai.llm import chat_completion

		reply = chat_completion(
			[{"role": "user", "content": "Reply with exactly: pong"}],
			settings=self,
		)
		return {"reply": reply}


def get_cached_settings() -> "AISettings":
	"""Single doctype, safe to cache for the life of the request."""
	return frappe.get_cached_doc("AI Settings")
