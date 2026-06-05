$(document).ready(function () {

    if (!window.marked) {
        const s = document.createElement('script');
        s.src = 'https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js';
        document.head.appendChild(s);
    }

    const ICONS = {
        sparkle:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/></svg>`,
        send:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`,
        close:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
        back:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="15 18 9 12 15 6"/></svg>`,
        newchat:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
        check:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`,
        spin:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>`,
        copy:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>`,
        bot:      `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><line x1="12" y1="7" x2="12" y2="11"/><line x1="8" y1="15" x2="8" y2="17"/><line x1="16" y1="15" x2="16" y2="17"/></svg>`,
        expand:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/></svg>`,
        compress: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="10" y1="14" x2="21" y2="3"/><line x1="3" y1="21" x2="14" y2="10"/></svg>`,
    };

    $('body').append(`
        <button id="ab-launcher" title="Agent Builder">${ICONS.sparkle}</button>
        <div id="ab-window">
            <div id="ab-header">
                <button id="ab-back">${ICONS.back}</button>
                <button id="ab-back">${ICONS.back}</button>
                <div id="ab-header-avatar">${ICONS.bot}</div>
                <div id="ab-header-info">
                    <div id="ab-header-name">Agent Builder</div>
                    <div id="ab-header-status">
                        <div id="ab-status-dot"></div>
                        <span id="ab-status-text">Ready</span>
                    </div>
                </div>
                <button id="ab-new-chat" title="New Chat">${ICONS.newchat}</button>
                <button id="ab-expand" title="Expand">${ICONS.expand}</button>
                <button id="ab-close">${ICONS.close}</button>
            </div>
            <div id="ab-views">
                <div id="ab-list-view">
                    <div id="ab-list-items"></div>
                </div>
                <div id="ab-conv-view">
                    <div id="ab-messages"></div>
                    <div id="ab-input-area">
                        <textarea id="ab-input" rows="1" placeholder="Ask anything…"></textarea>
                        <button id="ab-send">${ICONS.send}</button>
                    </div>
                </div>
                <div id="ab-conv-view">
                    <div id="ab-messages"></div>
                    <div id="ab-input-area">
                        <textarea id="ab-input" rows="1" placeholder="Ask anything…"></textarea>
                        <button id="ab-send">${ICONS.send}</button>
                    </div>
                </div>
            </div>
        </div>
    `);

    // ── State ──────────────────────────────────────────────────
    let isOpen        = false;
    let isThinking    = false;
    let currentChatId = null;
    let currentView   = 'list';
    let isExpanded    = false;
    let isDragging    = false;
    let dragOffset    = { x: 0, y: 0 };

    // ── Init modules ───────────────────────────────────────────
    ChatMessages.init(ICONS);

    ChatList.init({
        onSelect: openConversation,
        onNew:    startNewChat,          // ← fixed (was showConv)
    });

    ChatRealtime.init({
        onToken:        (delta) => ChatMessages.onToken(delta),
        onToolStart:    (data)  => ChatMessages.onToolStart(data),
        onToolDone:     (data)  => ChatMessages.onToolDone(data),
        onStatusChange: setStatus,
        onDone: (data) => {
            ChatMessages.onDone(data.response);
            setInputState(false);
            $('#ab-input').focus();
        },
    });

    // ── Views ──────────────────────────────────────────────────
    function showList() {
        currentView = 'list';
        $('#ab-window').removeClass('view-conv');
        $('#ab-back').hide();
        $('#ab-new-chat').show();
        $('#ab-header-name').text('Agent Builder');
        setStatus('Ready', false);
        ChatList.load();
    }

    function showConv(title) {
        currentView = 'conv';
        $('#ab-window').addClass('view-conv');
        $('#ab-back').show();
        $('#ab-new-chat').hide();
        $('#ab-header-name').text(title || 'Chat');
        $('#ab-input').focus();
    }

    function openConversation(chatId, title) {
        currentChatId = chatId;
        showConv(title);
        ChatMessages.loadHistory(chatId);
    }

    function startNewChat() {
        frappe.call({
            method: 'agent_builder.api.agent.new_chat',
            callback(r) {
                if (!r.message) return;
                currentChatId = r.message.chat_id;
                ChatList.prepend(r.message);
                ChatMessages.clear();
                showConv(r.message.title);
            }
        });
    }

    // ── Toggle ─────────────────────────────────────────────────
    $(document).on('click', '#ab-launcher', () => isOpen ? _close() : _open());
    $(document).on('click', '#ab-close',    _close);
    $(document).on('click', '#ab-back',     showList);

    function _open() {
        isOpen = true;
        $('#ab-window').addClass('open');
        if (currentView === 'list') ChatList.load();
        else if (currentChatId) $('#ab-input').focus();
    }
    function _close() {
        isOpen = false;
        $('#ab-window').removeClass('open');
    }

    // ── Expand ─────────────────────────────────────────────────
    $(document).on('click', '#ab-expand', function () {
        isExpanded = !isExpanded;
        $('#ab-window').toggleClass('ab-expanded', isExpanded);
        $(this).html(isExpanded ? ICONS.compress : ICONS.expand);
        // Reset drag when expanding/compressing
        if (isExpanded) {
            $('#ab-window').css({ top: '', left: '', right: '28px', bottom: '92px' });
        }
    });

    // ── Drag ───────────────────────────────────────────────────
    $(document).on('mousedown', '#ab-header', function (e) {
        if ($(e.target).closest('button').length || isExpanded) return;
        const rect = document.getElementById('ab-window').getBoundingClientRect();
        isDragging  = true;
        dragOffset  = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        $('#ab-window').css({ right: 'auto', bottom: 'auto', top: rect.top, left: rect.left });
        e.preventDefault();
    });

    $(document).on('mousemove', function (e) {
        if (!isDragging) return;
        const $w = $('#ab-window');
        const vw = window.innerWidth, vh = window.innerHeight;
        const w  = $w.outerWidth(), h = $w.outerHeight();
        const x  = Math.max(0, Math.min(e.clientX - dragOffset.x, vw - w));
        const y  = Math.max(0, Math.min(e.clientY - dragOffset.y, vh - h));
        $w.css({ left: x, top: y });
    });

    $(document).on('mouseup', () => { isDragging = false; });

    // ── Think pill expand ──────────────────────────────────────
    $(document).on('click', '.ab-think-pill', function () {
        const blockId = $(this).data('block');
        const $block  = $(`#${blockId}`);
        const isOpen  = $block.hasClass('ab-think-open');
        if (isOpen) {
            $block.removeClass('ab-think-open').find('.ab-think-detail').slideUp(160);
            $(this).find('.ab-think-pill-toggle').text('›');
        } else {
            if (!$block.find('.ab-think-detail').length) {
                const steps = ChatMessages.getThinkSteps(blockId);
                $block.append(`<div class="ab-think-detail" style="display:none">${steps}</div>`);
            }
            $block.addClass('ab-think-open').find('.ab-think-detail').slideDown(160);
            $(this).find('.ab-think-pill-toggle').text('⌄');
        }
    });

    // ── Artifact expand ────────────────────────────────────────
    $(document).on('click', '.ab-artifact-expand-btn', function () {
        const artId = $(this).data('art');
        $(`#${artId}`).toggleClass('ab-artifact-full');
    });

    // ── Status ─────────────────────────────────────────────────
    // ── Status ─────────────────────────────────────────────────
    function setStatus(text, thinking = false) {
        $('#ab-status-text').text(text);
        $('#ab-status-dot').toggleClass('thinking', thinking);
    }
    function setInputState(disabled) {
        isThinking = disabled;
        $('#ab-input').prop('disabled', disabled);
        $('#ab-send').prop('disabled', disabled);
    }

    // ── Send ───────────────────────────────────────────────────
    function sendMessage() {
        const msg = $('#ab-input').val().trim();
        if (!msg || isThinking) return;
        $('#ab-input').val('').css('height', 'auto');
        ChatMessages.appendUserMsg(msg);
        ChatMessages.appendUserMsg(msg);
        setInputState(true);
        setStatus('Thinking…', true);
        ChatMessages.showTyping();
        frappe.call({
            method: 'agent_builder.api.agent.chat',
            args: { message: msg, chat_id: currentChatId },
            callback(r) {
                if (r.message && r.message.chat_id) {
                    currentChatId = r.message.chat_id;
                }
            }
        });
    }

    $(document).on('click', '#ab-send', sendMessage);
    $(document).on('keydown', '#ab-input', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
    $(document).on('input', '#ab-input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
    });
    $(document).on('click', '.ab-copy-btn', function () {
        const id   = $(this).data('bubble');
        const text = $('#' + id).text();
        navigator.clipboard.writeText(text).then(() => {
            $(this).html(ICONS.check + ' Copied!');
            setTimeout(() => $(this).html(ICONS.copy + ' Copy'), 1500);
            setTimeout(() => $(this).html(ICONS.copy + ' Copy'), 1500);
        });
    });
    });

});