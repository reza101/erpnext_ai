// Copyright (c) 2026, Plus Care and contributors
// For license information, please see license.txt

frappe.ui.form.on("Item", {
	refresh(frm) {
		if (frm.is_new() || !(frappe.boot.erpnext_ai && frappe.boot.erpnext_ai.can_use)) return;

		frm.add_custom_button(__("Suggest Item Details (AI)"), () => {
			frappe.call({
				method: "erpnext_ai.erpnext_ai.stock_ai.suggest_item_details",
				args: { item_code: frm.doc.name },
				freeze: true,
				freeze_message: __("Thinking..."),
			}).then((r) => {
				if (!r.message) return;
				const dialog = new frappe.ui.Dialog({
					title: __("AI Suggestion — review before applying"),
					fields: [
						{
							fieldname: "description",
							label: __("Description"),
							fieldtype: "Small Text",
							default: r.message.description,
						},
						{
							fieldname: "item_group",
							label: __("Item Group"),
							fieldtype: "Link",
							options: "Item Group",
							default: r.message.item_group,
						},
					],
					primary_action_label: __("Apply"),
					primary_action: (values) => {
						frm.set_value("description", values.description);
						frm.set_value("item_group", values.item_group);
						frm.dirty();
						dialog.hide();
						frappe.show_alert({
							message: __("Applied — remember to save."),
							indicator: "blue",
						});
					},
				});
				dialog.show();
			});
		});

		frm.add_custom_button(__("Suggest Reorder Levels (AI)"), () => {
			frappe.call({
				method: "erpnext_ai.erpnext_ai.stock_ai.suggest_reorder_levels",
				args: { item_code: frm.doc.name },
				freeze: true,
				freeze_message: __("Analyzing consumption..."),
			}).then((r) => {
				if (!r.message || !r.message.suggestions) return;
				const rows = r.message.suggestions;
				const dialog = new frappe.ui.Dialog({
					title: __("AI Reorder Suggestions — review before applying"),
					size: "large",
					fields: [
						{
							fieldname: "suggestions_html",
							fieldtype: "HTML",
							options: `<table class="table table-bordered table-sm">
								<thead><tr>
									<th>${__("Warehouse")}</th>
									<th>${__("Reorder Level")}</th>
									<th>${__("Reorder Qty")}</th>
									<th>${__("Reason")}</th>
								</tr></thead>
								<tbody>
									${rows
										.map(
											(s) => `<tr>
												<td>${frappe.utils.escape_html(s.warehouse || "")}</td>
												<td>${frappe.utils.escape_html(String(s.reorder_level ?? ""))}</td>
												<td>${frappe.utils.escape_html(String(s.reorder_qty ?? ""))}</td>
												<td>${frappe.utils.escape_html(s.reason || "")}</td>
											</tr>`
										)
										.join("")}
								</tbody>
							</table>`,
						},
					],
					primary_action_label: __("Apply All"),
					primary_action: () => {
						frappe.call({
							method: "erpnext_ai.erpnext_ai.stock_ai.apply_reorder_levels",
							args: { item_code: frm.doc.name, suggestions: rows },
							freeze: true,
						}).then(() => {
							dialog.hide();
							frappe.show_alert({ message: __("Reorder levels updated."), indicator: "green" });
							frm.reload_doc();
						});
					},
				});
				dialog.show();
			});
		});
	},
});
