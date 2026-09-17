# Copyright (c) 2026, Plus Care and contributors
# For license information, please see license.txt

import frappe
from frappe import _


@frappe.whitelist()
def parse_resume(applicant: str) -> dict:
	"""Queue background parsing of a Job Applicant's uploaded resume.

	Runs on the `long` queue via `enqueue_ai_job` since PDF/DOCX extraction +
	an LLM round-trip is too slow for a blocking web request.
	"""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import check_ai_access
	from erpnext_ai.tasks import enqueue_ai_job

	check_ai_access(get_cached_settings())

	applicant_doc = frappe.get_doc("Job Applicant", applicant)
	if not applicant_doc.resume_attachment:
		frappe.throw(_("No resume attached to this applicant"))

	enqueue_ai_job("erpnext_ai.erpnext_ai.resume_ai.run_parse_resume", applicant=applicant)
	return {"queued": True}


def run_parse_resume(applicant: str) -> dict:
	"""Background worker target: extract resume text, ask the LLM to structure it,
	and fill in whichever Job Applicant fields are still blank (never overwrite
	values the user already entered).
	"""
	from erpnext_ai.erpnext_ai.doctype.ai_settings.ai_settings import get_cached_settings
	from erpnext_ai.erpnext_ai.utils import extract_json_object, extract_text_from_file
	from erpnext_ai.llm import chat_completion

	applicant_doc = frappe.get_doc("Job Applicant", applicant)
	file_doc = frappe.get_doc("File", {"file_url": applicant_doc.resume_attachment})
	text = extract_text_from_file(file_doc)[:8000]

	if not text.strip():
		frappe.throw(_("Could not extract any text from the resume file"))

	settings = get_cached_settings()
	messages = [
		{
			"role": "system",
			"content": (
				"Extract candidate info from this resume text. Reply with strict JSON only, "
				'keys: "full_name", "email", "phone", "summary" (a 2-3 sentence professional '
				"summary). Use an empty string for any field you can't find. No other text."
			),
		},
		{"role": "user", "content": text},
	]
	data = extract_json_object(chat_completion(messages, settings=settings))

	if not applicant_doc.applicant_name and data.get("full_name"):
		applicant_doc.applicant_name = data["full_name"]
	if not applicant_doc.email_id and data.get("email"):
		applicant_doc.email_id = data["email"]
	if not applicant_doc.phone_number and data.get("phone"):
		applicant_doc.phone_number = data["phone"]
	if not applicant_doc.cover_letter and data.get("summary"):
		applicant_doc.cover_letter = data["summary"]

	applicant_doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"applicant": applicant, "extracted": data}
