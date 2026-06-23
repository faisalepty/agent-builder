/**
 * Chat_Ui.js v4.3 — SOTA Omnis Orchestrator
 * v4.3: launcher redesigned (chat-bubble glyph, in-place open/close
 * crossfade instead of fading the whole button away, a one-time entrance
 * pop, 60px target size), bigger condensed/expanded window dimensions,
 * two new per-tool icons (search/terminal) for the redesigned agent-
 * actions list, and close() now collapses any fullscreen artifact plus a
 * visibility:hidden fallback once the close transition finishes.
 * v4.2: friendlier/more relatable icon set, Omnis branding, redesigned
 * message-action row, working slash-flyout persistence, a bigger (but not
 * fullscreen) expand mode, and robust error-state handling end to end.
 */
$(document).ready(function () {

    if (!window.marked) {
        const s = document.createElement('script');
        s.src = 'https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js';
        document.head.appendChild(s);
    }

    // ── Modern Lucide-style Icons (stroke-width: 1.5) ──────────
    const ICONS = {
        // Welcome screen / assistant identity icon: clean "message with wave" — friendly, minimal, no star
        sparkle:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M8 10h.01M12 10h.01M16 10h.01" stroke-width="2.5" stroke-linecap="round"/></svg>`,
        send:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>`,
        close:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
        back:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="15 18 9 12 15 6"/></svg>`,
        newchat:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
        check:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="20 6 9 17 4 12"/></svg>`,
        spin:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>`,
        copy:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>`,
        retry:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>`,
        // Header avatar: clean rounded chat orb with a subtle pulse dot — minimal, modern, no robot parts
        bot:      `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2C6.48 2 2 6.03 2 11c0 2.87 1.37 5.43 3.54 7.17L4 22l4.26-1.42A10.7 10.7 0 0 0 12 21c5.52 0 10-4.03 10-9S17.52 2 12 2z"/><circle cx="8.5" cy="11" r="1.2" fill="currentColor" stroke="none"/><circle cx="12" cy="11" r="1.2" fill="currentColor" stroke="none"/><circle cx="15.5" cy="11" r="1.2" fill="currentColor" stroke="none"/></svg>`,
        expand:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/></svg>`,
        compress: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="10" y1="14" x2="21" y2="3"/><line x1="3" y1="21" x2="14" y2="10"/></svg>`,
        reload:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>`,
        stop:     `<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="7" width="10" height="10" rx="1"/></svg>`,
        down:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>`,
        paperclip:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>`,
        skillIcon:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>`,
        chevronRight:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="9 18 15 12 9 6"/></svg>`,
        fileText:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/></svg>`,
        listIcon:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>`,
        plusCircle:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="13" x2="12" y2="19"/><line x1="9" y1="16" x2="15" y2="16"/></svg>`,
        layers:      `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="16" y2="12"/><line x1="4" y1="18" x2="11" y2="18"/></svg>`,
        barChart:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>`,
        edit:         `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 113 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
        alertTriangle:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
        search:       `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
        terminal:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="4" width="20" height="16" rx="2"/><polyline points="6 9 10 12 6 15"/><line x1="12" y1="15" x2="16" y2="15"/></svg>`,
        // Launcher: clean rounded-corner chat bubble, no decorations inside — instantly reads as "chat"
        launcherChat: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 14.5a2.5 2.5 0 0 1-2.5 2.5H6.5L2 21.5V5a2.5 2.5 0 0 1 2.5-2.5h14A2.5 2.5 0 0 1 21 5z"/><circle cx="8" cy="10" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="10" r="1" fill="currentColor" stroke="none"/><circle cx="16" cy="10" r="1" fill="currentColor" stroke="none"/></svg>`,
    };
    ICONS.plus = ICONS.newchat; // same glyph, reused intentionally for the input's "+" button

    const SUGGESTIONS = [
        { label: 'List records',    icon: 'listIcon',   text: 'Show me the latest 10 open Sales Orders' },
        { label: 'Create a doc',    icon: 'plusCircle', text: 'Create a new Lead for Acme Corp with email acme@example.com' },
        { label: 'Summarise data',  icon: 'layers',      text: 'Summarise outstanding invoices by customer' },
        { label: 'Run a report',    icon: 'barChart',    text: 'What are the top 5 items sold this month?' },
    ];

    // Shared HTML-escaping helper (falls back to frappe's own utility when present)
    function escapeHtml(txt) {
        if (txt === undefined || txt === null) return '';
        if (window.frappe && frappe.utils && frappe.utils.escape_html) return frappe.utils.escape_html(String(txt));
        return String(txt).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    // ── SOTA DOM Structure Injection ───────────────────────────
    $('body').append(`
        <button id="ab-launcher" title="Omnis — click to open, drag to reposition">
            <span class="ab-launcher-icon ab-launcher-icon-chat">${ICONS.launcherChat}</span>
            <span id="ab-badge"></span>
        </button>

        <div id="ab-window">
            <div id="ab-header">
                <button id="ab-back" class="ab-hbtn" title="Back">${ICONS.back}</button>
                <div id="ab-header-avatar">${ICONS.bot}</div>
                <div id="ab-header-info">
                    <div id="ab-header-name">Omnis</div>
                    <div id="ab-header-status">
                        <div id="ab-status-dot"></div>
                        <span id="ab-status-text">Online</span>
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
                            <div id="ab-attachments-row"></div>

                            <textarea id="ab-input" rows="1" placeholder="Ask Omnis anything…"></textarea>

                            <button id="ab-plus-btn" class="ab-input-icon-btn" title="Add files or a skill" type="button">${ICONS.plus}</button>

                            <div id="ab-input-actions">
                                <span id="ab-char-count"></span>
                                <button id="ab-stop" title="Stop generation">${ICONS.stop}</button>
                                <button id="ab-send" title="Send">${ICONS.send}</button>
                            </div>

                            <!-- "+" popover: upload files / browse skills -->
                            <div id="ab-plus-menu" class="ab-popover">
                                <button class="ab-plus-menu-item" data-action="upload" type="button">
                                    <span class="ab-plus-menu-icon">${ICONS.paperclip}</span>
                                    <span>Add photos &amp; files</span>
                                </button>
                                <div class="ab-plus-menu-item ab-has-flyout" data-action="skills" tabindex="0" role="button" aria-haspopup="true">
                                    <span class="ab-plus-menu-icon">${ICONS.skillIcon}</span>
                                    <span>Browse skills</span>
                                    <span class="ab-flyout-caret">${ICONS.chevronRight}</span>

                                    <div id="ab-skill-panel" class="ab-flyout">
                                        <div class="ab-flyout-header"><span>Skills</span></div>
                                        <div class="ab-flyout-search-wrap">
                                            <input type="text" id="ab-skill-search" placeholder="Search skills…" autocomplete="off"/>
                                        </div>
                                        <div id="ab-skill-list" class="ab-flyout-list">
                                            <div class="ab-skill-empty">Loading skills…</div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <!-- "/" slash-command skill autocomplete -->
                            <div id="ab-slash-menu" class="ab-popover">
                                <div class="ab-flyout-header"><span>Skills</span><span id="ab-slash-count"></span></div>
                                <div id="ab-slash-list" class="ab-flyout-list"></div>
                            </div>
                        </div>

                        <input type="file" id="ab-file-input" multiple/>

                        <div id="ab-input-footer">
                            <span id="ab-input-hint">Shift + Enter for new line · Type / for skills</span>
                        </div>
                    </div>
                </div>
            </div>

            <div id="ab-skill-tooltip"></div>
        </div>
    `);

    // Reusable function to render the welcome layout dynamically
    function renderWelcomeScreen() {
        const cardsHtml = SUGGESTIONS.map((s, i) => `
            <button class="ab-suggestion-card" data-text="${escapeHtml(s.text)}" type="button" style="animation-delay:${i * 40}ms">
                <span class="ab-suggestion-icon">${ICONS[s.icon] || ICONS.sparkle}</span>
                <span class="ab-suggestion-label">${escapeHtml(s.label)}</span>
            </button>
        `).join('');

        // Remove old instances if any exist, then append clean
        $('#ab-welcome').remove();
        $('#ab-messages').append(`
            <div id="ab-welcome">
                <div id="ab-welcome-icon">${ICONS.sparkle}</div>
                <h3>How can I help you today?</h3>
                <p>Query records, draft documents, or run a report — just ask.</p>
                <div class="ab-suggestions-grid">${cardsHtml}</div>
            </div>
        `);
    }

    // State
    let isOpen = false, isThinking = false, currentChatId = null, currentView = 'list', isExpanded = false;

    // Skills cache (shared by the "+" flyout and the "/" autocomplete)
    let _skills = [], _skillsLoaded = false, _skillsLoading = false, _skillsWaiters = [];

    // Slash-menu state
    let _slashFiltered = [], _slashActiveIndex = -1;

    // Staged file attachments for the next message
    let _pendingFiles = [];

    // Portal the skill flyout and tooltip to <body> so they escape
    // overflow:hidden on #ab-window (which clips child absolute elements).
    // They are positioned via JS using fixed viewport coordinates.
    (function portalOverlays() {
        const flyout = document.getElementById('ab-skill-panel');
        const tooltip = document.getElementById('ab-skill-tooltip');
        if (flyout) document.body.appendChild(flyout);
        if (tooltip) document.body.appendChild(tooltip);
    })();

    ChatMessages.init(ICONS);
    ChatList.init({ onSelect: openConversation, onNew: startNewChat });
    ChatRealtime.init({
        onToken: (delta) => { resetThinkingWatchdog(); ChatMessages.onToken(delta); },
        onToolStart: (data) => { resetThinkingWatchdog(); ChatMessages.onToolStart(data); },
        onToolDone: (data) => { resetThinkingWatchdog(); ChatMessages.onToolDone(data); },
        onStatusChange: (text, thinking) => { resetThinkingWatchdog(); setStatus(text, thinking); },
        onDone: (data) => {
            // However ChatMessages renders the response, setInputState(false)
            // below must always run — a rendering bug here should never be
            // able to leave the stop button stuck and the send button gone.
            clearThinkingWatchdog();
            try { ChatMessages.onDone((data && data.response) || '', false); }
            catch (err) { console.error('ChatMessages.onDone failed', err); }
            setInputState(false);
            setStatus('Online', false);
            setTimeout(() => $('#ab-input').focus(), 50);
        },
        onError: (data) => {
            clearThinkingWatchdog();
            const resp = (data && data.response) || 'Sorry, something went wrong.';
            try { ChatMessages.onDone(resp, true); }
            catch (err) { console.error('ChatMessages.onDone failed', err); }
            setInputState(false);
            setStatus('Error', false, true);
            setTimeout(() => $('#ab-input').focus(), 50);
        },
    });

    function showList() {
        currentView = 'list';
        closePlusMenu();
        closeSlashMenu();
        $('#ab-window').removeClass('view-conv');
        $('#ab-back').hide();
        $('#ab-new-chat').show();
        $('#ab-header-name').text('Omnis');
        setStatus('Online', false);
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
        _pendingFiles = [];
        renderAttachmentChips();
        showConv(title);
        ChatMessages.loadHistory(chatId);
    }

    function startNewChat() {
        // Clear runtime tracking to signify an un-saved conversation state
        currentChatId = null;
        _pendingFiles = [];
        renderAttachmentChips();

        // Prepare UI views instantly
        ChatMessages.clear();
        showConv('New Chat');
        renderWelcomeScreen();
    }

    // ───────────────────────────────────────────────────────────
    // Draggable launcher + draggable window
    // Both use a shared drag routine: pointer events on the handle
    // element, clamped to the viewport so neither floats offscreen.
    // A tiny hasDragged flag prevents the click handler from firing
    // if the pointer actually moved (drag vs click disambiguation).
    // ───────────────────────────────────────────────────────────
    function _makeDraggable(handleEl, movedEl, onDragEnd) {
        let startX, startY, startLeft, startTop, hasDragged = false;

        function _clamp(val, min, max) { return Math.max(min, Math.min(max, val)); }

        function onPointerDown(e) {
            if (e.button !== 0) return;
            // Don't intercept clicks on interactive children (buttons inside header etc.)
            if (handleEl !== movedEl && $(e.target).closest('button, a, input, textarea, select').length) return;

            hasDragged = false;
            const rect = movedEl.getBoundingClientRect();
            startLeft = rect.left;
            startTop  = rect.top;
            startX    = e.clientX;
            startY    = e.clientY;

            // Anchor element to current viewport position so we can drive it freely
            movedEl.style.left   = rect.left + 'px';
            movedEl.style.top    = rect.top  + 'px';
            movedEl.style.right  = 'auto';
            movedEl.style.bottom = 'auto';

            document.addEventListener('pointermove', onPointerMove);
            document.addEventListener('pointerup',   onPointerUp);
            // Do NOT call e.preventDefault() — it would suppress the click event
        }

        function onPointerMove(e) {
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            if (!hasDragged && Math.abs(dx) + Math.abs(dy) > 5) {
                hasDragged = true;
                // Only add drag cursor after we know it's a real drag
                movedEl.style.transition = 'none';
                movedEl.style.cursor = 'grabbing';
            }
            if (!hasDragged) return;

            const vw = window.innerWidth, vh = window.innerHeight;
            const w  = movedEl.offsetWidth,  h  = movedEl.offsetHeight;
            movedEl.style.left = _clamp(startLeft + dx, 0, vw - w) + 'px';
            movedEl.style.top  = _clamp(startTop  + dy, 0, vh - h) + 'px';
        }

        function onPointerUp() {
            document.removeEventListener('pointermove', onPointerMove);
            document.removeEventListener('pointerup',   onPointerUp);
            movedEl.style.transition = '';
            movedEl.style.cursor     = '';
            if (onDragEnd) onDragEnd(hasDragged);
        }

        // If a drag occurred, eat the subsequent click so it doesn't toggle open/close
        handleEl.addEventListener('click', function (e) {
            if (hasDragged) { e.stopImmediatePropagation(); hasDragged = false; }
        }, true);

        handleEl.addEventListener('pointerdown', onPointerDown);
    }

    // Launcher: drag to reposition, click to open/close
    const launcherEl = document.getElementById('ab-launcher');
    const windowEl   = document.getElementById('ab-window');
    _makeDraggable(launcherEl, launcherEl, function (wasDrag) {
        if (wasDrag) _syncWindowToLauncher();
    });
    // Separate click handler for open/close (drag handler eats clicks when dragged)
    launcherEl.addEventListener('click', function () {
        isOpen ? _close() : _open();
    });

    // Window: header is the drag handle, whole window is the moved element.
    const headerEl = document.getElementById('ab-header');
    _makeDraggable(headerEl, windowEl, null);

    function _syncWindowToLauncher() {
        if (!isOpen) return;
        const lr = launcherEl.getBoundingClientRect();
        const wr = windowEl.getBoundingClientRect();
        const vw = window.innerWidth, vh = window.innerHeight;
        let left = lr.left - wr.width + lr.width;
        let top  = lr.top  - wr.height - 12;
        left = Math.max(8, Math.min(left, vw - wr.width  - 8));
        top  = Math.max(8, Math.min(top,  vh - wr.height - 8));
        windowEl.style.left   = left + 'px';
        windowEl.style.top    = top  + 'px';
        windowEl.style.right  = 'auto';
        windowEl.style.bottom = 'auto';
    }

    $(document).on('click', '#ab-close', _close);
    $(document).on('click', '#ab-back', showList);

    let _closeVisibilityTimer = null;

    function _open() {
        isOpen = true;
        clearTimeout(_closeVisibilityTimer);
        $('#ab-window').removeClass('ab-fully-closed');
        $('#ab-window').addClass('open');
        if (currentView === 'list') ChatList.load();
        else if (currentChatId) $('#ab-input').focus();
    }
    function _close() {
        isOpen = false;
        $('#ab-window').removeClass('open');
        closePlusMenu();
        closeSlashMenu();
        // Collapsing any fullscreen artifact here is real defense-in-depth:
        // it's portaled to <body> while expanded, so it would otherwise be
        // left floating outside #ab-window if the chat is closed mid-view.
        // The visibility:hidden timer below is separate, lower-stakes
        // hardening for #ab-window's own closed state (see Chat_Ui.css).
        if (ChatMessages && ChatMessages.collapseAllFullscreenArtifacts) ChatMessages.collapseAllFullscreenArtifacts();
        clearTimeout(_closeVisibilityTimer);
        _closeVisibilityTimer = setTimeout(() => $('#ab-window').addClass('ab-fully-closed'), 420);
    }

    // Navigating elsewhere in the Frappe desk SPA while an artifact is
    // fullscreen would otherwise leave it orphaned on an unrelated page.
    if (window.frappe && frappe.router && frappe.router.on) {
        frappe.router.on('change', () => {
            if (ChatMessages && ChatMessages.collapseAllFullscreenArtifacts) ChatMessages.collapseAllFullscreenArtifacts();
        });
    }

    $(document).on('click', '#ab-expand', function () {
        isExpanded = !isExpanded;
        $('#ab-window').toggleClass('ab-expanded', isExpanded);
        $(this).html(isExpanded ? ICONS.compress : ICONS.expand)
               .attr('title', isExpanded ? 'Collapse' : 'Expand');
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

    $(document).on('click', '.ab-suggestion-card', function () {
        $('#ab-input').val($(this).data('text')).trigger('input').focus();
    });

    function setStatus(text, thinking, isError) {
        $('#ab-status-text').text(text);
        $('#ab-status-dot').toggleClass('thinking', !!thinking && !isError).toggleClass('error', !!isError);
    }

    // Safety net: if no realtime event arrives at all (dropped connection,
    // Redis hiccup, a thread that died without ever publishing), this makes
    // sure the input always recovers instead of staying stuck on "Thinking…"
    // with the stop button showing forever.
    const THINKING_TIMEOUT_MS = 175000;
    let _thinkingWatchdog = null;
    function resetThinkingWatchdog() {
        clearThinkingWatchdog();
        if (!isThinking) return;
        _thinkingWatchdog = setTimeout(handleThinkingTimeout, THINKING_TIMEOUT_MS);
    }
    function clearThinkingWatchdog() {
        if (_thinkingWatchdog) { clearTimeout(_thinkingWatchdog); _thinkingWatchdog = null; }
    }
    function handleThinkingTimeout() {
        if (!isThinking) return;
        try { ChatMessages.onDone('Omnis seems to have lost connection mid-response. Please try again.', true); }
        catch (err) { console.error(err); }
        setInputState(false);
        setStatus('Timed out', false, true);
    }

    function setInputState(disabled) {
        isThinking = disabled;
        $('#ab-input').prop('disabled', disabled);
        $('#ab-send').toggle(!disabled);
        $('#ab-stop').toggleClass('visible', disabled);
        if (disabled) resetThinkingWatchdog(); else clearThinkingWatchdog();
    }

    $(document).on('click', '#ab-stop', function () {
        ChatMessages.onStop();
        setInputState(false);
        setStatus('Stopped', false);
    });

    // ───────────────────────────────────────────────────────────
    // Skills: data loading (shared by "+" flyout and "/" autocomplete)
    // ───────────────────────────────────────────────────────────
    function loadSkills(onReady) {
        if (_skillsLoaded) { onReady && onReady(); return; }
        _skillsWaiters.push(onReady);
        if (_skillsLoading) return;
        _skillsLoading = true;
        frappe.call({
            method: 'agent_builder.api.agent.get_skills',
            callback(r) {
                _skills = (r.message && r.message.skills) || [];
                _finishSkillsLoad();
            },
            error() {
                _skills = [];
                _finishSkillsLoad();
            }
        });
    }
    function _finishSkillsLoad() {
        _skillsLoaded = true;
        _skillsLoading = false;
        const waiters = _skillsWaiters.slice();
        _skillsWaiters = [];
        waiters.forEach(cb => cb && cb());
    }

    function _skillItemHtml(skill) {
        const slug = escapeHtml(skill.name || '');
        const label = escapeHtml(skill.label || skill.name || '');
        const desc = escapeHtml(skill.description || '');
        return `<button type="button" class="ab-skill-item" data-skill="${slug}" data-description="${desc}">
            <span class="ab-skill-item-icon">${ICONS.skillIcon}</span>
            <span class="ab-skill-item-label">${label}</span>
        </button>`;
    }

    function renderSkillList($container, skills) {
        if (!skills || !skills.length) {
            $container.html(`<div class="ab-skill-empty">${_skillsLoaded ? 'No skills found' : 'Loading skills…'}</div>`);
            return;
        }
        $container.html(skills.map(_skillItemHtml).join(''));
    }

    function selectSkill(name) {
        if (!name) return;
        const $input = $('#ab-input');
        $input.val('/' + name + ' ').trigger('input').focus();
        const el = $input[0];
        if (el) el.selectionStart = el.selectionEnd = el.value.length;
        closePlusMenu();
        closeSlashMenu();
    }

    $(document).on('click', '.ab-skill-item', function () {
        selectSkill($(this).data('skill'));
    });

    // ───────────────────────────────────────────────────────────
    // "+" popover (upload files / browse skills)
    // ───────────────────────────────────────────────────────────
    function openPlusMenu() {
        closeSlashMenu();
        $('#ab-plus-menu').addClass('open');
        $('#ab-plus-btn').addClass('is-open');
    }
    function closePlusMenu() {
        $('#ab-plus-menu').removeClass('open');
        $('#ab-plus-btn').removeClass('is-open');
        closeSkillFlyout();
        $('#ab-skill-search').val('');
    }

    $(document).on('click', '#ab-plus-btn', function (e) {
        e.stopPropagation();
        if ($('#ab-plus-menu').hasClass('open')) closePlusMenu();
        else openPlusMenu();
    });

    $(document).on('click', '.ab-plus-menu-item[data-action="upload"]', function () {
        closePlusMenu();
        $('#ab-file-input').trigger('click');
    });

    function positionFlyout($trigger, $panel) {
        if (!$trigger.length) return;
        const triggerRect = $trigger[0].getBoundingClientRect();
        const panelWidth = $panel.outerWidth() || 240;
        const panelHeight = $panel.outerHeight() || 300;
        const vw = window.innerWidth, vh = window.innerHeight;

        // Prefer right of trigger; flip left if not enough space
        let left = triggerRect.right + 8;
        if (left + panelWidth > vw - 8) {
            left = triggerRect.left - panelWidth - 8;
        }
        left = Math.max(8, left);

        // Align top with trigger; push up if overflows viewport bottom
        let top = triggerRect.top;
        if (top + panelHeight > vh - 8) {
            top = vh - panelHeight - 8;
        }
        top = Math.max(8, top);

        $panel.css({ left: left + 'px', top: top + 'px', right: 'auto', bottom: 'auto' });
    }

    let _skillFlyoutCloseTimer = null;
    function scheduleCloseSkillFlyout() {
        clearTimeout(_skillFlyoutCloseTimer);
        _skillFlyoutCloseTimer = setTimeout(closeSkillFlyout, 350);
    }
    function cancelCloseSkillFlyout() {
        clearTimeout(_skillFlyoutCloseTimer);
        _skillFlyoutCloseTimer = null;
    }

    function openSkillFlyout($trigger) {
        cancelCloseSkillFlyout();
        const $panel = $('#ab-skill-panel');
        positionFlyout($trigger, $panel);
        $panel.addClass('open');
        if (!_skillsLoaded) {
            renderSkillList($('#ab-skill-list'), []);
            loadSkills(() => renderSkillList($('#ab-skill-list'), _skills));
        } else {
            renderSkillList($('#ab-skill-list'), _skills);
        }
    }
    function closeSkillFlyout() {
        cancelCloseSkillFlyout();
        $('#ab-skill-panel').removeClass('open');
        hideSkillTooltip();
    }

    // The trigger row and the flyout panel sit a few px apart visually, so a
    // plain mouseleave-on-trigger fires the instant the cursor crosses that
    // gap — closing the list before it can ever be hovered. Both elements
    // now share a single deferred close, cancelled the moment either is
    // re-entered, so quick diagonal mouse movement into the panel works.
    $(document).on('mouseenter', '#ab-plus-menu .ab-has-flyout', function () {
        cancelCloseSkillFlyout();
        if ($('#ab-plus-menu').hasClass('open')) openSkillFlyout($(this));
    });
    $(document).on('mouseleave', '#ab-plus-menu .ab-has-flyout', function () {
        scheduleCloseSkillFlyout();
    });
    $(document).on('mouseenter', '#ab-skill-panel', function () {
        cancelCloseSkillFlyout();
    });
    $(document).on('mouseleave', '#ab-skill-panel', function () {
        scheduleCloseSkillFlyout();
    });
    $(document).on('click', '#ab-plus-menu .ab-has-flyout', function (e) {
        e.stopPropagation();
        if ($('#ab-skill-panel').hasClass('open')) closeSkillFlyout();
        else openSkillFlyout($(this));
    });
    $(document).on('keydown', '.ab-has-flyout', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $(this).trigger('click'); }
    });

    $(document).on('input', '#ab-skill-search', function () {
        const q = this.value.trim().toLowerCase();
        const filtered = !q ? _skills : _skills.filter(s =>
            (s.name || '').toLowerCase().includes(q) || (s.label || '').toLowerCase().includes(q)
        );
        renderSkillList($('#ab-skill-list'), filtered);
    });

    // Skill description tooltip — portaled to <body> with position:fixed,
    // always placed to the RIGHT of the hovered skill item so it never
    // overlaps or hides the list below it.
    function showSkillTooltip($item, description) {
        if (!description) { hideSkillTooltip(); return; }
        const $tip = $('#ab-skill-tooltip');
        $tip.text(description).css({ display: 'block', visibility: 'hidden' });
        const itemRect = $item[0].getBoundingClientRect();
        const tipW = $tip.outerWidth() || 220;
        const tipH = $tip.outerHeight() || 40;
        const vw = window.innerWidth, vh = window.innerHeight;

        // Prefer right of the item; fall back to left if near viewport edge
        let left = itemRect.right + 10;
        if (left + tipW > vw - 8) left = itemRect.left - tipW - 10;
        left = Math.max(8, left);

        // Align vertically to mid-item; push up if it overflows viewport bottom
        let top = itemRect.top + (itemRect.height / 2) - (tipH / 2);
        top = Math.max(8, Math.min(top, vh - tipH - 8));

        $tip.css({ left: left + 'px', top: top + 'px', visibility: 'visible' });
    }
    function hideSkillTooltip() {
        $('#ab-skill-tooltip').css('display', 'none');
    }
    $(document).on('mouseenter', '.ab-skill-item', function () {
        showSkillTooltip($(this), $(this).data('description'));
    });
    $(document).on('mouseleave', '.ab-skill-item', function () {
        hideSkillTooltip();
    });

    // ───────────────────────────────────────────────────────────
    // "/" slash-command skill autocomplete
    // ───────────────────────────────────────────────────────────
    function openSlashMenu() {
        closePlusMenu();
        $('#ab-slash-menu').addClass('open');
    }
    function closeSlashMenu() {
        $('#ab-slash-menu').removeClass('open');
        _slashFiltered = [];
        _slashActiveIndex = -1;
        hideSkillTooltip();
    }

    function highlightSlashActive() {
        $('#ab-slash-list .ab-skill-item').removeClass('active').eq(_slashActiveIndex).addClass('active');
    }
    function moveSlashActive(delta) {
        if (!_slashFiltered.length) return;
        _slashActiveIndex = (_slashActiveIndex + delta + _slashFiltered.length) % _slashFiltered.length;
        highlightSlashActive();
    }

    function filterSlashMenu(query) {
        _slashFiltered = !query ? _skills.slice() : _skills.filter(s =>
            (s.name || '').toLowerCase().includes(query) || (s.label || '').toLowerCase().includes(query)
        );
        _slashActiveIndex = _slashFiltered.length ? 0 : -1;
        renderSkillList($('#ab-slash-list'), _slashFiltered);
        highlightSlashActive();
        $('#ab-slash-count').text(_slashFiltered.length ? `· ${_slashFiltered.length}` : '');
    }

    function handleSlashTrigger(value) {
        const match = /^\/([a-zA-Z0-9_-]*)$/.exec(value);
        if (!match) { closeSlashMenu(); return; }
        const query = match[1].toLowerCase();
        openSlashMenu();
        if (!_skillsLoaded) {
            renderSkillList($('#ab-slash-list'), []);
            loadSkills(() => filterSlashMenu(query));
        } else {
            filterSlashMenu(query);
        }
    }

    $(document).on('blur', '#ab-input', function () {
        setTimeout(closeSlashMenu, 150);
    });

    // ───────────────────────────────────────────────────────────
    // File attachments (staged before send)
    // ───────────────────────────────────────────────────────────
    $(document).on('change', '#ab-file-input', function () {
        const files = Array.from(this.files || []);
        files.forEach(f => _pendingFiles.push(f));
        this.value = '';
        renderAttachmentChips();
    });

    function renderAttachmentChips() {
        const $row = $('#ab-attachments-row');
        if (!_pendingFiles.length) { $row.removeClass('visible').empty(); return; }
        $row.addClass('visible').html(_pendingFiles.map((f, i) => `
            <div class="ab-attachment-chip" data-index="${i}">
                <span class="ab-attachment-icon">${ICONS.fileText}</span>
                <span class="ab-attachment-name">${escapeHtml(f.name)}</span>
                <button type="button" class="ab-attachment-remove" data-index="${i}" title="Remove">${ICONS.close}</button>
            </div>
        `).join(''));
    }

    $(document).on('click', '.ab-attachment-remove', function () {
        const i = $(this).data('index');
        _pendingFiles.splice(i, 1);
        renderAttachmentChips();
    });

    function uploadFiles(files) {
        if (!files.length) return Promise.resolve([]);
        return Promise.all(files.map(file => {
            const fd = new FormData();
            fd.append('file', file);
            fd.append('is_private', 1);
            return fetch('/api/method/upload_file', {
                method: 'POST',
                headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token },
                body: fd,
            }).then(res => {
                if (!res.ok) throw new Error('Upload failed');
                return res.json();
            }).then(data => {
                const f = data.message || {};
                return { file_name: f.file_name || file.name, file_url: f.file_url || '' };
            });
        }));
    }

    // ───────────────────────────────────────────────────────────
    // Close menus on outside click / Escape
    // ───────────────────────────────────────────────────────────
    $(document).on('mousedown', function (e) {
        const $t = $(e.target);
        if (!$t.closest('#ab-plus-menu, #ab-plus-btn').length) closePlusMenu();
        if (!$t.closest('#ab-slash-menu, #ab-input').length) closeSlashMenu();
    });
    $(document).on('keydown', function (e) {
        if (e.key === 'Escape') { closePlusMenu(); closeSlashMenu(); }
    });

    // ───────────────────────────────────────────────────────────
    // Sending messages
    // ───────────────────────────────────────────────────────────
    let _lastSentMessage = '', _lastSentAttachments = [];

    function dispatchChatRequest(msg, attachments, isFirstMessage) {
        _lastSentMessage = msg;
        _lastSentAttachments = attachments || [];

        ChatMessages.appendUserMsg(msg, attachments);
        setStatus('Thinking…', true);
        ChatMessages.showTyping();

        frappe.call({
            method: 'agent_builder.api.agent.chat',
            args: { message: msg, chat_id: currentChatId, attachments: JSON.stringify(attachments || []) },
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
            },
            error() {
                // The request never made it to the agent at all (permissions,
                // validation, network) — surface that clearly instead of
                // leaving the UI stuck on "Thinking…" forever.
                setInputState(false);
                setStatus('Error', false, true);
                try { ChatMessages.onDone("Sorry, I couldn't send that. Please try again.", true); } catch (err) { console.error(err); }
            }
        });
    }

    function sendMessage() {
        const msg = $('#ab-input').val().trim();
        if ((!msg && !_pendingFiles.length) || isThinking) return;

        // Check if this is the initial message of a deferred session
        const isFirstMessage = (currentChatId === null);

        // CLEAR WELCOME SCREEN: Remove the welcome element if this is the first message
        if (isFirstMessage) {
            $('#ab-welcome').remove();
        }

        closePlusMenu();
        closeSlashMenu();
        $('#ab-input').val('').css('height', 'auto');
        $('#ab-char-count').text('').removeClass('near-limit at-limit');

        const filesToUpload = _pendingFiles.slice();
        _pendingFiles = [];
        renderAttachmentChips();

        setInputState(true);
        setStatus(filesToUpload.length ? 'Uploading…' : 'Thinking…', true);

        uploadFiles(filesToUpload).then((attachments) => {
            dispatchChatRequest(msg, attachments, isFirstMessage);
        }).catch(() => {
            setInputState(false);
            setStatus('Upload failed', false, true);
            $('#ab-input').val(msg).trigger('input').focus();
            _pendingFiles = filesToUpload;
            renderAttachmentChips();
        });
    }

    function retryLastMessage() {
        if (isThinking || (!_lastSentMessage && !_lastSentAttachments.length)) return;
        setInputState(true);
        setStatus('Thinking…', true);
        dispatchChatRequest(_lastSentMessage, _lastSentAttachments, currentChatId === null);
    }
    $(document).on('click', '.ab-resend-btn', retryLastMessage);

    $(document).on('click', '#ab-send', sendMessage);
    $(document).on('keydown', '#ab-input', (e) => {
        if ($('#ab-slash-menu').hasClass('open')) {
            if (e.key === 'ArrowDown') { e.preventDefault(); moveSlashActive(1); return; }
            if (e.key === 'ArrowUp') { e.preventDefault(); moveSlashActive(-1); return; }
            if (e.key === 'Escape') { e.preventDefault(); closeSlashMenu(); return; }
            if ((e.key === 'Enter' && !e.shiftKey) || e.key === 'Tab') {
                e.preventDefault();
                if (_slashActiveIndex >= 0 && _slashFiltered[_slashActiveIndex]) {
                    selectSkill(_slashFiltered[_slashActiveIndex].name);
                }
                return;
            }
        }
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
        handleSlashTrigger(this.value);
    });

    $(document).on('click', '.ab-copy-btn', function () {
        const id = $(this).data('bubble');
        const text = $('#' + id).text();
        const $btn = $(this);
        navigator.clipboard.writeText(text).then(() => {
            $btn.html(ICONS.check);
            setTimeout(() => $btn.html(ICONS.copy), 1200);
        });
    });

    // "Edit" only loads the message back into the input for the person to
    // change — it must NOT send anything on its own.
    $(document).on('click', '.ab-edit-btn', function () {
        if (isThinking) return;
        const text = $('#' + $(this).data('bubble')).text();
        const $input = $('#ab-input');
        $input.val(text).trigger('input').focus();
        const el = $input[0];
        if (el) el.selectionStart = el.selectionEnd = el.value.length;
    });

    $('#ab-back').hide();
});