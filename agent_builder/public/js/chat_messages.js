/**
 * chat_messages.js v4.3 — SOTA DOM structure update
 * Generates cleaner HTML for bubbles to perfectly match the new CSS.
 * v4.3: artifact "fullscreen" now portals to <body> so it's a true
 * viewport-relative overlay regardless of the chat window's condensed vs.
 * expanded state (previously constrained to the window's own box because
 * #ab-window's transform makes it a containing block for position:fixed
 * descendants); a backdrop + Escape/click-outside to exit; tool-call steps
 * rewritten with per-tool icons, running→done label tense changes, and a
 * click-to-expand detail panel (raw tool name + arguments).
 * v4.2: persisted tool-call steps reconstructed on history reload, error-
 * styled bubbles with a Retry action, icon-only message actions, a real
 * "Edit" action that doesn't auto-send, and a redesigned thinking/typing
 * indicator.
 */
window.ChatMessages = (function () {

    let _icons = {};
    let _streamBubbleId = null, _streamBuffer = '', _streamFlushScheduled = false, _typingRowId = null;
    let _currentThinkingRow = null, _currentThinkingSteps = [], _thinkStartTime = null;
    let _stopped = false;
    const _artifactStore = new Map();
    const _artifactAnchors = new Map(); // artifactId -> placeholder comment node (records where to put it back)
    let _artifactSeq = 0;
    function _nextId() { return 'ab-' + (++_artifactSeq); }

    function init(icons) {
        _icons = icons;
        _listenResize();
    }

    function _listenResize() {
        window.addEventListener('message', function (e) {
            if (e.data && e.data.type === 'ab-resize') {
                document.querySelectorAll('.ab-artifact-iframe').forEach(function (iframe) {
                    try {
                        if (iframe.contentWindow !== e.source) return;
                        const cap = iframe.closest('.ab-artifact-full') ? Infinity : 640;
                        iframe.style.height = Math.max(80, Math.min(e.data.height, cap)) + 'px';
                    } catch (_) {}
                });
            }
        });
    }

    function clear() {
        collapseAllFullscreenArtifacts();
        $('#ab-messages').empty();
        _artifactStore.clear();
        _artifactAnchors.clear();
        _resetStreamState();
        _resetThinkingState();
        _stopped = false;
    }

    function _wrapTables(container) {
    $(container).find('table').each(function() {
        // Prevent double wrapping
        if (!$(this).parent().hasClass('ab-table-wrapper')) {
            $(this).wrap('<div class="ab-table-wrapper"></div>');
        }
    });
}

    function _resetStreamState() { _streamBubbleId = null; _streamBuffer = ''; _streamFlushScheduled = false; _typingRowId = null; }
    function _resetThinkingState() { _currentThinkingRow = null; _currentThinkingSteps = []; _thinkStartTime = null; }

    function loadHistory(chatId) {
        clear();
        $('#ab-welcome').hide();
        $('#ab-messages').html('<div class="ab-loading" style="text-align:center;color:var(--text-muted);padding:40px 0;">Loading conversation…</div>');

        frappe.call({
            method: 'agent_builder.api.agent.get_messages',
            args: { chat_id: chatId },
            callback(r) {
                $('#ab-messages').empty();
                if (!r.message || !r.message.messages.length) { $('#ab-welcome').show(); return; }
                r.message.messages.forEach(msg => {
                    if (msg.role === 'user') {
                        _appendUserMessage(msg.content, _safeParseJSON(msg.attachments));
                    } else if (msg.role === 'assistant') {
                        const steps = _safeParseJSON(msg.tool_calls);
                        if (steps && steps.length) _renderHistoricalToolSteps(steps);
                        _appendAgentMessage(msg.content, !!msg.is_error);
                    }
                });
                _whenDomReady(() => { _mountAllArtifacts(); _addAllCodeCopyButtons(); _scrollDown(); });
            }
        });
    }

    function _whenDomReady(callback, maxAttempts = 10, interval = 50) {
        let attempts = 0;
        function check() {
            const frames = document.querySelectorAll('.ab-artifact-frame');
            if (frames.length > 0 || attempts >= maxAttempts) callback();
            else { attempts++; setTimeout(check, interval); }
        }
        setTimeout(check, 0);
    }

    // SOTA Structure for Agent message
    function _appendAgentMessage(content, isError) {
        if (!content) return;
        const msgId = _nextId();
        $('#ab-messages').append(
            `<div class="ab-row agent${isError ? ' is-error' : ''}" id="${msgId}">
                <div class="ab-avatar">${isError ? (_icons.alertTriangle || _icons.bot) : _icons.bot}</div>
                <div class="ab-bubble-wrap">
                    <div class="ab-bubble${isError ? ' ab-bubble-error' : ''}" id="${msgId}-bubble"></div>
                    <div class="ab-msg-actions">
                        <button class="ab-msg-action-btn ab-copy-btn" data-bubble="${msgId}-bubble" title="Copy">${_icons.copy}</button>
                        ${isError ? `<button class="ab-msg-action-btn ab-resend-btn" title="Retry">${_icons.retry || ''}</button>` : ''}
                    </div>
                </div>
            </div>`
        );
        const bubbleEl = document.getElementById(msgId + '-bubble');
        if (isError) {
            bubbleEl.innerHTML = _escapeHtml(content);
        } else {
            bubbleEl.innerHTML = _renderContentWithArtifacts(content);
            // NEW: Ensure any tables rendered in this bubble are wrapped for responsiveness
            _wrapTables(bubbleEl);
        }
    }

    // SOTA Structure for User message (no avatar, rounded bubble)
    function _appendUserMessage(text, attachments) {
        const id = _nextId();
        const hasText = !!(text && String(text).trim());
        const attachmentsHtml = _renderAttachmentsHtml(attachments);
        const bubbleHtml = hasText ? `
            <div class="ab-bubble" id="${id}-bubble">${_escapeHtml(text)}</div>
            <div class="ab-msg-actions" style="justify-content:flex-end;width:100%;">
                <button class="ab-msg-action-btn ab-edit-btn" data-bubble="${id}-bubble" title="Edit">${_icons.edit || _icons.retry}</button>
                <button class="ab-msg-action-btn ab-copy-btn" data-bubble="${id}-bubble" title="Copy">${_icons.copy}</button>
            </div>` : '';
        $('#ab-messages').append(
            `<div class="ab-row user" id="${id}">
                <div class="ab-bubble-wrap">
                    ${attachmentsHtml}
                    ${bubbleHtml}
                </div>
            </div>`
        );
        _scrollDown();
    }

    function _renderAttachmentsHtml(attachments) {
        if (!attachments || !attachments.length) return '';
        const chips = attachments.map(a => `
            <a class="ab-msg-attachment" href="${_escapeHtml(a.file_url || '#')}" target="_blank" rel="noopener">
                ${_icons.fileText || ''}<span>${_escapeHtml(a.file_name || 'file')}</span>
            </a>
        `).join('');
        return `<div class="ab-msg-attachments">${chips}</div>`;
    }

    function _safeParseJSON(raw) {
        if (!raw) return null;
        if (typeof raw !== 'string') return raw;
        try { return JSON.parse(raw); } catch (_) { return null; }
    }

    function showTyping() {
        if (_typingRowId) return;
        _typingRowId = _nextId();
        $('#ab-messages').append(
            `<div class="ab-row agent" id="${_typingRowId}">
                <div class="ab-avatar">${_icons.bot}</div>
                <div class="ab-typing-pill">
                    <span class="ab-typing-label">Thinking</span>
                    <div class="ab-typing-dots"><span></span><span></span><span></span></div>
                </div>
            </div>`
        );
        _scrollDown();
    }

    function hideTyping() { if (_typingRowId) { $('#' + _typingRowId).remove(); _typingRowId = null; } }

    function _ensureStreamBubble() {
        if (_streamBubbleId && document.getElementById(_streamBubbleId)) return;
        _streamBubbleId = _nextId();
        _streamBuffer = '';
        $('#ab-messages').append(
            `<div class="ab-row agent" id="row-${_streamBubbleId}">
                <div class="ab-avatar">${_icons.bot}</div>
                <div class="ab-bubble-wrap">
                    <div class="ab-bubble" id="${_streamBubbleId}"></div>
                    <div class="ab-msg-actions">
                        <button class="ab-msg-action-btn ab-copy-btn" data-bubble="${_streamBubbleId}" title="Copy">${_icons.copy}</button>
                    </div>
                </div>
            </div>`
        );
        _scrollDown();
    }

    function onToken(delta) {
        if (!delta || _stopped) return;
        _ensureStreamBubble();
        _streamBuffer += delta;
        if (!_streamFlushScheduled) { _streamFlushScheduled = true; requestAnimationFrame(_flushStream); }
    }

    function _flushStream() {
        _streamFlushScheduled = false;
        if (!_streamBubbleId || _stopped) return;
        const el = document.getElementById(_streamBubbleId);
        if (el) {
            el.innerHTML = _md(_streamBuffer) + '<span class="ab-cursor"></span>';
            _wrapTables(el);
            _scrollDown(true);
        }
    }

    // SOTA Thinking Accordion
    function _bindThinkingToggle($container) {
        $container.find('.ab-thinking-pill').off('click').on('click', function () {
            $(this).siblings('.ab-thinking-steps').toggle();
            $(this).toggleClass('expanded');
        });
    }

    // Per-step click-to-expand: reveals the raw tool name + arguments (and,
    // once available, the result/error) below the one-line summary —
    // collapsed by default so the common case stays a clean glance-able
    // list, with full transparency one click away.
    $(document).on('click', '.ab-thinking-step', function () {
        $(this).toggleClass('ab-step-expanded');
    });

    // Maps a backend tool name to one of the icons already in the shared
    // ICONS set (passed in via init()), so each action row carries a
    // consistent, recognizable glyph instead of a generic spinner/check.
    const TOOL_ICON_MAP = {
        frappe_get_list: 'listIcon',
        frappe_get_doc: 'fileText',
        frappe_save_doc: 'edit',
        web_search: 'search',
        execute_code: 'terminal',
    };

    // Builds { icon, args, running, done } for a tool call. "running" and
    // "done" are deliberately different tenses (present continuous vs.
    // simple past) — the tense change, not an icon swap, is what signals
    // completion, matching how Claude itself narrates tool use.
    function _toolMeta(toolName, argsStr) {
        let args = {};
        try { args = typeof argsStr === 'string' ? JSON.parse(argsStr) : (argsStr || {}); } catch (_) {}

        const builders = {
            frappe_get_list: () => { const dt = args.doctype || 'records'; return [`Fetching ${dt}`, `Fetched ${dt}`]; },
            frappe_get_doc: () => { const dt = args.doctype || 'document'; const n = args.name ? ` › ${args.name}` : ''; return [`Reading ${dt}${n}`, `Read ${dt}${n}`]; },
            frappe_save_doc: () => {
                const dt = (args.doc && args.doc.doctype) || 'record';
                return (args.doc && args.doc.name) ? [`Updating ${dt}`, `Updated ${dt}`] : [`Creating ${dt}`, `Created ${dt}`];
            },
            web_search: () => { const q = (args.query || '').slice(0, 48); return [`Searching the web for "${q}"`, `Searched the web for "${q}"`]; },
            execute_code: () => { const lang = args.language || 'script'; return [`Running ${lang}`, `Ran ${lang}`]; },
        };

        let running, done;
        if (builders[toolName]) {
            [running, done] = builders[toolName]();
        } else {
            const human = (toolName || 'tool').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            running = `${human}…`; done = human;
        }
        const icon = _icons[TOOL_ICON_MAP[toolName]] || _icons.skillIcon || _icons.check;
        return { icon, args, running, done };
    }

    function _prettyArgs(args) {
        try {
            const json = JSON.stringify(args, null, 2);
            return _escapeHtml(json && json !== '{}' ? json : 'No arguments');
        } catch (_) { return ''; }
    }

    function _finalizedPillHtml(isError, label) {
        const icon = isError ? (_icons.alertTriangle || _icons.check) : _icons.check;
        return `<span class="ab-thinking-status-icon">${icon}</span><span>${label}</span><span class="ab-chevron">${_icons.down}</span>`;
    }

    function _formatElapsed(ms) {
        if (!ms || ms < 0) return '0ms';
        return ms < 1000 ? ms + 'ms' : (ms / 1000).toFixed(1) + 's';
    }

    function onToolStart(data) {
        hideTyping();
        if (!_currentThinkingRow) {
            _thinkStartTime = Date.now();
            _currentThinkingRow = _nextId();
            _currentThinkingSteps = [];
            const $thinking = $(
                `<div class="ab-thinking-container" id="${_currentThinkingRow}">
                    <div class="ab-thinking-pill expanded">
                        <div class="ab-spinner"></div>
                        <span>Thinking</span>
                        <span class="ab-chevron">${_icons.down}</span>
                    </div>
                    <div class="ab-thinking-steps"></div>
                </div>`
            );
            _streamBubbleId ? $(`#row-${_streamBubbleId}`).before($thinking) : $('#ab-messages').append($thinking);
            _bindThinkingToggle($thinking);
        }

        const stepId = _nextId();
        const meta = _toolMeta(data.tool, data.args);
        _currentThinkingSteps.push({ id: stepId, startTime: Date.now(), status: 'running', doneLabel: meta.done });

        $(`#${_currentThinkingRow} .ab-thinking-steps`).append(
            `<div class="ab-thinking-step" id="${stepId}">
                <div class="ab-step-icon running">${meta.icon}</div>
                <div class="ab-step-main">
                    <div class="ab-step-headline">
                        <span class="ab-step-name running">${_escapeHtml(meta.running)}</span>
                        <span class="ab-step-time"></span>
                        <span class="ab-step-chevron">${_icons.down}</span>
                    </div>
                    <div class="ab-step-detail">
                        <div class="ab-step-detail-label">${_escapeHtml(data.tool || '')}</div>
                        <pre class="ab-step-detail-block">${_prettyArgs(meta.args)}</pre>
                    </div>
                </div>
            </div>`
        );
        _scrollDown();
    }

    function onToolDone(data) {
        const step = _currentThinkingSteps.find(s => s.status === 'running');
        if (!step) return;
        const elapsed = Date.now() - step.startTime;
        const elStr = _formatElapsed(elapsed);
        const isError = !!(data && (data.error || data.success === false));

        const $step = $('#' + step.id);
        $step.find('.ab-step-icon').removeClass('running');
        $step.find('.ab-step-name').removeClass('running').addClass(isError ? 'errored' : 'done').text(step.doneLabel || '');
        $step.find('.ab-step-time').text(elStr);
        $step.toggleClass('ab-step-is-error', isError);
        if (isError) $step.find('.ab-step-icon').addClass('errored').html(_icons.alertTriangle || _icons.check);

        // Backend payload shape for tool-done isn't fixed elsewhere in this
        // app, so this checks the common field names defensively and simply
        // shows nothing extra (just the args already rendered) if none are
        // present — never throws either way.
        const resultText = data && (data.error || data.result || data.output || data.response);
        if (resultText !== undefined && resultText !== null && resultText !== '') {
            const pretty = typeof resultText === 'string' ? resultText : JSON.stringify(resultText, null, 2);
            $step.find('.ab-step-detail').append(
                `<div class="ab-step-detail-label">${isError ? 'Error' : 'Result'}</div>
                 <pre class="ab-step-detail-block${isError ? ' is-error' : ''}">${_escapeHtml(String(pretty).slice(0, 4000))}</pre>`
            );
        }

        step.status = isError ? 'error' : 'done';
        _scrollDown();
    }

    function _addResendButton(row) {
        if (!row) return;
        const $actions = $(row).find('.ab-msg-actions');
        if (!$actions.length || $actions.find('.ab-resend-btn').length) return;
        $actions.append(`<button class="ab-msg-action-btn ab-resend-btn" title="Retry">${_icons.retry || ''}</button>`);
    }

    function onDone(response, isError) {
        hideTyping();
        if (_currentThinkingRow) {
            const total = _thinkStartTime ? Date.now() - _thinkStartTime : 0;
            const totalStr = _formatElapsed(total);
            const $pill = $(`#${_currentThinkingRow} .ab-thinking-pill`);

            $pill.removeClass('expanded').addClass(isError ? 'errored' : 'done').html(
                _finalizedPillHtml(isError, isError ? 'Stopped after an error' : `Thought for ${totalStr}`)
            );
            $(`#${_currentThinkingRow} .ab-thinking-steps`).hide(); // Auto collapse on done
            _resetThinkingState();
        }

        if (_streamBubbleId) {
            const el = document.getElementById(_streamBubbleId);
            const row = document.getElementById('row-' + _streamBubbleId);
            if (el) {
                if (isError) {
                    if (row) row.classList.add('is-error');
                    el.classList.add('ab-bubble-error');
                    el.innerHTML = _escapeHtml(response || 'Sorry, something went wrong.');
                    _addResendButton(row);
                } else {
                    el.innerHTML = _renderContentWithArtifacts(response || _streamBuffer || '');
                    _wrapTables(el);
                    setTimeout(() => { _mountAllArtifacts(); _addCodeCopyButtons(el); _scrollDown(); }, 0);
                }
            }
        } else if (response) {
            _appendAgentMessage(response, isError);
            setTimeout(() => { _mountAllArtifacts(); _scrollDown(); }, 0);
        }
        _resetStreamState();
    }

    function onStop() {
        _stopped = true;
        if (_streamBubbleId) {
            const el = document.getElementById(_streamBubbleId);
            if (el) { el.innerHTML = _md(_streamBuffer); _addCodeCopyButtons(el); }
            _streamBubbleId = null;
        }
        hideTyping();
    }

    function _renderContentWithArtifacts(text) {
        if (!text) return '';
        const htmlBlockRegex = /```html\s*\n([\s\S]*?)```/g;
        let lastIndex = 0, match, parts = [];
        while ((match = htmlBlockRegex.exec(text)) !== null) {
            if (match.index > lastIndex) parts.push({ type: 'md', content: text.slice(lastIndex, match.index) });
            parts.push({ type: 'html', id: _nextId(), content: match[1].trim() });
            lastIndex = match.index + match[0].length;
        }
        if (lastIndex < text.length) parts.push({ type: 'md', content: text.slice(lastIndex) });
        if (!parts.length || (parts.length === 1 && parts[0].type === 'md')) return _md(text);
        return parts.map(p => p.type === 'md' ? _md(p.content) : _createArtifactHTML(p.id, p.content)).join('');
    }

    function _createArtifactHTML(id, htmlContent) {
        _artifactStore.set(id, htmlContent);
        return `
            <div class="ab-artifact" data-artifact-id="${id}">
                <div class="ab-artifact-bar">
                    <div class="ab-artifact-dot"></div>
                    <span class="ab-artifact-label">Generated UI</span>
                    <div class="ab-artifact-actions">
                        <button class="ab-artifact-bar-btn ab-artifact-reload" data-artifact="${id}" title="Reload">${_icons.reload}</button>
                        <button class="ab-artifact-bar-btn ab-artifact-expand" data-artifact="${id}" title="Fullscreen">${_icons.expand}</button>
                    </div>
                </div>
                <div class="ab-artifact-frame"></div>
            </div>`;
    }

    function _mountAllArtifacts() {
        document.querySelectorAll('.ab-artifact').forEach(artifactDiv => {
            const id = artifactDiv.dataset.artifactId;
            const frame = artifactDiv.querySelector('.ab-artifact-frame');
            if (!id || !frame || frame.querySelector('iframe')) return;
            const html = _artifactStore.get(id);
            if (html) _mountSingleArtifact(frame, html);
        });
    }

    function _mountSingleArtifact(frame, htmlContent) {
        const old = frame.querySelector('iframe');
        const iframe = document.createElement('iframe');
        // IMPORTANT: never combine 'allow-scripts' with 'allow-same-origin' here.
        // A sandboxed srcdoc iframe only gets an opaque, isolated origin when
        // allow-same-origin is ABSENT. Adding it back lets generated-HTML
        // script reach window.parent.document directly (it becomes
        // same-origin with the Frappe desk page), which is exactly how
        // artifact-injected dropdowns/overlays were leaking onto the desk
        // and swallowing clicks even after the widget was closed. Resizing
        // still works fine without it — postMessage is cross-origin safe.
        iframe.setAttribute('sandbox', 'allow-scripts allow-popups allow-popups-to-escape-sandbox allow-forms allow-modals');
        iframe.className = 'ab-artifact-iframe';
        iframe.srcdoc = htmlContent;
        if (old) frame.replaceChild(iframe, old); else frame.appendChild(iframe);
        iframe.addEventListener('load', () => _adjustIframeHeight(iframe));
    }

    function _adjustIframeHeight(iframe) {
        try {
            // Without allow-same-origin this throws (cross-origin), which is
            // expected — the resize protocol below (postMessage) is the
            // supported path now. The try/catch just keeps same-origin-ish
            // edge cases (e.g. blank/about: frames) from erroring out.
            const doc = iframe.contentDocument || iframe.contentWindow.document;
            const h = Math.max(doc.body?.scrollHeight || 0, doc.documentElement?.scrollHeight || 0);
            const cap = iframe.closest('.ab-artifact-full') ? Infinity : 640;
            if (h > 50) iframe.style.height = Math.min(h + 20, cap) + 'px';
        } catch (_) {}
    }

    function reloadArtifact(artifactId) {
        const artifactDiv = document.querySelector(`.ab-artifact[data-artifact-id="${artifactId}"]`);
        if (artifactDiv) {
            const frame = artifactDiv.querySelector('.ab-artifact-frame');
            if (frame && _artifactStore.get(artifactId)) _mountSingleArtifact(frame, _artifactStore.get(artifactId));
        }
    }

    // Fullscreen is implemented as a "portal": the whole .ab-artifact node
    // (toolbar + iframe) is moved out to be a direct child of <body>, behind
    // a click-to-close backdrop. That's what makes it genuinely fill the
    // browser viewport — left in place, #ab-window's open/close transform
    // makes the window a containing block for any position:fixed descendant,
    // so a "fullscreen" artifact would otherwise only ever fill the (much
    // smaller) chat window's own box, whether the window is condensed or
    // expanded. A comment-node anchor records exactly where to put it back.
    function expandArtifact(artifactId) {
        const el = document.querySelector(`.ab-artifact[data-artifact-id="${artifactId}"]`);
        if (!el) return;
        if (el.classList.contains('ab-artifact-full')) _collapseArtifactEl(el);
        else _expandArtifactEl(el, artifactId);
    }

    function _expandArtifactEl(el, artifactId) {
        if (document.querySelector('.ab-artifact-full')) return; // one fullscreen artifact at a time
        const anchor = document.createComment('ab-artifact-anchor-' + artifactId);
        el.parentNode.insertBefore(anchor, el);
        _artifactAnchors.set(artifactId, anchor);

        const backdrop = document.createElement('div');
        backdrop.className = 'ab-artifact-backdrop';
        backdrop.dataset.artifact = artifactId;
        document.body.appendChild(backdrop);
        document.body.appendChild(el);
        document.body.classList.add('ab-artifact-fullscreen-active');

        el.classList.add('ab-artifact-full');
        $(el).find('.ab-artifact-expand').html(_icons.compress || _icons.expand).attr('title', 'Exit fullscreen');

        const iframe = el.querySelector('.ab-artifact-iframe');
        if (iframe) requestAnimationFrame(() => _adjustIframeHeight(iframe));
    }

    function _collapseArtifactEl(el) {
        const artifactId = el.dataset.artifactId;
        el.classList.remove('ab-artifact-full');
        $(el).find('.ab-artifact-expand').html(_icons.expand).attr('title', 'Fullscreen');

        const anchor = _artifactAnchors.get(artifactId);
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(el, anchor);
            anchor.remove();
        } else {
            // Anchor's gone (e.g. the conversation was cleared/switched) —
            // the safest place left for it is back in the message stream
            // rather than orphaned as a direct child of <body>.
            $('#ab-messages').append(el);
        }
        _artifactAnchors.delete(artifactId);

        document.querySelectorAll(`.ab-artifact-backdrop[data-artifact="${artifactId}"]`).forEach(b => b.remove());
        if (!document.querySelector('.ab-artifact-full')) document.body.classList.remove('ab-artifact-fullscreen-active');

        const iframe = el.querySelector('.ab-artifact-iframe');
        if (iframe) setTimeout(() => _adjustIframeHeight(iframe), 0);
    }

    // Exposed so the chat window can guarantee nothing is left floating on
    // <body> when it closes, a new chat starts, or another conversation
    // loads — independent of (and in addition to) the iframe sandbox fix.
    function collapseAllFullscreenArtifacts() {
        document.querySelectorAll('.ab-artifact.ab-artifact-full').forEach(_collapseArtifactEl);
    }

    $(document).on('click', '.ab-artifact-backdrop', function () {
        const el = document.querySelector(`.ab-artifact[data-artifact-id="${this.dataset.artifact}"]`);
        if (el) _collapseArtifactEl(el);
    });
    $(document).on('keydown', function (e) {
        if (e.key === 'Escape') collapseAllFullscreenArtifacts();
    });

    function _addAllCodeCopyButtons() {
        document.querySelectorAll('#ab-messages .ab-bubble').forEach(b => _addCodeCopyButtons(b));
    }

    function _addCodeCopyButtons(container) {
        $(container).find('pre').each(function () {
            if ($(this).find('.ab-pre-copy').length) return;
            const $pre = $(this);
            const $btn = $(`<button class="ab-pre-copy">${_icons.copy} Copy</button>`);
            $btn.on('click', function () {
                navigator.clipboard.writeText($pre.find('code').text() || $pre.text()).then(() => {
                    $btn.html(`${_icons.check} Copied!`);
                    setTimeout(() => $btn.html(`${_icons.copy} Copy`), 1500);
                });
            });
            $pre.append($btn);
        });
    }

    // Rebuilds a finalized (collapsed) thinking accordion from persisted
    // tool_calls JSON, so reopening a chat still shows what the agent did —
    // previously this only ever existed live in the DOM for that session.
    function _renderHistoricalToolSteps(steps) {
        const rowId = _nextId();
        const totalMs = steps.reduce((sum, s) => sum + (s.elapsed_ms || 0), 0);
        const hasError = steps.some(s => s.status !== 'done');

        const stepsHtml = steps.map(s => {
            const meta = _toolMeta(s.tool, s.args);
            const stepError = s.status !== 'done';
            // Tool-specific icon throughout, same as the live render — only
            // swapped for the alert glyph on error, never a generic check.
            const icon = stepError ? (_icons.alertTriangle || _icons.check) : meta.icon;
            const timeStr = s.elapsed_ms != null ? _formatElapsed(s.elapsed_ms) : '';
            // Not every backend version persists a result/error payload per
            // step — show it if present, render nothing extra if not.
            const resultText = s.error || s.result || s.output || s.response;
            const detailExtra = (resultText !== undefined && resultText !== null && resultText !== '')
                ? `<div class="ab-step-detail-label">${stepError ? 'Error' : 'Result'}</div>
                   <pre class="ab-step-detail-block${stepError ? ' is-error' : ''}">${_escapeHtml(String(typeof resultText === 'string' ? resultText : JSON.stringify(resultText, null, 2)).slice(0, 4000))}</pre>`
                : '';
            return `<div class="ab-thinking-step${stepError ? ' ab-step-is-error' : ''}">
                <div class="ab-step-icon${stepError ? ' errored' : ''}">${icon}</div>
                <div class="ab-step-main">
                    <div class="ab-step-headline">
                        <span class="ab-step-name ${stepError ? 'errored' : 'done'}">${_escapeHtml(meta.done)}</span>
                        <span class="ab-step-time">${_escapeHtml(timeStr)}</span>
                        <span class="ab-step-chevron">${_icons.down}</span>
                    </div>
                    <div class="ab-step-detail">
                        <div class="ab-step-detail-label">${_escapeHtml(s.tool || '')}</div>
                        <pre class="ab-step-detail-block">${_prettyArgs(meta.args)}</pre>
                        ${detailExtra}
                    </div>
                </div>
            </div>`;
        }).join('');

        const $thinking = $(
            `<div class="ab-thinking-container" id="${rowId}">
                <div class="ab-thinking-pill ${hasError ? 'errored' : 'done'}">
                    ${_finalizedPillHtml(hasError, hasError ? 'Stopped after an error' : `Thought for ${_formatElapsed(totalMs)}`)}
                </div>
                <div class="ab-thinking-steps" style="display:none;">${stepsHtml}</div>
            </div>`
        );
        $('#ab-messages').append($thinking);
        _bindThinkingToggle($thinking);
    }

    function _scrollDown(soft) {
        const el = document.getElementById('ab-messages');
        if (!el) return;
        if (soft) { if (el.scrollHeight - el.scrollTop - el.clientHeight < 120) el.scrollTop = el.scrollHeight; }
        else el.scrollTop = el.scrollHeight;
    }

    function _escapeHtml(str) { return (str || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }

    function _md(text) {
        if (!text) return '';
        if (window.marked) return window.marked.parse(text, { breaks: true, gfm: true });
        return _escapeHtml(text).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\n/g, '<br>');
    }

    return { init, clear, loadHistory, appendUserMsg: _appendUserMessage, onToken, onToolStart, onToolDone, onDone, onStop, showTyping, hideTyping, reloadArtifact, expandArtifact, collapseAllFullscreenArtifacts };
})();