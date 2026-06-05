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
            _mountArtifacts();
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
        $(`#${thinkBlockId}-steps`).append(`
            <div class="ab-think-step" id="${stepId}">
                <span class="ab-think-step-icon ab-spin">${_icons.spin}</span>
                <span class="ab-think-step-name">${data.tool}</span>
                <span class="ab-think-step-time"></span>
            </div>`);
        _scrollDown();
    }

    function onToolDone(data) {
        if (activeStepId) {
            const elapsed = toolStartTimes[data.tool]
                ? ((Date.now() - toolStartTimes[data.tool]) / 1000).toFixed(2) + 's'
                : '';
            $(`#${activeStepId}`)
                .find('.ab-think-step-icon').removeClass('ab-spin').html(_icons.check).addClass('ab-think-step-done').end()
                .find('.ab-think-step-time').text(elapsed);
            activeStepId = null;
        }
        _scrollDown();
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

    // ── Generative UI — sandboxed HTML artifacts ───────────────
    function _renderContent(text) {
        if (!text) return '';
        const regex = /```html\n([\s\S]*?)```/g;
        const parts = [];
        let last = 0, match;

        while ((match = regex.exec(text)) !== null) {
            if (match.index > last) parts.push({ type: 'md', content: text.slice(last, match.index) });
            parts.push({ type: 'html', content: match[1], id: 'art-' + Date.now() + Math.random().toString(36).slice(2) });
            last = match.index + match[0].length;
        }
        if (last < text.length) parts.push({ type: 'md', content: text.slice(last) });
        if (!parts.length) return _md(text);

        return parts.map(p => {
            if (p.type === 'md') return _md(p.content);
            return `<div class="ab-artifact" id="${p.id}" data-html="${encodeURIComponent(p.content)}">
                <div class="ab-artifact-bar">
                    <span class="ab-artifact-label">Preview</span>
                    <button class="ab-artifact-expand-btn" data-art="${p.id}">⤢</button>
                </div>
                <div class="ab-artifact-frame" id="${p.id}-frame"></div>
            </div>`;
        }).join('');
    }

    function _mountArtifacts() {
        $('.ab-artifact-frame:empty').each(function () {
            const artId = $(this).closest('.ab-artifact').attr('id');
            const html  = decodeURIComponent($(`#${artId}`).data('html') || '');
            if (!html) return;
            const iframe = document.createElement('iframe');
            iframe.setAttribute('sandbox', 'allow-scripts allow-same-origin');
            iframe.className = 'ab-artifact-iframe';
            this.appendChild(iframe);
            iframe.contentDocument.open();
            iframe.contentDocument.write(html);
            iframe.contentDocument.close();
            setTimeout(() => {
                try {
                    const h = iframe.contentDocument.documentElement.scrollHeight;
                    iframe.style.height = Math.max(Math.min(h + 8, 420), 80) + 'px';
                } catch(e) { iframe.style.height = '160px'; }
            }, 120);
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