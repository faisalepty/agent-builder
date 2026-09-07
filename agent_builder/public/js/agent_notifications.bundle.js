// agent_builder/public/js/notifications.js
//
// Bottom-right floating toast stack for Agent Trigger runs.
//
//   - queued:    blue,  auto-dismisses after 5s
//   - completed: green, auto-dismisses after 8s
//   - failed:    red,   stays until manually dismissed
//
// Binds directly to frappe.realtime.socket (not the frappe.realtime.on
// wrapper — on this stack the wrapper's registrations did not reliably
// survive; a direct socket bind does). Waits for frappe.realtime.socket
// to exist before binding, and re-binds on reconnect.

(function _ab_init() {
	try {
		if (typeof frappe === "undefined" || typeof $ === "undefined" || !frappe.realtime || !frappe.realtime.socket) {
			setTimeout(_ab_init, 500);
			return;
		}

		const $stack = ensureStack();
		ensureStyles();

		function addCard({ kind, message, success, autoDismissMs }) {
			const statusClass = kind === "queued" ? "ab-blue" : success ? "ab-green" : "ab-red";

			const $card = $(`
				<div class="ab-toast ${statusClass}">
					<span class="ab-toast-dot"></span>
					<div class="ab-toast-body">${frappe.utils.escape_html(message)}</div>
					<button class="ab-toast-close" aria-label="Dismiss">&times;</button>
				</div>
			`);

			$card.find(".ab-toast-close").on("click", () => removeCard($card));
			$stack.append($card);
			requestAnimationFrame(() => $card.addClass("ab-in"));

			if (autoDismissMs) setTimeout(() => removeCard($card), autoDismissMs);
			return $card;
		}

		function removeCard($card) {
			$card.removeClass("ab-in");
			setTimeout(() => $card.remove(), 150);
		}

		function ensureStack() {
			let $s = $("#ab-toast-stack");
			if (!$s.length) {
				$s = $('<div id="ab-toast-stack"></div>');
				$("body").append($s);
			}
			return $s;
		}

		function ensureStyles() {
			if (document.getElementById("ab-inline-style")) return;
			const style = document.createElement("style");
			style.id = "ab-inline-style";
			style.textContent = `
				#ab-toast-stack {
					position: fixed; bottom: 24px; right: 24px; z-index: 9999;
					display: flex; flex-direction: column; gap: 10px; max-width: 380px;
				}
				.ab-toast {
					display: flex; align-items: flex-start; gap: 12px;
					background: var(--fg-color, #fff);
					border: 1px solid var(--border-color, #d1d8dd);
					border-left: 5px solid var(--gray-400, #a6b1b9);
					border-radius: 10px;
					box-shadow: 0 10px 28px rgba(0,0,0,0.18), 0 2px 8px rgba(0,0,0,0.10);
					padding: 14px 16px;
					font-size: 13.5px; line-height: 1.5;
					opacity: 0; transform: translateX(16px);
					transition: opacity 0.2s ease, transform 0.2s ease;
				}
				.ab-toast.ab-in { opacity: 1; transform: translateX(0); }
				.ab-toast.ab-blue { border-left-color: var(--blue-500, #2490ef); background: var(--blue-50, #eaf4ff); }
				.ab-toast.ab-green { border-left-color: var(--green-500, #29a745); background: var(--green-50, #eafaf0); }
				.ab-toast.ab-red { border-left-color: var(--red-500, #e24c4c); background: var(--red-50, #fdedec); }
				.ab-toast-dot {
					flex-shrink: 0; width: 11px; height: 11px; border-radius: 50%;
					margin-top: 4px;
				}
				.ab-toast.ab-blue .ab-toast-dot { background: var(--blue-500, #2490ef); }
				.ab-toast.ab-green .ab-toast-dot { background: var(--green-500, #29a745); }
				.ab-toast.ab-red .ab-toast-dot { background: var(--red-500, #e24c4c); }
				.ab-toast-body { flex: 1; color: var(--text-color, #1c2126); font-weight: 500; word-break: break-word; }
				.ab-toast-close {
					background: none; border: none; cursor: pointer;
					font-size: 19px; line-height: 1; color: var(--text-muted, #8d99a6);
					padding: 0 2px;
				}
				.ab-toast-close:hover { color: var(--text-color, #1c2126); }
			`;
			document.head.appendChild(style);
		}

		let pending = [];
		let pendingTimer = null;

		function onProgress(data) {
			if (!data || !data.message) return;
			pending.push(data);
			if (pendingTimer) return;
			pendingTimer = setTimeout(() => {
				const batch = pending;
				pending = [];
				pendingTimer = null;
				if (!batch.length) return;
				const msg = batch.length === 1 ? batch[0].message : __("{0} agent runs queued", [batch.length]);
				addCard({ kind: "queued", message: msg, autoDismissMs: 5000 });
			}, 1200);
		}

		function onComplete(data) {
			if (!data || !data.message) return;
			addCard({
				kind: "complete",
				message: data.message,
				success: data.success,
				autoDismissMs: data.success ? 8000 : null,
			});
		}

		function bindDirect() {
			const socket = frappe.realtime.socket;
			if (!socket) return;
			socket.off("agent_builder_progress", onProgress);
			socket.off("agent_builder_run_complete", onComplete);
			socket.on("agent_builder_progress", onProgress);
			socket.on("agent_builder_run_complete", onComplete);
		}

		bindDirect();
		frappe.realtime.socket.on("connect", bindDirect);

		// Manual test helper — renders fake cards with no realtime involved.
		window._ab_test = function () {
			addCard({ kind: "queued", message: "Test: queued", autoDismissMs: 3000 });
			setTimeout(() => addCard({ kind: "complete", message: "Test: completed", success: true, autoDismissMs: 4000 }), 800);
			setTimeout(() => addCard({ kind: "complete", message: "Test: failed", success: false }), 1600);
		};
	} catch (err) {
		console.error("agent_builder notifications: initialization error", err);
	}
})();