// Copyright (c) 2026, Plus Care and contributors
// For license information, please see license.txt

frappe.provide("erpnext_ai");

$(document).ready(() => {
	if (!frappe.boot || !frappe.boot.erpnext_ai || !frappe.boot.erpnext_ai.show_widget) {
		return;
	}
	erpnext_ai.chat_widget = new erpnext_ai.ChatWidget();
});

erpnext_ai.ChatWidget = class ChatWidget {
	constructor() {
		this.is_open = false;
		this.is_sending = false;
		this.make();
	}

	make() {
		this.$launcher = $(`
			<button class="erpnext-ai-launcher" title="${__("AI Assistant")}">
				<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
					<path d="M12 2a1 1 0 0 1 1 1v1.06A8.004 8.004 0 0 1 20 12v1a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-1a8.004 8.004 0 0 1 7-7.94V3a1 1 0 0 1 1-1Z" fill="currentColor"/>
					<circle cx="9" cy="12" r="1.2" fill="white"/>
					<circle cx="15" cy="12" r="1.2" fill="white"/>
					<path d="M4 17h16v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2Z" fill="currentColor"/>
				</svg>
			</button>
		`).appendTo("body");

		this.$panel = $(`
			<div class="erpnext-ai-panel" style="display:none;">
				<div class="erpnext-ai-header">
					<span>${__("AI Assistant")}</span>
					<button class="erpnext-ai-close">&times;</button>
				</div>
				<div class="erpnext-ai-messages"></div>
				<div class="erpnext-ai-input-row">
					<textarea class="erpnext-ai-input" rows="1" placeholder="${__("Ask something...")}"></textarea>
					<button class="erpnext-ai-send">${__("Send")}</button>
				</div>
			</div>
		`).appendTo("body");

		this.$messages = this.$panel.find(".erpnext-ai-messages");
		this.$input = this.$panel.find(".erpnext-ai-input");
		this.$send = this.$panel.find(".erpnext-ai-send");

		this.$launcher.on("click", () => this.toggle());
		this.$panel.find(".erpnext-ai-close").on("click", () => this.toggle(false));
		this.$send.on("click", () => this.send());
		this.$input.on("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				this.send();
			}
		});
	}

	toggle(force) {
		this.is_open = force === undefined ? !this.is_open : force;
		this.$panel.toggle(this.is_open);
		if (this.is_open) this.$input.trigger("focus");
	}

	append(role, text) {
		const $msg = $("<div>").addClass(`erpnext-ai-msg erpnext-ai-msg-${role}`).text(text);
		this.$messages.append($msg);
		this.$messages.scrollTop(this.$messages[0].scrollHeight);
		return $msg;
	}

	send() {
		const message = (this.$input.val() || "").trim();
		if (!message || this.is_sending) return;

		this.is_sending = true;
		this.$input.val("");
		this.append("user", message);
		const $pending = this.append("assistant", __("Thinking..."));

		frappe.call({
			method: "erpnext_ai.api.chat.ask",
			args: { message },
			callback: (r) => {
				$pending.text((r.message && r.message.reply) || __("No response"));
			},
			error: () => {
				$pending.text(__("Something went wrong. Please try again."));
			},
			always: () => {
				this.is_sending = false;
				this.$messages.scrollTop(this.$messages[0].scrollHeight);
			},
		});
	}
};
