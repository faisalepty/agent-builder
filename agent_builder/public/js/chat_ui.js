/**
 * Chat_Ui.js v4.0 — SOTA Hermes Orchestrator
 * Updated Lucide-style thin icons, streamlined input DOM structure, and logic hooks.
 */
$(document).ready(function () {

    if (!window.marked) {
        const s = document.createElement('script');
        s.src = 'https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js';
        document.head.appendChild(s);
    }

    // ── Modern Lucide-style Icons (stroke-width: 1.5) ──────────
    const ICONS = {
        sparkle:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/></svg>`,
        send:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>`, // Up Arrow
        close:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
        back:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="15 18 9 12 15 6"/></svg>`,
        newchat:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
        check:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="20 6 9 17 4 12"/></svg>`,
        spin:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>`,
        copy:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>`,
        retry:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>`,
        bot:      `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>`, // Spark / AI Logo
        expand:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/></svg>`,
        compress: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="10" y1="14" x2="21" y2="3"/><line x1="3" y1="21" x2="14" y2="10"/></svg>`,
        reload:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>`,
        stop:     `<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="7" width="10" height="10" rx="1"/></svg>`,
        down:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>`,
    };

    const SUGGESTIONS = [
        { label: 'List records',    text: 'Show me the latest 10 open Sales Orders' },
        { label: 'Create a doc',    text: 'Create a new Lead for Acme Corp with email acme@example.com' },
        { label: 'Summarise data',  text: 'Summarise outstanding invoices by customer' },
        { label: 'Run a report',    text: 'What are the top 5 items sold this month?' },
    ];

    // ── SOTA DOM Structure Injection ───────────────────────────
    $('body').append(`
        <button id="ab-launcher" title="Hermes Chat">
            ${ICONS.sparkle}
            <span id="ab-badge"></span>
        </button>

        <div id="ab-window">
            <div id="ab-header">
                <button id="ab-back" class="ab-hbtn" title="Back">${ICONS.back}</button>
                <div id="ab-header-avatar">${ICONS.bot}</div>
                <div id="ab-header-info">
                    <div id="ab-header-name">Hermes</div>
                    <div id="ab-header-status">
                        <div id="ab-status-dot"></div>
                        <span id="ab-status-text">Ready</span>
                    </div>
                </div>
                <button id="ab-new-chat" class="ab-hbtn" title="New Chat">${ICONS.newchat}</button>
                <button id="ab-expand"   class="ab-hbtn" title="Expand">${ICONS.expand}</button>
                <button id="ab-close"    class="ab-hbtn" title="Close">${ICONS.close}</button>
            </div>

            <div id="ab-views">
                <div id="ab-list-view">
                    <div id="ab-list-search-wrap">
                        <span class="ab-search-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                            </svg>
                        </span>
                        <input id="ab-list-search" type="text" placeholder="Search conversations…" autocomplete="off"/>
                    </div>
                    <div id="ab-list-items"></div>
                </div>

                <div id="ab-conv-view">
                    <div id="ab-conv-body">
                        <div id="ab-messages"></div>
                    </div>
                    <button id="ab-scroll-btn">${ICONS.down} Jump to latest</button>
                    <div id="ab-input-area">
                        <div id="ab-input-box">
                            <textarea id="ab-input" rows="1" placeholder="Ask Hermes anything…"></textarea>
                            <div id="ab-input-actions">
                                <span id="ab-char-count"></span>
                                <button id="ab-stop" title="Stop generation">${ICONS.stop}</button>
                                <button id="ab-send" title="Send">${ICONS.send}</button>
                            </div>
                        </div>
                        <div id="ab-input-footer">
                            <span id="ab-input-hint">Shift + Enter for new line</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `);

    // Reusable function to render the welcome layout dynamically
    function renderWelcomeScreen() {
        // Defensive check to prevent scripts crashing if frappe utilities aren't fully ready
        const escape = (txt) => (window.frappe && frappe.utils && frappe.utils.escape_html)
            ? frappe.utils.escape_html(txt)
            : txt.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

        const chipsHtml = SUGGESTIONS.map(s => `
            <button class="ab-suggestion-chip" data-text="${escape(s.text)}">
                <strong>${escape(s.label)}</strong>
                ${escape(s.text)}
            </button>
        `).join('');

        // Remove old instances if any exist, then append clean
        $('#ab-welcome').remove();
        $('#ab-messages').append(`
            <div id="ab-welcome">
                <div id="ab-welcome-icon">${ICONS.sparkle}</div>
                <h3>How can I help you today?</h3>
                <p>I can query records, create documents, or run reports for you.</p>
                <div class="ab-suggestions">${chipsHtml}</div>
            </div>
        `);
    }

    // const $suggestions = SUGGESTIONS.map(s =>
    //     `<button class="ab-suggestion-chip" data-text="${frappe.utils.escape_html(s.text)}">
    //         <strong>${frappe.utils.escape_html(s.label)}</strong>
    //         ${frappe.utils.escape_html(s.text)}
    //     </button>`
    // ).join('');
    // $('#ab-messages').append(`
    //     <div id="ab-welcome" style="display:none">
    //         <div id="ab-welcome-icon">${ICONS.sparkle}</div>
    //         <h3>How can I help you today?</h3>
    //         <p>I can query records, create documents, or run reports for you.</p>
    //         <div class="ab-suggestions">${$suggestions}</div>
    //     </div>
    // `);

    // State
    let isOpen = false, isThinking = false, currentChatId = null, currentView = 'list', isExpanded = false;

    ChatMessages.init(ICONS);
    ChatList.init({ onSelect: openConversation, onNew: startNewChat });
    ChatRealtime.init({
        onToken: (delta) => ChatMessages.onToken(delta),
        onToolStart: (data) => ChatMessages.onToolStart(data),
        onToolDone: (data) => ChatMessages.onToolDone(data),
        onStatusChange: setStatus,
        onDone: (data) => {
            ChatMessages.onDone(data.response);
            setInputState(false);
            setTimeout(() => $('#ab-input').focus(), 50);
        },
    });

    function showList() {
        currentView = 'list';
        $('#ab-window').removeClass('view-conv');
        $('#ab-back').hide();
        $('#ab-new-chat').show();
        $('#ab-header-name').text('Hermes');
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
        ChatList.setActive(chatId);
        showConv(title);
        ChatMessages.loadHistory(chatId);
    }

    function startNewChat() {
        // Clear runtime tracking to signify an un-saved conversation state
        currentChatId = null;
        
        // Prepare UI views instantly
        ChatMessages.clear();
        showConv('New Chat');
        renderWelcomeScreen();
    }

    $(document).on('click', '#ab-launcher', () => isOpen ? _close() : _open());
    $(document).on('click', '#ab-close', _close);
    $(document).on('click', '#ab-back', showList);

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

    $(document).on('click', '#ab-expand', function () {
        isExpanded = !isExpanded;
        $('#ab-window').toggleClass('ab-expanded', isExpanded);
        $(this).html(isExpanded ? ICONS.compress : ICONS.expand);
        if (isExpanded) $('#ab-window').css({ top: '', left: '', right: '32px', bottom: '32px' });
    });

    $(document).on('click', '.ab-artifact-reload', function() {
        const artifactId = $(this).data('artifact');
        if (artifactId) ChatMessages.reloadArtifact(artifactId);
    });
    $(document).on('click', '.ab-artifact-expand', function() {
        const artifactId = $(this).data('artifact');
        if (artifactId) ChatMessages.expandArtifact(artifactId);
    });

    $(document).on('scroll', '#ab-messages', function () {
        const el = this;
        const atB = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
        $('#ab-scroll-btn').toggleClass('visible', !atB);
    });
    $(document).on('click', '#ab-scroll-btn', function () {
        const el = document.getElementById('ab-messages');
        if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    });

    $(document).on('click', '.ab-suggestion-chip', function () {
        $('#ab-input').val($(this).data('text')).trigger('input').focus();
    });

    function setStatus(text, thinking) {
        $('#ab-status-text').text(text);
        $('#ab-status-dot').toggleClass('thinking', !!thinking).toggleClass('error', false);
    }

    function setInputState(disabled) {
        isThinking = disabled;
        $('#ab-input').prop('disabled', disabled);
        $('#ab-send').toggle(!disabled);
        $('#ab-stop').toggleClass('visible', disabled);
    }

    $(document).on('click', '#ab-stop', function () {
        ChatMessages.onStop();
        setInputState(false);
        setStatus('Stopped', false);
    });

    function sendMessage() {
        const msg = $('#ab-input').val().trim();
        if (!msg || isThinking) return;
        
        // Check if this is the initial message of a deferred session
        const isFirstMessage = (currentChatId === null);

        // CLEAR WELCOME SCREEN: Remove the welcome element if this is the first message
        if (isFirstMessage) {
            $('#ab-welcome').remove();
        }

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
                    
                    // If this was a deferred chat initialization, update the sidebar UI registry now
                    if (isFirstMessage) {
                        ChatList.prepend(r.message);
                        ChatList.setActive(currentChatId);
                        $('#ab-header-name').text(r.message.title || 'Chat');
                    }
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
        this.style.height = Math.min(this.scrollHeight, 150) + 'px';
        const len = this.value.length;
        if (len > MAX_CHARS * 0.7) {
            $('#ab-char-count').text(`${len}/${MAX_CHARS}`).toggleClass('near-limit', len < MAX_CHARS).toggleClass('at-limit', len >= MAX_CHARS);
        } else {
            $('#ab-char-count').text('').removeClass('near-limit at-limit');
        }
    });

    $(document).on('click', '.ab-copy-btn', function () {
        const id = $(this).data('bubble');
        const text = $('#' + id).text();
        navigator.clipboard.writeText(text).then(() => {
            $(this).html(ICONS.check + ' Copied!');
            setTimeout(() => $(this).html(ICONS.copy + ' Copy'), 1500);
        });
    });

    $(document).on('click', '.ab-retry-btn', function () {
        const text = $('#' + $(this).data('bubble')).text().trim();
        if (text && !isThinking) { $('#ab-input').val(text); sendMessage(); }
    });

    $('#ab-back').hide();
});