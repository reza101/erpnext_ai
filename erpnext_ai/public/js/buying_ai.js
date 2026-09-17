// Copyright (c) 2026, Plus Care and contributors
// For license information, please see license.txt

function erpnext_ai_can_use() {
	return !!(frappe.boot.erpnext_ai && frappe.boot.erpnext_ai.can_use);
}

frappe.ui.form.on("Supplier Scorecard", {
	refresh(frm) {
		if (frm.is_new() || !erpnext_ai_can_use()) return;

		frm.add_custom_button(__("AI Summary"), () => {
			frappe.call({
				method: "erpnext_ai.erpnext_ai.buying_ai.summarize_scorecard",
				args: { scorecard: frm.doc.name },
				freeze: true,
				freeze_message: __("Summarizing..."),
			}).then((r) => {
				if (r.message && r.message.summary) {
					frappe.msgprint({
						title: __("AI Supplier Summary"),
						indicator: "blue",
						message: frappe.utils.escape_html(r.message.summary).replace(/\n/g, "<br>"),
					});
				}
			});
		});
	},
});

frappe.ui.form.on("Item", {
	refresh(frm) {
		if (frm.is_new() || !erpnext_ai_can_use()) return;

		frm.add_custom_button(__("AI Price Trend"), () => {
			frappe.call({
				method: "erpnext_ai.erpnext_ai.buying_ai.price_trend",
				args: { item_code: frm.doc.item_code },
				freeze: true,
				freeze_message: __("Analyzing price history..."),
			}).then((r) => {
				if (r.message && r.message.summary) {
					frappe.msgprint({
						title: __("AI Price Trend"),
						indicator: "blue",
						message: frappe.utils.escape_html(r.message.summary).replace(/\n/g, "<br>"),
					});
				}
			});
		});
	},
});

frappe.ui.form.on("Material Request", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 1 || !erpnext_ai_can_use()) return;
		if (frm.doc.material_request_type !== "Purchase") return;

		frm.add_custom_button(__("Draft RFQ (AI)"), () => {
			frappe.call({
				method: "erpnext_ai.erpnext_ai.buying_ai.draft_rfq",
				args: { material_request: frm.doc.name },
				freeze: true,
				freeze_message: __("Drafting RFQ..."),
			}).then((r) => {
				if (r.message && r.message.rfq) {
					frappe.set_route("Form", "Request for Quotation", r.message.rfq);
				}
			});
		});
	},
});
