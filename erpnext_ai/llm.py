# Copyright (c) 2026, Plus Care and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def get_client():
	"""Build an OpenAI client from AI Settings. Raises frappe.ValidationError if unconfigured."""
	import openai

	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings

	settings = get_cached_settings()
	api_key = settings.get_password("api_key", raise_exception=False)
	if not api_key:
		frappe.throw(_("OpenAI API Key is not configured in AI Settings"))

	return openai.OpenAI(api_key=api_key)


def chat_completion(messages: list[dict], settings=None, with_usage: bool = False):
	"""Send a chat completion request using AI Settings for model/temperature.

	`messages` follows the OpenAI chat format: [{"role": "user", "content": "..."}, ...]
	Returns the assistant's reply text, or (text, usage_dict) when `with_usage=True`.
	Raises frappe.ValidationError on failure.
	"""
	import openai

	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings

	settings = settings or get_cached_settings()
	client = get_client()

	try:
		response = client.chat.completions.create(
			model=settings.model or "gpt-4o-mini",
			messages=messages,
			temperature=settings.temperature or 0.3,
			max_tokens=settings.max_tokens or 1024,
		)
	except openai.APIError as e:
		frappe.throw(_("OpenAI request failed: {0}").format(str(e)))

	text = response.choices[0].message.content
	if not with_usage:
		return text

	usage = response.usage
	return text, {
		"prompt_tokens": usage.prompt_tokens if usage else 0,
		"completion_tokens": usage.completion_tokens if usage else 0,
	}
