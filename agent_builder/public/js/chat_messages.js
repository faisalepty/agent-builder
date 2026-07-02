/**
 * chat_messages.js v4.3.3 — SOTA DOM structure update
 * Generates cleaner HTML for bubbles to perfectly match the new CSS.
 * v4.3: artifact "fullscreen" now portals to <body> so it's a true
 * viewport-relative overlay regardless of the chat window's condensed vs.
 * expanded state; a backdrop + Escape/click-outside to exit; tool-call
 * steps rewritten with per-tool icons, running→done label tense changes,
 * and a click-to-expand detail panel (raw tool name + arguments).
 * v4.2: persisted tool-call steps reconstructed on history reload, error-
 * styled bubbles with a Retry action, icon-only message actions, a real
 * "Edit" action that doesn't auto-send, and a redesigned thinking/typing
 * indicator.
 * v4.3.1: FIX — historical tool calls no longer show as errors (was
 * comparing against "done" but backend persists "success"/"error"); FIX —
 * reasoning (chain-of-thought) now renders on session reload.
 * v4.3.2: FIX — multiple reasoning/tool segments within a single episode
 * are correctly grouped into ONE thinking container on reload.
 * v4.3.3: All elapsed-time displays removed from tool steps and reasoning.
 *   Labels unified: "Thinking" while reasoning streams, "Thought Process"
 *   when finalized; "Working" while tools execute.
 */
window.ChatMessages = (function () {

    var _icons = {};
    var _CLOCK_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15.5 14"/></svg>';
    var _streamBubbleId = null, _streamBuffer = '', _streamFlushScheduled = false, _typingRowId = null;
    var _currentThinkingRow = null, _currentThinkingSteps = [], _thinkStartTime = null;
    var _reasoningBlockId = null, _reasoningBuffer = '', _reasoningFlushScheduled = false;
    var _reasoningStartTime = null, _reasoningElapsedMs = null, _reasoningLive = false;
    var _stopped = false;
    var _artifactStore = new Map();
    var _artifactAnchors = new Map();
    var _artifactSeq = 0;
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
                        var cap = iframe.closest('.ab-artifact-full') ? Infinity : 640;
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
        $(container).find('table').each(function () {
            if (!$(this).parent().hasClass('ab-table-wrapper')) {
                $(this).wrap('<div class="ab-table-wrapper"></div>');
            }
        });
    }

    function _resetStreamState() { _streamBubbleId = null; _streamBuffer = ''; _streamFlushScheduled = false; _typingRowId = null; }
    function _resetThinkingState() {
        _currentThinkingRow = null; _currentThinkingSteps = []; _thinkStartTime = null;
        _reasoningBlockId = null; _reasoningBuffer = ''; _reasoningFlushScheduled = false;
        _reasoningStartTime = null; _reasoningElapsedMs = null; _reasoningLive = false;
    }

    // ──────────────────────────────────────────────────────────────────
    // History reload
    //
    // Consecutive empty assistant rows (reasoning + tool pairs with no
    // text content) are accumulated into a single episode and flushed
    // as ONE thinking container when text arrives — mirroring the live
    // _currentThinkingRow state machine.
    // ──────────────────────────────────────────────────────────────────
    function loadHistory(chatId) {
        clear();
        $('#ab-welcome').hide();
        $('#ab-messages').html('<div class="ab-loading" style="text-align:center;color:var(--text-muted);padding:40px 0;">Loading conversation…</div>');

        frappe.call({
            method: 'agent_builder.native_api.verify.get_messages',
            args: { chat_id: chatId },
            callback: function (r) {
                $('#ab-messages').empty();
                if (!r.message || !r.message.messages.length) { $('#ab-welcome').show(); return; }

                var pendingSegments = [];

                function flushPending() {
                    if (pendingSegments.length) {
                        _renderHistoricalThinkingContainer(pendingSegments);
                        pendingSegments = [];
                    }
                }

                r.message.messages.forEach(function (msg) {
                    if (msg.role === 'user') {
                        flushPending();
                        _appendUserMessage(msg.content, _safeParseJSON(msg.attachments));

                    } else if (msg.role === 'assistant') {
                        var steps = _safeParseJSON(msg.tool_calls);
                        var hasContent = !!(msg.content && msg.content.trim());

                        if (hasContent) {
                            // Reasoning attached to this text-carrying row
                            // belongs to the current episode.
                            if (msg.reasoning && msg.reasoning.text) {
                                pendingSegments.push({ type: 'reasoning', data: msg.reasoning });
                            }
                            flushPending();
                            _appendAgentMessage(msg.content, !!msg.is_error);
                            // Rare: LLM returns both content AND tool_calls
                            if (steps && steps.length) {
                                _renderHistoricalThinkingContainer([{ type: 'steps', data: steps }]);
                            }

                        } else {
                            var hasWork = (steps && steps.length) || (msg.reasoning && msg.reasoning.text);
                            if (hasWork) {
                                if (msg.reasoning && msg.reasoning.text) {
                                    pendingSegments.push({ type: 'reasoning', data: msg.reasoning });
                                }
                                if (steps && steps.length) {
                                    pendingSegments.push({ type: 'steps', data: steps });
                                }
                            }
                        }
                    }
                });

                flushPending();

                _whenDomReady(function () { _mountAllArtifacts(); _addAllCodeCopyButtons(); _scrollDown(); });
            }
        });
    }

    function _whenDomReady(callback, maxAttempts, interval) {
        maxAttempts = maxAttempts || 10;
        interval = interval || 50;
        var attempts = 0;
        function check() {
            var frames = document.querySelectorAll('.ab-artifact-frame');
            if (frames.length > 0 || attempts >= maxAttempts) callback();
            else { attempts++; setTimeout(check, interval); }
        }
        setTimeout(check, 0);
    }

    // SOTA Structure for Agent message
    function _appendAgentMessage(content, isError) {
        if (!content) return;
        var msgId = _nextId();
        $('#ab-messages').append(
            '<div class="ab-row agent' + (isError ? ' is-error' : '') + '" id="' + msgId + '">' +
                '<div class="ab-avatar">' + (isError ? (_icons.alertTriangle || _icons.bot) : _icons.bot) + '</div>' +
                '<div class="ab-bubble-wrap">' +
                    '<div class="ab-bubble' + (isError ? ' ab-bubble-error' : '') + '" id="' + msgId + '-bubble"></div>' +
                    '<div class="ab-msg-actions">' +
                        '<button class="ab-msg-action-btn ab-copy-btn" data-bubble="' + msgId + '-bubble" title="Copy">' + _icons.copy + '</button>' +
                        (isError ? '<button class="ab-msg-action-btn ab-resend-btn" title="Retry">' + (_icons.retry || '') + '</button>' : '') +
                    '</div>' +
                '</div>' +
            '</div>'
        );
        var bubbleEl = document.getElementById(msgId + '-bubble');
        if (isError) {
            bubbleEl.innerHTML = _escapeHtml(content);
        } else {
            bubbleEl.innerHTML = _renderContentWithArtifacts(content);
            _wrapTables(bubbleEl);
        }
    }

    // SOTA Structure for User message
    function _appendUserMessage(text, attachments) {
        var id = _nextId();
        var hasText = !!(text && String(text).trim());
        var attachmentsHtml = _renderAttachmentsHtml(attachments);
        var bubbleHtml = hasText ?
            '<div class="ab-bubble" id="' + id + '-bubble">' + _escapeHtml(text) + '</div>' +
            '<div class="ab-msg-actions" style="justify-content:flex-end;width:100%;">' +
                '<button class="ab-msg-action-btn ab-edit-btn" data-bubble="' + id + '-bubble" title="Edit">' + (_icons.edit || _icons.retry) + '</button>' +
                '<button class="ab-msg-action-btn ab-copy-btn" data-bubble="' + id + '-bubble" title="Copy">' + _icons.copy + '</button>' +
            '</div>' : '';
        $('#ab-messages').append(
            '<div class="ab-row user" id="' + id + '">' +
                '<div class="ab-bubble-wrap">' +
                    attachmentsHtml +
                    bubbleHtml +
                '</div>' +
            '</div>'
        );
        _scrollDown();
    }

    function _renderAttachmentsHtml(attachments) {
        if (!attachments || !attachments.length) return '';
        var chips = attachments.map(function (a) {
            return '<a class="ab-msg-attachment" href="' + _escapeHtml(a.file_url || '#') + '" target="_blank" rel="noopener">' +
                (_icons.fileText || '') +
                '<span>' + _escapeHtml(a.file_name || 'file') + '</span>' +
            '</a>';
        }).join('');
        return '<div class="ab-msg-attachments">' + chips + '</div>';
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
            '<div class="ab-row agent" id="' + _typingRowId + '">' +
                '<div class="ab-avatar">' + _icons.bot + '</div>' +
                '<div class="ab-thinking-flat">' +
                    '<span class="ab-shimmer-text">Thinking</span>' +
                '</div>' +
            '</div>'
        );
        _scrollDown();
    }

    function hideTyping() { if (_typingRowId) { $('#' + _typingRowId).remove(); _typingRowId = null; } }

    function _ensureStreamBubble() {
        if (_streamBubbleId && document.getElementById(_streamBubbleId)) return;
        _streamBubbleId = _nextId();
        _streamBuffer = '';
        $('#ab-messages').append(
            '<div class="ab-row agent" id="row-' + _streamBubbleId + '">' +
                '<div class="ab-avatar">' + _icons.bot + '</div>' +
                '<div class="ab-bubble-wrap">' +
                    '<div class="ab-bubble" id="' + _streamBubbleId + '"></div>' +
                    '<div class="ab-msg-actions">' +
                        '<button class="ab-msg-action-btn ab-copy-btn" data-bubble="' + _streamBubbleId + '" title="Copy">' + _icons.copy + '</button>' +
                    '</div>' +
                '</div>' +
            '</div>'
        );
        _scrollDown();
    }

    function onToken(delta) {
        if (!delta || _stopped) return;
        hideTyping();
        if (_currentThinkingRow) _finalizeThinkingContainer(false);
        _ensureStreamBubble();
        _streamBuffer += delta;
        if (!_streamFlushScheduled) { _streamFlushScheduled = true; requestAnimationFrame(_flushStream); }
    }

    function _flushStream() {
        _streamFlushScheduled = false;
        if (!_streamBubbleId || _stopped) return;
        var el = document.getElementById(_streamBubbleId);
        if (el) {
            el.innerHTML = _md(_streamBuffer);
            el.classList.add('ab-streaming-cursor');
            _wrapTables(el);
            _scrollDown(true);
        }
    }

    function _freezeStreamBubble() {
        if (!_streamBubbleId) return;
        var el = document.getElementById(_streamBubbleId);
        if (el) {
            el.innerHTML = _md(_streamBuffer);
            el.classList.remove('ab-streaming-cursor');
            _wrapTables(el);
            _addCodeCopyButtons(el);
        }
        _streamBubbleId = null;
        _streamBuffer = '';
    }

    function _ensureThinkingContainer(initialLabel) {
        hideTyping();
        if (_currentThinkingRow) return _currentThinkingRow;
        _freezeStreamBubble();
        _thinkStartTime = Date.now();
        _currentThinkingRow = _nextId();
        _currentThinkingSteps = [];
        var $thinking = $(
            '<div class="ab-thinking-container" id="' + _currentThinkingRow + '">' +
                '<button class="ab-thinking-pill ab-thinking-live" type="button">' +
                    '<span class="ab-thinking-live-label ab-shimmer-text">' + initialLabel + '</span>' +
                    '<span class="ab-chevron">' + _icons.down + '</span>' +
                '</button>' +
                '<div class="ab-thinking-steps" style="display:none;"></div>' +
            '</div>'
        );
        _streamBubbleId ? $('#row-' + _streamBubbleId).before($thinking) : $('#ab-messages').append($thinking);
        _bindThinkingToggle($thinking);
        return _currentThinkingRow;
    }

    function _setLiveLabel(text) {
        if (!_currentThinkingRow) return;
        $('#' + _currentThinkingRow + ' .ab-thinking-live-label').text(text);
    }

    // ── Reasoning (chain-of-thought) block ──────────────────────────────
    function onReasoning(delta) {
        if (!delta || _stopped) return;
        _ensureThinkingContainer('Thinking…');
        if (!_reasoningBlockId) {
            _reasoningBlockId = _nextId();
            _reasoningStartTime = Date.now();
            _reasoningLive = true;
            $('#' + _currentThinkingRow + ' .ab-thinking-steps').append(
                '<div class="ab-thinking-step ab-reasoning-block live" id="' + _reasoningBlockId + '">' +
                    '<div class="ab-step-icon-col">' +
                        '<div class="ab-step-icon running">' + _CLOCK_ICON + '</div>' +
                        '<div class="ab-step-connector"></div>' +
                    '</div>' +
                    '<div class="ab-step-main">' +
                        '<div class="ab-step-headline">' +
                            '<span class="ab-step-name running ab-shimmer-text">Thinking…</span>' +
                            '<span class="ab-step-chevron">' + _icons.down + '</span>' +
                        '</div>' +
                        '<div class="ab-reasoning-wrap">' +
                            '<div class="ab-reasoning-text"></div>' +
                            '<span class="ab-reasoning-hint">Show more</span>' +
                        '</div>' +
                    '</div>' +
                 '</div>'
            );
        } else {
            _setLiveLabel('Thinking…');
        }
        _reasoningBuffer += delta;
        if (!_reasoningFlushScheduled) { _reasoningFlushScheduled = true; requestAnimationFrame(_flushReasoning); }
    }

    function _flushReasoning() {
        _reasoningFlushScheduled = false;
        if (!_reasoningBlockId) return;
        var el = document.querySelector('#' + _reasoningBlockId + ' .ab-reasoning-text');
        if (el) {
            el.innerHTML = _escapeHtml(_reasoningBuffer).replace(/\n/g, '<br>') + (_reasoningLive ? '<span class="ab-cursor ab-cursor--ghost"></span>' : '');
            var $block = $('#' + _reasoningBlockId);
            if (!$block.hasClass('ab-reasoning-expanded')) {
                el.scrollTop = el.scrollHeight;
                $block.toggleClass('truncated', el.scrollHeight > el.clientHeight + 2);
            }
        }
        _scrollDown(true);
    }

    function _finalizeReasoning() {
        if (!_reasoningBlockId || !_reasoningLive) return;
        _reasoningLive = false;
        _reasoningElapsedMs = _reasoningStartTime ? Date.now() - _reasoningStartTime : 0;
        var $block = $('#' + _reasoningBlockId);
        $block.removeClass('live');
        $block.find('.ab-step-icon').removeClass('running').addClass('done');
        $block.find('.ab-step-name').removeClass('running ab-shimmer-text').addClass('done').text('Thought Process');
        $block.find('.ab-reasoning-text .ab-cursor').remove();
        _reasoningBlockId = null;
        _reasoningBuffer = '';
    }

    function _bindThinkingToggle($container) {
        $container.find('.ab-thinking-pill').off('click').on('click', function () {
            $(this).siblings('.ab-thinking-steps').toggle();
            $(this).toggleClass('expanded');
        });
    }

    $(document).on('click', '.ab-thinking-step', function () {
        $(this).toggleClass('ab-step-expanded');
        if ($(this).hasClass('ab-step-expanded')) {
            var $rt = $(this).find('.ab-reasoning-text');
            if ($rt.length) {
                var el = $rt[0];
                $(this).toggleClass('truncated', el.scrollHeight > el.clientHeight + 2);
            }
        }
    });

    $(document).on('click', '.ab-reasoning-text', function (e) {
        e.stopPropagation();
        $(this).closest('.ab-reasoning-block').toggleClass('ab-reasoning-expanded');
    });

    var TOOL_ICON_MAP = {
        frappe_get_list: 'listIcon',
        frappe_get_doc: 'fileText',
        frappe_save_doc: 'edit',
        web_search: 'search',
        execute_code: 'terminal',
    };

    function _toolMeta(toolName, argsStr) {
        var args = {};
        try { args = typeof argsStr === 'string' ? JSON.parse(argsStr) : (argsStr || {}); } catch (_) {}

        var builders = {
            frappe_get_list: function () { var dt = args.doctype || 'records'; return ['Fetching ' + dt, 'Fetched ' + dt]; },
            frappe_get_doc: function () { var dt = args.doctype || 'document'; var n = args.name ? ' › ' + args.name : ''; return ['Reading ' + dt + n, 'Read ' + dt + n]; },
            frappe_save_doc: function () {
                var dt = (args.doc && args.doc.doctype) || 'record';
                return (args.doc && args.doc.name) ? ['Updating ' + dt, 'Updated ' + dt] : ['Creating ' + dt, 'Created ' + dt];
            },
            web_search: function () { var q = (args.query || '').slice(0, 48); return ['Searching the web for "' + q + '"', 'Searched the web for "' + q + '"']; },
            execute_code: function () { var lang = args.language || 'script'; return ['Running ' + lang, 'Ran ' + lang]; },
        };

        var running, done;
        if (builders[toolName]) {
            var pair = builders[toolName]();
            running = pair[0];
            done = pair[1];
        } else {
            var human = (toolName || 'tool').replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
            running = human + '…';
            done = human;
        }
        var icon = _icons[TOOL_ICON_MAP[toolName]] || _icons.skillIcon || _icons.check;
        return { icon: icon, args: args, running: running, done: done };
    }

    function _prettyArgs(args) {
        try {
            var json = JSON.stringify(args, null, 2);
            return _escapeHtml(json && json !== '{}' ? json : 'No arguments');
        } catch (_) { return ''; }
    }

    function _finalizedPillHtml(isError, label) {
        var icon = isError ? (_icons.alertTriangle || _icons.check) : _icons.check;
        return '<span class="ab-thinking-status-icon">' + icon + '</span><span>' + label + '</span><span class="ab-chevron">' + _icons.down + '</span>';
    }

    function onToolStart(data) {
        _ensureThinkingContainer('Working…');
        if (_reasoningLive) { _finalizeReasoning(); }
        _setLiveLabel('Working…');

        var stepId = _nextId();
        var meta = _toolMeta(data.tool, data.args);
        _currentThinkingSteps.push({ id: stepId, startTime: Date.now(), status: 'running', doneLabel: meta.done });

        var _stepArgsHtml = _prettyArgs(meta.args);
        var _noArgs = !_stepArgsHtml || _stepArgsHtml === _escapeHtml('No arguments');
        $('#' + _currentThinkingRow + ' .ab-thinking-steps').append(
            '<div class="ab-thinking-step" id="' + stepId + '">' +
                '<div class="ab-step-icon-col">' +
                    '<div class="ab-step-icon running">' + meta.icon + '</div>' +
                    '<div class="ab-step-connector"></div>' +
                '</div>' +
                '<div class="ab-step-main">' +
                    '<div class="ab-step-headline">' +
                        '<span class="ab-step-name running ab-shimmer-text">' + _escapeHtml(meta.running) + '</span>' +
                        '<span class="ab-step-chevron">' + _icons.down + '</span>' +
                    '</div>' +
                    '<div class="ab-step-detail">' +
                        (!_noArgs ? '<pre class="ab-step-detail-block">' + _stepArgsHtml + '</pre>' : '<span style="font-size:10.5px;color:var(--text-muted);opacity:0.6;">No input</span>') +
                        '<div class="ab-step-detail-footer">' +
                            '<span class="ab-step-detail-status running" id="' + stepId + '-status">Running…</span>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
            '</div>'
        );
        _scrollDown();
    }

    function onToolDone(data) {
        var step = _currentThinkingSteps.find(function (s) { return s.status === 'running'; });
        if (!step) return;
        var isError = !!(data && (data.error || data.success === false));

        var $step = $('#' + step.id);
        var $icon = $step.find('.ab-step-icon');
        $icon.removeClass('running').addClass(isError ? 'errored' : 'done');
        if (isError) $icon.html(_icons.alertTriangle || _icons.check);
        $step.find('.ab-step-name').removeClass('running ab-shimmer-text').addClass(isError ? 'errored' : 'done').text(step.doneLabel || '');
        $step.toggleClass('ab-step-is-error', isError);
        var $statusBadge = $('#' + step.id + '-status');
        $statusBadge.removeClass('running')
            .addClass(isError ? 'error' : 'success')
            .text(isError ? 'Failed' : 'Done');

        var resultText = data && (data.error || data.result || data.output || data.response);
        if (resultText !== undefined && resultText !== null && resultText !== '') {
            var pretty = typeof resultText === 'string' ? resultText : JSON.stringify(resultText, null, 2);
            var $footer = $step.find('.ab-step-detail-footer');
            $footer.before(
                '<div class="ab-step-detail-section">' +
                    '<div class="ab-step-detail-label">' + (isError ? 'Error' : 'Output') + '</div>' +
                    '<pre class="ab-step-detail-block' + (isError ? ' is-error' : '') + '">' + _escapeHtml(String(pretty).slice(0, 4000)) + '</pre>' +
                 '</div>'
            );
        }

        step.status = isError ? 'error' : 'done';
        _scrollDown();
    }

    function _addResendButton(row) {
        if (!row) return;
        var $actions = $(row).find('.ab-msg-actions');
        if (!$actions.length || $actions.find('.ab-resend-btn').length) return;
        $actions.append('<button class="ab-msg-action-btn ab-resend-btn" title="Retry">' + (_icons.retry || '') + '</button>');
    }

    function _finalizeThinkingContainer(isError) {
        if (!_currentThinkingRow) return;
        if (_reasoningLive) _finalizeReasoning();

        var $container = $('#' + _currentThinkingRow);
        var nTools = _currentThinkingSteps.length;

        var label;
        if (isError) {
            label = 'Stopped after an error';
        } else {
            var parts = [];
            if (_reasoningElapsedMs != null) parts.push('Thought Process');
            if (nTools > 0) parts.push(nTools + ' action' + (nTools !== 1 ? 's' : ''));
            label = parts.join(' · ') || '';
        }

        $container.find('.ab-thinking-live').replaceWith(
            '<button class="ab-thinking-pill ' + (isError ? 'errored' : 'done') + '" type="button">' +
                _finalizedPillHtml(isError, label) +
            '</button>'
        );
        $container.find('.ab-thinking-steps').hide();
        _bindThinkingToggle($container);
        _resetThinkingState();
    }

    function onDone(response, isError) {
        hideTyping();
        _finalizeThinkingContainer(isError);

        if (_streamBubbleId) {
            var el = document.getElementById(_streamBubbleId);
            var row = document.getElementById('row-' + _streamBubbleId);
            if (el) {
                el.classList.remove('ab-streaming-cursor');
                if (isError) {
                    if (row) row.classList.add('is-error');
                    el.classList.add('ab-bubble-error');
                    el.innerHTML = _escapeHtml(response || 'Sorry, something went wrong.');
                    _addResendButton(row);
                } else {
                    el.innerHTML = _renderContentWithArtifacts(response || _streamBuffer || '');
                    _wrapTables(el);
                    setTimeout(function () { _mountAllArtifacts(); _addCodeCopyButtons(el); _scrollDown(); }, 0);
                }
            }
        } else if (response) {
            _appendAgentMessage(response, isError);
            setTimeout(function () { _mountAllArtifacts(); _scrollDown(); }, 0);
        }
        _resetStreamState();
    }

    function onStop() {
        _stopped = true;
        if (_reasoningLive) _finalizeReasoning();
        if (_streamBubbleId) {
            var el = document.getElementById(_streamBubbleId);
            if (el) { el.innerHTML = _md(_streamBuffer); el.classList.remove('ab-streaming-cursor'); _addCodeCopyButtons(el); }
            _streamBubbleId = null;
        }
        hideTyping();
    }

    function _renderContentWithArtifacts(text) {
        if (!text) return '';
        var htmlBlockRegex = /```html\s*\n([\s\S]*?)```/g;
        var lastIndex = 0, match, parts = [];
        while ((match = htmlBlockRegex.exec(text)) !== null) {
            if (match.index > lastIndex) parts.push({ type: 'md', content: text.slice(lastIndex, match.index) });
            parts.push({ type: 'html', id: _nextId(), content: match[1].trim() });
            lastIndex = match.index + match[0].length;
        }
        if (lastIndex < text.length) parts.push({ type: 'md', content: text.slice(lastIndex) });
        if (!parts.length || (parts.length === 1 && parts[0].type === 'md')) return _md(text);
        return parts.map(function (p) { return p.type === 'md' ? _md(p.content) : _createArtifactHTML(p.id, p.content); }).join('');
    }

    function _createArtifactHTML(id, htmlContent) {
        _artifactStore.set(id, htmlContent);
        return '<div class="ab-artifact" data-artifact-id="' + id + '">' +
                '<div class="ab-artifact-bar">' +
                    '<div class="ab-artifact-dot"></div>' +
                    '<span class="ab-artifact-label">Generated UI</span>' +
                    '<div class="ab-artifact-actions">' +
                        '<button class="ab-artifact-bar-btn ab-artifact-reload" data-artifact="' + id + '" title="Reload">' + _icons.reload + '</button>' +
                        '<button class="ab-artifact-bar-btn ab-artifact-expand" data-artifact="' + id + '" title="Fullscreen">' + _icons.expand + '</button>' +
                    '</div>' +
                '</div>' +
                '<div class="ab-artifact-frame"></div>' +
            '</div>';
    }

    function _mountAllArtifacts() {
        document.querySelectorAll('.ab-artifact').forEach(function (artifactDiv) {
            var id = artifactDiv.dataset.artifactId;
            var frame = artifactDiv.querySelector('.ab-artifact-frame');
            if (!id || !frame || frame.querySelector('iframe')) return;
            var html = _artifactStore.get(id);
            if (html) _mountSingleArtifact(frame, html);
        });
    }

    function _mountSingleArtifact(frame, htmlContent) {
        var old = frame.querySelector('iframe');
        var iframe = document.createElement('iframe');
        iframe.setAttribute('sandbox', 'allow-scripts allow-popups allow-popups-to-escape-sandbox allow-forms allow-modals');
        iframe.className = 'ab-artifact-iframe';
        iframe.srcdoc = htmlContent;
        if (old) frame.replaceChild(iframe, old); else frame.appendChild(iframe);
        iframe.addEventListener('load', function () { _adjustIframeHeight(iframe); });
    }

    function _adjustIframeHeight(iframe) {
        try {
            var doc = iframe.contentDocument || iframe.contentWindow.document;
            var h = Math.max(doc.body ? doc.body.scrollHeight : 0, doc.documentElement ? doc.documentElement.scrollHeight : 0);
            var cap = iframe.closest('.ab-artifact-full') ? Infinity : 640;
            if (h > 50) iframe.style.height = Math.min(h + 20, cap) + 'px';
        } catch (_) {}
    }

    function reloadArtifact(artifactId) {
        var artifactDiv = document.querySelector('.ab-artifact[data-artifact-id="' + artifactId + '"]');
        if (artifactDiv) {
            var frame = artifactDiv.querySelector('.ab-artifact-frame');
            if (frame && _artifactStore.get(artifactId)) _mountSingleArtifact(frame, _artifactStore.get(artifactId));
        }
    }

    function expandArtifact(artifactId) {
        var el = document.querySelector('.ab-artifact[data-artifact-id="' + artifactId + '"]');
        if (!el) return;
        if (el.classList.contains('ab-artifact-full')) _collapseArtifactEl(el);
        else _expandArtifactEl(el, artifactId);
    }

    function _expandArtifactEl(el, artifactId) {
        if (document.querySelector('.ab-artifact-full')) return;
        var anchor = document.createComment('ab-artifact-anchor-' + artifactId);
        el.parentNode.insertBefore(anchor, el);
        _artifactAnchors.set(artifactId, anchor);

        var backdrop = document.createElement('div');
        backdrop.className = 'ab-artifact-backdrop';
        backdrop.dataset.artifact = artifactId;
        document.body.appendChild(backdrop);
        document.body.appendChild(el);
        document.body.classList.add('ab-artifact-fullscreen-active');

        el.classList.add('ab-artifact-full');
        $(el).find('.ab-artifact-expand').html(_icons.compress || _icons.expand).attr('title', 'Exit fullscreen');

        var iframe = el.querySelector('.ab-artifact-iframe');
        if (iframe) requestAnimationFrame(function () { _adjustIframeHeight(iframe); });
    }

    function _collapseArtifactEl(el) {
        var artifactId = el.dataset.artifactId;
        el.classList.remove('ab-artifact-full');
        $(el).find('.ab-artifact-expand').html(_icons.expand).attr('title', 'Fullscreen');

        var anchor = _artifactAnchors.get(artifactId);
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(el, anchor);
            anchor.remove();
        } else {
            $('#ab-messages').append(el);
        }
        _artifactAnchors.delete(artifactId);

        document.querySelectorAll('.ab-artifact-backdrop[data-artifact="' + artifactId + '"]').forEach(function (b) { b.remove(); });
        if (!document.querySelector('.ab-artifact-full')) document.body.classList.remove('ab-artifact-fullscreen-active');

        var iframe = el.querySelector('.ab-artifact-iframe');
        if (iframe) setTimeout(function () { _adjustIframeHeight(iframe); }, 0);
    }

    function collapseAllFullscreenArtifacts() {
        document.querySelectorAll('.ab-artifact.ab-artifact-full').forEach(_collapseArtifactEl);
    }

    $(document).on('click', '.ab-artifact-backdrop', function () {
        var el = document.querySelector('.ab-artifact[data-artifact-id="' + this.dataset.artifact + '"]');
        if (el) _collapseArtifactEl(el);
    });
    $(document).on('keydown', function (e) {
        if (e.key === 'Escape') collapseAllFullscreenArtifacts();
    });

    function _addAllCodeCopyButtons() {
        document.querySelectorAll('#ab-messages .ab-bubble').forEach(function (b) { _addCodeCopyButtons(b); });
    }

    function _addCodeCopyButtons(container) {
        $(container).find('pre').each(function () {
            if ($(this).find('.ab-pre-copy').length) return;
            var $pre = $(this);
            var $btn = $('<button class="ab-pre-copy">' + _icons.copy + ' Copy</button>');
            $btn.on('click', function () {
                navigator.clipboard.writeText($pre.find('code').text() || $pre.text()).then(function () {
                    $btn.html(_icons.check + ' Copied!');
                    setTimeout(function () { $btn.html(_icons.copy + ' Copy'); }, 1500);
                });
            });
            $pre.append($btn);
        });
    }

    // ──────────────────────────────────────────────────────────────────
    // Historical thinking container renderer
    //
    // Accepts an ordered array of segments accumulated by loadHistory:
    //   { type: 'reasoning', data: { text, elapsed_ms } }
    //   { type: 'steps',    data: [ { tool, args, status, ... }, ... ] }
    //
    // Renders as ONE finalized collapsed container — mirroring the live
    // _currentThinkingRow state machine.
    // ──────────────────────────────────────────────────────────────────

    /** Build a single finalized reasoning step row */
    function _buildReasoningStepHtml(reasoning) {
        return '<div class="ab-thinking-step ab-reasoning-block">' +
                    '<div class="ab-step-icon-col">' +
                        '<div class="ab-step-icon done">' + _CLOCK_ICON + '</div>' +
                        '<div class="ab-step-connector"></div>' +
                    '</div>' +
                    '<div class="ab-step-main">' +
                        '<div class="ab-step-headline">' +
                            '<span class="ab-step-name done">Thought Process</span>' +
                            '<span class="ab-step-chevron">' + _icons.down + '</span>' +
                        '</div>' +
                        '<div class="ab-step-detail">' +
                            '<div class="ab-reasoning-wrap">' +
                                '<div class="ab-reasoning-text">' + _escapeHtml(reasoning.text).replace(/\n/g, '<br>') + '</div>' +
                                '<span class="ab-reasoning-hint">Show more</span>' +
                            '</div>' +
                        '</div>' +
                    '</div>' +
                '</div>';
    }

    /** Build a single finalized tool-call step row */
    function _buildToolStepHtml(s) {
        var stepError = s.status === 'error';
        var meta = _toolMeta(s.tool, s.args);
        var icon = stepError ? (_icons.alertTriangle || _icons.check) : meta.icon;
        var resultText = s.error || s.result || s.output || s.response;
        var _rPretty = resultText ? (typeof resultText === 'string' ? resultText : JSON.stringify(resultText, null, 2)) : '';
        var _hArgsHtml = _prettyArgs(s.args);
        var _hNoArgs = !_hArgsHtml || _hArgsHtml === _escapeHtml('No arguments') || _hArgsHtml === _escapeHtml('{}');
        var _hStatus = stepError ? 'error' : 'success';
        var _hStatusLabel = stepError ? 'Failed' : 'Done';
        return '<div class="ab-thinking-step' + (stepError ? ' ab-step-is-error' : '') + '">' +
                    '<div class="ab-step-icon-col">' +
                        '<div class="ab-step-icon ' + (stepError ? 'errored' : 'done') + '">' + icon + '</div>' +
                        '<div class="ab-step-connector"></div>' +
                    '</div>' +
                    '<div class="ab-step-main">' +
                        '<div class="ab-step-headline">' +
                            '<span class="ab-step-name ' + (stepError ? 'errored' : 'done') + '">' + _escapeHtml(meta.done) + '</span>' +
                            '<span class="ab-step-chevron">' + _icons.down + '</span>' +
                        '</div>' +
                        '<div class="ab-step-detail">' +
                            (!_hNoArgs ? '<pre class="ab-step-detail-block">' + _hArgsHtml + '</pre>' : '') +
                            (_rPretty ? '<pre class="ab-step-detail-block' + (stepError ? ' is-error' : '') + '">' + _escapeHtml(String(_rPretty).slice(0, 4000)) + '</pre>' : '') +
                            '<div class="ab-step-detail-footer">' +
                                '<span class="ab-step-detail-status ' + _hStatus + '">' + _hStatusLabel + '</span>' +
                            '</div>' +
                        '</div>' +
                    '</div>' +
                '</div>';
    }

    /** Render one finalized collapsed thinking container from segments */
    function _renderHistoricalThinkingContainer(segments) {
        if (!segments || !segments.length) return;

        var rowId = _nextId();
        var hasError = false;
        var toolCount = 0;
        var hasReasoning = false;
        var allStepsHtml = '';

        segments.forEach(function (seg) {
            if (seg.type === 'reasoning') {
                hasReasoning = true;
                allStepsHtml += _buildReasoningStepHtml(seg.data);
            } else if (seg.type === 'steps') {
                seg.data.forEach(function (s) {
                    toolCount++;
                    if (s.status === 'error') hasError = true;
                    allStepsHtml += _buildToolStepHtml(s);
                });
            }
        });

        // Pill label — no elapsed times
        var label;
        if (hasError) {
            label = 'Stopped after an error';
        } else {
            var parts = [];
            if (hasReasoning) parts.push('Thought Process');
            if (toolCount > 0) parts.push(toolCount + ' action' + (toolCount !== 1 ? 's' : ''));
            label = parts.join(' · ') || '';
        }

        var $thinking = $(
            '<div class="ab-thinking-container" id="' + rowId + '">' +
                '<div class="ab-thinking-pill ' + (hasError ? 'errored' : 'done') + '">' +
                    _finalizedPillHtml(hasError, label) +
                '</div>' +
                '<div class="ab-thinking-steps" style="display:none;">' + allStepsHtml + '</div>' +
            '</div>'
        );
        $('#ab-messages').append($thinking);
        _bindThinkingToggle($thinking);

        // Measure each reasoning block for the "Show more" overflow hint
        requestAnimationFrame(function () {
            $thinking.find('.ab-reasoning-block').each(function () {
                var $rt = $(this).find('.ab-reasoning-text');
                if ($rt.length) {
                    var el = $rt[0];
                    $(this).toggleClass('truncated', el.scrollHeight > el.clientHeight + 2);
                }
            });
        });
    }

    function _scrollDown(soft) {
        var el = document.getElementById('ab-messages');
        if (!el) return;
        if (soft) { if (el.scrollHeight - el.scrollTop - el.clientHeight < 120) el.scrollTop = el.scrollHeight; }
        else el.scrollTop = el.scrollHeight;
    }

    function _escapeHtml(str) {
        return (str || '').replace(/[&<>"']/g, function (c) {
            return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
        });
    }

    function _md(text) {
        if (!text) return '';
        if (window.marked) return window.marked.parse(text, { breaks: true, gfm: true });
        return _escapeHtml(text).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\n/g, '<br>');
    }

    return {
        init: init,
        clear: clear,
        loadHistory: loadHistory,
        appendUserMsg: _appendUserMessage,
        onToken: onToken,
        onReasoning: onReasoning,
        onToolStart: onToolStart,
        onToolDone: onToolDone,
        onDone: onDone,
        onStop: onStop,
        showTyping: showTyping,
        hideTyping: hideTyping,
        reloadArtifact: reloadArtifact,
        expandArtifact: expandArtifact,
        collapseAllFullscreenArtifacts: collapseAllFullscreenArtifacts
    };
}());