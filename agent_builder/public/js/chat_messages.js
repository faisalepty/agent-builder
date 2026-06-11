/**
 * chat_messages.js v4.0 — SOTA DOM structure update
 * Generates cleaner HTML for bubbles to perfectly match the new CSS.
 */
window.ChatMessages = (function () {

    let _icons = {};
    let _streamBubbleId = null, _streamBuffer = '', _streamFlushScheduled = false, _typingRowId = null;
    let _currentThinkingRow = null, _currentThinkingSteps = [], _thinkStartTime = null;
    let _stopped = false;
    const _artifactStore = new Map();
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
                    try { if (iframe.contentWindow === e.source) iframe.style.height = Math.max(80, Math.min(e.data.height, 600)) + 'px'; } catch (_) {}
                });
            }
        });
    }

    function clear() {
        $('#ab-messages').empty();
        _artifactStore.clear();
        _resetStreamState();
        _resetThinkingState();
        _stopped = false;
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
                    if (msg.role === 'user') _appendUserMessage(msg.content);
                    else if (msg.role === 'assistant') _appendAgentMessage(msg.content);
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
    function _appendAgentMessage(content) {
        if (!content) return;
        const msgId = _nextId();
        $('#ab-messages').append(
            `<div class="ab-row agent" id="${msgId}">
                <div class="ab-avatar">${_icons.bot}</div>
                <div class="ab-bubble-wrap">
                    <div class="ab-bubble" id="${msgId}-bubble"></div>
                    <div class="ab-msg-actions">
                        <button class="ab-msg-action-btn ab-copy-btn" data-bubble="${msgId}-bubble">${_icons.copy} Copy</button>
                    </div>
                </div>
            </div>`
        );
        document.getElementById(msgId + '-bubble').innerHTML = _renderContentWithArtifacts(content);
    }

    // SOTA Structure for User message (no avatar, rounded bubble)
    function _appendUserMessage(text) {
        const id = _nextId();
        $('#ab-messages').append(
            `<div class="ab-row user" id="${id}">
                <div class="ab-bubble-wrap">
                    <div class="ab-bubble" id="${id}-bubble">${_escapeHtml(text)}</div>
                    <div class="ab-msg-actions" style="justify-content:flex-end;width:100%;">
                        <button class="ab-msg-action-btn ab-retry-btn" data-bubble="${id}-bubble">${_icons.retry} Edit</button>
                        <button class="ab-msg-action-btn ab-copy-btn" data-bubble="${id}-bubble">${_icons.copy}</button>
                    </div>
                </div>
            </div>`
        );
        _scrollDown();
    }

    function showTyping() {
        if (_typingRowId) return;
        _typingRowId = _nextId();
        $('#ab-messages').append(
            `<div class="ab-row agent" id="${_typingRowId}">
                <div class="ab-avatar">${_icons.bot}</div>
                <div class="ab-typing"><span></span><span></span><span></span></div>
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
                        <button class="ab-msg-action-btn ab-copy-btn" data-bubble="${_streamBubbleId}">${_icons.copy} Copy</button>
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
            _scrollDown(true);
        }
    }

    // SOTA Thinking Accordion
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
                        <span>Thought Process</span>
                        <span class="ab-chevron">${_icons.expand || '›'}</span>
                    </div>
                    <div class="ab-thinking-steps"></div>
                </div>`
            );
            _streamBubbleId ? $(`#row-${_streamBubbleId}`).before($thinking) : $('#ab-messages').append($thinking);
            
            $thinking.find('.ab-thinking-pill').on('click', function() {
                const $steps = $(this).siblings('.ab-thinking-steps');
                $steps.toggle();
                $(this).toggleClass('expanded');
            });
        }
        
        const stepId = _nextId();
        const description = _describeToolCall(data.tool, data.args);
        _currentThinkingSteps.push({ id: stepId, startTime: Date.now(), status: 'running' });
        
        $(`#${_currentThinkingRow} .ab-thinking-steps`).append(
            `<div class="ab-thinking-step" id="${stepId}">
                <div class="ab-step-icon running">${_icons.spin}</div>
                <div class="ab-step-name">${_escapeHtml(description)}</div>
                <div class="ab-step-time"></div>
            </div>`
        );
        _scrollDown();
    }

    function onToolDone(data) {
        const step = _currentThinkingSteps.find(s => s.status === 'running');
        if (!step) return;
        const elapsed = Date.now() - step.startTime;
        const elStr = elapsed < 1000 ? elapsed + 'ms' : (elapsed / 1000).toFixed(1) + 's';
        
        $(`#${step.id} .ab-step-icon`).removeClass('running').addClass('done').html(_icons.check);
        $(`#${step.id} .ab-step-time`).text(elStr);
        step.status = 'done';
        _scrollDown();
    }

    function onDone(response) {
        hideTyping();
        if (_currentThinkingRow) {
            const total = _thinkStartTime ? Date.now() - _thinkStartTime : 0;
            const totalStr = total < 1000 ? total + 'ms' : (total / 1000).toFixed(1) + 's';
            const $pill = $(`#${_currentThinkingRow} .ab-thinking-pill`);
            
            $pill.removeClass('expanded').addClass('done').html(
                `${_icons.check} <span>Analyzed for ${totalStr}</span><span class="ab-chevron">›</span>`
            );
            $(`#${_currentThinkingRow} .ab-thinking-steps`).hide(); // Auto collapse on done
            _resetThinkingState();
        }
        
        if (_streamBubbleId) {
            const el = document.getElementById(_streamBubbleId);
            if (el) {
                el.innerHTML = _renderContentWithArtifacts(response || _streamBuffer || '');
                setTimeout(() => { _mountAllArtifacts(); _addCodeCopyButtons(el); _scrollDown(); }, 0);
            }
        } else if (response) {
            _appendAgentMessage(response);
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
        iframe.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-popups allow-forms allow-modals');
        iframe.className = 'ab-artifact-iframe';
        iframe.srcdoc = htmlContent;
        if (old) frame.replaceChild(iframe, old); else frame.appendChild(iframe);
        iframe.addEventListener('load', () => _adjustIframeHeight(iframe));
    }

    function _adjustIframeHeight(iframe) {
        try {
            const doc = iframe.contentDocument || iframe.contentWindow.document;
            const h = Math.max(doc.body?.scrollHeight || 0, doc.documentElement?.scrollHeight || 0);
            if (h > 50) iframe.style.height = Math.min(h + 20, 600) + 'px';
        } catch (_) {}
    }

    function reloadArtifact(artifactId) {
        const artifactDiv = document.querySelector(`.ab-artifact[data-artifact-id="${artifactId}"]`);
        if (artifactDiv) {
            const frame = artifactDiv.querySelector('.ab-artifact-frame');
            if (frame && _artifactStore.get(artifactId)) _mountSingleArtifact(frame, _artifactStore.get(artifactId));
        }
    }

    function expandArtifact(artifactId) {
        const el = document.querySelector(`.ab-artifact[data-artifact-id="${artifactId}"]`);
        if (el) el.classList.toggle('ab-artifact-full');
    }

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

    function _describeToolCall(toolName, argsStr) {
        try {
            const args = typeof argsStr === 'string' ? JSON.parse(argsStr) : (argsStr || {});
            const map = {
                'frappe_get_list': () => `Fetching ${args.doctype || 'records'}`,
                'frappe_get_doc': () => `Reading ${args.doctype} › ${args.name || 'document'}`,
                'frappe_save_doc': () => args.doc?.name ? `Updating ${args.doc.doctype}` : `Creating ${args.doc?.doctype || 'record'}`,
                'web_search': () => `Searching Web: "${(args.query || '').slice(0, 40)}"`,
                'execute_code': () => `Executing ${args.language || 'script'}`
            };
            return (map[toolName] || (() => toolName.replace(/_/g, ' ')))();
        } catch (_) { return toolName.replace(/_/g, ' '); }
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

    return { init, clear, loadHistory, appendUserMsg: _appendUserMessage, onToken, onToolStart, onToolDone, onDone, onStop, showTyping, hideTyping, reloadArtifact, expandArtifact };
})();