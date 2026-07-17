/**
 * ChatList v4.0
 */
window.ChatList = (function () {

    let _onSelect = null;
    let _onNew    = null;
    let _allChats = [];
    let _searchQ  = '';
    let _debounceTimer = null;

    function init({ onSelect, onNew }) {
        _onSelect = onSelect;
        _onNew    = onNew;
        _bindEvents();
    }

    function load() {
        frappe.call({
            method: 'agent_builder.native_api.verify.get_chats',
            callback(r) {
                if (r.message) {
                    _allChats = r.message.chats || [];
                    _render();
                }
            }
        });
    }

    function _render() {
        const q     = _searchQ.toLowerCase().trim();
        const chats = q
            ? _allChats.filter(c => (c.title || '').toLowerCase().includes(q) || (c.preview || '').toLowerCase().includes(q))
            : _allChats;

        const $el = $('#ab-list-items');
        $el.empty();

        if (!chats.length) {
            if (q) {
                $el.html(`<div class="ab-list-empty">No chats matching "${frappe.utils.escape_html(_searchQ)}"</div>`);
            } else {
                $el.html(`
                    <div class="ab-list-empty ab-list-empty-first">
                        <div class="ab-list-empty-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                        </div>
                        <div class="ab-list-empty-title">No conversations yet</div>
                        <div class="ab-list-empty-sub">Ask about sales, invoices, stock, or anything in your ERP data.</div>
                        <button class="ab-empty-new-chat-btn" type="button">Start a new chat</button>
                    </div>`);
            }
            return;
        }

        const groups = _groupByDate(chats);
        groups.forEach(({ label, items }) => {
            if (label) $el.append(`<div class="ab-list-group-label">${label}</div>`);
            items.forEach(c => {
                const time    = frappe.datetime.prettyDate(c.last_active);
                const title   = frappe.utils.escape_html(c.title || 'Untitled');
                const preview = frappe.utils.escape_html((c.preview || '').slice(0, 60));
                $el.append(`
                    <div class="ab-chat-item" data-id="${c.name}" data-title="${title}" tabindex="0" role="button">
                        <div class="ab-chat-item-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
                            </svg>
                        </div>
                        <div class="ab-chat-item-body">
                            <div class="ab-chat-item-title">${title}</div>
                            ${preview ? `<div class="ab-chat-item-preview">${preview}</div>` : ''}
                        </div>
                        <div style="font-size:11px;color:var(--text-muted);">${time}</div>
                    </div>`);
            });
        });
    }

    function _groupByDate(chats) {
        const now = new Date(), today = _dateKey(now), yest = _dateKey(new Date(now - 86400000)), weekAgo = new Date(now - 7 * 86400000);
        const groups = { Today: [], Yesterday: [], 'This week': [], Older: [] };
        chats.forEach(c => {
            const d = new Date(c.last_active), k = _dateKey(d);
            if (k === today) groups['Today'].push(c);
            else if (k === yest) groups['Yesterday'].push(c);
            else if (d >= weekAgo) groups['This week'].push(c);
            else groups['Older'].push(c);
        });
        return ['Today', 'Yesterday', 'This week', 'Older'].filter(g => groups[g].length).map(g => ({ label: g, items: groups[g] }));
    }

    function _dateKey(d) { return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`; }

    function prepend(chat) {
        _allChats = _allChats.filter(c => c.name !== chat.chat_id);
        _allChats.unshift({ name: chat.chat_id, title: chat.title, last_active: new Date().toISOString(), preview: '' });
        _render();
        setActive(chat.chat_id);
    }

    function setActive(chatId) {
        $('.ab-chat-item').removeClass('active');
        $('.ab-chat-item').filter(function () { return $(this).data('id') === chatId; }).addClass('active');
    }

    function _bindEvents() {
        $(document).on('click', '.ab-chat-item', function () {
            setActive($(this).data('id'));
            if (_onSelect) _onSelect($(this).data('id'), $(this).data('title'));
        });

        $(document).on('keydown', '.ab-chat-item', function (e) {
            if (e.key === 'Enter' || e.key === ' ') $(this).trigger('click');
            if (e.key === 'ArrowDown') { $(this).nextAll('.ab-chat-item').first().focus(); e.preventDefault(); }
            if (e.key === 'ArrowUp')   { $(this).prevAll('.ab-chat-item').first().focus(); e.preventDefault(); }
        });

        $(document).on('click', '#ab-new-chat', function () { if (_onNew) _onNew(); });

        $(document).on('input', '#ab-list-search', function () {
            clearTimeout(_debounceTimer);
            _debounceTimer = setTimeout(() => { _searchQ = $(this).val(); _render(); }, 180);
        });

        $(document).on('keydown', '#ab-list-search', function (e) {
            if (e.key === 'Escape') { $(this).val(''); _searchQ = ''; _render(); }
        });
    }

    return { init, load, prepend, setActive };
})();