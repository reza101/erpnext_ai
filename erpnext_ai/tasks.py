# Copyright (c) 2026, Plus Care and contributors
# For license information, please see license.txt

import frappe


def enqueue_ai_job(method: str, **kwargs):
	"""Queue a long-running AI job (OCR, forecasting, scoring, ...) on the
	`long` worker instead of blocking a web request.

	`method` is the dotted path of a function to run in the background.
	On completion (success or failure) an `erpnext_ai:job_done` realtime
	event is published to the requesting user so a feature's UI can react
	without polling.
	"""
	return frappe.enqueue(
		"erpnext_ai.tasks.run_ai_job",
		queue="long",
		method=method,
		user=frappe.session.user,
		job_kwargs=kwargs,
	)


def run_ai_job(method: str, user: str, job_kwargs: dict):
	result, error = None, None
	try:
		result = frappe.get_attr(method)(**job_kwargs)
	except Exception:
		error = frappe.get_traceback()
		frappe.log_error(title=f"erpnext_ai job failed: {method}")
	finally:
		frappe.publish_realtime(
			"erpnext_ai:job_done",
			{"method": method, "result": result, "error": error},
			user=user,
		)
