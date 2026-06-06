window.ChatMessages = (function () {

    let _icons = {};
    let streamBubbleId = null;
    let streamBuffer   = '';
    let typingRowId    = null;

    // ── Thinking block state ───────────────────────────────────
    let thinkBlockId   = null;
    let thinkStart     = null;
    let thinkStepCount = 0;
    let activeStepId   = null;
    let toolStartTimes = {};
    const _savedSteps  = {};

    function init(icons) { _icons = icons; }

    function getThinkSteps(id) { return _savedSteps[id] || ''; }

    function clear() {
        $('#ab-messages').empty();
        streamBubbleId = null;
        streamBuffer   = '';
        typingRowId    = null;
        thinkBlockId   = null;
        thinkStart     = null;
        thinkStepCount = 0;
        activeStepId   = null;
        toolStartTimes = {};
        // No _artifacts to clear — HTML lives in the DOM via textarea
    }

    function loadHistory(chatId) {
        clear();
        $('#ab-messages').html(`<div class="ab-loading">Loading…</div>`);
        frappe.call({
            method: 'agent_builder.api.agent.get_messages',
            args: { chat_id: chatId },
            callback(r) {
                $('#ab-messages').empty();
                if (!r.message || !r.message.messages.length) {
                    $('#ab-messages').html(`<div class="ab-list-empty">No messages yet.</div>`);
                    return;
                }
                // Append all messages — no mounting inside _appendStatic
                r.message.messages.forEach(msg => {
                    _appendStatic(msg.role === 'user' ? 'user' : 'agent', msg.content);
                });
                // Single mount pass after all DOM is ready
                setTimeout(function () {
                    _mountArtifacts();
                    _scrollDown();
                }, 80);
            }
        });
    }

    function _appendStatic(role, content) {
        const initials = (frappe.session.user || 'U').charAt(0).toUpperCase();
        const id = 'b-' + Date.now() + Math.random().toString(36).slice(2);
        if (role === 'user') {
            $('#ab-messages').append(`
                <div class="ab-row user no-anim">
                    <div class="ab-bubble">${frappe.utils.escape_html(content)}</div>
                    <div class="ab-avatar">${initials}</div>
                </div>`);
        } else {
            $('#ab-messages').append(`
                <div class="ab-row agent no-anim">
                    <div class="ab-avatar">${_icons.bot}</div>
                    <div class="ab-bubble" id="${id}">
                        ${_renderContent(content)}
                        <button class="ab-copy-btn" data-bubble="${id}">${_icons.copy} Copy</button>
                    </div>
                </div>`);
            // No setTimeout here — loadHistory handles the final mount pass
        }
    }

    function appendUserMsg(text) {
        const initials = (frappe.session.user || 'U').charAt(0).toUpperCase();
        $('#ab-messages').append(`
            <div class="ab-row user">
                <div class="ab-bubble">${frappe.utils.escape_html(text)}</div>
                <div class="ab-avatar">${initials}</div>
            </div>`);
        _scrollDown();
    }

    function createAgentBubble() {
        hideTyping();
        const id = 'bubble-' + Date.now();
        streamBubbleId = id;
        streamBuffer   = '';
        $('#ab-messages').append(`
            <div class="ab-row agent" id="row-${id}">
                <div class="ab-avatar">${_icons.bot}</div>
                <div class="ab-bubble" id="${id}">
                    <span class="ab-cursor"></span>
                    <button class="ab-copy-btn" data-bubble="${id}">${_icons.copy} Copy</button>
                </div>
            </div>`);
        _scrollDown();
    }

    // ── Thinking block ─────────────────────────────────────────
    function onToolStart(data) {
        if (!thinkBlockId) {
            thinkStart     = Date.now();
            thinkStepCount = 0;
            const id = 'think-' + Date.now();
            thinkBlockId = id;
            $('#ab-messages').append(`
                <div class="ab-think-block" id="${id}">
                    <div class="ab-think-steps" id="${id}-steps"></div>
                </div>`);
        }
        thinkStepCount++;
        toolStartTimes[data.tool] = Date.now();
        const stepId = 'step-' + Date.now();
        activeStepId = stepId;
        const desc = _describeToolCall(data.tool, data.args);
        $(`#${thinkBlockId}-steps`).append(`
            <div class="ab-think-step" id="${stepId}">
                <span class="ab-think-step-icon ab-spin">${_icons.spin}</span>
                <span class="ab-think-step-name">${desc}</span>
                <span class="ab-think-step-time"></span>
            </div>`);
        _scrollDown();
    }

    function onToolDone(data) {
        if (activeStepId) {
            const elapsed = toolStartTimes[data.tool]
                ? ((Date.now() - toolStartTimes[data.tool]) / 1000).toFixed(2) + 's'
                : '';
            const summary = _summariseToolResult(data.tool, data.result);
            $(`#${activeStepId}`)
                .find('.ab-think-step-icon').removeClass('ab-spin').html(_icons.check).addClass('ab-think-step-done').end()
                .find('.ab-think-step-name').text(summary).end()
                .find('.ab-think-step-time').text(elapsed);
            activeStepId = null;
        }
        _scrollDown();
    }

    function _describeToolCall(toolName, argsStr) {
        try {
            const a = typeof argsStr === 'string' ? JSON.parse(argsStr) : (argsStr || {});
            switch (toolName) {
                case 'frappe_get_list': {
                    const filterDesc = a.filters && Object.keys(a.filters).length ? ' — filtered' : '';
                    const limit = a.limit ? ` (up to ${a.limit})` : '';
                    return `Querying ${a.doctype || 'records'}${filterDesc}${limit}`;
                }
                case 'frappe_get_doc':
                    return `Reading ${a.doctype} › ${a.name}`;
                case 'frappe_save_doc': {
                    const doc = a.doc || {};
                    return doc.name ? `Updating ${doc.doctype} › ${doc.name}` : `Creating ${doc.doctype || 'document'}`;
                }
                case 'frappe_delete_doc':
                    return `Deleting ${a.doctype} › ${a.name}`;
                case 'skill_view':
                    return `Loading skill: ${(a.name || '').split(':').pop()}`;
                case 'skills_list':
                    return 'Browsing available skills';
                case 'memory':
                    return `Memory: ${a.action || 'recall'}`;
                case 'web_search':
                    return `Searching: ${(a.query || '').slice(0, 48)}`;
                case 'web_extract':
                    return `Reading: ${(a.url || '').replace(/^https?:\/\//, '').slice(0, 44)}`;
                case 'execute_code':
                    return `Running ${a.language || 'code'}`;
                default:
                    return toolName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            }
        } catch (e) {
            return toolName.replace(/_/g, ' ');
        }
    }

    function _summariseToolResult(toolName, resultStr) {
        try {
            const r = typeof resultStr === 'string' ? JSON.parse(resultStr) : resultStr;
            if (r && r.error) return `Error: ${String(r.error).slice(0, 60)}`;
            switch (toolName) {
                case 'frappe_get_list':
                    return Array.isArray(r) ? `${r.length} record${r.length !== 1 ? 's' : ''} returned` : 'Query complete';
                case 'frappe_get_doc':
                    return r && r.name ? `Loaded ${r.name}` : 'Document loaded';
                case 'frappe_save_doc':
                    return r && r.name ? `Saved — ${r.name}` : 'Saved';
                case 'frappe_delete_doc':
                    return 'Deleted successfully';
                case 'skill_view':
                    return 'Skill loaded';
                case 'web_search':
                    return Array.isArray(r) ? `${r.length} results` : 'Search complete';
                default:
                    return 'Done';
            }
        } catch (e) {
            return 'Done';
        }
    }

    function _finalizeThinking() {
        if (!thinkBlockId) return;
        const id      = thinkBlockId;
        const elapsed = ((Date.now() - thinkStart) / 1000).toFixed(1) + 's';
        const count   = thinkStepCount;
        _savedSteps[id] = $(`#${id}-steps`).html();
        $(`#${id}`).addClass('ab-think-done').html(`
            <div class="ab-think-pill" data-block="${id}">
                <span class="ab-think-pill-icon">${_icons.check}</span>
                <span class="ab-think-pill-label">${count} action${count !== 1 ? 's' : ''}</span>
                <span class="ab-think-pill-time">${elapsed}</span>
                <span class="ab-think-pill-toggle">›</span>
            </div>`);
        thinkBlockId   = null;
        thinkStart     = null;
        thinkStepCount = 0;
    }

    // ── Tokens ─────────────────────────────────────────────────
    function onToken(delta) {
        if (!delta) return;
        if (!streamBubbleId) createAgentBubble();
        streamBuffer += delta;
        $(`#${streamBubbleId}`).html(
            _md(streamBuffer) +
            `<span class="ab-cursor"></span>` +
            `<button class="ab-copy-btn" data-bubble="${streamBubbleId}">${_icons.copy} Copy</button>`
        );
        _scrollDown();
    }

    function onDone(response) {
        hideTyping();
        _finalizeThinking();
        if (!streamBubbleId) createAgentBubble();
        $(`#${streamBubbleId}`).html(
            _renderContent(response || '') +
            `<button class="ab-copy-btn" data-bubble="${streamBubbleId}">${_icons.copy} Copy</button>`
        );
        setTimeout(function () {
            _mountArtifacts();
            _scrollDown();
        }, 40);
        streamBubbleId = null;
        streamBuffer   = '';
    }

    // ── Typing ─────────────────────────────────────────────────
    function showTyping() {
        if (typingRowId) return;
        const id = 'typing-' + Date.now();
        typingRowId = id;
        $('#ab-messages').append(`
            <div class="ab-row agent" id="${id}">
                <div class="ab-avatar">${_icons.bot}</div>
                <div class="ab-typing"><span></span><span></span><span></span></div>
            </div>`);
        _scrollDown();
    }

    function hideTyping() {
        if (typingRowId) { $('#' + typingRowId).remove(); typingRowId = null; }
    }

    // ── Generative UI — textarea-based artifact storage ────────
    // HTML lives in a hidden <textarea> in the DOM itself.
    // Survives clear(), navigation, back/forward, and re-renders.

    function _renderContent(text) {
        if (!text) return '';

        const regex = /`{3}html[ \t]*\r?\n([\s\S]*?)`{3}/g;
        const parts = [];
        let last = 0, match;

        while ((match = regex.exec(text)) !== null) {
            if (match.index > last) {
                parts.push({ type: 'md', content: text.slice(last, match.index) });
            }
            const id   = 'art-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
            // Escape </textarea> so inner HTML can't break the container
            const safe = match[1].replace(/<\/textarea/gi, '<\\/textarea');
            parts.push({ type: 'html', id, safe });
            last = match.index + match[0].length;
        }
        if (last < text.length) {
            parts.push({ type: 'md', content: text.slice(last) });
        }

        if (!parts.some(p => p.type === 'html')) return _md(text);

        return parts.map(p => {
            if (p.type === 'md') return p.content ? _md(p.content) : '';
            return `<div class="ab-artifact" id="${p.id}">
                <div class="ab-artifact-bar">
                    <span class="ab-artifact-label">Interactive</span>
                    <button class="ab-artifact-expand-btn" data-art="${p.id}">⤢</button>
                </div>
                <div class="ab-artifact-frame" id="${p.id}-frame"></div>
                <textarea class="ab-artifact-src" style="display:none;visibility:hidden;position:absolute;width:0;height:0;overflow:hidden">${p.safe}</textarea>
            </div>`;
        }).join('');
    }

    function _mountArtifacts() {
        document.querySelectorAll('.ab-artifact-frame').forEach(function (frame) {
            // Skip if already has an iframe
            if (frame.querySelector('iframe')) return;

            const artDiv = frame.closest('.ab-artifact');
            if (!artDiv) return;

            // Read from sibling textarea — always present, never lost
            const srcEl = artDiv.querySelector('.ab-artifact-src');
            if (!srcEl || !srcEl.value.trim()) return;

            const html   = _wrapArtifact(srcEl.value);
            const iframe = document.createElement('iframe');
            iframe.setAttribute('sandbox', 'allow-scripts allow-same-origin');
            iframe.className   = 'ab-artifact-iframe';
            iframe.style.height = '240px';
            frame.appendChild(iframe);

            try {
                const doc = iframe.contentDocument || iframe.contentWindow.document;
                doc.open();
                doc.write(html);
                doc.close();
            } catch (e) {
                iframe.srcdoc = html;
            }
        });
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
        setTimeout(report,200);
        setTimeout(report,600);
        setTimeout(report,1400);
        if(window.ResizeObserver){new ResizeObserver(report).observe(document.body);}
    });
})();
<\/script>`;

        if (/<html[\s>]/i.test(html)) {
            return html.includes('</body>')
                ? html.replace('</body>', resizeScript + '</body>')
                : html + resizeScript;
        }

        return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  *{box-sizing:border-box}
  body{margin:0;padding:0;background:transparent;font-family:'Inter','Segoe UI',system-ui,sans-serif}
</style>
</head>
<body>
${html}
${resizeScript}
</body>
</html>`;
    }

    // ── Helpers ────────────────────────────────────────────────
    function _scrollDown() {
        const el = document.getElementById('ab-messages');
        if (el) el.scrollTop = el.scrollHeight;
    }

    function _md(text) {
        if (!text) return '';
        if (window.marked) return marked.parse(text, { breaks: true, gfm: true });
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    return { init, clear, loadHistory, appendUserMsg, onToken, onToolStart, onToolDone, onDone, showTyping, hideTyping, getThinkSteps };

})();