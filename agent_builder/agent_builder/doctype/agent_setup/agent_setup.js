// Copyright (c) 2026, Faisal Imali and contributors
// For license information, please see license.txt

frappe.ui.form.on("Agent Setup", {
	refresh(frm) {
		frm.set_query("model", function() {
			let filters = {};
			if (frm.doc.provider) {
				filters.provider = frm.doc.provider;
			}
			if (frm.doc.free_models_only) {
				filters.input_price = 0;
				filters.output_price = 0;
			}
			return { filters: filters };
		});

		// Add custom button at the top and style it black
		let btn = frm.add_custom_button(__('Sync Models'), function() {
			frappe.call({
				method: "agent_builder.api.agent.sync_models",
				freeze: true,
				freeze_message: "Syncing models from OpenRouter and LiteLLM...",
				callback: function(r) {
					if(r.message && r.message.status === "success") {
						frappe.msgprint(r.message.message);
					}
				}
			});
		});
		btn.removeClass('btn-default').addClass('btn-dark');
	},
	provider(frm) {
		frm.set_value("model", "");
	},
	free_models_only(frm) {
		frm.set_value("model", "");
	},
	model(frm) {
		if (frm.doc.model) {
			frappe.db.get_value("AI Model", frm.doc.model, [
				"input_price", "output_price", "context_window", 
				"max_output_tokens", "supports_vision", "supports_tool_calling"
			]).then(r => {
				if (r && r.message) {
					frm.set_value("input_price", r.message.input_price);
					frm.set_value("output_price", r.message.output_price);
					frm.set_value("context_window", r.message.context_window);
					frm.set_value("max_output_tokens", r.message.max_output_tokens);
					frm.set_value("supports_vision", r.message.supports_vision);
					frm.set_value("supports_tool_calling", r.message.supports_tool_calling);
				}
			});
		} else {
			frm.set_value("input_price", 0);
			frm.set_value("output_price", 0);
			frm.set_value("context_window", 0);
			frm.set_value("max_output_tokens", 0);
			frm.set_value("supports_vision", 0);
			frm.set_value("supports_tool_calling", 0);
		}
	}
});
