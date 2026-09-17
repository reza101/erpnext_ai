# Copyright (c) 2026, Plus Care and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def get_client(settings=None):
	"""Build an OpenAI client from AI Settings. Raises frappe.ValidationError if unconfigured.

	Accepts an optional in-memory `settings` doc (e.g. an unsaved AI Settings
	form) so callers like "Test Connection" exercise the key the user just
	typed rather than whatever is already persisted in the database.
	"""
	import openai

	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings

	settings = settings or get_cached_settings()
	api_key = settings.get_password("api_key", raise_exception=False)
	if not api_key:
		frappe.throw(_("OpenAI API Key is not configured in AI Settings"))

	return openai.OpenAI(api_key=api_key)


def chat_completion(messages: list[dict], settings=None, with_usage: bool = False):
	"""Send a chat completion request using AI Settings for provider/model/temperature.

	`messages` follows the OpenAI chat format: [{"role": "user", "content": "..."}, ...]
	Returns the assistant's reply text, or (text, usage_dict) when `with_usage=True`.
	Raises frappe.ValidationError on failure.
	"""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings

	settings = settings or get_cached_settings()

	if settings.provider == "Ollama":
		text, usage = _ollama_chat_completion(messages, settings)
	else:
		text, usage = _openai_chat_completion(messages, settings)

	if not with_usage:
		return text
	return text, usage


def _openai_chat_completion(messages: list[dict], settings):
	import openai

	client = get_client(settings)

	try:
		response = client.chat.completions.create(
			model=settings.model or "gpt-4o-mini",
			messages=messages,
			temperature=settings.temperature or 0.3,
			max_tokens=settings.max_tokens or 1024,
		)
	except openai.APIError as e:
		frappe.throw(_("OpenAI request failed: {0}").format(str(e)))

	usage = response.usage
	return response.choices[0].message.content, {
		"prompt_tokens": usage.prompt_tokens if usage else 0,
		"completion_tokens": usage.completion_tokens if usage else 0,
	}


def _ollama_chat_completion(messages: list[dict], settings):
	import ollama

	if not settings.ollama_base_url:
		frappe.throw(_("Ollama Base URL is not configured in AI Settings"))

	client = ollama.Client(host=settings.ollama_base_url)
	try:
		response = client.chat(
			model=settings.model or "llama3.1",
			messages=messages,
			options={
				"temperature": settings.temperature or 0.3,
				"num_predict": settings.max_tokens or 1024,
			},
		)
	except Exception as e:
		frappe.throw(_("Ollama request failed: {0}").format(str(e)))

	return response.message.content, {
		"prompt_tokens": response.prompt_eval_count or 0,
		"completion_tokens": response.eval_count or 0,
	}


def extract_from_image(image_bytes: bytes, mime_type: str, prompt: str, settings=None) -> str:
	"""Send an image + instruction prompt to a vision-capable model, return the raw text reply.

	Both providers' vision APIs take images in incompatible shapes (OpenAI:
	an `image_url` content block; Ollama: a top-level `images` list per
	message), so this wraps that difference the same way chat_completion()
	wraps the plain-text APIs.
	"""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings

	settings = settings or get_cached_settings()

	if settings.provider == "Ollama":
		return _ollama_extract_from_image(image_bytes, mime_type, prompt, settings)
	return _openai_extract_from_image(image_bytes, mime_type, prompt, settings)


def _openai_extract_from_image(image_bytes: bytes, mime_type: str, prompt: str, settings) -> str:
	import base64

	b64 = base64.b64encode(image_bytes).decode()
	messages = [
		{
			"role": "user",
			"content": [
				{"type": "text", "text": prompt},
				{"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
			],
		}
	]
	return _openai_chat_completion(messages, settings)[0]


def _ollama_extract_from_image(image_bytes: bytes, mime_type: str, prompt: str, settings) -> str:
	import base64

	import ollama

	if not settings.ollama_base_url:
		frappe.throw(_("Ollama Base URL is not configured in AI Settings"))

	client = ollama.Client(host=settings.ollama_base_url)
	b64 = base64.b64encode(image_bytes).decode()
	try:
		response = client.chat(
			model=settings.model or "llava",
			messages=[{"role": "user", "content": prompt, "images": [b64]}],
		)
	except Exception as e:
		frappe.throw(_("Ollama request failed: {0}").format(str(e)))

	return response.message.content
