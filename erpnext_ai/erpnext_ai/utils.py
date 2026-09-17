# Copyright (c) 2026, Plus Care and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def check_ai_access(settings):
	"""Server-side gate for every AI feature, not just the chat widget.

	The client-side widget/page hides itself based on boot info, but that's a
	UX nicety — this is the actual permission boundary, so every AI feature
	must route through here (or an equivalent check) rather than trusting the
	client.
	"""
	if not settings.enabled:
		frappe.throw(_("The AI assistant is not enabled"), frappe.PermissionError)

	if settings.allowed_role not in frappe.get_roles():
		frappe.throw(_("You are not permitted to use the AI assistant"), frappe.PermissionError)


def extract_text_from_file(file_doc) -> str:
	"""Extract plain text from a File doc's content (.pdf, .docx, or plain text)."""
	content = file_doc.get_content()
	filename = (file_doc.file_name or "").lower()

	if filename.endswith(".pdf"):
		import io

		from pypdf import PdfReader

		reader = PdfReader(io.BytesIO(content))
		return "\n".join(page.extract_text() or "" for page in reader.pages)

	if filename.endswith(".docx"):
		import io

		from docx import Document as DocxDocument

		doc = DocxDocument(io.BytesIO(content))
		return "\n".join(p.text for p in doc.paragraphs)

	if isinstance(content, bytes):
		return content.decode("utf-8", errors="ignore")
	return content or ""


def extract_json_object(text: str) -> dict:
	"""Best-effort parse of a JSON object the LLM may have wrapped in prose/code fences."""
	import json
	import re

	text = (text or "").strip()
	match = re.search(r"\{.*\}", text, re.DOTALL)
	if match:
		text = match.group(0)
	try:
		return json.loads(text)
	except (ValueError, TypeError):
		return {}


def extract_json_list(text: str) -> list:
	"""Best-effort parse of a JSON array the LLM may have wrapped in prose/code fences."""
	import json
	import re

	text = (text or "").strip()
	match = re.search(r"\[.*\]", text, re.DOTALL)
	if match:
		text = match.group(0)
	try:
		data = json.loads(text)
		return data if isinstance(data, list) else []
	except (ValueError, TypeError):
		return []
