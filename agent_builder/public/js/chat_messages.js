/**
 * chat_messages.js v4.3.6 — SOTA DOM structure update
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
 * v4.3.4: FIX — empty assistant bubbles no longer appear during live
 *   streaming (e.g. when the LLM emits whitespace before reasoning or
 *   tool calls). Ghost rows are now removed from the DOM instead of
 *   being frozen with no visible content.
 * v4.3.5: FIX — multiple "Thought Process" blocks no longer appear during
 *   multi-turn tool loops. The thinking container is only finalized when
 *   actual visible text arrives; whitespace-only tokens are buffered
 *   silently. A safety merge in onDone consolidates any adjacent
 *   finalized containers that slipped through.
 * v4.3.6: FIX — first tokens of text between thinking containers are no
 *   longer lost. _ensureStreamBubble() no longer resets _streamBuffer,
 *   which was destroying content that onToken had just accumulated before
 *   the bubble DOM element existed. The buffer is now only reset by
 *   _freezeStreamBubble() and _resetStreamState(), both of which run
 *   after the content has been consumed.
 */
window.ChatMessages = (function () {

    var _icons = {};
    var _CLOCK_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15.5 14"/></svg>';
    // Used for reasoning/"Thought Process" steps, both while live and once
    // finalized — swapped in for the old clock glyph.
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
                var lastAgentBubble = null;   // { rowId, bubbleId, isError } — the most
                                               // recent agent bubble that hasn't been
                                               // confirmed "final" yet.

                function flushPending() {
                    if (pendingSegments.length) {
                        _renderHistoricalThinkingContainer(pendingSegments);
                        pendingSegments = [];
                    }
                }

                // Copy is only meaningful on the last agent bubble of a turn —
                // call this whenever we're about to move past one (a new user
                // message starts, or history reconstruction ends).
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
                            // Reasoning attached to this text-carrying row
                            // belongs to the PRIOR episode (it was produced
                            // before this text) — flush it now, before the
                            // text, same as the live renderer.
                            if (msg.reasoning && msg.reasoning.text) {
                                pendingSegments.push({ type: 'reasoning', data: msg.reasoning });
                            }
                            flushPending();
                            var isErr = !!msg.is_error;
                            var msgId = _appendAgentMessage(msg.content, isErr, false);
                            lastAgentBubble = { rowId: msgId, bubbleId: msgId + '-bubble', isError: isErr };

                            // Tool calls attached to THIS SAME row happen
                            // after this text was generated (e.g. "Let me
                            // check X:" + a tool call in one completion).
                            // They belong to the NEXT episode, together with
                            // any action-only rows that follow — so
                            // accumulate them instead of rendering as their
                            // own orphaned single-action container.
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

    // SOTA Structure for Agent message.
    // withActions controls whether the copy/retry row renders immediately.
    // Default false — copy is only meaningful once generation is actually
    // finished, so intermediate text (followed by more thought-process
    // blocks) renders without it; the caller attaches it later via
    // _addMsgActions() once it knows this is the final bubble.
    function _appendAgentMessage(content, isError, withActions) {
        if (!content || !content.trim()) return null;
        var msgId = _nextId();
        $('#ab-messages').append(
            '<div class="ab-row agent' + (isError ? ' is-error' : '') + '" id="' + msgId + '">' +
                '<div class="ab-avatar">' + (isError ? (_icons.alertTriangle || _icons.bot) : _icons.bot) + '</div>' +
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

    // Attaches the copy/retry row to an already-rendered bubble — used once
    // we know a given bubble is the last one in the turn (end of live
    // generation, or end of a turn on history reload).
    function _addMsgActions(rowElId, bubbleElId, isError) {
        if (!rowElId || !bubbleElId) return;
        var $wrap = $('#' + rowElId).find('.ab-bubble-wrap');
        if (!$wrap.length || $wrap.find('.ab-msg-actions').length) return;
        $wrap.append(_msgActionsHtml(bubbleElId, isError));
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
        // Neutral "request is in flight" indicator — deliberately doesn't
        // say "Thinking" (that label is reserved for once reasoning
        // actually starts streaming; showing it here was misleading since
        // nothing has happened yet on the agent side).
        $('#ab-messages').append(
            '<div class="ab-row agent" id="' + _typingRowId + '">' +
                '<div class="ab-typing-indicator"><span></span><span></span><span></span></div>' +
            '</div>'
        );
        _scrollDown();
    }

    function hideTyping() { if (_typingRowId) { $('#' + _typingRowId).remove(); _typingRowId = null; } }

    function _ensureStreamBubble() {
        if (_streamBubbleId && document.getElementById(_streamBubbleId)) return;
        _streamBubbleId = _nextId();
        // IMPORTANT: Do NOT reset _streamBuffer here.
        // onToken accumulates content into _streamBuffer BEFORE calling this
        // function. If we reset the buffer here, the first token(s) are lost,
        // causing truncated text like "me use..." instead of "Let me use...".
        // The buffer is properly reset only by _freezeStreamBubble() (after
        // rendering content into the bubble) and _resetStreamState() (on
        // clear/new session).
        $('#ab-messages').append(
            '<div class="ab-row agent" id="row-' + _streamBubbleId + '">' +
                '<div class="ab-avatar">' + _icons.bot + '</div>' +
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

        // Only finalize the thinking container when there's actual visible
        // text to display. Whitespace-only tokens (which LLMs often emit
        // between reasoning and tool calls) must NOT trigger a finalize,
        // otherwise each turn creates a separate "Thought Process" block.
        if (_currentThinkingRow && _streamBuffer.trim()) {
            _finalizeThinkingContainer(false);
        }

        // Don't create the DOM bubble for leading whitespace — keeps the
        // thinking indicator visible instead of flashing an empty row.
        if (!_streamBubbleId && !_streamBuffer.trim()) {
            if (!_streamFlushScheduled) { _streamFlushScheduled = true; requestAnimationFrame(_flushStream); }
            return;
        }

        _ensureStreamBubble();
        if (!_streamFlushScheduled) { _streamFlushScheduled = true; requestAnimationFrame(_flushStream); }
    }

    function _flushStream() {
        _streamFlushScheduled = false;
        if (!_streamBubbleId || _stopped) return;
        var el = document.getElementById(_streamBubbleId);
        if (el) {
            el.innerHTML = _md(_streamBuffer) + '<span class="ab-cursor ab-cursor--ghost"></span>';
            el.classList.add('ab-streaming-cursor');
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
                    var cursor = el.querySelector('.ab-cursor');
                    if (cursor) cursor.remove();
                    el.innerHTML = _md(trimmed);
                    el.classList.remove('ab-streaming-cursor');
                    _wrapTables(el);
                    _addCodeCopyButtons(el);
                } else {
                    // Bubble has no visible content — remove the entire row
                    var row = document.getElementById('row-' + _streamBubbleId);
                    if (row) row.remove();
                }
            }
        }
        // Always reset both — content has been consumed (rendered or discarded)
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

    // ──────────────────────────────────────────────────────────────────
    // Safety merge: consolidate adjacent finalized thinking containers
    //
    // Called in onDone/onStop as a defense-in-depth measure. If multiple
    // "Thought Process · N actions" blocks ended up adjacent (separated
    // only by empty/whitespace-only agent rows), this merges them into
    // a single container — matching what loadHistory does on reload.
    // ──────────────────────────────────────────────────────────────────
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
                    if (text) {
                        onlyEmptyAgentRows = false;
                        return false;
                    }
                } else {
                    onlyEmptyAgentRows = false;
                    return false;
                }
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
            var totalTools = 0;
            var hasReasoning = false;
            var hasError = false;

            $first.find('.ab-thinking-step').each(function () {
                if ($(this).hasClass('ab-reasoning-block')) {
                    hasReasoning = true;
                } else {
                    totalTools++;
                }
                if ($(this).hasClass('ab-step-is-error')) hasError = true;
            });

            for (var i = 1; i < group.length; i++) {
                var $container = group[i];

                $container.find('.ab-thinking-steps > *').appendTo($first.find('.ab-thinking-steps'));

                $container.find('.ab-thinking-step').each(function () {
                    if ($(this).hasClass('ab-reasoning-block')) {
                        hasReasoning = true;
                    } else {
                        totalTools++;
                    }
                    if ($(this).hasClass('ab-step-is-error')) hasError = true;
                });

                var $prevInGroup = group[i - 1];
                $prevInGroup.nextUntil($container).each(function () {
                    var $el = $(this);
                    if ($el.hasClass('ab-row') && $el.hasClass('agent')) {
                        var text = $el.find('.ab-bubble').text().trim();
                        if (!text) {
                            $el.remove();
                        }
                    }
                });

                $container.remove();
            }

            var label;
            if (hasError) {
                label = 'Stopped after an error';
            } else {
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

        if (_currentThinkingRow) {
            _finalizeThinkingContainer(isError);
        }

        _mergeAdjacentThinkingContainers();

        if (_streamBubbleId) {
            var el = document.getElementById(_streamBubbleId);
            var row = document.getElementById('row-' + _streamBubbleId);
            if (el) {
                var finalContent = (response || _streamBuffer || '').trim();
                if (finalContent) {
                    el.classList.remove('ab-streaming-cursor');
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
        if (_currentThinkingRow) {
            _finalizeThinkingContainer(false);
        }
        _mergeAdjacentThinkingContainers();

        if (_streamBubbleId) {
            var el = document.getElementById(_streamBubbleId);
            var row = document.getElementById('row-' + _streamBubbleId);
            if (el) {
                var trimmed = (_streamBuffer || '').trim();
                if (trimmed) {
                    el.innerHTML = _md(trimmed);
                    el.classList.remove('ab-streaming-cursor');
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
    // ──────────────────────────────────────────────────────────────────

    /** Build a single finalized reasoning step row */
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
                    _finalizedPillHtml(hasError, label, hasReasoning) +
                '</div>' +
                '<div class="ab-thinking-steps" style="display:none;">' + allStepsHtml + '</div>' +
            '</div>'
        );
        $('#ab-messages').append($thinking);
        _bindThinkingToggle($thinking);

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