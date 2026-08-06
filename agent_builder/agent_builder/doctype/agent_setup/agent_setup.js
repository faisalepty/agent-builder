// agent_builder/agent_builder/doctype/agent_setup/agent_setup.js

frappe.ui.form.on("Agent Setup", {
	onload(frm) {
		set_model_query(frm);
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