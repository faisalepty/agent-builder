$(document).ready(function () {

    // ── Load marked.js for markdown rendering ──────────────────
    if (!window.marked) {
        const s = document.createElement('script');
        s.src = 'https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js';
        document.head.appendChild(s);
    }

    // ── Icons (inline SVG) ─────────────────────────────────────
    const ICONS = {
        sparkle: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/></svg>`,
        send:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`,
        close:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
        tool:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>`,
        check:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`,
        spin:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>`,
        copy:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>`,
        bot:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><line x1="12" y1="7" x2="12" y2="11"/><line x1="8" y1="15" x2="8" y2="17"/><line x1="16" y1="15" x2="16" y2="17"/></svg>`,
    };

    // ── Inject HTML ────────────────────────────────────────────
    $('body').append(`
        <button id="ab-launcher" title="Agent Builder">${ICONS.sparkle}</button>
        <div id="ab-window">
            <div id="ab-header">
                <div id="ab-header-avatar">${ICONS.bot}</div>
                <div id="ab-header-info">
                    <div id="ab-header-name">Agent Builder</div>
                    <div id="ab-header-status">
                        <div id="ab-status-dot"></div>
                        <span id="ab-status-text">Ready</span>
                    </div>
                </div>
                <button id="ab-close">${ICONS.close}</button>
            </div>
            <div id="ab-messages">
                <div class="ab-row agent">
                    <div class="ab-avatar">${ICONS.bot}</div>
                    <div class="ab-bubble">Hello! I have full access to your Frappe data. What can I help you with?</div>
                </div>
            </div>
            <div id="ab-input-area">
                <textarea id="ab-input" rows="1" placeholder="Ask anything about your data…"></textarea>
                <button id="ab-send">${ICONS.send}</button>
            </div>
        </div>
    `);

    // ── State ──────────────────────────────────────────────────
    let isOpen      = false;
    let isThinking  = false;
    let streamBubbleId  = null;
    let streamBuffer    = '';
    let toolBlockId     = null;
    let activeToolId    = null;
    let toolStartTimes  = {};
    let typingRowId     = null;

    // ── Toggle ─────────────────────────────────────────────────
    function openChat()  { isOpen = true;  $('#ab-window').addClass('open'); $('#ab-input').focus(); }
    function closeChat() { isOpen = false; $('#ab-window').removeClass('open'); }

    $(document).on('click', '#ab-launcher', () => isOpen ? closeChat() : openChat());
    $(document).on('click', '#ab-close',    () => closeChat());

    // ── Scroll ─────────────────────────────────────────────────
    const scrollDown = () => {
        const el = document.getElementById('ab-messages');
        if (el) el.scrollTop = el.scrollHeight;
    };

    // ── Markdown render (safe fallback if marked not loaded) ───
    const renderMd = (text) => {
        if (!text) return '';
        if (window.marked) {
            return marked.parse(text, { breaks: true, gfm: true });
        }
        // Fallback: minimal formatting
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    };

    // ── Status helpers ─────────────────────────────────────────
    function setStatus(text, thinking = false) {
        $('#ab-status-text').text(text);
        $('#ab-status-dot').toggleClass('thinking', thinking);
    }

    function setInputState(disabled) {
        isThinking = disabled;
        $('#ab-input').prop('disabled', disabled);
        $('#ab-send').prop('disabled', disabled);
    }

    // ── Typing indicator ───────────────────────────────────────
    function showTyping() {
        if (typingRowId) return;
        const id = 'typing-' + Date.now();
        typingRowId = id;
        $('#ab-messages').append(`
            <div class="ab-row agent" id="${id}">
                <div class="ab-avatar">${ICONS.bot}</div>
                <div class="ab-typing"><span></span><span></span><span></span></div>
            </div>
        `);
        scrollDown();
    }

    function hideTyping() {
        if (typingRowId) {
            $('#' + typingRowId).remove();
            typingRowId = null;
        }
    }

    // ── Append user message ────────────────────────────────────
    function appendUserMsg(text) {
        const initials = (frappe.session.user || 'U').charAt(0).toUpperCase();
        $('#ab-messages').append(`
            <div class="ab-row user">
                <div class="ab-bubble">${frappe.utils.escape_html(text)}</div>
                <div class="ab-avatar">${initials}</div>
            </div>
        `);
        scrollDown();
    }

    // ── Create agent bubble for streaming ─────────────────────
    function createAgentBubble() {
        hideTyping();
        const id = 'bubble-' + Date.now();
        streamBubbleId = id;
        streamBuffer   = '';
        $('#ab-messages').append(`
            <div class="ab-row agent" id="row-${id}">
                <div class="ab-avatar">${ICONS.bot}</div>
                <div class="ab-bubble" id="${id}">
                    <span class="ab-cursor"></span>
                    <button class="ab-copy-btn" data-bubble="${id}">
                        ${ICONS.copy} Copy
                    </button>
                </div>
            </div>
        `);
        scrollDown();
    }

    // ── Tool block ─────────────────────────────────────────────
    function ensureToolBlock() {
        if (toolBlockId) return;
        const id = 'tools-' + Date.now();
        toolBlockId = id;
        $('#ab-messages').append(`<div class="ab-tool-block" id="${id}"></div>`);
    }

    // ── Send ───────────────────────────────────────────────────
    function sendMessage() {
        const msg = $('#ab-input').val().trim();
        if (!msg || isThinking) return;

        $('#ab-input').val('').css('height', 'auto');
        appendUserMsg(msg);
        setInputState(true);
        setStatus('Thinking…', true);
        showTyping();

        // Reset state
        streamBubbleId = null;
        streamBuffer   = '';
        toolBlockId    = null;
        activeToolId   = null;
        toolStartTimes = {};

        frappe.call({ method: 'agent_builder.api.agent.chat', args: { message: msg } });
    }

    $(document).on('click', '#ab-send', sendMessage);
    $(document).on('keydown', '#ab-input', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });

    // ── Auto-resize textarea ───────────────────────────────────
    $(document).on('input', '#ab-input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
    });

    // ── Copy button ────────────────────────────────────────────
    $(document).on('click', '.ab-copy-btn', function () {
        const bubbleId = $(this).data('bubble');
        const text = $('#' + bubbleId).text();
        navigator.clipboard.writeText(text).then(() => {
            $(this).html(ICONS.check + ' Copied!');
            setTimeout(() => { $(this).html(ICONS.copy + ' Copy'); }, 1500);
        });
    });

    // ── Realtime: streaming token ──────────────────────────────
  frappe.realtime.on('agent_token', (data) => {
    // console.log('Agent token received:', data);
    if (!data.delta) return;   // ← guard against null delta
    if (!streamBubbleId) createAgentBubble();
    streamBuffer += data.delta;
    $(`#${streamBubbleId}`).html(
        renderMd(streamBuffer) +
        `<span class="ab-cursor"></span>` +
        `<button class="ab-copy-btn" data-bubble="${streamBubbleId}">${ICONS.copy} Copy</button>`
    );
    scrollDown();
});

    // ── Realtime: tool events ──────────────────────────────────
    frappe.realtime.on('agent_event', (data) => {
        // console.log('Agent event received:', data);
        ensureToolBlock();

        if (data.type === 'tool_start') {
            const id = 'tool-' + Date.now();
            activeToolId = id;
            toolStartTimes[data.tool] = Date.now();
            $(`#${toolBlockId}`).append(`
                <div class="ab-tool-item running" id="${id}">
                    <span class="ab-tool-icon ab-spin">${ICONS.spin}</span>
                    <span class="ab-tool-name">${data.tool}</span>
                </div>
            `);
            setStatus(`Running ${data.tool}…`, true);

        } else if (data.type === 'tool_done') {
            const elapsed = toolStartTimes[data.tool]
                ? ((Date.now() - toolStartTimes[data.tool]) / 1000).toFixed(2) + 's'
                : '';
            if (activeToolId) {
                $(`#${activeToolId}`)
                    .removeClass('running')
                    .addClass('done')
                    .html(`
                        <span class="ab-tool-icon">${ICONS.check}</span>
                        <span class="ab-tool-name">${data.tool}</span>
                        <span class="ab-tool-time">${elapsed}</span>
                    `);
            }
            activeToolId = null;
            setStatus('Thinking…', true);
        }
        scrollDown();
    });

    // ── Realtime: done ─────────────────────────────────────────
    frappe.realtime.on('agent_done', (data) => {
        // console.log('Agent done event received:', data);
    hideTyping();
    if (!streamBubbleId) createAgentBubble();
    $(`#${streamBubbleId}`).html(
        renderMd(data.response || '')  +  // ← guard against null response
        `<button class="ab-copy-btn" data-bubble="${streamBubbleId}">${ICONS.copy} Copy</button>`
    );
    streamBubbleId = null;
    streamBuffer   = '';
    toolBlockId    = null;
    activeToolId   = null;
    setInputState(false);
    setStatus('Ready', false);
    $('#ab-input').focus();
    scrollDown();
});

});