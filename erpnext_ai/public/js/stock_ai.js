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
				let selected_image = null;
				const has_usage_fields = frm.fields_dict.custom_how_to_use && frm.fields_dict.custom_when_not_to_use;
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
						...(has_usage_fields
							? [
									{
										fieldname: "how_to_use",
										label: __("How to Use"),
										fieldtype: "Small Text",
										default: r.message.how_to_use,
									},
									{
										fieldname: "when_not_to_use",
										label: __("When Not to Use"),
										fieldtype: "Small Text",
										default: r.message.when_not_to_use,
									},
								]
							: []),
						{
							fieldname: "find_image",
							label: __("Find Image on the Web"),
							fieldtype: "Button",
							click: () => {
								selected_image = null;
								const wrapper = dialog.get_field("image_candidates").$wrapper;
								wrapper.html(`<p class="text-muted">${__("Searching...")}</p>`);
								frappe
									.call({
										method: "erpnext_ai.erpnext_ai.stock_ai.suggest_item_images",
										args: { item_code: frm.doc.name },
									})
									.then((res) => {
										const images = res.message || [];
										if (!images.length) {
											wrapper.html(`<p class="text-muted">${__("No images found.")}</p>`);
											return;
										}
										wrapper.html(
											`<div style="display:flex;flex-wrap:wrap;gap:8px">${images
												.map(
													(img, i) =>
														`<img data-i="${i}" referrerpolicy="no-referrer" src="${frappe.utils.escape_html(img.image_url)}"
															style="width:90px;height:90px;object-fit:contain;cursor:pointer;border:2px solid transparent;border-radius:6px">`
												)
												.join("")}</div>
											<p class="text-muted small">${__("Click an image to use it for this item.")}</p>`
										);
										wrapper.find("img").on("click", function () {
											wrapper.find("img").css("border-color", "transparent");
											$(this).css("border-color", "var(--primary)");
											selected_image = images[$(this).data("i")].image_url;
										});
									})
									.catch(() => wrapper.html(""));
							},
						},
						{ fieldname: "image_candidates", fieldtype: "HTML" },
					],
					primary_action_label: __("Apply"),
					primary_action: async (values) => {
						frm.set_value("description", values.description);
						frm.set_value("item_group", values.item_group);
						if (has_usage_fields) {
							frm.set_value("custom_how_to_use", values.how_to_use);
							frm.set_value("custom_when_not_to_use", values.when_not_to_use);
						}
						if (selected_image) {
							const res = await frappe.call({
								method: "erpnext_ai.erpnext_ai.stock_ai.apply_item_image",
								args: { item_code: frm.doc.name, image_url: selected_image },
								freeze: true,
								freeze_message: __("Saving image..."),
							});
							if (res.message) frm.set_value("image", res.message);
						}
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
