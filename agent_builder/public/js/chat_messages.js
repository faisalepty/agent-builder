/**
 * chat_messages.js v4.7.0 — Claude-style generation footer
 * v4.7.0: Removed inline cursor entirely. The AP logo drawing 
 *   animation now sits in a dedicated footer below the generating
 *   text block until the response completes.
 * v4.6.0: Replaced 3-dot typing indicator with custom logo drawing.
 */
window.ChatMessages = (function () {

    var _icons = {};
    var _CLOCK_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15.5 14"/></svg>';
    var _BRAIN_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 3.5a2.5 2.5 0 00-2.5 2.5v.18A2.75 2.75 0 005.25 8.5v1A2.75 2.75 0 004 12a2.75 2.75 0 001.25 2.3v1.2a2.75 2.75 0 002 2.65v.35a2.5 2.5 0 002.5 2.5H10a1.5 1.5 0 001.5-1.5V6a2.5 2.5 0 00-2-2.45 2.49 2.49 0 00-0-.05z"/><path d="M14.5 3.5a2.5 2.5 0 012.5 2.5v.18A2.75 2.75 0 0118.75 8.5v1A2.75 2.75 0 0120 12a2.75 2.75 0 01-1.25 2.3v1.2a2.75 2.75 0 01-2 2.65v.35a2.5 2.5 0 01-2.5 2.5H14a1.5 1.5 0 01-1.5-1.5V6a2.5 2.5 0 012-2.45 2.49 2.49 0 010-.05z"/></svg>';
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
        _chartStore.forEach(function (_, id) {
            var inst = _chartInstances.get(id);
            if (inst && inst.destroy) inst.destroy();
        });
        _chartStore.clear();
        _chartInstances.clear();
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
                var lastAgentBubble = null;

                function flushPending() {
                    if (pendingSegments.length) {
                        _renderHistoricalThinkingContainer(pendingSegments);
                        pendingSegments = [];
                    }
                }

                function finalizeAgentTurn() {
                    if (lastAgentBubble) {
                        _addMsgActions(lastAgentBubble.rowId, lastAgentBubble.bubbleId, lastAgentBubble.isError);
                        lastAgentBubble = null;
                    }
                }

                r.message.messages.forEach(function (msg) {
                    if (msg.role === 'user') {
                        finalizeAgentTurn();
                        flushPending();
                        _appendUserMessage(msg.content, _safeParseJSON(msg.attachments));

                    } else if (msg.role === 'assistant') {
                        var steps = _safeParseJSON(msg.tool_calls);
                        var hasContent = !!(msg.content && msg.content.trim());

                        if (hasContent) {
                            if (msg.reasoning && msg.reasoning.text) {
                                pendingSegments.push({ type: 'reasoning', data: msg.reasoning });
                            }
                            flushPending();
                            var isErr = !!msg.is_error;
                            var msgId = _appendAgentMessage(msg.content, isErr, false);
                            lastAgentBubble = { rowId: msgId, bubbleId: msgId + '-bubble', isError: isErr };

                            if (steps && steps.length) {
                                pendingSegments.push({ type: 'steps', data: steps });
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
                finalizeAgentTurn();

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

    function _appendAgentMessage(content, isError, withActions) {
        if (!content || !content.trim()) return null;
        var msgId = _nextId();
        $('#ab-messages').append(
            '<div class="ab-row agent' + (isError ? ' is-error' : '') + '" id="' + msgId + '">' +
                '<div class="ab-avatar">' + (isError ? (_icons.alertTriangle || _icons.logo) : _icons.logo) + '</div>' +
                '<div class="ab-bubble-wrap">' +
                    '<div class="ab-bubble' + (isError ? ' ab-bubble-error' : '') + '" id="' + msgId + '-bubble"></div>' +
                    (withActions ? _msgActionsHtml(msgId + '-bubble', isError) : '') +
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
        return msgId;
    }

    function _msgActionsHtml(bubbleElId, isError) {
        return '<div class="ab-msg-actions">' +
            '<button class="ab-msg-action-btn ab-copy-btn" data-bubble="' + bubbleElId + '" title="Copy">' + _icons.copy + '</button>' +
            (isError ? '<button class="ab-msg-action-btn ab-resend-btn" title="Retry">' + (_icons.retry || '') + '</button>' : '') +
        '</div>';
    }

    function _addMsgActions(rowElId, bubbleElId, isError) {
        if (!rowElId || !bubbleElId) return;
        var $wrap = $('#' + rowElId).find('.ab-bubble-wrap');
        if (!$wrap.length || $wrap.find('.ab-msg-actions').length) return;
        $wrap.append(_msgActionsHtml(bubbleElId, isError));
    }

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
                '<div class="ab-typing-indicator ab-typing-logo">' + (_icons.logoLoader || _icons.logo) + '</div>' +
            '</div>'
        );
        _scrollDown();
    }

    function hideTyping() { if (_typingRowId) { $('#' + _typingRowId).remove(); _typingRowId = null; } }

    function _ensureStreamBubble() {
        if (_streamBubbleId && document.getElementById(_streamBubbleId)) return;
        _streamBubbleId = _nextId();
        $('#ab-messages').append(
            '<div class="ab-row agent" id="row-' + _streamBubbleId + '">' +
                '<div class="ab-avatar">' + _icons.logo + '</div>' +
                '<div class="ab-bubble-wrap">' +
                    '<div class="ab-bubble" id="' + _streamBubbleId + '"></div>' +
                '</div>' +
            '</div>'
        );
        _scrollDown();
    }

    function onToken(delta) {
        if (!delta || _stopped) return;
        hideTyping();

        _streamBuffer += delta;

        if (_currentThinkingRow && _streamBuffer.trim()) {
            _finalizeThinkingContainer(false);
        }

        if (!_streamBubbleId && !_streamBuffer.trim()) {
            if (!_streamFlushScheduled) { _streamFlushScheduled = true; requestAnimationFrame(_flushStream); }
            return;
        }

        _ensureStreamBubble();
        if (!_streamFlushScheduled) { _streamFlushScheduled = true; requestAnimationFrame(_flushStream); }
    }

    // ── Streaming renderer: hides chart/html code behind placeholders ──
    function _mdStreaming(text) {
        if (!text) return '';

        var result = '';
        var pos = 0;
        var len = text.length;

        while (pos < len) {
            var chartIdx = text.indexOf('```chart', pos);
            var htmlIdx  = text.indexOf('```html', pos);

            var fenceIdx = -1;
            var lang = null;

            if (chartIdx !== -1 && (htmlIdx === -1 || chartIdx <= htmlIdx)) {
                fenceIdx = chartIdx;
                lang = 'chart';
            } else if (htmlIdx !== -1) {
                fenceIdx = htmlIdx;
                lang = 'html';
            }

            if (fenceIdx === -1) {
                result += _md(text.slice(pos));
                break;
            }

            if (fenceIdx > pos) {
                result += _md(text.slice(pos, fenceIdx));
            }

            var afterLang = text.slice(fenceIdx + 3 + lang.length);
            var nlMatch = afterLang.match(/^\s*\n/);

            if (!nlMatch) {
                result += _md(text.slice(fenceIdx, fenceIdx + 3 + lang.length));
                pos = fenceIdx + 3 + lang.length;
                continue;
            }

            var contentStart = fenceIdx + 3 + lang.length + nlMatch[0].length;
            var closeIdx = text.indexOf('```', contentStart);

            if (closeIdx !== -1) {
                pos = closeIdx + 3;
            } else {
                pos = len;
            }

            result += lang === 'chart' ? _createChartPlaceholder() : _createHtmlPlaceholder();
        }

        return result;
    }

    function _createChartPlaceholder() {
        return '<div class="ab-artifact-placeholder">' +
                   '<div class="ab-artifact-placeholder-icon">' + (_icons.barChart || '') + '</div>' +
                   '<span class="ab-artifact-placeholder-label ab-shimmer-text">Generating chart…</span>' +
               '</div>';
    }

    function _createHtmlPlaceholder() {
        return '<div class="ab-artifact-placeholder">' +
                   '<div class="ab-artifact-placeholder-icon">' + (_icons.sparkle || '') + '</div>' +
                   '<span class="ab-artifact-placeholder-label ab-shimmer-text">Generating UI…</span>' +
               '</div>';
    }

    function _flushStream() {
        _streamFlushScheduled = false;
        if (!_streamBubbleId || _stopped) return;
        var el = document.getElementById(_streamBubbleId);
        if (el) {
            el.innerHTML = _mdStreaming(_streamBuffer);
            
            // Append/Ensure the generation footer (AP logo animation) is below the text
            var $wrap = $('#row-' + _streamBubbleId).find('.ab-bubble-wrap');
            if (!$wrap.find('.ab-streaming-footer').length) {
                $wrap.append('<div class="ab-streaming-footer">' + (_icons.logoLoader || _icons.logo) + '</div>');
            }
            
            _wrapTables(el);
            _scrollDown(true);
        }
    }

    function _freezeStreamBubble() {
        if (_streamBubbleId) {
            var el = document.getElementById(_streamBubbleId);
            if (el) {
                var trimmed = (_streamBuffer || '').trim();
                if (trimmed) {
                    $('#row-' + _streamBubbleId).find('.ab-streaming-footer').remove();
                    el.innerHTML = _md(trimmed);
                    _wrapTables(el);
                    _addCodeCopyButtons(el);
                } else {
                    var row = document.getElementById('row-' + _streamBubbleId);
                    if (row) row.remove();
                }
            }
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
        if (_streamBubbleId) {
            var $row = $('#row-' + _streamBubbleId);
            var $bubbleWrap = $row.find('.ab-bubble-wrap');
            if ($bubbleWrap.length) {
                $bubbleWrap.prepend($thinking);
            } else {
                $row.before($thinking);
            }
        } else {
            $('#ab-messages').append($thinking);
        }
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
                        '<div class="ab-step-icon ab-step-icon-brain running">' + _BRAIN_ICON + '</div>' +
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
            el.innerHTML = _escapeHtml(_reasoningBuffer).replace(/\n/g, '<br>');
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

    function _finalizedPillHtml(isError, label, hasReasoning) {
        var icon = isError ? (_icons.alertTriangle || _icons.check) : (hasReasoning ? _BRAIN_ICON : _icons.check);
        return '<span class="ab-thinking-status-icon' + (hasReasoning && !isError ? ' ab-step-icon-brain' : '') + '">' + icon + '</span><span>' + label + '</span><span class="ab-chevron">' + _icons.down + '</span>';
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

    function _finalizeThinkingContainer(isError) {
        if (!_currentThinkingRow) return;
        if (_reasoningLive) _finalizeReasoning();

        var $container = $('#' + _currentThinkingRow);
        var nTools = _currentThinkingSteps.length;

        var hasReasoning = _reasoningElapsedMs != null;
        var label;
        if (isError) {
            label = 'Stopped after an error';
        } else {
            var parts = [];
            if (hasReasoning) parts.push('Thought Process');
            if (nTools > 0) parts.push(nTools + ' action' + (nTools !== 1 ? 's' : ''));
            label = parts.join(' · ') || '';
        }

        $container.find('.ab-thinking-live').replaceWith(
            '<button class="ab-thinking-pill ' + (isError ? 'errored' : 'done') + '" type="button">' +
                _finalizedPillHtml(isError, label, hasReasoning) +
            '</button>'
        );
        $container.find('.ab-thinking-steps').hide();
        _bindThinkingToggle($container);
        _resetThinkingState();
    }

    // ── Safety merge: consolidate adjacent finalized thinking containers ──
    function _mergeAdjacentThinkingContainers() {
        var $all = $('#ab-messages .ab-thinking-container.done, #ab-messages .ab-thinking-container.errored');
        if ($all.length <= 1) return;

        var groups = [];
        var currentGroup = [];

        $all.each(function () {
            var $this = $(this);
            if (currentGroup.length === 0) {
                currentGroup.push($this);
                return;
            }
            var $prev = currentGroup[currentGroup.length - 1];
            var $between = $prev.nextUntil($this);
            var onlyEmptyAgentRows = true;
            $between.each(function () {
                var $el = $(this);
                if ($el.hasClass('ab-row') && $el.hasClass('agent')) {
                    var text = $el.find('.ab-bubble').text().trim();
                    if (text) { onlyEmptyAgentRows = false; return false; }
                } else { onlyEmptyAgentRows = false; return false; }
            });
            if (onlyEmptyAgentRows) {
                currentGroup.push($this);
            } else {
                if (currentGroup.length > 1) groups.push(currentGroup);
                currentGroup = [$this];
            }
        });
        if (currentGroup.length > 1) groups.push(currentGroup);

        groups.forEach(function (group) {
            var $first = group[0];
            var totalTools = 0, hasReasoning = false, hasError = false;

            $first.find('.ab-thinking-step').each(function () {
                if ($(this).hasClass('ab-reasoning-block')) hasReasoning = true; else totalTools++;
                if ($(this).hasClass('ab-step-is-error')) hasError = true;
            });

            for (var i = 1; i < group.length; i++) {
                var $container = group[i];
                $container.find('.ab-thinking-steps > *').appendTo($first.find('.ab-thinking-steps'));
                $container.find('.ab-thinking-step').each(function () {
                    if ($(this).hasClass('ab-reasoning-block')) hasReasoning = true; else totalTools++;
                    if ($(this).hasClass('ab-step-is-error')) hasError = true;
                });
                var $prevInGroup = group[i - 1];
                $prevInGroup.nextUntil($container).each(function () {
                    var $el = $(this);
                    if ($el.hasClass('ab-row') && $el.hasClass('agent')) {
                        if (!$el.find('.ab-bubble').text().trim()) $el.remove();
                    }
                });
                $container.remove();
            }

            var label;
            if (hasError) { label = 'Stopped after an error'; }
            else {
                var parts = [];
                if (hasReasoning) parts.push('Thought Process');
                if (totalTools > 0) parts.push(totalTools + ' action' + (totalTools !== 1 ? 's' : ''));
                label = parts.join(' · ') || '';
            }
            $first.find('.ab-thinking-pill').html(_finalizedPillHtml(hasError, label, hasReasoning));
        });
    }

    function onDone(response, isError) {
        hideTyping();
        if (_currentThinkingRow) _finalizeThinkingContainer(isError);
        _mergeAdjacentThinkingContainers();

        if (_streamBubbleId) {
            var el = document.getElementById(_streamBubbleId);
            var row = document.getElementById('row-' + _streamBubbleId);
            if (el) {
                var finalContent = (response || _streamBuffer || '').trim();
                if (finalContent) {
                    $('#row-' + _streamBubbleId).find('.ab-streaming-footer').remove();
                    if (isError) {
                        if (row) row.classList.add('is-error');
                        el.classList.add('ab-bubble-error');
                        el.innerHTML = _escapeHtml(response || 'Sorry, something went wrong.');
                    } else {
                        el.innerHTML = _renderContentWithArtifacts(finalContent);
                        _wrapTables(el);
                        setTimeout(function () { _mountAllArtifacts(); _addCodeCopyButtons(el); _scrollDown(); }, 0);
                    }
                    if (row) _addMsgActions(row.id, el.id, isError);
                } else {
                    if (row) row.remove();
                }
            }
        } else if (response && response.trim()) {
            _appendAgentMessage(response, isError, true);
            setTimeout(function () { _mountAllArtifacts(); _scrollDown(); }, 0);
        }
        _resetStreamState();
    }

    function onStop() {
        _stopped = true;
        if (_reasoningLive) _finalizeReasoning();
        if (_currentThinkingRow) _finalizeThinkingContainer(false);
        _mergeAdjacentThinkingContainers();

        if (_streamBubbleId) {
            var el = document.getElementById(_streamBubbleId);
            var row = document.getElementById('row-' + _streamBubbleId);
            if (el) {
                var trimmed = (_streamBuffer || '').trim();
                if (trimmed) {
                    $('#row-' + _streamBubbleId).find('.ab-streaming-footer').remove();
                    el.innerHTML = _md(trimmed);
                    _wrapTables(el);
                    _addCodeCopyButtons(el);
                    if (row) _addMsgActions(row.id, el.id, false);
                } else {
                    if (row) row.remove();
                }
            }
            _streamBubbleId = null;
        }
        hideTyping();
    }

    // ── Fenced block parsing (used for final render, not streaming) ────
    var _blockFenceRegex = /```(html|chart)\s*\n([\s\S]*?)```/g;

    function _renderContentWithArtifacts(text) {
        if (!text) return '';
        var lastIndex = 0, match, parts = [];
        _blockFenceRegex.lastIndex = 0;
        while ((match = _blockFenceRegex.exec(text)) !== null) {
            if (match.index > lastIndex) parts.push({ type: 'md', content: text.slice(lastIndex, match.index) });
            if (match[1] === 'chart') {
                parts.push({ type: 'chart', id: _nextId(), content: match[2].trim() });
            } else {
                parts.push({ type: 'html', id: _nextId(), content: match[2].trim() });
            }
            lastIndex = match.index + match[0].length;
        }
        if (lastIndex < text.length) parts.push({ type: 'md', content: text.slice(lastIndex) });
        if (!parts.length || (parts.length === 1 && parts[0].type === 'md')) return _md(text);
        return parts.map(function (p) {
            if (p.type === 'md') return _md(p.content);
            if (p.type === 'chart') return _createChartHTML(p.id, p.content);
            return _createArtifactHTML(p.id, p.content);
        }).join('');
    }

    // ── Charts (frappe.Chart) — thin border, subtle shadow ────────────
    var _chartStore = new Map();
    var _chartInstances = new Map();

    function _createChartHTML(id, rawJson) {
        _chartStore.set(id, rawJson);
        return '<div class="ab-chart" data-chart-id="' + id + '">' +
                '<div class="ab-chart-canvas"></div>' +
            '</div>';
    }

    function _mountAllCharts() {
        document.querySelectorAll('.ab-chart').forEach(function (chartDiv) {
            var id = chartDiv.dataset.chartId;
            var canvas = chartDiv.querySelector('.ab-chart-canvas');
            if (!id || !canvas || canvas.dataset.mounted) return;
            _mountSingleChart(canvas, id);
        });
    }

    function _mountSingleChart(canvas, id) {
        var raw = _chartStore.get(id);
        if (!raw) return;
        canvas.dataset.mounted = '1';
        canvas.innerHTML = '';

        var spec;
        try { spec = JSON.parse(raw); } catch (e) {
            canvas.innerHTML = '<div class="ab-chart-error">Couldn\'t parse chart data.</div>';
            return;
        }
        if (typeof frappe === 'undefined' || !frappe.Chart) {
            canvas.innerHTML = '<div class="ab-chart-error">Chart library not available.</div>';
            return;
        }
        try {
            var old = _chartInstances.get(id);
            if (old && old.destroy) old.destroy();

            var axisOptions = Object.assign(
                { shortenYAxisNumbers: 1 },
                spec.axisOptions || {}
            );

            var instance = new frappe.Chart(canvas, Object.assign({
                height: 300,
                colors: ['#7cd6fd', '#743ee2', '#5e64ff', '#00c30e', '#ff7300']
            }, spec, { axisOptions: axisOptions }));
            _chartInstances.set(id, instance);
        } catch (e) {
            canvas.innerHTML = '<div class="ab-chart-error">Couldn\'t render chart: ' + (e && e.message ? e.message : 'unknown error') + '</div>';
        }
    }

    // ── HTML Artifacts ──────────────────────────────────────────────
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
        _mountAllCharts();
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

    // ── Historical thinking container renderer ───────────────────────
    function _buildReasoningStepHtml(reasoning) {
        return '<div class="ab-thinking-step ab-reasoning-block">' +
                    '<div class="ab-step-icon-col">' +
                        '<div class="ab-step-icon ab-step-icon-brain done">' + _BRAIN_ICON + '</div>' +
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

    function _renderHistoricalThinkingContainer(segments) {
        var id = _nextId();
        var stepsHtml = segments.map(function (seg) {
            if (seg.type === 'reasoning') {
                return _buildReasoningStepHtml(seg.data);
            } else if (seg.type === 'steps') {
                return seg.data.map(function (step) {
                    var meta = _toolMeta(step.tool, step.args);
                    var isError = step.status === 'error';
                    return '<div class="ab-thinking-step' + (isError ? ' ab-step-is-error' : '') + '">' +
                        '<div class="ab-step-icon-col">' +
                            '<div class="ab-step-icon ' + (isError ? 'errored' : 'done') + '">' + meta.icon + '</div>' +
                            '<div class="ab-step-connector"></div>' +
                        '</div>' +
                        '<div class="ab-step-main">' +
                            '<div class="ab-step-headline">' +
                                '<span class="ab-step-name ' + (isError ? 'errored' : 'done') + '">' + _escapeHtml(meta.done) + '</span>' +
                                '<span class="ab-step-chevron">' + _icons.down + '</span>' +
                            '</div>' +
                            '<div class="ab-step-detail">' +
                                '<pre class="ab-step-detail-block">' + _prettyArgs(meta.args) + '</pre>' +
                                '<div class="ab-step-detail-footer">' +
                                    '<span class="ab-step-detail-status ' + (isError ? 'error' : 'success') + '">' + (isError ? 'Failed' : 'Done') + '</span>' +
                                '</div>' +
                            '</div>' +
                        '</div>' +
                    '</div>';
                }).join('');
            }
            return '';
        }).join('');

        var hasReasoning = segments.some(function (s) { return s.type === 'reasoning'; });
        var nTools = segments.reduce(function (sum, s) { return sum + (s.type === 'steps' ? s.data.length : 0); }, 0);
        var hasError = segments.some(function (s) {
            if (s.type === 'steps') return s.data.some(function (t) { return t.status === 'error'; });
            return false;
        });

        var label;
        if (hasError) { label = 'Stopped after an error'; }
        else {
            var parts = [];
            if (hasReasoning) parts.push('Thought Process');
            if (nTools > 0) parts.push(nTools + ' action' + (nTools !== 1 ? 's' : ''));
            label = parts.join(' · ') || '';
        }

        $('#ab-messages').append(
            '<div class="ab-thinking-container done' + (hasError ? ' errored' : '') + '" id="' + id + '">' +
                '<button class="ab-thinking-pill ' + (hasError ? 'errored' : 'done') + '" type="button">' +
                    _finalizedPillHtml(hasError, label, hasReasoning) +
                '</button>' +
                '<div class="ab-thinking-steps" style="display:none;">' + stepsHtml + '</div>' +
            '</div>'
        );
        _bindThinkingToggle($('#' + id));
    }

    function _scrollDown(smooth) {
        var el = document.getElementById('ab-messages');
        if (el) {
            if (smooth) {
                el.scrollTop = el.scrollHeight;
            } else {
                el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
            }
        }
    }

    function _md(text) {
        if (!text) return '';
        if (window.marked) {
            return marked.parse(text, { breaks: true, gfm: true });
        }
        return _escapeHtml(text).replace(/\n/g, '<br>');
    }

    function _escapeHtml(text) {
        if (!text) return '';
        return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // ── Public API ──────────────────────────────────────────────────
    return {
        init: init,
        clear: clear,
        loadHistory: loadHistory,
        appendUserMsg: _appendUserMessage,
        showTyping: showTyping,
        hideTyping: hideTyping,
        onToken: onToken,
        onReasoning: onReasoning,
        onToolStart: onToolStart,
        onToolDone: onToolDone,
        onDone: onDone,
        onStop: onStop,
        reloadArtifact: reloadArtifact,
        expandArtifact: expandArtifact,
        collapseAllFullscreenArtifacts: collapseAllFullscreenArtifacts,
    };
})();