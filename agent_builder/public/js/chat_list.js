window.ChatList = (function () {

    let _onSelect = null;
    let _onNew    = null;

    function init({ onSelect, onNew }) {
        _onSelect = onSelect;
        _onNew    = onNew;
        _bindEvents();
    }

    function load() {
        frappe.call({
            method: 'agent_builder.api.agent.get_chats',
            callback(r) {
                if (r.message) _render(r.message.chats);
            }
        });
    }

    function _render(chats) {
        const $el = $('#ab-list-items');
        $el.empty();
        if (!chats || !chats.length) {
            $el.html(`<div class="ab-list-empty">No conversations yet.<br>Start a new chat.</div>`);
            return;
        }
        chats.forEach(c => {
            const time = frappe.datetime.prettyDate(c.last_active);
            $el.append(`
                <div class="ab-chat-item" data-id="${c.name}" data-title="${frappe.utils.escape_html(c.title)}">
                    <div class="ab-chat-item-title">${frappe.utils.escape_html(c.title)}</div>
                    <div class="ab-chat-item-meta">${time}</div>
                </div>
            `);
        });
    }

    function prepend(chat) {
        $('.ab-list-empty').remove();
        $('#ab-list-items').prepend(`
            <div class="ab-chat-item active" data-id="${chat.chat_id}" data-title="${frappe.utils.escape_html(chat.title)}">
                <div class="ab-chat-item-title">${frappe.utils.escape_html(chat.title)}</div>
                <div class="ab-chat-item-meta">Just now</div>
            </div>
        `);
    }

    function setActive(chatId) {
        $('.ab-chat-item').removeClass('active');
        $(`.ab-chat-item[data-id="${chatId}"]`).addClass('active');
    }

    function _bindEvents() {
        $(document).on('click', '.ab-chat-item', function () {
            const id    = $(this).data('id');
            const title = $(this).data('title');
            setActive(id);
            if (_onSelect) _onSelect(id, title);
        });
        $(document).on('click', '#ab-new-chat', function () {
            if (_onNew) _onNew();
        });
    }

    return { init, load, prepend, setActive };

})();