// Copyright (c) 2026, Plus Care and contributors
// For license information, please see license.txt

function erpnext_ai_can_use() {
	return !!(frappe.boot.erpnext_ai && frappe.boot.erpnext_ai.can_use);
}

frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0 || !erpnext_ai_can_use()) return;

		frm.add_custom_button(__("Scan & Fill (AI)"), () => {
			new frappe.ui.FileUploader({
				folder: "Home",
				on_success: (file_doc) => {
					frappe.call({
						method: "erpnext_ai.erpnext_ai.accounts_ai.scan_purchase_invoice",
						args: { file_url: file_doc.file_url },
						freeze: true,
						freeze_message: __("Reading invoice..."),
					}).then((r) => {
						if (r.message) erpnext_ai_show_scan_review(frm, r.message);
					});
				},
			});
		});
	},
});

function erpnext_ai_show_scan_review(frm, data) {
	const items = data.items || [];
	const matched = items.filter((i) => i.item_code);
	const unmatched = items.filter((i) => !i.item_code);

	const rows_html = matched
		.map(
			(i) => `<tr>
				<td>${frappe.utils.escape_html(i.item_code)}
					<br><small class="text-muted">${frappe.utils.escape_html(i.description || "")}</small></td>
				<td>${frappe.utils.escape_html(String(i.qty ?? ""))}</td>
				<td>${frappe.utils.escape_html(String(i.rate ?? ""))}</td>
				<td>${frappe.utils.escape_html(String(i.amount ?? ""))}</td>
			</tr>`
		)
		.join("");
	const unmatched_html = unmatched.length
		? `<p class="text-muted">${__("Not matched to an existing Item — add these manually")}: ${unmatched
				.map((i) => frappe.utils.escape_html(i.description || __("(unknown)")))
				.join(", ")}</p>`
		: "";

	const dialog = new frappe.ui.Dialog({
		title: __("Review Extracted Invoice Data"),
		size: "large",
		fields: [
			{
				fieldname: "supplier",
				label: __("Supplier"),
				fieldtype: "Link",
				options: "Supplier",
				default: data.supplier,
			},
			{
				fieldname: "supplier_name_raw",
				label: __("Supplier (as printed on invoice)"),
				fieldtype: "Data",
				default: data.supplier_name_raw,
				read_only: 1,
			},
			{ fieldname: "column_break_1", fieldtype: "Column Break" },
			{ fieldname: "bill_no", label: __("Bill No"), fieldtype: "Data", default: data.bill_no },
			{ fieldname: "bill_date", label: __("Bill Date"), fieldtype: "Date", default: data.bill_date },
			{ fieldname: "section_items", fieldtype: "Section Break", label: __("Items") },
			{
				fieldname: "items_html",
				fieldtype: "HTML",
				options: `<table class="table table-bordered table-sm">
					<thead><tr><th>${__("Item")}</th><th>${__("Qty")}</th><th>${__("Rate")}</th><th>${__("Amount")}</th></tr></thead>
					<tbody>${rows_html}</tbody>
				</table>${unmatched_html}`,
			},
		],
		primary_action_label: __("Apply"),
		primary_action: (values) => {
			frm.set_value("supplier", values.supplier);
			frm.set_value("bill_no", values.bill_no);
			frm.set_value("bill_date", values.bill_date);
			matched.forEach((i) => {
				const row = frm.add_child("items");
				frappe.model.set_value(row.doctype, row.name, "item_code", i.item_code);
				frappe.model.set_value(row.doctype, row.name, "qty", i.qty || 1);
				frappe.model.set_value(row.doctype, row.name, "rate", i.rate || 0);
			});
			frm.refresh_field("items");
			dialog.hide();
			frappe.show_alert({
				message: __("Applied — review items and save before submitting."),
				indicator: "blue",
			});
		},
	});
	dialog.show();
}

frappe.ui.form.on("Company", {
	refresh(frm) {
		if (frm.is_new() || !erpnext_ai_can_use()) return;

		frm.add_custom_button(__("Financial Trend (AI)"), () => {
			frappe.call({
				method: "erpnext_ai.erpnext_ai.accounts_ai.financial_trend_summary",
				args: { company: frm.doc.name, months: 6 },
				freeze: true,
				freeze_message: __("Analyzing trend..."),
			}).then((r) => {
				if (r.message && r.message.summary) {
					frappe.msgprint({
						title: __("AI Financial Trend"),
						indicator: "blue",
						message: frappe.utils.escape_html(r.message.summary).replace(/\n/g, "<br>"),
					});
				}
			});
		});
	},
});
