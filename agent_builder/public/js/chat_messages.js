window.ChatMessages = (function () {

    let _icons = {};
    let streamBubbleId = null;
    let streamBuffer   = '';
    let typingRowId    = null;

    // ── Thinking block state ───────────────────────────────────
    let thinkBlockId   = null;
    let thinkStart     = null;
    let thinkStepCount = 0;
    let activeStepId   = null;
    let toolStartTimes = {};
    const _savedSteps  = {};

    function init(icons) { _icons = icons; }

    function getThinkSteps(id) { return _savedSteps[id] || ''; }

    function clear() {
    $('#ab-messages').empty();
    streamBubbleId = null;
    streamBuffer   = '';
    typingRowId    = null;
    thinkBlockId   = null;
    thinkStart     = null;
    thinkStepCount = 0;
    activeStepId   = null;
    toolStartTimes = {};
    // Clear artifact store on every clear so reopening works cleanly
    Object.keys(_artifacts).forEach(k => delete _artifacts[k]);
}

  function loadHistory(chatId) {
    clear();
    $('#ab-messages').html(`<div class="ab-loading">Loading…</div>`);
    frappe.call({
        method: 'agent_builder.api.agent.get_messages',
        args: { chat_id: chatId },
        callback(r) {
            $('#ab-messages').empty();
            if (!r.message || !r.message.messages.length) {
                $('#ab-messages').html(`<div class="ab-list-empty">No messages yet.</div>`);
                return;
            }
            r.message.messages.forEach(msg => {
                _appendStatic(msg.role === 'user' ? 'user' : 'agent', msg.content);
            });
            // Defer mounting — let jQuery flush all DOM appends first
            setTimeout(() => { _mountArtifacts(); _scrollDown(); }, 60);
        }
    });
}
    function _appendStatic(role, content) {
    const initials = (frappe.session.user || 'U').charAt(0).toUpperCase();
    const id = 'b-' + Date.now() + Math.random().toString(36).slice(2);
    if (role === 'user') {
        $('#ab-messages').append(`
            <div class="ab-row user no-anim">
                <div class="ab-bubble">${frappe.utils.escape_html(content)}</div>
                <div class="ab-avatar">${initials}</div>
            </div>`);
    } else {
        $('#ab-messages').append(`
            <div class="ab-row agent no-anim">
                <div class="ab-avatar">${_icons.bot}</div>
                <div class="ab-bubble" id="${id}">
                    ${_renderContent(content)}
                    <button class="ab-copy-btn" data-bubble="${id}">${_icons.copy} Copy</button>
                </div>
            </div>`);
        // Defer per-message — caller does a final deferred mount after all messages
        setTimeout(() => _mountArtifacts(), 0);
    }
}
    function appendUserMsg(text) {
        const initials = (frappe.session.user || 'U').charAt(0).toUpperCase();
        $('#ab-messages').append(`
            <div class="ab-row user">
                <div class="ab-bubble">${frappe.utils.escape_html(text)}</div>
                <div class="ab-avatar">${initials}</div>
            </div>`);
        _scrollDown();
    }

    function createAgentBubble() {
        hideTyping();
        const id = 'bubble-' + Date.now();
        streamBubbleId = id;
        streamBuffer   = '';
        $('#ab-messages').append(`
            <div class="ab-row agent" id="row-${id}">
                <div class="ab-avatar">${_icons.bot}</div>
                <div class="ab-bubble" id="${id}">
                    <span class="ab-cursor"></span>
                    <button class="ab-copy-btn" data-bubble="${id}">${_icons.copy} Copy</button>
                </div>
            </div>`);
        _scrollDown();
    }

    // ── Thinking block ─────────────────────────────────────────
    function onToolStart(data) {
    if (!thinkBlockId) {
        thinkStart     = Date.now();
        thinkStepCount = 0;
        const id = 'think-' + Date.now();
        thinkBlockId = id;
        $('#ab-messages').append(`
            <div class="ab-think-block" id="${id}">
                <div class="ab-think-steps" id="${id}-steps"></div>
            </div>`);
    }
    thinkStepCount++;
    toolStartTimes[data.tool] = Date.now();
    const stepId = 'step-' + Date.now();
    activeStepId = stepId;

    // Human-readable description instead of raw tool name
    const desc = _describeToolCall(data.tool, data.args);

    $(`#${thinkBlockId}-steps`).append(`
        <div class="ab-think-step" id="${stepId}">
            <span class="ab-think-step-icon ab-spin">${_icons.spin}</span>
            <span class="ab-think-step-name">${desc}</span>
            <span class="ab-think-step-time"></span>
        </div>`);
    _scrollDown();
}

   function onToolDone(data) {
    if (activeStepId) {
        const elapsed = toolStartTimes[data.tool]
            ? ((Date.now() - toolStartTimes[data.tool]) / 1000).toFixed(2) + 's'
            : '';
        // Brief outcome summary instead of tool name
        const summary = _summariseToolResult(data.tool, data.result);
        $(`#${activeStepId}`)
            .find('.ab-think-step-icon').removeClass('ab-spin').html(_icons.check).addClass('ab-think-step-done').end()
            .find('.ab-think-step-name').text(summary).end()
            .find('.ab-think-step-time').text(elapsed);
        activeStepId = null;
    }
    _scrollDown();
}

function _describeToolCall(toolName, argsStr) {
    try {
        const a = typeof argsStr === 'string' ? JSON.parse(argsStr) : (argsStr || {});
        switch (toolName) {
            case 'frappe_get_list': {
                const filterDesc = a.filters && Object.keys(a.filters).length
                    ? ' — filtered'
                    : '';
                const limit = a.limit ? ` (up to ${a.limit})` : '';
                return `Querying ${a.doctype || 'records'}${filterDesc}${limit}`;
            }
            case 'frappe_get_doc':
                return `Reading ${a.doctype} › ${a.name}`;
            case 'frappe_save_doc': {
                const doc = a.doc || {};
                return doc.name
                    ? `Updating ${doc.doctype} › ${doc.name}`
                    : `Creating ${doc.doctype || 'document'}`;
            }
            case 'frappe_delete_doc':
                return `Deleting ${a.doctype} › ${a.name}`;
            case 'skill_view':
                return `Loading skill: ${(a.name || '').split(':').pop()}`;
            case 'skills_list':
                return 'Browsing available skills';
            case 'memory':
                return `Memory: ${a.action || 'recall'}`;
            case 'web_search':
                return `Searching: ${(a.query || '').slice(0, 48)}`;
            case 'web_extract':
                return `Reading: ${(a.url || '').replace(/^https?:\/\//, '').slice(0, 44)}`;
            case 'execute_code':
                return `Running ${a.language || 'code'}`;
            default:
                return toolName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        }
    } catch (e) {
        return toolName.replace(/_/g, ' ');
    }
}

function _summariseToolResult(toolName, resultStr) {
    try {
        const r = typeof resultStr === 'string' ? JSON.parse(resultStr) : resultStr;
        if (r && r.error) return `Error: ${String(r.error).slice(0, 60)}`;
        switch (toolName) {
            case 'frappe_get_list':
                return Array.isArray(r)
                    ? `${r.length} record${r.length !== 1 ? 's' : ''} returned`
                    : 'Query complete';
            case 'frappe_get_doc':
                return r && r.name ? `Loaded ${r.name}` : 'Document loaded';
            case 'frappe_save_doc':
                return r && r.name ? `Saved — ${r.name}` : 'Saved';
            case 'frappe_delete_doc':
                return 'Deleted successfully';
            case 'skill_view':
                return 'Skill loaded';
            case 'web_search':
                return Array.isArray(r) ? `${r.length} results` : 'Search complete';
            default:
                return 'Done';
        }
    } catch (e) {
        return 'Done';
    }
}

    function _finalizeThinking() {
        if (!thinkBlockId) return;
        const id      = thinkBlockId;
        const elapsed = ((Date.now() - thinkStart) / 1000).toFixed(1) + 's';
        const count   = thinkStepCount;

        _savedSteps[id] = $(`#${id}-steps`).html();

        $(`#${id}`).addClass('ab-think-done').html(`
            <div class="ab-think-pill" data-block="${id}">
                <span class="ab-think-pill-icon">${_icons.check}</span>
                <span class="ab-think-pill-label">${count} action${count !== 1 ? 's' : ''}</span>
                <span class="ab-think-pill-time">${elapsed}</span>
                <span class="ab-think-pill-toggle">›</span>
            </div>`);

        thinkBlockId   = null;
        thinkStart     = null;
        thinkStepCount = 0;
    }

    // ── Tokens ─────────────────────────────────────────────────
    function onToken(delta) {
        if (!delta) return;
        if (!streamBubbleId) createAgentBubble();
        streamBuffer += delta;
        $(`#${streamBubbleId}`).html(
            _md(streamBuffer) +
            `<span class="ab-cursor"></span>` +
            `<button class="ab-copy-btn" data-bubble="${streamBubbleId}">${_icons.copy} Copy</button>`
        );
        _scrollDown();
    }

    function onDone(response) {
        hideTyping();
        _finalizeThinking();
        if (!streamBubbleId) createAgentBubble();
        $(`#${streamBubbleId}`).html(
            _renderContent(response || '') +
            `<button class="ab-copy-btn" data-bubble="${streamBubbleId}">${_icons.copy} Copy</button>`
        );
        _mountArtifacts();
        streamBubbleId = null;
        streamBuffer   = '';
        _scrollDown();
    }

    // ── Typing ─────────────────────────────────────────────────
    function showTyping() {
        if (typingRowId) return;
        const id = 'typing-' + Date.now();
        typingRowId = id;
        $('#ab-messages').append(`
            <div class="ab-row agent" id="${id}">
                <div class="ab-avatar">${_icons.bot}</div>
                <div class="ab-typing"><span></span><span></span><span></span></div>
            </div>`);
        _scrollDown();
    }

    function hideTyping() {
        if (typingRowId) { $('#' + typingRowId).remove(); typingRowId = null; }
    }

   // ── Artifact store (memory, not data attribute) ────────────────
const _artifacts = {};

function _renderContent(text) {
    if (!text) return '';

    // Permissive: handles spaces after ```html, \r\n, and \n
    const regex = /`{3}html[ \t]*\r?\n([\s\S]*?)`{3}/g;
    const parts = [];
    let last = 0, match;

    while ((match = regex.exec(text)) !== null) {
        if (match.index > last) {
            parts.push({ type: 'md', content: text.slice(last, match.index) });
        }
        const id = 'art-' + Date.now() + Math.random().toString(36).slice(2, 7);
        _artifacts[id] = _injectResizeScript(match[1]);
        parts.push({ type: 'html', id });
        last = match.index + match[0].length;
    }
    if (last < text.length) {
        parts.push({ type: 'md', content: text.slice(last) });
    }

    // No HTML blocks found — just render markdown
    const hasHtml = parts.some(p => p.type === 'html');
    if (!hasHtml) return _md(text);

    return parts.map(p => {
        if (p.type === 'md') return p.content ? _md(p.content) : '';
        return `
            <div class="ab-artifact" id="${p.id}">
                <div class="ab-artifact-bar">
                    <span class="ab-artifact-label">Interactive</span>
                    <button class="ab-artifact-expand-btn" data-art="${p.id}">⤢</button>
                </div>
                <div class="ab-artifact-frame" id="${p.id}-frame"></div>
            </div>`;
    }).join('');
}

function _injectResizeScript(html) {
    // Injects a postMessage resize script so the iframe reports its height
    const script = `<script>
(function() {
    function send() {
        var h = Math.max(
            document.body ? document.body.scrollHeight : 0,
            document.documentElement ? document.documentElement.scrollHeight : 0
        );
        window.parent.postMessage({ type: 'ab-resize', height: h }, '*');
    }
    window.addEventListener('load', function() {
        send();
        setTimeout(send, 300);
        setTimeout(send, 800);
        if (window.ResizeObserver) {
            new ResizeObserver(send).observe(document.body);
        }
    });
})();
<\/script>`;
    if (html.includes('</body>')) return html.replace('</body>', script + '</body>');
    return html + script;
}

function _mountArtifacts() {
    document.querySelectorAll('.ab-artifact-frame').forEach(function(frame) {
        if (frame.childNodes.length > 0) return; // already mounted
        const artDiv = frame.closest('.ab-artifact');
        if (!artDiv) return;
        const html = _artifacts[artDiv.id];
        if (!html) return;

        const iframe = document.createElement('iframe');
        iframe.setAttribute('sandbox', 'allow-scripts allow-same-origin');
        iframe.className = 'ab-artifact-iframe';
        iframe.style.height = '200px';
        frame.appendChild(iframe);
        iframe.srcdoc = html;
    });
}
    // ── Helpers ────────────────────────────────────────────────
    function _scrollDown() {
        const el = document.getElementById('ab-messages');
        if (el) el.scrollTop = el.scrollHeight;
    }

    function _md(text) {
        if (!text) return '';
        if (window.marked) return marked.parse(text, { breaks: true, gfm: true });
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    return { init, clear, loadHistory, appendUserMsg, onToken, onToolStart, onToolDone, onDone, showTyping, hideTyping, getThinkSteps };

})();