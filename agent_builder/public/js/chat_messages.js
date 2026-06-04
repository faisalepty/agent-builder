window.ChatMessages = (function () {

    let _icons = {};
    let streamBubbleId = null;
    let streamBuffer   = '';
    let toolBlockId    = null;
    let activeToolId   = null;
    let toolStartTimes = {};
    let typingRowId    = null;

    function init(icons) { _icons = icons; }

    function clear() {
        $('#ab-messages').empty();
        streamBubbleId = null;
        streamBuffer   = '';
        toolBlockId    = null;
        activeToolId   = null;
        toolStartTimes = {};
        typingRowId    = null;
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
                    if (msg.role === 'user') _appendStatic('user', msg.content);
                    else _appendStatic('agent', msg.content);
                });
                _scrollDown();
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
                </div>
            `);
        } else {
            $('#ab-messages').append(`
                <div class="ab-row agent no-anim">
                    <div class="ab-avatar">${_icons.bot}</div>
                    <div class="ab-bubble" id="${id}">
                        ${_md(content)}
                        <button class="ab-copy-btn" data-bubble="${id}">${_icons.copy} Copy</button>
                    </div>
                </div>
            `);
        }
    }

    function appendUserMsg(text) {
        const initials = (frappe.session.user || 'U').charAt(0).toUpperCase();
        $('#ab-messages').append(`
            <div class="ab-row user">
                <div class="ab-bubble">${frappe.utils.escape_html(text)}</div>
                <div class="ab-avatar">${initials}</div>
            </div>
        `);
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
            </div>
        `);
        _scrollDown();
    }

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

    function onToolStart(data) {
        if (!toolBlockId) {
            const id = 'tools-' + Date.now();
            toolBlockId = id;
            $('#ab-messages').append(`<div class="ab-tool-block" id="${id}"></div>`);
        }
        const id = 'tool-' + Date.now();
        activeToolId = id;
        toolStartTimes[data.tool] = Date.now();
        $(`#${toolBlockId}`).append(`
            <div class="ab-tool-item running" id="${id}">
                <span class="ab-tool-icon ab-spin">${_icons.spin}</span>
                <span class="ab-tool-name">${data.tool}</span>
            </div>
        `);
        _scrollDown();
    }

    function onToolDone(data) {
        const elapsed = toolStartTimes[data.tool]
            ? ((Date.now() - toolStartTimes[data.tool]) / 1000).toFixed(2) + 's'
            : '';
        if (activeToolId) {
            $(`#${activeToolId}`)
                .removeClass('running').addClass('done')
                .html(`
                    <span class="ab-tool-icon">${_icons.check}</span>
                    <span class="ab-tool-name">${data.tool}</span>
                    <span class="ab-tool-time">${elapsed}</span>
                `);
        }
        activeToolId = null;
        _scrollDown();
    }

    function onDone(response) {
        hideTyping();
        if (!streamBubbleId) createAgentBubble();
        $(`#${streamBubbleId}`).html(
            _md(response || '') +
            `<button class="ab-copy-btn" data-bubble="${streamBubbleId}">${_icons.copy} Copy</button>`
        );
        streamBubbleId = null;
        streamBuffer   = '';
        toolBlockId    = null;
        activeToolId   = null;
        _scrollDown();
    }

    function showTyping() {
        if (typingRowId) return;
        const id = 'typing-' + Date.now();
        typingRowId = id;
        $('#ab-messages').append(`
            <div class="ab-row agent" id="${id}">
                <div class="ab-avatar">${_icons.bot}</div>
                <div class="ab-typing"><span></span><span></span><span></span></div>
            </div>
        `);
        _scrollDown();
    }

    function hideTyping() {
        if (typingRowId) { $('#' + typingRowId).remove(); typingRowId = null; }
    }

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

    return { init, clear, loadHistory, appendUserMsg, onToken, onToolStart, onToolDone, onDone, showTyping, hideTyping };

})();