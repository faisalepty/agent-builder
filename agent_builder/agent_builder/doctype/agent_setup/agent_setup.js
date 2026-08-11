// agent_builder/agent_builder/doctype/agent_setup/agent_setup.js

frappe.ui.form.on("Agent Setup", {
	onload(frm) {
		set_model_query(frm);
		add_sync_models_button(frm);
	},

	refresh(frm) {
		add_sync_models_button(frm);
	},

	provider(frm) {
		// Provider changed — the previously selected model likely belongs
		// to a different provider, so clear it rather than leave a stale
		// mismatched value that OpenAIProvider.__init__ would silently trust.
		frm.set_value("model", "");
		set_model_query(frm);
	},

	model(frm) {
		show_model_capabilities(frm);
	},
});

function add_sync_models_button(frm) {
	frm.add_custom_button(__("Sync model pricing"), () => {
		if (!frm.doc.provider) {
			frappe.msgprint(__("Select a provider before syncing model pricing."));
			return;
		}

		frappe.call({
			method: "agent_builder.native_api.providers.model_sync.sync_models",
			args: { dry_run: 0 },
			freeze: true,
			freeze_message: __("Syncing model pricing for {0}...", [frm.doc.provider]),
			callback(r) {
				if (r.exc) {
					frappe.msgprint({
						title: __("Sync failed"),
						message: __("Model pricing sync failed. Check the server logs."),
						indicator: "red",
					});
					return;
				}

				const summary = r.message || {};
				const created = (summary.created || []).length;
				const updated = (summary.updated || []).length;
				const skipped = (summary.skipped || []).length;
				const errors = (summary.errors || []).length;
				const parts = [];
				if (created) parts.push(__("created: {0}", [created]));
				if (updated) parts.push(__("updated: {0}", [updated]));
				if (skipped) parts.push(__("skipped: {0}", [skipped]));
				if (errors) parts.push(__("errors: {0}", [errors]));

				frappe.msgprint({
					title: __("Sync complete"),
					message: parts.length ? parts.join(" · ") : __("No model records were changed."),
					indicator: errors ? "orange" : "green",
				});
			},
		});
	}, __("Actions"));
}

function set_model_query(frm) {
	frm.set_query("model", () => ({
		filters: frm.doc.provider
			? { provider: frm.doc.provider, active: 1 }
			: { provider: ["is", "not set"] },
	}));
}

function show_model_capabilities(frm) {
	frm.dashboard.clear_headline();
	if (!frm.doc.model) return;

	frappe.db.get_value(
		"Model Pricing",
		frm.doc.model,
		["context_window", "supports_tools", "supports_vision", "supports_reasoning", "reasoning_efforts"],
		(r) => {
			if (!r || !r.context_window) return;
			const bits = [];
			if (r.context_window) bits.push(`${r.context_window.toLocaleString()} ctx`);
			if (r.supports_tools) bits.push("tools");
			if (r.supports_vision) bits.push("vision");
			if (r.supports_reasoning) bits.push(`reasoning (${r.reasoning_efforts || "?"})`);
			if (bits.length) {
				frm.dashboard.set_headline(bits.join(" · "));
			}

			// Nudge if reasoning_effort is set on a model that doesn't support it.
			if (frm.doc.reasoning_effort && !r.supports_reasoning) {
				frm.dashboard.set_headline_alert(
					`Warning: ${frm.doc.model} is not marked as supporting reasoning, but a reasoning_effort is set.`,
					"orange"
				);
			}
		}
	);
}