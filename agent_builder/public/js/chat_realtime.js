/**
 * ChatRealtime v4.0
 */
window.ChatRealtime = (function () {

    let _bound = false;
    let _cbs   = {};

    function init(callbacks) {
        _cbs = callbacks;
        if (!_bound) { _bound = true; _bind(); }
    }

    function _bind() {
        frappe.realtime.on('agent_token', (data) => {
            if (!data || !data.delta) return;
            _cbs.onToken && _cbs.onToken(data.delta);
        });

        frappe.realtime.on('agent_event', (data) => {
            if (!data) return;
            if (data.type === 'tool_start') {
                _cbs.onStatusChange && _cbs.onStatusChange(`Running ${data.tool}…`, true);
                _cbs.onToolStart    && _cbs.onToolStart(data);
            } else if (data.type === 'tool_done') {
                _cbs.onStatusChange && _cbs.onStatusChange('Thinking…', true);
                _cbs.onToolDone     && _cbs.onToolDone(data);
            }
        });

        frappe.realtime.on('agent_done', (data) => {
            _cbs.onStatusChange && _cbs.onStatusChange('Ready', false);
            _cbs.onDone         && _cbs.onDone(data || {});
        });

        frappe.realtime.on('agent_error', (data) => {
            _cbs.onStatusChange && _cbs.onStatusChange('Error', false);
            _cbs.onError        && _cbs.onError(data);
        });
    }

    return { init };
})();