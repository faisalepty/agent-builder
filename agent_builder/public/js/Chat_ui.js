$(document).ready(function () {

    const chatHTML = `
        <div id="ai-chat-container">
            <div id="ai-chat-window" style="display: none !important;">
                <div class="ai-chat-header">
                    <span><i class="fa fa-magic"></i> Agent Builder</span>
                    <i class="fa fa-times" id="ai-close" style="cursor:pointer; opacity: 0.5;"></i>
                </div>
                <div class="ai-chat-log" id="ai-log">
                    <div class="ai-bubble agent">Ready. What do you need?</div>
                </div>
                <div class="ai-chat-input-area">
                    <input type="text" id="ai-input" class="form-control" placeholder="Ask anything...">
                    <button class="btn btn-primary btn-sm" id="ai-send">
                        <i class="fa fa-paper-plane"></i>
                    </button>
                </div>
            </div>
            <div id="ai-chat-button">
                <i class="fa fa-magic"></i>
            </div>
        </div>
    `;
    $('body').append(chatHTML);

    // ── Toggle ──────────────────────────────────────────────────
    $(document).on('click', '#ai-chat-button', function () {
        const $w = $('#ai-chat-window');
        $w.attr('style', $w.attr('style').includes('none')
            ? 'display: flex !important;'
            : 'display: none !important;');
        if (!$w.attr('style').includes('none')) $('#ai-input').focus();
    });

    $(document).on('click', '#ai-close', function () {
        $('#ai-chat-window').attr('style', 'display: none !important;');
    });

    // ── State ───────────────────────────────────────────────────
    let currentBlockId = null;
    let currentAgentBubble = null;
    let streamBuffer = '';

    // ── Helpers ─────────────────────────────────────────────────
    const scrollDown = () => {
        const log = document.getElementById('ai-log');
        log.scrollTop = log.scrollHeight;
    };

    const appendProcessBlock = () => {
        const id = 'proc-' + Date.now();
        $('#ai-log').append(`
            <div class="process-block" id="${id}">
                <div class="process-header">
                    <i class="fa fa-circle-notch fa-spin"></i> Working
                </div>
                <div class="process-steps"></div>
            </div>
        `);
        scrollDown();
        return id;
    };

    const appendStep = (icon, text) => {
        if (!currentBlockId) return;
        $(`#${currentBlockId} .process-steps`).append(`
            <div class="step-item">
                <i class="fa ${icon}"></i> ${text}
            </div>
        `);
        scrollDown();
    };

    const finaliseBlock = () => {
        if (!currentBlockId) return;
        $(`#${currentBlockId} .process-header`)
            .html('<i class="fa fa-check-circle"></i> Done');
        currentBlockId = null;
    };

    const startAgentBubble = () => {
        streamBuffer = '';
        const id = 'bubble-' + Date.now();
        $('#ai-log').append(`
            <div class="ai-bubble agent" id="${id}"></div>
        `);
        currentAgentBubble = id;
        scrollDown();
        return id;
    };

    // ── Send ────────────────────────────────────────────────────
    const sendMessage = () => {
        const msg = $('#ai-input').val().trim();
        if (!msg) return;

        $('#ai-log').append(`<div class="ai-bubble user">${msg}</div>`);
        $('#ai-input').val('');

        currentBlockId = appendProcessBlock();
        startAgentBubble();

        frappe.call({
            method: 'agent_builder.api.agent.chat',
            args: { message: msg }
        });
    };

    $(document).on('click', '#ai-send', sendMessage);
    $(document).on('keypress', '#ai-input', (e) => {
        if (e.which === 13) sendMessage();
    });

    // ── Realtime ────────────────────────────────────────────────

    // Streaming tokens — build the agent bubble character by character
    frappe.realtime.on('agent_token', (data) => {
        if (!currentAgentBubble) startAgentBubble();
        streamBuffer += data.delta;
        $(`#${currentAgentBubble}`).text(streamBuffer);
        scrollDown();
    });

    // Tool events — update the process block
    frappe.realtime.on('agent_event', (data) => {
        if (data.type === 'tool_start') {
            appendStep('fa-wrench', `${data.tool}`);
        } else if (data.type === 'tool_progress') {
            appendStep('fa-circle-notch fa-spin', `${data.status}`);
        } else if (data.type === 'tool_done') {
            appendStep('fa-check', `${data.tool} done`);
        }
    });

    // Final response — close the process block
    frappe.realtime.on('agent_done', (data) => {
        finaliseBlock();
        // If streaming didn't fire (non-streaming model), set the bubble now
        if (!streamBuffer && currentAgentBubble) {
            $(`#${currentAgentBubble}`).text(data.response);
        }
        currentAgentBubble = null;
        streamBuffer = '';
        scrollDown();
    });

});