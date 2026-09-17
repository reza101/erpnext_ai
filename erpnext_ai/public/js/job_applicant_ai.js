// Copyright (c) 2026, Plus Care and contributors
// For license information, please see license.txt

frappe.ui.form.on("Job Applicant", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.resume_attachment) return;
		if (!(frappe.boot.erpnext_ai && frappe.boot.erpnext_ai.can_use)) return;

		frm.add_custom_button(__("Parse Resume (AI)"), () => {
			frappe.call({
				method: "erpnext_ai.erpnext_ai.resume_ai.parse_resume",
				args: { applicant: frm.doc.name },
				freeze: true,
				freeze_message: __("Queuing resume parsing..."),
			}).then(() => {
				frappe.show_alert({
					message: __("Parsing started — this form will refresh when done."),
					indicator: "blue",
				});
			});
		});
	},
});

frappe.realtime.on("erpnext_ai:job_done", (data) => {
	if (data.method !== "erpnext_ai.erpnext_ai.resume_ai.run_parse_resume") return;
	if (!(cur_frm && cur_frm.doctype === "Job Applicant")) return;
	if (!data.result || data.result.applicant !== cur_frm.doc.name) return;

	if (data.error) {
		frappe.msgprint({
			title: __("Resume Parsing Failed"),
			indicator: "red",
			message: data.error,
		});
	} else {
		frappe.show_alert({ message: __("Resume parsed — fields updated."), indicator: "green" });
		cur_frm.reload_doc();
	}
});
