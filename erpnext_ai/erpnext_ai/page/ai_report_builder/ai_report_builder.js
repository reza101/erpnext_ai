// Copyright (c) 2026, Plus Care and contributors
// For license information, please see license.txt

frappe.pages["ai-report-builder"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("AI Report Builder"),
		single_column: true,
	});

	new erpnext_ai.ReportBuilder(page);
};

frappe.provide("erpnext_ai");

erpnext_ai.ReportBuilder = class ReportBuilder {
	constructor(page) {
		this.page = page;
		this.last_result = null;

		const ai_boot = frappe.boot.erpnext_ai || {};
		if (!ai_boot.can_use) {
			this.page.main.html(`<div class="text-muted padding">${__("You are not permitted to use the AI assistant.")}</div>`);
			return;
		}

		this.make();
	}

	make() {
		this.page.main.html(`
			<div class="ai-report-builder">
				<div class="form-group">
					<label>${__("Describe the report you want")}</label>
					<textarea class="form-control ai-rb-prompt" rows="2"
						placeholder="${__("e.g. Total purchase invoice amount by supplier this month")}"></textarea>
				</div>
				<button class="btn btn-primary btn-sm ai-rb-generate">${__("Generate SQL")}</button>

				<div class="ai-rb-query-section" style="display:none; margin-top: 20px;">
					<label>${__("Generated Query (review before running)")}</label>
					<textarea class="form-control ai-rb-query" rows="6" style="font-family: monospace;"></textarea>
					<div style="margin-top: 8px;">
						<button class="btn btn-default btn-sm ai-rb-run">${__("Run Query")}</button>
						<button class="btn btn-default btn-sm ai-rb-save">${__("Save as Report")}</button>
					</div>
				</div>

				<div class="ai-rb-results-section" style="display:none; margin-top: 20px;">
					<div style="display:flex; justify-content: space-between; align-items: center;">
						<label>${__("Results")}</label>
						<button class="btn btn-default btn-xs ai-rb-summarize">${__("Summarize (3 bullets)")}</button>
					</div>
					<div class="ai-rb-table" style="overflow:auto; max-height: 400px;"></div>
					<div class="ai-rb-summary text-muted" style="margin-top: 10px; white-space: pre-line;"></div>
				</div>
			</div>
		`);

		this.$prompt = this.page.main.find(".ai-rb-prompt");
		this.$query = this.page.main.find(".ai-rb-query");
		this.$query_section = this.page.main.find(".ai-rb-query-section");
		this.$results_section = this.page.main.find(".ai-rb-results-section");
		this.$table = this.page.main.find(".ai-rb-table");
		this.$summary = this.page.main.find(".ai-rb-summary");

		this.page.main.find(".ai-rb-generate").on("click", () => this.generate());
		this.page.main.find(".ai-rb-run").on("click", () => this.run());
		this.page.main.find(".ai-rb-save").on("click", () => this.save_as_report());
		this.page.main.find(".ai-rb-summarize").on("click", () => this.summarize());
	}

	generate() {
		const prompt = (this.$prompt.val() || "").trim();
		if (!prompt) {
			frappe.msgprint(__("Describe the report you want first"));
			return;
		}
		frappe.call({
			method: "erpnext_ai.erpnext_ai.report_ai.generate_query",
			args: { prompt },
			freeze: true,
			freeze_message: __("Generating SQL..."),
		}).then((r) => {
			if (r.message && r.message.query) {
				this.$query.val(r.message.query);
				this.$query_section.show();
			}
		});
	}

	run() {
		const query = (this.$query.val() || "").trim();
		if (!query) return;
		frappe.call({
			method: "erpnext_ai.erpnext_ai.report_ai.run_query",
			args: { query },
			freeze: true,
			freeze_message: __("Running query..."),
		}).then((r) => {
			if (!r.message) return;
			this.last_result = r.message;
			this.render_table(r.message.columns, r.message.rows);
			this.$results_section.show();
			this.$summary.text("");
		});
	}

	render_table(columns, rows) {
		if (!rows.length) {
			this.$table.html(`<div class="text-muted">${__("No rows returned")}</div>`);
			return;
		}
		const head = columns.map((c) => `<th>${frappe.utils.escape_html(c)}</th>`).join("");
		const body = rows
			.map(
				(row) =>
					`<tr>${columns.map((c) => `<td>${frappe.utils.escape_html(String(row[c] ?? ""))}</td>`).join("")}</tr>`
			)
			.join("");
		this.$table.html(`<table class="table table-bordered table-sm"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`);
	}

	save_as_report() {
		const query = (this.$query.val() || "").trim();
		if (!query) return;

		frappe.prompt(
			[
				{ fieldname: "report_name", label: __("Report Name"), fieldtype: "Data", reqd: 1 },
				{
					fieldname: "ref_doctype",
					label: __("Reference DocType"),
					fieldtype: "Link",
					options: "DocType",
					default: "User",
					reqd: 1,
				},
			],
			(values) => {
				frappe.call({
					method: "erpnext_ai.erpnext_ai.report_ai.save_as_report",
					args: { report_name: values.report_name, query, ref_doctype: values.ref_doctype },
					freeze: true,
				}).then((r) => {
					if (r.message && r.message.report) {
						frappe.msgprint({
							title: __("Saved"),
							indicator: "green",
							message: __("Report {0} created.", [
								`<a href="/app/query-report/${encodeURIComponent(r.message.report)}">${r.message.report}</a>`,
							]),
						});
					}
				});
			},
			__("Save as Report")
		);
	}

	summarize() {
		if (!this.last_result || !this.last_result.rows || !this.last_result.rows.length) {
			frappe.msgprint(__("Run a query first"));
			return;
		}
		frappe.call({
			method: "erpnext_ai.erpnext_ai.report_ai.summarize",
			args: { rows: this.last_result.rows, columns: this.last_result.columns },
			freeze: true,
			freeze_message: __("Summarizing..."),
		}).then((r) => {
			if (r.message && r.message.summary) {
				this.$summary.text(r.message.summary);
			}
		});
	}
};
