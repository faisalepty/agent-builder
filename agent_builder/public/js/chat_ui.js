/**
 * Chat_Ui.js v4.1 — SOTA Hermes Orchestrator
 * v4.1 adds: "+" input menu (file upload + skill browser), "/" slash-command
 * skill autocomplete, and a redesigned welcome/suggestions screen.
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
        // ── New in v4.1 ──
        paperclip:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>`,
        skillIcon:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="5"/><line x1="15" y1="7" x2="9" y2="17"/></svg>`,
        chevronRight:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="9 18 15 12 9 6"/></svg>`,
        fileText:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/></svg>`,
        listIcon:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>`,
        plusCircle:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>`,
        layers:      `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`,
        barChart:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>`,
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
                            <div id="ab-attachments-row"></div>

                            <textarea id="ab-input" rows="1" placeholder="Ask Hermes anything…"></textarea>

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
        closePlusMenu();
        closeSlashMenu();
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
        closePlusMenu();
        closeSlashMenu();
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

    $(document).on('click', '.ab-suggestion-card', function () {
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
        const winEl = document.getElementById('ab-window');
        if (!winEl || !$trigger.length) return;
        const triggerRect = $trigger[0].getBoundingClientRect();
        const winRect = winEl.getBoundingClientRect();
        const panelWidth = $panel.outerWidth() || 240;
        const spaceRight = winRect.right - triggerRect.right;
        if (spaceRight < panelWidth + 16) {
            $panel.css({ left: 'auto', right: '100%', marginLeft: 0, marginRight: '8px' });
        } else {
            $panel.css({ left: '100%', right: 'auto', marginRight: 0, marginLeft: '8px' });
        }
    }

    function openSkillFlyout($trigger) {
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
        $('#ab-skill-panel').removeClass('open');
        hideSkillTooltip();
    }

    $(document).on('mouseenter', '#ab-plus-menu .ab-has-flyout', function () {
        if ($('#ab-plus-menu').hasClass('open')) openSkillFlyout($(this));
    });
    $(document).on('mouseleave', '#ab-plus-menu .ab-has-flyout', function () {
        closeSkillFlyout();
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

    // Skill description tooltip (shared by flyout + slash menu)
    function showSkillTooltip($item, description) {
        if (!description) { hideSkillTooltip(); return; }
        const winEl = document.getElementById('ab-window');
        const $tip = $('#ab-skill-tooltip');
        if (!winEl) return;
        $tip.text(description).css({ display: 'block', visibility: 'hidden' });
        const winRect = winEl.getBoundingClientRect();
        const itemRect = $item[0].getBoundingClientRect();
        const tipW = $tip.outerWidth() || 200;
        const tipH = $tip.outerHeight() || 40;

        let left = itemRect.right - winRect.left + 10;
        if (itemRect.right + tipW + 10 > winRect.right) {
            left = itemRect.left - winRect.left - tipW - 10;
        }
        left = Math.max(8, left);

        let top = itemRect.top - winRect.top;
        if (itemRect.top + tipH > winRect.bottom) {
            top = winRect.height - tipH - 12;
        }
        top = Math.max(8, top);

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
            ChatMessages.appendUserMsg(msg, attachments);
            setStatus('Thinking…', true);
            ChatMessages.showTyping();

            frappe.call({
                method: 'agent_builder.api.agent.chat',
                args: { message: msg, chat_id: currentChatId, attachments: JSON.stringify(attachments) },
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
                    setInputState(false);
                    setStatus('Error', false);
                }
            });
        }).catch(() => {
            setInputState(false);
            setStatus('Upload failed', false);
            $('#ab-input').val(msg).trigger('input').focus();
            _pendingFiles = filesToUpload;
            renderAttachmentChips();
        });
    }

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