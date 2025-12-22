$(document).ready(function() {
    console.log("Agent Chat UI Loading...");

    const chatHTML = `
        <div id="ai-chat-container">
            <div id="ai-chat-window" style="display: none !important;">
                <div class="ai-chat-header">
                    <span><i class="fa fa-magic"></i> Agent Builder</span>
                    <i class="fa fa-times" id="ai-close" style="cursor:pointer; opacity: 0.5;"></i>
                </div>
                <div class="ai-chat-log" id="ai-log">
                    <div class="ai-bubble agent">Ready to build. What's on your mind?</div>
                </div>
                <div class="ai-chat-input-area">
                    <input type="text" id="ai-input" class="form-control" placeholder="Describe your DocType...">
                    <button class="btn btn-primary btn-sm" id="ai-send">
                        <i class="fa fa-paper-plane"></i>
                    </button>
                </div>
            </div>
            <div id="ai-chat-button">
                <i class="fa-solid fa-wand-magic-sparkles"></i>
            </div>
        </div>
    `;
    $('body').append(chatHTML);

    $(document).on('click', '#ai-chat-button', function() {
        const $window = $('#ai-chat-window');
        if ($window.attr('style').includes('none')) {
            $window.attr('style', 'display: flex !important;');
            $("#ai-input").focus();
        } else {
            $window.attr('style', 'display: none !important;');
        }
    });

    $(document).on('click', '#ai-close', function() {
        $('#ai-chat-window').attr('style', 'display: none !important;');
    });

    // NEW MODERN LOG STRUCTURE
    const appendProcessBlock = () => {
        const blockId = "proc-" + Date.now();
        const html = `
            <div class="process-block" id="${blockId}">
                <div class="process-header">
                    <i class="fa fa-circle-notch fa-spin"></i> Building Resource
                </div>
                <div class="process-steps"></div>
            </div>
        `;
        $('#ai-log').append(html);
        return blockId;
    };

    let currentBlockId = null;

    const sendMessage = () => {
        const msg = $('#ai-input').val();
        if(!msg) return;

        $('#ai-log').append(`<div class="ai-bubble user">${msg}</div>`);
        $('#ai-input').val('');
        
        currentBlockId = appendProcessBlock();
        $("#ai-log").scrollTop($("#ai-log")[0].scrollHeight);

        frappe.call({
            method: 'agent_builder.agent2.orchestrator.execute_orch',
            args: { prompt: msg }
        });
    };

    $(document).on('click', '#ai-send', sendMessage);
    $(document).on('keypress', '#ai-input', (e) => { if(e.which == 13) sendMessage(); });

    if (window.frappe && frappe.realtime) {
        frappe.realtime.on('agent_builder_msg', (data) => {
            if (data.status === 'progress' && currentBlockId) {
                // The new item is appended and will grow the block height naturally
                $(`#${currentBlockId} .process-steps`).append(`
                    <div class="step-item">
                        <i class="fa fa-terminal"></i> ${data.text}
                    </div>
                `);
                // Auto-scroll to keep the latest log in view
                $("#ai-log").scrollTop($("#ai-log")[0].scrollHeight);
            } 
            else if (data.status === 'success' || data.status === 'error') {
                const $block = $(`#${currentBlockId}`);
                $block.css('border-left-color', 'var(--border-color)');
                $block.find('.process-header').html('<i class="fa fa-check-circle"></i> Build Sequence Complete');
                
                $('#ai-log').append(`
                    <div class="ai-bubble agent">
                        <small style="display:block; font-weight:bold; color:var(--text-muted); margin-bottom:4px;">
                            ${data.agent || 'AI Assistant'}
                        </small>
                        ${data.text}
                    </div>
                `);
                currentBlockId = null;
                $("#ai-log").scrollTop($("#ai-log")[0].scrollHeight);
            }
        });
    }
});