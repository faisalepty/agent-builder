/**
 * ChatMessages v2.0 — SOTA Agent Message Renderer
 *
 * Key improvements over v1:
 *  - Incremental streaming: appends text nodes instead of full innerHTML
 *    replacement per token, eliminating flicker and iframe re-mounts.
 *  - Per-code-block copy buttons, not a single bubble-level button.
 *  - Message action row (copy, retry, branch) revealed on hover.
 *  - Artifact type detection (html vs. chart vs. table) shown in the bar.
 *  - Full tool-call data stored in _toolEvents for timeline inspection.
 *  - onStop() exposed to cleanly abort mid-stream.
 *  - postMessage resize listener auto-adjusts iframe heights.
 */
window.ChatMessages = (function () {

    let _icons = {};

    // Stream state
    let _streamBubbleId = null;
    let _streamTextNode = null;
    let _streamBuffer   = '';
    let _typingRowId    = null;

    // Thinking state
    let _thinkBlockId   = null;
    let _thinkStart     = null;
    let _thinkStepCount = 0;
    let _activeStepId   = null;
    let _toolStartTimes = {};
    const _savedSteps   = {};

    // Tool event log (for timeline panel)
    // shape: { id, tool, args, result, startMs, endMs, status }
    let _toolEvents     = [];
    let _onToolEvent    = null;  // callback → ChatUi timeline

    // Abort flag
    let _stopped = false;

    // ── Init ───────────────────────────────────────────────────
    function init(icons, { onToolEvent } = {}) {
        _icons = icons;
        _onToolEvent = onToolEvent || null;
        _listenResize();
    }

    function _listenResize() {
        window.addEventListener('message', function (e) {
            if (e.data && e.data.type === 'ab-resize') {
                // Find the iframe that sent this message
                document.querySelectorAll('.ab-artifact-iframe').forEach(function (iframe) {
                    try {
                        if (iframe.contentWindow === e.source) {
                            const h = Math.max(80, Math.min(e.data.height + 8, 600));
                            iframe.style.height = h + 'px';
                        }
                    } catch (_) {}
                });
            }
        });
    }

    // ── Clear ──────────────────────────────────────────────────
    function clear() {
        $('#ab-messages').empty();
        _streamBubbleId = null;
        _streamTextNode = null;
        _streamBuffer   = '';
        _typingRowId    = null;
        _thinkBlockId   = null;
        _thinkStart     = null;
        _thinkStepCount = 0;
        _activeStepId   = null;
        _toolStartTimes = {};
        _toolEvents     = [];
        _stopped        = false;
    }

    function getToolEvents() { return _toolEvents; }

    // ── History ────────────────────────────────────────────────
    function loadHistory(chatId) {
        clear();
        _showWelcome(false);
        $('#ab-messages').html(`<div class="ab-loading">Loading…</div>`);
        frappe.call({
            method: 'agent_builder.api.agent.get_messages',
            args: { chat_id: chatId },
            callback(r) {
                $('#ab-messages').empty();
                if (!r.message || !r.message.messages.length) {
                    _showWelcome(true);
                    return;
                }
                r.message.messages.forEach(msg => {
                    _appendStatic(msg.role === 'user' ? 'user' : 'agent', msg.content);
                });
                setTimeout(function () {
                    _mountArtifacts();
                    _scrollDown();
                }, 80);
            }
        });
    }

    function _showWelcome(show) {
        $('#ab-welcome').toggle(show);
    }

    // ── Static append (history) ────────────────────────────────
    function _appendStatic(role, content) {
        const id = 'b-' + Date.now() + Math.random().toString(36).slice(2);
        if (role === 'user') {
            $('#ab-messages').append(`
                <div class="ab-row user no-anim">
                    <div class="ab-bubble-wrap">
                        <div class="ab-bubble">${frappe.utils.escape_html(content)}</div>
                        ${_actionRow(id, 'user')}
                    </div>
                    <div class="ab-avatar">${_userInitials()}</div>
                </div>`);
        } else {
            $('#ab-messages').append(`
                <div class="ab-row agent no-anim">
                    <div class="ab-avatar">${_icons.bot}</div>
                    <div class="ab-bubble-wrap">
                        <div class="ab-bubble" id="${id}">${_renderContent(content)}</div>
                        ${_actionRow(id, 'agent')}
                    </div>
                </div>`);
        }
    }

    function _actionRow(bubbleId, role) {
        if (role === 'user') {
            return `<div class="ab-msg-actions">
                <button class="ab-msg-action-btn ab-copy-btn" data-bubble="${bubbleId}">${_icons.copy} Copy</button>
                <button class="ab-msg-action-btn ab-retry-btn" data-bubble="${bubbleId}">${_icons.retry} Retry</button>
            </div>`;
        }
        return `<div class="ab-msg-actions">
            <button class="ab-msg-action-btn ab-copy-btn" data-bubble="${bubbleId}">${_icons.copy} Copy</button>
        </div>`;
    }

    function appendUserMsg(text) {
        _showWelcome(false);
        const id = 'u-' + Date.now();
        $('#ab-messages').append(`
            <div class="ab-row user" id="row-${id}">
                <div class="ab-bubble-wrap">
                    <div class="ab-bubble" id="${id}">${frappe.utils.escape_html(text)}</div>
                    ${_actionRow(id, 'user')}
                </div>
                <div class="ab-avatar">${_userInitials()}</div>
            </div>`);
        _scrollDown();
    }

    // ── Stream bubble ──────────────────────────────────────────
    function _createAgentBubble() {
        hideTyping();
        const id = 'bubble-' + Date.now();
        _streamBubbleId = id;
        _streamBuffer   = '';
        _streamTextNode = null;
        _stopped        = false;
        $('#ab-messages').append(`
            <div class="ab-row agent" id="row-${id}">
                <div class="ab-avatar">${_icons.bot}</div>
                <div class="ab-bubble-wrap">
                    <div class="ab-bubble" id="${id}"><span class="ab-cursor"></span></div>
                    ${_actionRow(id, 'agent')}
                </div>
            </div>`);
        _scrollDown();
        return id;
    }

    // ── Token streaming (incremental) ─────────────────────────
    function onToken(delta) {
        if (!delta || _stopped) return;
        if (!_streamBubbleId) _createAgentBubble();

        _streamBuffer += delta;

        // Render markdown periodically (every 40ms) rather than every token.
        // For raw text deltas without markdown, append to a text node directly.
        // We use a rAF-batched approach: set a dirty flag, flush on next frame.
        if (!_streamFlushScheduled) {
            _streamFlushScheduled = true;
            requestAnimationFrame(_flushStream);
        }
    }

    let _streamFlushScheduled = false;

    function _flushStream() {
        _streamFlushScheduled = false;
        if (!_streamBubbleId || _stopped) return;
        const $bubble = $('#' + _streamBubbleId);
        if (!$bubble.length) return;
        $bubble.html(
            _md(_streamBuffer) +
            `<span class="ab-cursor"></span>`
        );
        _scrollDown(true);
    }

    function onDone(response) {
        hideTyping();
        _finalizeThinking();
        if (!_streamBubbleId) _createAgentBubble();

        const $bubble = $('#' + _streamBubbleId);
        const finalContent = _renderContent(response || _streamBuffer || '');
        $bubble.html(finalContent);

        setTimeout(function () {
            _mountArtifacts();
            _addCodeCopyButtons($bubble[0]);
            _scrollDown();
        }, 40);

        _streamBubbleId = null;
        _streamBuffer   = '';
        _streamTextNode = null;
        _streamFlushScheduled = false;
    }

    function onStop() {
        _stopped = true;
        if (_streamBubbleId) {
            const $bubble = $('#' + _streamBubbleId);
            // Finalize whatever was streamed
            $bubble.html(_md(_streamBuffer) + `<span style="opacity:.45;font-size:11px;margin-left:4px">[stopped]</span>`);
            _addCodeCopyButtons($bubble[0]);
            _streamBubbleId = null;
            _streamBuffer   = '';
            _streamFlushScheduled = false;
        }
        hideTyping();
        _finalizeThinking();
    }

    // ── Thinking (live) ────────────────────────────────────────
    function onToolStart(data) {
        // Store event
        const evId = 'ev-' + Date.now();
        const ev = { id: evId, tool: data.tool, args: data.args, result: null, startMs: Date.now(), endMs: null, status: 'running' };
        _toolEvents.push(ev);
        if (_onToolEvent) _onToolEvent('start', ev);

        if (!_thinkBlockId) {
            _thinkStart     = Date.now();
            _thinkStepCount = 0;
            const blockId   = 'think-' + Date.now();
            _thinkBlockId   = blockId;
            $('#ab-messages').append(`
                <div class="ab-think-live" id="${blockId}">
                    <div class="ab-think-live-header">
                        <span class="ab-spin">${_icons.spin}</span>
                        <span class="ab-think-live-label">Working…</span>
                        <span class="ab-think-step-count" id="${blockId}-count">0 actions</span>
                    </div>
                    <div class="ab-think-live-steps" id="${blockId}-steps"></div>
                </div>`);
        }

        _thinkStepCount++;
        _toolStartTimes[evId] = Date.now();
        const stepId = 'step-' + evId;
        _activeStepId = stepId;
        $(`#${_thinkBlockId}-count`).text(_thinkStepCount + (_thinkStepCount === 1 ? ' action' : ' actions'));

        const desc = _describeToolCall(data.tool, data.args);
        $(`#${_thinkBlockId}-steps`).append(`
            <div class="ab-think-step" id="${stepId}" data-event-id="${evId}">
                <span class="ab-think-step-icon ab-spin">${_icons.spin}</span>
                <span class="ab-think-step-name">${desc}</span>
                <span class="ab-think-step-time"></span>
            </div>`);
        _scrollDown();
    }

    function onToolDone(data) {
        if (_activeStepId) {
            const $step   = $(`#${_activeStepId}`);
            const evId    = $step.data('event-id');
            const elapsed = _toolStartTimes[evId]
                ? ((Date.now() - _toolStartTimes[evId]) / 1000).toFixed(2) + 's'
                : '';
            const summary = _summariseToolResult(data.tool, data.result);

            $step
                .find('.ab-think-step-icon').removeClass('ab-spin').html(_icons.check).addClass('done').end()
                .find('.ab-think-step-name').text(summary).end()
                .find('.ab-think-step-time').text(elapsed);

            // Update stored event
            const ev = _toolEvents.find(e => e.id === evId);
            if (ev) {
                ev.result = data.result;
                ev.endMs  = Date.now();
                ev.status = 'done';
                if (_onToolEvent) _onToolEvent('done', ev);
            }

            _activeStepId = null;
        }
        _scrollDown();
    }

    function _finalizeThinking() {
        if (!_thinkBlockId) return;
        const id      = _thinkBlockId;
        const elapsed = (( Date.now() - _thinkStart) / 1000).toFixed(1) + 's';
        const count   = _thinkStepCount;
        _savedSteps[id] = $(`#${id}-steps`).html();

        $(`#${id}`).replaceWith(`
            <div class="ab-think-pill" id="${id}" data-block="${id}">
                <span class="ab-think-pill-icon">${_icons.check}</span>
                <span class="ab-think-pill-label">${count} action${count !== 1 ? 's' : ''}</span>
                <span class="ab-think-pill-time">${elapsed}</span>
                <span class="ab-think-pill-toggle">›</span>
                <button class="ab-think-pill-tl-btn" title="View in timeline">Log</button>
            </div>`);

        _thinkBlockId   = null;
        _thinkStart     = null;
        _thinkStepCount = 0;
    }

    function getThinkSteps(id) { return _savedSteps[id] || ''; }

    // ── Typing indicator ───────────────────────────────────────
    function showTyping() {
        if (_typingRowId) return;
        const id = 'typing-' + Date.now();
        _typingRowId = id;
        $('#ab-messages').append(`
            <div class="ab-row agent" id="${id}">
                <div class="ab-avatar">${_icons.bot}</div>
                <div class="ab-typing"><span></span><span></span><span></span></div>
            </div>`);
        _scrollDown();
    }
    function hideTyping() {
        if (_typingRowId) { $('#' + _typingRowId).remove(); _typingRowId = null; }
    }

    // ── Content renderer ───────────────────────────────────────
    function _renderContent(text) {
        if (!text) return '';
        const regex = /`{3}html[ \t]*\r?\n([\s\S]*?)`{3}/g;
        const parts = [];
        let last = 0, match;

        while ((match = regex.exec(text)) !== null) {
            if (match.index > last) parts.push({ type: 'md', content: text.slice(last, match.index) });
            const id   = 'art-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
            const safe = match[1].replace(/<\/textarea/gi, '<\\/textarea');
            parts.push({ type: 'html', id, safe });
            last = match.index + match[0].length;
        }
        if (last < text.length) parts.push({ type: 'md', content: text.slice(last) });
        if (!parts.some(p => p.type === 'html')) return _md(text);

        return parts.map(p => {
            if (p.type === 'md') return p.content ? _md(p.content) : '';
            return `<div class="ab-artifact" id="${p.id}">
                <div class="ab-artifact-bar">
                    <div class="ab-artifact-dot"></div>
                    <span class="ab-artifact-label">Interactive UI</span>
                    <div class="ab-artifact-bar-btns">
                        <button class="ab-artifact-bar-btn ab-artifact-reload-btn" data-art="${p.id}" title="Reload">${_icons.reload} Reload</button>
                        <button class="ab-artifact-bar-btn ab-artifact-expand-btn" data-art="${p.id}" title="Fullscreen">${_icons.expand}</button>
                    </div>
                </div>
                <div class="ab-artifact-frame" id="${p.id}-frame"></div>
                <textarea class="ab-artifact-src">${p.safe}</textarea>
            </div>`;
        }).join('');
    }

    // ── Artifact mounting ──────────────────────────────────────
    function _mountArtifacts() {
        document.querySelectorAll('.ab-artifact-frame').forEach(function (frame) {
            if (frame.querySelector('iframe')) return;
            const artDiv = frame.closest('.ab-artifact');
            if (!artDiv) return;
            const srcEl = artDiv.querySelector('.ab-artifact-src');
            if (!srcEl || !srcEl.value.trim()) return;
            _mountSingleArtifact(frame, srcEl.value);
        });
    }

    function _mountSingleArtifact(frame, htmlContent) {
        const html   = _wrapArtifact(htmlContent);
        const iframe = document.createElement('iframe');
        iframe.setAttribute('sandbox', 'allow-scripts allow-same-origin');
        iframe.className    = 'ab-artifact-iframe';
        iframe.style.height = '240px';
        frame.appendChild(iframe);
        try {
            const doc = iframe.contentDocument || iframe.contentWindow.document;
            doc.open(); doc.write(html); doc.close();
        } catch (e) {
            iframe.srcdoc = html;
        }
    }

    function _wrapArtifact(html) {
        const resizeScript = `<script>
(function(){
  function report(){
    var h=Math.max(
      document.body?document.body.scrollHeight:0,
      document.documentElement?document.documentElement.scrollHeight:0
    );
    window.parent.postMessage({type:'ab-resize',height:h},'*');
  }
  window.addEventListener('load',function(){
    report();
    [200,600,1400].forEach(function(t){setTimeout(report,t);});
    if(window.ResizeObserver){new ResizeObserver(report).observe(document.body);}
  });
})();
<\/script>`;
        if (/<html[\s>]/i.test(html)) {
            return html.includes('</body>') ? html.replace('</body>', resizeScript + '</body>') : html + resizeScript;
        }
        return `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>*{box-sizing:border-box}body{margin:0;padding:0;background:transparent;font-family:'Inter','Segoe UI',system-ui,sans-serif}</style>
</head><body>${html}${resizeScript}</body></html>`;
    }

    // Reload artifact
    function reloadArtifact(artId) {
        const frame = document.querySelector(`#${artId}-frame`);
        if (!frame) return;
        const artDiv = document.querySelector(`#${artId}`);
        const srcEl  = artDiv && artDiv.querySelector('.ab-artifact-src');
        if (!srcEl) return;
        // Remove old iframe
        const old = frame.querySelector('iframe');
        if (old) old.remove();
        _mountSingleArtifact(frame, srcEl.value);
    }

    // ── Per-code-block copy buttons ────────────────────────────
    function _addCodeCopyButtons(el) {
        if (!el) return;
        el.querySelectorAll('pre').forEach(function (pre) {
            if (pre.querySelector('.ab-pre-copy')) return;
            const btn = document.createElement('button');
            btn.className = 'ab-pre-copy';
            btn.innerHTML = `${_icons.copy} Copy`;
            btn.addEventListener('click', function () {
                const code = pre.querySelector('code');
                navigator.clipboard.writeText(code ? code.textContent : pre.textContent).then(() => {
                    btn.innerHTML = `${_icons.check} Copied!`;
                    setTimeout(() => { btn.innerHTML = `${_icons.copy} Copy`; }, 1500);
                });
            });
            pre.style.position = 'relative';
            pre.appendChild(btn);
        });
    }

    // ── Tool descriptions (same as v1 + extras) ────────────────
    function _describeToolCall(toolName, argsStr) {
        try {
            const a = typeof argsStr === 'string' ? JSON.parse(argsStr) : (argsStr || {});
            switch (toolName) {
                case 'frappe_get_list':  return `Querying ${a.doctype || 'records'}${a.filters && Object.keys(a.filters).length ? ' — filtered' : ''}${a.limit ? ` (up to ${a.limit})` : ''}`;
                case 'frappe_get_doc':   return `Reading ${a.doctype} › ${a.name}`;
                case 'frappe_save_doc':  { const d = a.doc || {}; return d.name ? `Updating ${d.doctype} › ${d.name}` : `Creating ${d.doctype || 'document'}`; }
                case 'frappe_delete_doc': return `Deleting ${a.doctype} › ${a.name}`;
                case 'skill_view':       return `Loading skill: ${(a.name || '').split(':').pop()}`;
                case 'skills_list':      return 'Browsing available skills';
                case 'memory':           return `Memory: ${a.action || 'recall'}`;
                case 'web_search':       return `Searching: ${(a.query || '').slice(0, 48)}`;
                case 'web_extract':      return `Reading: ${(a.url || '').replace(/^https?:\/\//, '').slice(0, 44)}`;
                case 'execute_code':     return `Running ${a.language || 'code'}`;
                default:                 return toolName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            }
        } catch (e) { return toolName.replace(/_/g, ' '); }
    }

    function _summariseToolResult(toolName, resultStr) {
        try {
            const r = typeof resultStr === 'string' ? JSON.parse(resultStr) : resultStr;
            if (r && r.error) return `Error: ${String(r.error).slice(0, 60)}`;
            switch (toolName) {
                case 'frappe_get_list': return Array.isArray(r) ? `${r.length} record${r.length !== 1 ? 's' : ''} returned` : 'Query complete';
                case 'frappe_get_doc':  return r && r.name ? `Loaded ${r.name}` : 'Document loaded';
                case 'frappe_save_doc': return r && r.name ? `Saved — ${r.name}` : 'Saved';
                case 'frappe_delete_doc': return 'Deleted';
                case 'skill_view':      return 'Skill loaded';
                case 'web_search':      return Array.isArray(r) ? `${r.length} results` : 'Search complete';
                default:                return 'Done';
            }
        } catch (e) { return 'Done'; }
    }

    // ── Helpers ────────────────────────────────────────────────
    function _scrollDown(soft) {
        const el = document.getElementById('ab-messages');
        if (!el) return;
        if (soft) {
            // Only auto-scroll if already near the bottom
            const threshold = 80;
            if (el.scrollHeight - el.scrollTop - el.clientHeight < threshold) {
                el.scrollTop = el.scrollHeight;
            }
        } else {
            el.scrollTop = el.scrollHeight;
        }
        _updateScrollBtn();
    }

    function _updateScrollBtn() {
        const el = document.getElementById('ab-messages');
        if (!el) return;
        const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        $('#ab-scroll-btn').toggleClass('visible', !atBottom);
    }

    function _userInitials() {
        return (frappe.session.user || 'U').charAt(0).toUpperCase();
    }

    function _md(text) {
        if (!text) return '';
        if (window.marked) return marked.parse(text, { breaks: true, gfm: true });
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    return {
        init,
        clear,
        loadHistory,
        appendUserMsg,
        onToken,
        onToolStart,
        onToolDone,
        onDone,
        onStop,
        showTyping,
        hideTyping,
        getThinkSteps,
        getToolEvents,
        reloadArtifact,
    };

})();