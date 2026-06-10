/**
 * Chat_Ui.js v2.0 — Hermes Agent Chat Orchestrator
 *
 * New in v2:
 *  - Activity Timeline side panel (persistent, inspectable tool log).
 *  - Stop generation button.
 *  - Scroll-to-bottom pill.
 *  - Welcome screen with suggested prompts.
 *  - Char counter with limit warning.
 *  - Artifact reload + fullscreen.
 *  - Per-code-block copy (delegated to ChatMessages).
 *  - Avatar ring animation during thinking.
 */
$(document).ready(function () {

    // ── Markdown ───────────────────────────────────────────────
    if (!window.marked) {
        const s = document.createElement('script');
        s.src = 'https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js';
        document.head.appendChild(s);
    }

    // ── Icon set ───────────────────────────────────────────────
    const ICONS = {
        sparkle:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/></svg>`,
        send:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`,
        close:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
        back:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="15 18 9 12 15 6"/></svg>`,
        newchat:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
        check:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`,
        spin:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>`,
        copy:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>`,
        retry:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>`,
        bot:      `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><line x1="12" y1="7" x2="12" y2="11"/><line x1="8" y1="15" x2="8" y2="17"/><line x1="16" y1="15" x2="16" y2="17"/></svg>`,
        expand:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/></svg>`,
        compress: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="10" y1="14" x2="21" y2="3"/><line x1="3" y1="21" x2="14" y2="10"/></svg>`,
        reload:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>`,
        stop:     `<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>`,
        timeline: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>`,
        down:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>`,
    };

    // ── Suggested prompts ──────────────────────────────────────
    const SUGGESTIONS = [
        { label: 'List records',    text: 'Show me the latest 10 open Sales Orders' },
        { label: 'Create a doc',    text: 'Create a new Lead for Acme Corp with email acme@example.com' },
        { label: 'Summarise data',  text: 'Summarise outstanding invoices by customer' },
        { label: 'Run a report',    text: 'What are the top 5 items sold this month?' },
    ];

    // ── DOM ────────────────────────────────────────────────────
    $('body').append(`
        <button id="ab-launcher" title="Hermes Agent">
            ${ICONS.sparkle}
            <span id="ab-badge"></span>
        </button>

        <div id="ab-window">
            <!-- Header -->
            <div id="ab-header">
                <button id="ab-back" class="ab-hbtn">${ICONS.back}</button>
                <div id="ab-header-avatar">
                    ${ICONS.bot}
                    <div id="ab-avatar-ring"></div>
                </div>
                <div id="ab-header-info">
                    <div id="ab-header-name">Hermes</div>
                    <div id="ab-header-status">
                        <div id="ab-status-dot"></div>
                        <span id="ab-status-text">Ready</span>
                    </div>
                </div>
                <button id="ab-timeline-toggle" class="ab-hbtn" title="Activity log">${ICONS.timeline}</button>
                <button id="ab-new-chat"         class="ab-hbtn" title="New Chat">${ICONS.newchat}</button>
                <button id="ab-expand"            class="ab-hbtn" title="Expand">${ICONS.expand}</button>
                <button id="ab-close"             class="ab-hbtn">${ICONS.close}</button>
            </div>

            <!-- Views -->
            <div id="ab-views">

                <!-- List view -->
                <div id="ab-list-view">
                    <div id="ab-list-search-wrap">
                        <span class="ab-search-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                            </svg>
                        </span>
                        <input id="ab-list-search" type="text" placeholder="Search conversations…" autocomplete="off"/>
                    </div>
                    <div id="ab-list-items"></div>
                </div>

                <!-- Conv view -->
                <div id="ab-conv-view">
                    <div id="ab-conv-body">
                        <!-- Messages -->
                        <div id="ab-messages">
                            <!-- Welcome / suggestions injected here when empty -->
                        </div>

                        <!-- Activity timeline panel -->
                        <div id="ab-timeline">
                            <div id="ab-timeline-header">Activity Log</div>
                            <div id="ab-timeline-items"></div>
                            <!-- Detail popover (absolutely positioned within timeline) -->
                            <div id="ab-tl-detail"></div>
                        </div>
                    </div>

                    <!-- Scroll-to-bottom pill -->
                    <button id="ab-scroll-btn">${ICONS.down} Jump to latest</button>

                    <!-- Input area -->
                    <div id="ab-input-area">
                        <div id="ab-input-box">
                            <textarea id="ab-input" rows="1" placeholder="Ask anything…"></textarea>
                            <div id="ab-input-footer">
                                <span id="ab-input-hint"><kbd>Enter</kbd> send &nbsp;·&nbsp; <kbd>Shift+Enter</kbd> newline</span>
                                <div id="ab-input-footer-right">
                                    <span id="ab-char-count"></span>
                                    <button id="ab-stop" title="Stop generation">${ICONS.stop}</button>
                                    <button id="ab-send">${ICONS.send}</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

            </div><!-- /ab-views -->
        </div><!-- /ab-window -->
    `);

    // Inject welcome screen inside #ab-messages
    const $suggestions = SUGGESTIONS.map(s =>
        `<button class="ab-suggestion-chip" data-text="${frappe.utils.escape_html(s.text)}">
            <strong>${frappe.utils.escape_html(s.label)}</strong>
            ${frappe.utils.escape_html(s.text)}
        </button>`
    ).join('');

    $('#ab-messages').append(`
        <div id="ab-welcome" style="display:none">
            <div id="ab-welcome-icon">${ICONS.sparkle}</div>
            <h3>Hi, I'm Hermes</h3>
            <p>Your ERPNext agent. Ask me to query records,<br>create documents, or run reports.</p>
            <div class="ab-suggestions">${$suggestions}</div>
        </div>
    `);

    // ── State ──────────────────────────────────────────────────
    let isOpen          = false;
    let isThinking      = false;
    let currentChatId   = null;
    let currentView     = 'list';
    let isExpanded      = false;
    let isDragging      = false;
    let dragOffset      = { x: 0, y: 0 };
    let timelineOpen    = false;

    // ── Init modules ───────────────────────────────────────────
    ChatMessages.init(ICONS, {
        onToolEvent: (type, ev) => _syncTimeline(type, ev),
    });

    ChatList.init({
        onSelect: openConversation,
        onNew:    startNewChat,
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
        $('#ab-timeline-toggle').hide();
        $('#ab-header-name').text('Hermes');
        setStatus('Ready', false);
        ChatList.load();
    }

    function showConv(title) {
        currentView = 'conv';
        $('#ab-window').addClass('view-conv');
        $('#ab-back').show();
        $('#ab-new-chat').hide();
        $('#ab-timeline-toggle').show();
        $('#ab-header-name').text(title || 'Chat');
        $('#ab-input').focus();
    }

    function openConversation(chatId, title) {
        currentChatId = chatId;
        ChatList.setActive(chatId);
        showConv(title);
        ChatMessages.loadHistory(chatId);
        _clearTimeline();
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
                _clearTimeline();
                // Show welcome suggestions on fresh chat
                $('#ab-welcome').show();
            }
        });
    }

    // ── Toggle open/close ──────────────────────────────────────
    $(document).on('click', '#ab-launcher', () => isOpen ? _close() : _open());
    $(document).on('click', '#ab-close',    _close);
    $(document).on('click', '#ab-back',     showList);

    function _open() {
        isOpen = true;
        $('#ab-launcher').addClass('is-open');
        $('#ab-window').addClass('open');
        if (currentView === 'list') ChatList.load();
        else if (currentChatId) $('#ab-input').focus();
    }
    function _close() {
        isOpen = false;
        $('#ab-launcher').removeClass('is-open');
        $('#ab-window').removeClass('open');
    }

    // ── Expand ─────────────────────────────────────────────────
    $(document).on('click', '#ab-expand', function () {
        isExpanded = !isExpanded;
        $('#ab-window').toggleClass('ab-expanded', isExpanded);
        $(this).html(isExpanded ? ICONS.compress : ICONS.expand);
        if (isExpanded) {
            $('#ab-window').css({ top: '', left: '', right: '28px', bottom: '92px' });
        }
    });

    // ── Timeline toggle ────────────────────────────────────────
    $(document).on('click', '#ab-timeline-toggle', function () {
        timelineOpen = !timelineOpen;
        $('#ab-timeline').toggleClass('open', timelineOpen);
        $(this).toggleClass('active', timelineOpen);
    });

    // ── Timeline sync ──────────────────────────────────────────
    function _clearTimeline() {
        $('#ab-timeline-items').empty();
        $('#ab-tl-detail').hide().html('');
    }

    function _syncTimeline(type, ev) {
        if (type === 'start') {
            const name = ev.tool.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            $('#ab-timeline-items').append(`
                <div class="ab-tl-entry" id="tl-${ev.id}" data-event-id="${ev.id}">
                    <div class="ab-tl-dot-row">
                        <div class="ab-tl-dot running" id="tl-dot-${ev.id}">${ICONS.spin}</div>
                        <div class="ab-tl-name">${frappe.utils.escape_html(name)}</div>
                    </div>
                    <div class="ab-tl-meta" id="tl-meta-${ev.id}">Running…</div>
                </div>`);
            // Auto-open timeline on first tool call
            if (!timelineOpen && $('#ab-timeline-items .ab-tl-entry').length === 1) {
                timelineOpen = true;
                $('#ab-timeline').addClass('open');
            }
            _scrollTimeline();
        } else if (type === 'done') {
            const elapsed = ev.endMs && ev.startMs ? ((ev.endMs - ev.startMs) / 1000).toFixed(2) + 's' : '';
            $(`#tl-dot-${ev.id}`)
                .removeClass('running')
                .addClass(ev.status === 'error' ? 'error' : 'done')
                .html(ev.status === 'error' ? '!' : ICONS.check);
            $(`#tl-meta-${ev.id}`).text(elapsed);
        }
    }

    function _scrollTimeline() {
        const el = document.getElementById('ab-timeline-items');
        if (el) el.scrollTop = el.scrollHeight;
    }

    // Timeline entry click → show detail popover
    $(document).on('click', '.ab-tl-entry', function () {
        const evId = $(this).data('event-id');
        const ev   = ChatMessages.getToolEvents().find(e => e.id === evId);
        if (!ev) return;

        $('.ab-tl-entry').removeClass('selected');
        $(this).addClass('selected');

        const $detail = $('#ab-tl-detail');
        const argsStr   = typeof ev.args   === 'string' ? ev.args   : JSON.stringify(ev.args,   null, 2);
        const resultStr = typeof ev.result === 'string' ? ev.result : JSON.stringify(ev.result, null, 2);

        $detail.html(`
            <h4>${frappe.utils.escape_html(ev.tool)}</h4>
            <div class="ab-tl-detail-section">
                <div class="ab-tl-detail-label">Arguments</div>
                <div class="ab-tl-detail-code">${frappe.utils.escape_html(argsStr || '—')}</div>
            </div>
            ${ev.result !== null ? `
            <div class="ab-tl-detail-section">
                <div class="ab-tl-detail-label">Result</div>
                <div class="ab-tl-detail-code">${frappe.utils.escape_html((resultStr || '').slice(0, 800))}</div>
            </div>` : ''}
        `).addClass('visible').show();
    });

    // Close detail on outside click
    $(document).on('click', function (e) {
        if (!$(e.target).closest('.ab-tl-entry, #ab-tl-detail').length) {
            $('#ab-tl-detail').removeClass('visible').hide();
            $('.ab-tl-entry').removeClass('selected');
        }
    });

    // ── Think pill interactions ────────────────────────────────
    $(document).on('click', '.ab-think-pill', function (e) {
        if ($(e.target).hasClass('ab-think-pill-tl-btn')) {
            // Show timeline
            timelineOpen = true;
            $('#ab-timeline').addClass('open');
            return;
        }
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

    // ── Artifact ───────────────────────────────────────────────
    $(document).on('click', '.ab-artifact-expand-btn', function () {
        const artId = $(this).data('art');
        $(`#${artId}`).toggleClass('ab-artifact-full');
    });
    $(document).on('click', '.ab-artifact-reload-btn', function () {
        ChatMessages.reloadArtifact($(this).data('art'));
    });

    // ── Scroll-to-bottom ───────────────────────────────────────
    $(document).on('scroll', '#ab-messages', function () {
        const el  = this;
        const atB = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        $('#ab-scroll-btn').toggleClass('visible', !atB);
    });
    $(document).on('click', '#ab-scroll-btn', function () {
        const el = document.getElementById('ab-messages');
        if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    });

    // ── Suggestions ────────────────────────────────────────────
    $(document).on('click', '.ab-suggestion-chip', function () {
        const text = $(this).data('text');
        $('#ab-input').val(text).trigger('input').focus();
    });

    // ── Status / input state ───────────────────────────────────
    function setStatus(text, thinking) {
        $('#ab-status-text').text(text);
        $('#ab-status-dot').toggleClass('thinking', !!thinking).toggleClass('error', false);
        $('#ab-header-avatar').toggleClass('thinking', !!thinking);
    }

    function setInputState(disabled) {
        isThinking = disabled;
        $('#ab-input').prop('disabled', disabled);
        $('#ab-send').prop('disabled', disabled).toggleClass('visible', !disabled);
        $('#ab-stop').toggleClass('visible', disabled);
    }

    // ── Stop ───────────────────────────────────────────────────
    $(document).on('click', '#ab-stop', function () {
        ChatMessages.onStop();
        setInputState(false);
        setStatus('Stopped', false);
    });

    // ── Drag ───────────────────────────────────────────────────
    $(document).on('mousedown', '#ab-header', function (e) {
        if ($(e.target).closest('button, .ab-hbtn').length || isExpanded) return;
        const rect = document.getElementById('ab-window').getBoundingClientRect();
        isDragging = true;
        dragOffset = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        $('#ab-window').css({ right: 'auto', bottom: 'auto', top: rect.top, left: rect.left });
        e.preventDefault();
    });
    $(document).on('mousemove', function (e) {
        if (!isDragging) return;
        const $w = $('#ab-window'), vw = window.innerWidth, vh = window.innerHeight;
        const w  = $w.outerWidth(), h = $w.outerHeight();
        const x  = Math.max(0, Math.min(e.clientX - dragOffset.x, vw - w));
        const y  = Math.max(0, Math.min(e.clientY - dragOffset.y, vh - h));
        $w.css({ left: x, top: y });
    });
    $(document).on('mouseup', () => { isDragging = false; });

    // ── Send ───────────────────────────────────────────────────
    function sendMessage() {
        const msg = $('#ab-input').val().trim();
        if (!msg || isThinking) return;
        $('#ab-input').val('').css('height', 'auto');
        $('#ab-char-count').text('').removeClass('near-limit at-limit');
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

    const MAX_CHARS = 4000;
    $(document).on('input', '#ab-input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
        const len = this.value.length;
        if (len > MAX_CHARS * 0.7) {
            $('#ab-char-count')
                .text(`${len}/${MAX_CHARS}`)
                .toggleClass('near-limit', len < MAX_CHARS)
                .toggleClass('at-limit', len >= MAX_CHARS);
        } else {
            $('#ab-char-count').text('').removeClass('near-limit at-limit');
        }
    });

    // ── Copy buttons ───────────────────────────────────────────
    $(document).on('click', '.ab-copy-btn', function () {
        const id   = $(this).data('bubble');
        const text = $('#' + id).text();
        navigator.clipboard.writeText(text).then(() => {
            $(this).html(ICONS.check + ' Copied!');
            setTimeout(() => $(this).html(ICONS.copy + ' Copy'), 1500);
        });
    });

    // ── Retry (re-send the user message) ──────────────────────
    $(document).on('click', '.ab-retry-btn', function () {
        const id   = $(this).data('bubble');
        const text = $('#' + id).text().trim();
        if (text && !isThinking) {
            $('#ab-input').val(text);
            sendMessage();
        }
    });

    // Initial header state
    $('#ab-back').hide();
    $('#ab-timeline-toggle').hide();

});