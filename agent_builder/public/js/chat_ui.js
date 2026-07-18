/**
 * Chat_Ui.js v5.4 — Apex Piping branding integration
 * v5.4: Extracted exact A+P blended monogram from logo. Updated
 *   drawing animation to trace the monogram paths.
 * v5.3: Replaced generic bot icon with custom triangle logo. 
 */
 $(document).ready(function () {

     if (!frappe.user.has_role('Omnis User')) {
        return;
    }

    if (!window.marked) {
        const s = document.createElement('script');
        s.src = 'https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js';
        document.head.appendChild(s);
    }

    // ── Modern Lucide-style Icons (stroke-width: 1.5) ──────────
    // Custom AP Monogram extracted from Apex Piping Logo
    const ICONS = {
        // A/P monogram traced directly from the approved sketch: two nested
        // chevrons (the "A") sharing a peak, with the outer one curling
        // into a small hook (the "P") on the right.
        // A/P monogram traced from the approved v2 sketch: a short inner
        // chevron and a taller outer chevron sharing the same peak region,
        // the outer one flowing into a single smooth hook (one bezier, not
        
        logo: `<svg viewBox="0 0 407 365" xmlns="http://www.w3.org/2000/svg"><g transform="translate(0,365) scale(0.1,-0.1)" fill="currentColor" stroke="none"><path d="M1945 3441c-16 -4 -40 -13 -53 -20 -29 -15 -34 -23 -680 -916 -36 -49 -89 -121 -117 -160 -29 -38 -130 -178 -226 -310 -95 -132 -234 -323 -308 -425 -254 -347 -255 -350 -230 -437 26 -93 123 -154 213 -133 62 14 103 56 238 246 124 173 225 312 373 513 39 53 142 195 230 316 88 121 231 319 320 440 88 121 192 264 230 318 38 53 72 97 75 97 3 0 224 -222 491 -492 893 -906 875 -887 920 -1001 49 -123 44 -292 -13 -398 -36 -69 -109 -139 -177 -171 -39 -19 -63 -22 -151 -22 -93 0 -113 3 -174 29 -159 66 -328 206 -484 402 -90 115 -163 145 -263 112 -69 -23 -129 -111 -129 -188 1 -116 304 -444 554 -600 85 -53 244 -117 344 -138 173 -35 384 -2 532 84 88 51 217 181 269 270 84 143 128 323 117 483 -8 122 -35 220 -96 346 -62 128 -134 218 -291 366 -114 107 -505 498 -1109 1110 -134 136 -257 254 -274 262 -41 19 -94 26 -131 17z"/><path d="M1973 2519c-45 -22 -59 -39 -253 -309 -124 -173 -340 -471 -384 -531 -81 -110 -286 -393 -304 -419 -22 -33 -187 -261 -272 -375 -273 -370 -275 -374 -249 -468 31 -113 170 -173 276 -118 46 23 74 56 205 241 154 218 314 440 478 665 224 306 471 650 562 782 24 34 50 62 59 63 8 0 53 -42 100 -92 46 -51 154 -165 240 -253 85 -88 234 -242 330 -343 96 -101 188 -192 204 -202 92 -57 214 -20 265 81 26 50 25 104 -3 156 -17 32 -806 864 -1022 1078 -66 65 -155 82 -232 44z"/></g></svg>`,
        
        logoLoader: `<svg viewBox="0 0 407 365" xmlns="http://www.w3.org/2000/svg" class="ab-mark-svg"><defs><linearGradient id="ab-shimmer-grad" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="currentColor" stop-opacity="0.2"/><stop offset="45%" stop-color="currentColor" stop-opacity="1"/><stop offset="55%" stop-color="currentColor" stop-opacity="1"/><stop offset="100%" stop-color="currentColor" stop-opacity="0.2"/><animateTransform attributeName="gradientTransform" type="translate" values="-1.4 0; 1.4 0; -1.4 0" keyTimes="0;0.5;1" dur="1.9s" repeatCount="indefinite"/></linearGradient></defs><g transform="translate(0,365) scale(0.1,-0.1)" fill="url(#ab-shimmer-grad)" stroke="none"><path class="ab-mark-outer" d="M1945 3441c-16 -4 -40 -13 -53 -20 -29 -15 -34 -23 -680 -916 -36 -49 -89 -121 -117 -160 -29 -38 -130 -178 -226 -310 -95 -132 -234 -323 -308 -425 -254 -347 -255 -350 -230 -437 26 -93 123 -154 213 -133 62 14 103 56 238 246 124 173 225 312 373 513 39 53 142 195 230 316 88 121 231 319 320 440 88 121 192 264 230 318 38 53 72 97 75 97 3 0 224 -222 491 -492 893 -906 875 -887 920 -1001 49 -123 44 -292 -13 -398 -36 -69 -109 -139 -177 -171 -39 -19 -63 -22 -151 -22 -93 0 -113 3 -174 29 -159 66 -328 206 -484 402 -90 115 -163 145 -263 112 -69 -23 -129 -111 -129 -188 1 -116 304 -444 554 -600 85 -53 244 -117 344 -138 173 -35 384 -2 532 84 88 51 217 181 269 270 84 143 128 323 117 483 -8 122 -35 220 -96 346 -62 128 -134 218 -291 366 -114 107 -505 498 -1109 1110 -134 136 -257 254 -274 262 -41 19 -94 26 -131 17z"/><path class="ab-mark-inner" d="M1973 2519c-45 -22 -59 -39 -253 -309 -124 -173 -340 -471 -384 -531 -81 -110 -286 -393 -304 -419 -22 -33 -187 -261 -272 -375 -273 -370 -275 -374 -249 -468 31 -113 170 -173 276 -118 46 23 74 56 205 241 154 218 314 440 478 665 224 306 471 650 562 782 24 34 50 62 59 63 8 0 53 -42 100 -92 46 -51 154 -165 240 -253 85 -88 234 -242 330 -343 96 -101 188 -192 204 -202 92 -57 214 -20 265 81 26 50 25 104 -3 156 -17 32 -806 864 -1022 1078 -66 65 -155 82 -232 44z"/></g></svg>`,


        sparkle:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M8 10h.01M12 10h.01M16 10h.01" stroke-width="2.5" stroke-linecap="round"/></svg>`,
        send:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>`,
        close:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
        back:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="15 18 9 12 15 6"/></svg>`,
        newchat:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
        check:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="20 6 9 17 4 12"/></svg>`,
        spin:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>`,
        copy:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>`,
        retry:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>`,
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
        launcherChat: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 14.5a2.5 2.5 0 0 1-2.5 2.5H6.5L2 21.5V5a2.5 2.5 0 0 1 2.5-2.5h14A2.5 2.5 0 0 1 21 5z"/><circle cx="8" cy="10" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="10" r="1" fill="currentColor" stroke="none"/><circle cx="16" cy="10" r="1" fill="currentColor" stroke="none"/></svg>`,
    };
    ICONS.plus = ICONS.newchat;

    const SUGGESTIONS = [
        { label: "What were today's sales?",         icon: 'barChart',   text: "What were today's sales?" },
        { label: 'Which invoices are overdue?',      icon: 'fileText',   text: 'Which invoices are overdue?' },
        { label: 'Show stock for an item',           icon: 'listIcon',   text: 'Show stock for Item XYZ.' },
        { label: 'Who are our top customers?',       icon: 'layers',     text: 'Who are our top 10 customers this month?' },
    ];

    const WELCOME_FEATURES = [
        { icon: '📊', text: 'Analyze sales and purchases' },
        { icon: '💰', text: 'Check customer balances and outstanding invoices' },
        { icon: '📦', text: 'Review inventory and stock levels' },
        { icon: '📈', text: 'Generate business insights and reports' },
        { icon: '🧾', text: 'Find quotations, sales orders, and purchase orders' },
        { icon: '👥', text: 'Look up customers and suppliers' },
        { icon: '🤖', text: 'Answer questions about your ERP data in natural language' },
    ];

    function escapeHtml(txt) {
        if (txt === undefined || txt === null) return '';
        if (window.frappe && frappe.utils && frappe.utils.escape_html) return frappe.utils.escape_html(String(txt));
        return String(txt).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    // ── SOTA DOM Structure Injection ───────────────────────────
    $('body').append(`
        <div id="ab-launcher-wrap">
            <div id="ab-launcher-bubbles"></div>
            <button id="ab-launcher" title="APS Copilot — click to open, hover for quick questions">
                <span class="ab-launcher-icon ab-launcher-icon-chat">${ICONS.launcherChat}</span>
                <span id="ab-badge"></span>
            </button>
        </div>

        <div id="ab-window">
            <div id="ab-header">
                <button id="ab-back" class="ab-hbtn" title="Back to conversations">${ICONS.back}</button>
                <div id="ab-header-avatar">${ICONS.logo}</div>
                <div id="ab-header-info">
                    <div id="ab-header-name">APS Copilot</div>
                    <div id="ab-header-status">
                        <div id="ab-status-dot"></div>
                        <span id="ab-status-text">Online</span>
                    </div>
                </div>
                <button id="ab-new-chat" class="ab-hbtn ab-hbtn-labeled" title="Start a new chat">${ICONS.newchat}<span>New chat</span></button>
                <button id="ab-expand"   class="ab-hbtn" title="Expand window">${ICONS.expand}</button>
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

                            <div id="ab-input-wrap">
                                <div id="ab-input-highlight" aria-hidden="true"></div>
                                <textarea id="ab-input" rows="1" placeholder="Ask APS Copilot anything…"></textarea>
                            </div>

                            <button id="ab-plus-btn" class="ab-input-icon-btn" title="Add files or a skill" type="button">${ICONS.plus}</button>

                            <div id="ab-input-actions">
                                <span id="ab-char-count"></span>
                                <button id="ab-stop" title="Stop generation">${ICONS.stop}</button>
                                <button id="ab-send" title="Send">${ICONS.send}</button>
                            </div>

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

    function renderWelcomeScreen() {
        const featuresHtml = WELCOME_FEATURES.map(f => `
            <li><span class="ab-welcome-feature-icon">${f.icon}</span><span>${escapeHtml(f.text)}</span></li>
        `).join('');

        const cardsHtml = SUGGESTIONS.map((s, i) => `
            <button class="ab-suggestion-card" data-text="${escapeHtml(s.text)}" type="button" style="animation-delay:${i * 40}ms">
                <span class="ab-suggestion-icon">${ICONS[s.icon] || ICONS.sparkle}</span>
                <span class="ab-suggestion-label">${escapeHtml(s.label)}</span>
            </button>
        `).join('');

        $('#ab-welcome').remove();
        $('#ab-messages').append(`
            <div id="ab-welcome">
                <div id="ab-welcome-icon">${ICONS.logo}</div>
                <h3>Welcome to APS Copilot</h3>
                <p>I'm your AI assistant for ERPNext. I can help you:</p>
                <ul id="ab-welcome-features">${featuresHtml}</ul>
                <p class="ab-welcome-subtext">Just ask me a question — tap an example below or type your own.</p>
                <div class="ab-suggestions-grid">${cardsHtml}</div>
            </div>
        `);
    }

    window._copyToClipboard = function(text) {
        if (navigator.clipboard && window.isSecureContext) {
            return navigator.clipboard.writeText(text);
        }
        return new Promise(function (resolve, reject) {
            var ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            try { document.execCommand('copy'); resolve(); }
            catch (e) { reject(e); }
            finally { document.body.removeChild(ta); }
        });
    };

    // State
    let isOpen = false, isThinking = false, currentChatId = null, currentView = 'list', isExpanded = false;
    let _currentJobId = null;

    // Skills cache
    let _skills = [], _skillsLoaded = false, _skillsLoading = false, _skillsWaiters = [];
    let _skillSlugSet = new Set();

    // Slash-menu state
    let _slashFiltered = [], _slashActiveIndex = -1, _slashStartPos = -1;
    let _slashBlurTimeout = null;

    // Staged file attachments
    let _pendingFiles = [];

    // Portal overlays to <body>
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
        onReasoning: (delta) => { resetThinkingWatchdog(); ChatMessages.onReasoning(delta); },
        onToolStart: (data) => { resetThinkingWatchdog(); ChatMessages.onToolStart(data); },
        onToolDone: (data) => { resetThinkingWatchdog(); ChatMessages.onToolDone(data); },
        onStatusChange: (text, thinking) => { resetThinkingWatchdog(); setStatus(text, thinking); },
        onDone: (data) => {
            clearThinkingWatchdog();
            _currentJobId = null;
            try { ChatMessages.onDone((data && data.response) || '', false); }
            catch (err) { console.error('ChatMessages.onDone failed', err); }
            setInputState(false);
            setStatus('Online', false);
            setTimeout(() => $('#ab-input').focus(), 50);
        },
        onError: (data) => {
            clearThinkingWatchdog();
            _currentJobId = null;
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
        $('#ab-header-name').text('APS Copilot');
        setStatus('Online', false);
        ChatList.load();
    }

    function showConv(title) {
        currentView = 'conv';
        $('#ab-window').addClass('view-conv');
        $('#ab-back').show();
        $('#ab-header-name').text(title || 'Chat');
        $('#ab-input').focus();
    }

    function openConversation(chatId, title) {
        currentChatId = chatId;
        _currentJobId = null;
        ChatRealtime.setActiveSession(chatId);
        ChatList.setActive(chatId);
        _pendingFiles = [];
        renderAttachmentChips();
        showConv(title);
        ChatMessages.loadHistory(chatId);
        $('#ab-input').val('').css('height', 'auto');
        _updateInputHighlight();
        closeSlashMenu();
        closePlusMenu();
    }

    function startNewChat() {
        currentChatId = null;
        _currentJobId = null;
        ChatRealtime.setActiveSession(null);
        _pendingFiles = [];
        renderAttachmentChips();
        ChatMessages.clear();
        showConv('New Chat');
        renderWelcomeScreen();
        $('#ab-input').val('').css('height', 'auto');
        _updateInputHighlight();
        closeSlashMenu();
        closePlusMenu();
    }

    // ── Draggable Engine ───────────────────────────────────────
    function _makeDraggable(handleEl, movedEl, onDragEnd) {
        let startX, startY, startLeft, startTop, hasDragged = false;

        function _clamp(val, min, max) { return Math.max(min, Math.min(max, val)); }

        function onPointerDown(e) {
            if (e.button !== 0) return;
            if (handleEl !== movedEl && $(e.target).closest('button, a, input, textarea, select').length) return;

            hasDragged = false;
            const rect = movedEl.getBoundingClientRect();
            startLeft = rect.left;
            startTop  = rect.top;
            startX    = e.clientX;
            startY    = e.clientY;

            movedEl.style.left   = rect.left + 'px';
            movedEl.style.top    = rect.top  + 'px';
            movedEl.style.right  = 'auto';
            movedEl.style.bottom = 'auto';

            document.addEventListener('pointermove', onPointerMove);
            document.addEventListener('pointerup',   onPointerUp);
        }

        function onPointerMove(e) {
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;
            if (!hasDragged && Math.abs(dx) + Math.abs(dy) > 5) {
                hasDragged = true;
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
            document.removeEventListener('pointerup', onPointerUp);
            movedEl.style.transition = '';
            movedEl.style.cursor     = '';
            if (onDragEnd) onDragEnd(hasDragged);
        }

        handleEl.addEventListener('click', function (e) {
            if (hasDragged) { e.stopImmediatePropagation(); hasDragged = false; }
        }, true);

        handleEl.addEventListener('pointerdown', onPointerDown);
    }

    const launcherWrapEl = document.getElementById('ab-launcher-wrap');
    const launcherEl     = document.getElementById('ab-launcher');
    const windowEl       = document.getElementById('ab-window');
    _makeDraggable(launcherWrapEl, launcherWrapEl, function (wasDrag) {
        if (wasDrag) _syncWindowToLauncher();
    });
    launcherEl.addEventListener('click', function () {
        isOpen ? _close() : _open();
    });

    // ── Hover suggestion bubbles ─────────────────────────────────
    (function initLauncherBubbles() {
        const $bubbles = $('#ab-launcher-bubbles');
        if (!$bubbles.length) return;

        $bubbles.html(SUGGESTIONS.map((s, i) => `
            <button class="ab-launcher-bubble" data-text="${escapeHtml(s.text)}" type="button" style="transition-delay:${i * 30}ms">${escapeHtml(s.label)}</button>
        `).join(''));

        let hideTimer = null;
        function showBubbles() {
            clearTimeout(hideTimer);
            if (isOpen) return;
            $bubbles.addClass('visible');
        }
        function hideBubbles(delay) {
            clearTimeout(hideTimer);
            hideTimer = setTimeout(() => $bubbles.removeClass('visible'), delay || 0);
        }

        launcherWrapEl.addEventListener('mouseenter', showBubbles);
        launcherWrapEl.addEventListener('mouseleave', () => hideBubbles(250));

        $(document).on('click', '.ab-launcher-bubble', function () {
            const text = $(this).data('text');
            hideBubbles(0);
            _open();
            startNewChat();
            setTimeout(() => {
                $('#ab-input').val(text).trigger('input').focus();
            }, currentView === 'list' ? 0 : 0);
        });
    })();

    const headerEl = document.getElementById('ab-header');
    _makeDraggable(headerEl, windowEl, null);

    function _syncWindowToLauncher() {
        if (!isOpen) return;
        const lr = launcherWrapEl.getBoundingClientRect();
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
    $(document).on('click', '.ab-empty-new-chat-btn', startNewChat);

    let _closeVisibilityTimer = null;

    function _open() {
        isOpen = true;
        clearTimeout(_closeVisibilityTimer);
        $('#ab-window').removeClass('ab-fully-closed');
        $('#ab-window').addClass('open');
        $('#ab-launcher-wrap').addClass('ab-launcher-hidden');
        $('#ab-launcher-bubbles').removeClass('visible');
        if (currentView === 'list') ChatList.load();
        else if (currentChatId) $('#ab-input').focus();
    }
    function _close() {
        isOpen = false;
        $('#ab-window').removeClass('open');
        $('#ab-launcher-wrap').removeClass('ab-launcher-hidden');
        closePlusMenu();
        closeSlashMenu();
        if (ChatMessages && ChatMessages.collapseAllFullscreenArtifacts) ChatMessages.collapseAllFullscreenArtifacts();
        clearTimeout(_closeVisibilityTimer);
        _closeVisibilityTimer = setTimeout(() => $('#ab-window').addClass('ab-fully-closed'), 420);
    }

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

    // ── Status Administration ──────────────────────────────────
    function setStatus(text, thinking, isError) {
        const $dot = $('#ab-status-dot');
        const $text = $('#ab-status-text');
        if ($text.length) { $text.text(text || 'Online'); }
        if ($dot.length) {
            $dot.removeClass('thinking error');
            if (thinking) { $dot.addClass('thinking'); }
            else if (isError) { $dot.addClass('error'); }
        }
    }

    const THINKING_TIMEOUT_MS = 1175000;
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
        try { ChatMessages.onDone('APS Copilot seems to have lost connection mid-response. Please try again.', true); }
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

    // ── STOP BUTTON: kills the backend background job ───────────
    $(document).on('click', '#ab-stop', function () {
        ChatMessages.onStop();
        setInputState(false);
        setStatus('Stopped', false);

        if (currentChatId) {
            frappe.call({
                method: 'agent_builder.native_api.verify.stop_chat',
                args: {
                    chat_id: currentChatId,
                    job_id: _currentJobId || '',
                },
                error: function () {},
            });
        }
        _currentJobId = null;
    });

    // ── Skills Loader ──────────────────────────────────────────
    function loadSkills(onReady) {
        if (_skillsLoaded) { onReady && onReady(); return; }
        _skillsWaiters.push(onReady);
        if (_skillsLoading) return;
        _skillsLoading = true;
        frappe.call({
            method: 'agent_builder.native_api.verify.get_skills',
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
        _skillSlugSet = new Set(_skills.map(function (s) { return (s.name || '').toLowerCase(); }));
        const waiters = _skillsWaiters.slice();
        _skillsWaiters = [];
        waiters.forEach(cb => cb && cb());
        _updateInputHighlight();
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
        const el = $input[0];
        if (!el) return;

        const value = el.value || '';
        const cursorPos = typeof el.selectionStart === 'number' ? el.selectionStart : value.length;

        let newText;
        let newPos;

        if (_slashStartPos >= 0 && _slashStartPos <= cursorPos) {
            const before = value.slice(0, _slashStartPos);
            const after = value.slice(cursorPos);
            newText = before + '/' + name + ' ' + after;
            newPos = _slashStartPos + 1 + name.length + 1;
        } else {
            newText = value + '/' + name + ' ';
            newPos = newText.length;
        }

        $input.val(newText);
        if (typeof el.setSelectionRange === 'function') {
            el.setSelectionRange(newPos, newPos);
        } else {
            el.selectionStart = el.selectionEnd = newPos;
        }

        _slashStartPos = -1;
        closePlusMenu();
        closeSlashMenu();

        requestAnimationFrame(function () {
            el.focus();
            if (typeof el.setSelectionRange === 'function') {
                el.setSelectionRange(newPos, newPos);
            } else {
                el.selectionStart = el.selectionEnd = newPos;
            }
            $input.trigger('input');
        });
    }

    $(document).on('mousedown', '.ab-skill-item', function (e) {
        e.stopPropagation();
        selectSkill($(this).data('skill'));
    });

    // ── Plus Flyout Menu ───────────────────────────────────────
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

        let left = triggerRect.right + 8;
        if (left + panelWidth > vw - 8) {
            left = triggerRect.left - panelWidth - 8;
        }
        left = Math.max(8, left);

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

    function showSkillTooltip($item, description) {
        if (!description) { hideSkillTooltip(); return; }
        const $tip = $('#ab-skill-tooltip');
        $tip.text(description).css({ display: 'block', visibility: 'hidden' });
        const itemRect = $item[0].getBoundingClientRect();
        const tipW = $tip.outerWidth() || 220;
        const tipH = $tip.outerHeight() || 40;
        const vw = window.innerWidth, vh = window.innerHeight;

        let left = itemRect.right + 10;
        if (left + tipW > vw - 8) left = itemRect.left - tipW - 10;
        left = Math.max(8, left);

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

    // ── Slash Command Infrastructure ───────────────────────────
    function openSlashMenu() {
        closePlusMenu();
        $('#ab-slash-menu').addClass('open');
    }
    function closeSlashMenu() {
        $('#ab-slash-menu').removeClass('open');
        _slashFiltered = [];
        _slashActiveIndex = -1;
        _slashStartPos = -1;
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
        const q = query.toLowerCase();
        _slashFiltered = !q ? _skills.slice() : _skills.filter(s =>
            (s.name || '').toLowerCase().startsWith(q) || (s.label || '').toLowerCase().startsWith(q)
        );
        _slashActiveIndex = _slashFiltered.length ? 0 : -1;
        renderSkillList($('#ab-slash-list'), _slashFiltered);
        highlightSlashActive();
        $('#ab-slash-count').text(_slashFiltered.length ? `· ${_slashFiltered.length}` : '');
    }

    function handleSlashTrigger() {
        const el = document.getElementById('ab-input');
        if (!el) return;
        const value = el.value;
        const cursorPos = el.selectionStart;

        let slashPos = -1;
        for (let i = cursorPos - 1; i >= 0; i--) {
            const ch = value[i];
            if (ch === ' ' || ch === '\n') break;
            if (ch === '/' && (i === 0 || /[\s\n]/.test(value[i - 1]))) {
                slashPos = i;
                break;
            }
        }

        if (slashPos === -1) {
            _slashStartPos = -1;
            closeSlashMenu();
            return;
        }

        const query = value.slice(slashPos + 1, cursorPos);
        if (!/^[a-zA-Z0-9_-]*$/.test(query)) {
            _slashStartPos = -1;
            closeSlashMenu();
            return;
        }

        _slashStartPos = slashPos;
        openSlashMenu();
        if (!_skillsLoaded) {
            renderSkillList($('#ab-slash-list'), []);
            loadSkills(() => filterSlashMenu(query));
        } else {
            filterSlashMenu(query);
        }
    }

    $(document).on('blur', '#ab-input', function () {
        _slashBlurTimeout = setTimeout(closeSlashMenu, 150);
    });

    $(document).on('focus', '#ab-input', function () {
        if (_slashBlurTimeout) {
            clearTimeout(_slashBlurTimeout);
            _slashBlurTimeout = null;
        }
    });

    $(document).on('keyup', '#ab-input', function (e) {
        if ($('#ab-slash-menu').hasClass('open') &&
            ['ArrowLeft', 'ArrowRight', 'Home', 'End'].indexOf(e.key) !== -1) {
            handleSlashTrigger();
        }
    });

    // ── Twin-Layer Highlighting Synchronization ────────────────
    function _updateInputHighlight() {
        const el = document.getElementById('ab-input');
        const hl = document.getElementById('ab-input-highlight');
        if (!el || !hl) return;

        if (!_skillSlugSet.size || !el.value) {
            hl.innerHTML = '';
            el.classList.remove('ab-has-highlight');
            return;
        }

        const text = el.value;
        let html = '';
        let lastIndex = 0;
        const regex = /\/([a-zA-Z0-9_-]+)/g;
        let match;

        while ((match = regex.exec(text)) !== null) {
            if (match.index > lastIndex) {
                html += escapeHtml(text.slice(lastIndex, match.index));
            }
            const slug = match[1].toLowerCase();
            if (_skillSlugSet.has(slug)) {
                html += '<span class="ab-skill-token">' + escapeHtml(match[0]) + '</span>';
            } else {
                html += escapeHtml(match[0]);
            }
            lastIndex = match.index + match[0].length;
        }

        if (lastIndex < text.length) {
            html += escapeHtml(text.slice(lastIndex));
        }

        hl.innerHTML = html;
        el.classList.add('ab-has-highlight');
    }

    $(document).on('scroll', '#ab-input', function () {
        const hl = document.getElementById('ab-input-highlight');
        if (hl) hl.scrollTop = this.scrollTop;
    });

    // ── Attachment Processing ──────────────────────────────────
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

    // ── Context Boundary Controls ──────────────────────────────
    $(document).on('mousedown', function (e) {
        const $t = $(e.target);
        if (!$t.closest('#ab-plus-menu, #ab-plus-btn, #ab-skill-panel, #ab-skill-tooltip').length) {
            closePlusMenu();
        }
        if (!$t.closest('#ab-slash-menu, #ab-slash-list, #ab-input').length) {
            closeSlashMenu();
        }
    });
    $(document).on('keydown', function (e) {
        if (e.key === 'Escape') { closePlusMenu(); closeSlashMenu(); }
    });

    // ── Dispatch Controls ──────────────────────────────────────
    let _lastSentMessage = '', _lastSentAttachments = [];

    function dispatchChatRequest(msg, attachments, isFirstMessage) {
        _lastSentMessage = msg;
        _lastSentAttachments = attachments || [];

        ChatMessages.appendUserMsg(msg, attachments);
        setStatus('Thinking…', true);
        ChatMessages.showTyping();

        if (isFirstMessage) ChatRealtime.expectNewSession();

        frappe.call({
            method: 'agent_builder.native_api.verify.chat',
            args: { message: msg, chat_id: currentChatId, attachments: JSON.stringify(attachments || []) },
            callback(r) {
                if (r.message && r.message.chat_id) {
                    currentChatId = r.message.chat_id;
                    _currentJobId = r.message.job_id || null;
                    ChatRealtime.setActiveSession(currentChatId);

                    if (isFirstMessage) {
                        ChatList.prepend(r.message);
                        ChatList.setActive(currentChatId);
                        $('#ab-header-name').text(r.message.title || 'Chat');
                    }
                }
            },
            error() {
                _currentJobId = null;
                setInputState(false);
                setStatus('Error', false, true);
                try { ChatMessages.onDone("Sorry, I couldn't send that. Please try again.", true); } catch (err) { console.error(err); }
            }
        });
    }

    function sendMessage() {
        const msg = $('#ab-input').val().trim();
        if ((!msg && !_pendingFiles.length) || isThinking) return;

        const isFirstMessage = (currentChatId === null);

        if (isFirstMessage) {
            $('#ab-welcome').remove();
        }

        closePlusMenu();
        closeSlashMenu();
        $('#ab-input').val('').css('height', 'auto');
        _updateInputHighlight();
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
    $(document).on('keydown', '#ab-input', function (e) {
        if ($('#ab-slash-menu').hasClass('open')) {
            if (e.key === 'ArrowDown') { e.preventDefault(); moveSlashActive(1); return; }
            if (e.key === 'ArrowUp') { e.preventDefault(); moveSlashActive(-1); return; }
            if (e.key === 'Escape') { e.preventDefault(); closeSlashMenu(); return; }
            if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'Home' || e.key === 'End') {
                return;
            }
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
        handleSlashTrigger();
        _updateInputHighlight();
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