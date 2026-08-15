// Copyright (c) 2026, Plus Care and contributors
// For license information, please see license.txt

frappe.ui.form.on("AI Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => {
			frappe.call({
				doc: frm.doc,
				method: "test_connection",
				freeze: true,
				freeze_message: __("Contacting OpenAI..."),
			}).then((r) => {
				if (r.message && r.message.reply) {
					frappe.msgprint({
						title: __("Success"),
						indicator: "green",
						message: __("Model replied: {0}", [r.message.reply]),
					});
				}
			});
		});
	},
});
