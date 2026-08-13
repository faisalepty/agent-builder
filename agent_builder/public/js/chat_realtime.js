/**
 * ChatRealtime v4.1
 * Now filters incoming socket events by session_id so that multiple tabs
 * open on the same logged-in user (same Frappe realtime "user room") don't
 * bleed tokens/events into each other's active conversation.
 */
window.ChatRealtime = (function () {

    let _bound = false;
    let _cbs   = {};
    let _activeSessionId  = null;   // session currently open in THIS tab
    let _awaitingNewChat  = false;  // true while a brand-new chat's first
                                     // message is in flight (no session_id yet)

    function init(callbacks) {
        _cbs = callbacks;
        if (!_bound) { _bound = true; _bind(); }
    }

    // Call whenever the tab switches to a different (existing) chat.
    function setActiveSession(sessionId) {
        _activeSessionId = sessionId || null;
        _awaitingNewChat = false;
    }

    // Call right before sending the first message of a brand-new chat,
    // where we don't have a session_id yet. The first event that arrives
    // will be adopted as the active session for this tab.
    function expectNewSession() {
        _activeSessionId = null;
        _awaitingNewChat = true;
    }

    function _accepts(data) {
        if (!data || !data.session_id) return true; // no session info, let it through
        if (_awaitingNewChat) {
            // Lock this tab onto the first session_id we see.
            _activeSessionId = data.session_id;
            _awaitingNewChat = false;
            return true;
        }
        return data.session_id === _activeSessionId;
    }

    function _bind() {
        frappe.realtime.on('agent_token', (data) => {
            if (!data || !data.delta) return;
            if (!_accepts(data)) return;
            _cbs.onToken && _cbs.onToken(data.delta);
        });

        frappe.realtime.on('agent_reasoning', (data) => {
            if (!data || !data.delta) return;
            if (!_accepts(data)) return;
            _cbs.onReasoning && _cbs.onReasoning(data.delta);
        });

        frappe.realtime.on('agent_event', (data) => {
            if (!data) return;
            if (!_accepts(data)) return;
            if (data.type === 'tool_start') {
                _cbs.onStatusChange && _cbs.onStatusChange(`Running ${data.tool}…`, true);
                _cbs.onToolStart    && _cbs.onToolStart(data);
            } else if (data.type === 'tool_done') {
                _cbs.onStatusChange && _cbs.onStatusChange('Thinking…', true);
                _cbs.onToolDone     && _cbs.onToolDone(data);
            }
        });

        frappe.realtime.on('agent_done', (data) => {
            if (!_accepts(data)) return;
            _cbs.onStatusChange && _cbs.onStatusChange('Ready', false);
            _cbs.onDone         && _cbs.onDone(data || {});
        });

        frappe.realtime.on('agent_error', (data) => {
            if (!_accepts(data)) return;
            _cbs.onStatusChange && _cbs.onStatusChange('Error', false);
            _cbs.onError        && _cbs.onError(data);
        });

        // --- Headless runs (Agent Trigger / Workflow) ---------------------
        // These are user-scoped, not session-scoped — they represent a
        // background job that isn't tied to whatever chat session this tab
        // happens to have open, so they intentionally skip _accepts().

        frappe.realtime.on('agent_builder_progress', (data) => {
            if (!data) return;
            if (_cbs.onProgress) {
                _cbs.onProgress(data);
            } else {
                frappe.show_alert({ message: data.message, indicator: 'blue' }, 4);
            }
        });

        frappe.realtime.on('agent_builder_run_complete', (data) => {
            if (!data) return;
            if (_cbs.onRunComplete) {
                _cbs.onRunComplete(data);
            } else {
                frappe.msgprint({
                    title: data.title,
                    message: data.message,
                    indicator: data.indicator,
                });
            }
        });
    }
    frappe.realtime.on('agent_builder_progress', (d) => console.log('PROGRESS', d));
frappe.realtime.on('agent_builder_run_complete', (d) => console.log('COMPLETE', d));

    return { init, setActiveSession, expectNewSession };
})();