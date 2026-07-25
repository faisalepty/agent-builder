// agent_builder/page/agent_management/agent_management.js
frappe.pages['agent-builder'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Agent Management',
		single_column: true,
	});

	new AgentManagement(page);
};

class AgentManagement {
	constructor(page) {
		this.page = page;
		this.state = { tab: 'sessions', sessions: [], workflows: [], expanded: {}, selected: null };

		this.$root = $('<div class="am-root"></div>').appendTo(page.main);
		this.injectStyles();
		this.renderShell();
		this.load();
	}

	async load() {
		this.$body.html('<div class="am-empty">Loading…</div>');
		const [sessionsRes, workflowsRes] = await Promise.all([
			frappe.call("agent_builder.agent_builder.page.agent_builder.agent_builder.get_sessions"),
			frappe.call("agent_builder.agent_builder.page.agent_builder.agent_builder.get_workflows"),
		]);
		this.state.sessions = sessionsRes.message || [];
		this.state.workflows = workflowsRes.message || [];
		this.renderBody();
	}

	renderShell() {
		const $tabs = $(`
			<div class="am-tabs">
				<button class="am-tab active" data-tab="sessions">Sessions</button>
				<button class="am-tab" data-tab="workflows">Workflows</button>
			</div>
		`).appendTo(this.$root);

		$tabs.on('click', '.am-tab', (e) => {
			const tab = $(e.currentTarget).data('tab');
			this.state.tab = tab;
			$tabs.find('.am-tab').removeClass('active');
			$(e.currentTarget).addClass('active');
			this.renderBody();
		});

		this.$body = $('<div class="am-panel-wrap"></div>').appendTo(this.$root);
	}

	renderBody() {
		this.$body.empty();
		if (this.state.tab === 'sessions') this.renderSessions();
		else this.renderWorkflows();
	}

	statusColor(s) {
		if (s.status === 'Active') return '#5B8DEF';
		if (s.ended_reason === 'Completed') return '#3ECF8E';
		if (s.ended_reason === 'MaxTurnsError' || s.ended_reason === 'LoopDetected') return '#E8A33D';
		if (s.ended_reason === 'Error') return '#E5484D';
		return '#8B8D98';
	}

	renderSessions() {
		const { sessions } = this.state;
		if (!sessions.length) {
			this.$body.html('<div class="am-empty">No sessions yet. They\'ll show up here once agents start running.</div>');
			return;
		}

		const $panel = $('<div class="am-panel"></div>').appendTo(this.$body);

		sessions.forEach((s) => {
			const expanded = !!this.state.expanded[s.name];
			const hasChildren = s.children && s.children.length;

			const $row = $(`
				<div class="am-row">
					<span class="am-caret" style="${hasChildren ? '' : 'opacity:0'}">${expanded ? '▾' : '▸'}</span>
					<span class="am-dot" style="background:${this.statusColor(s)}"></span>
					<span class="am-title">${frappe.utils.escape_html(s.title || s.name)}</span>
					<span class="am-id">${s.name}</span>
					<span class="am-badge">${s.trigger_type || '—'}</span>
					<span class="am-meta">${s.turn_count || 0} turns</span>
					<span class="am-meta">$${(s.estimated_cost || 0).toFixed(4)}</span>
					<span class="am-meta">${hasChildren ? s.children.length + ' delegate' + (s.children.length > 1 ? 's' : '') : ''}</span>
				</div>
			`).appendTo($panel);

			$row.on('click', () => {
				if (hasChildren) {
					this.state.expanded[s.name] = !expanded;
					this.renderSessions();
				} else {
					this.showDrawer(s);
				}
			});

			if (expanded && hasChildren) {
				const $children = $('<div class="am-children"></div>').appendTo($panel);
				s.children.forEach((c) => {
					const $crow = $(`
						<div class="am-row am-child-row">
							<span class="am-thread"></span>
							<span class="am-dot" style="background:${this.statusColor(c)}"></span>
							<span class="am-title">${frappe.utils.escape_html(c.title || c.name)}</span>
							<span class="am-id">${c.name}</span>
							<span class="am-badge am-badge-skill">${c.delegated_skill || '—'}</span>
							<span class="am-meta">depth ${c.delegate_depth}</span>
							<span class="am-meta">${c.turn_count || 0} turns</span>
							<span class="am-meta">$${(c.estimated_cost || 0).toFixed(4)}</span>
						</div>
					`).appendTo($children);
					$crow.on('click', () => this.showDrawer(c));
				});
			}
		});
	}

	renderWorkflows() {
		const { workflows } = this.state;
		if (!workflows.length) {
			this.$body.html('<div class="am-empty">No workflows defined yet.</div>');
			return;
		}

		const $table = $(`
			<table class="am-table">
				<thead>
					<tr><th>Name</th><th>Description</th><th>Steps</th><th>Status</th><th>Modified</th></tr>
				</thead>
				<tbody></tbody>
			</table>
		`).appendTo($('<div class="am-panel"></div>').appendTo(this.$body));

		const $tbody = $table.find('tbody');
		workflows.forEach((w) => {
			const $tr = $(`
				<tr class="am-wf-row">
					<td class="am-id">${w.workflow_name}</td>
					<td class="am-desc">${frappe.utils.escape_html(w.description || '—')}</td>
					<td class="am-meta">${w.step_count}</td>
					<td><span class="am-badge" style="color:${w.is_enabled ? '#3ECF8E' : '#8B8D98'}">${w.is_enabled ? 'Enabled' : 'Disabled'}</span></td>
					<td class="am-meta">${frappe.datetime.comment_when(w.modified)}</td>
				</tr>
			`).appendTo($tbody);
			$tr.on('click', () => frappe.set_route('workflow-builder', w.name));
		});
	}

	showDrawer(session) {
		$('.am-drawer').remove();
		const $drawer = $(`
			<div class="am-drawer">
				<div class="am-drawer-panel">
					<div class="am-drawer-head">
						<span class="am-id">${session.name}</span>
						<button class="am-close">×</button>
					</div>
					<div class="am-drawer-body">
						<div class="am-kv"><span>Status</span><b>${session.status} / ${session.ended_reason || '—'}</b></div>
						<div class="am-kv"><span>Trigger</span><b>${session.trigger_type || ''} · ${session.trigger_source || ''}</b></div>
						${session.delegated_skill ? `<div class="am-kv"><span>Delegated as</span><b>${session.delegated_skill}</b></div>` : ''}
						<div class="am-kv"><span>Turns</span><b>${session.turn_count || 0}</b></div>
						<div class="am-kv"><span>Cost</span><b>$${(session.estimated_cost || 0).toFixed(4)}</b></div>
						<a class="am-open-link" href="/app/agent-session/${session.name}" target="_blank">Open full record →</a>
					</div>
				</div>
			</div>
		`).appendTo('body');

		$drawer.on('click', (e) => { if (e.target === $drawer[0]) $drawer.remove(); });
		$drawer.find('.am-close').on('click', () => $drawer.remove());
	}

	injectStyles() {
		if (document.getElementById('am-styles')) return;
		const style = document.createElement('style');
		style.id = 'am-styles';
		style.textContent = `
			.am-root { font-family: 'Inter', -apple-system, sans-serif; color: #EDEDF0; background: #14151A; padding: 20px 28px 60px; margin: -15px; }
			.am-tabs { display: flex; gap: 4px; margin-bottom: 18px; border-bottom: 1px solid #2A2C36; }
			.am-tab { background: none; border: none; color: #8B8D98; font-size: 13px; font-weight: 600; padding: 10px 16px; cursor: pointer; border-bottom: 2px solid transparent; }
			.am-tab.active { color: #EDEDF0; border-bottom-color: #5B8DEF; }
			.am-empty { color: #8B8D98; font-size: 13px; padding: 40px 0; text-align: center; }
			.am-panel { background: #1C1E26; border: 1px solid #2A2C36; border-radius: 8px; overflow: hidden; }
			.am-row { display: flex; align-items: center; gap: 10px; padding: 10px 14px; cursor: pointer; border-bottom: 1px solid #23252F; transition: background 120ms; }
			.am-row:hover { background: #23252F; }
			.am-caret { color: #5B5D68; font-size: 10px; width: 10px; }
			.am-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
			.am-title { font-size: 13px; font-weight: 500; flex: 0 0 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
			.am-id { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #6C6E79; flex: 0 0 160px; overflow: hidden; text-overflow: ellipsis; }
			.am-badge { font-size: 10px; text-transform: uppercase; letter-spacing: 0.4px; color: #8B8D98; background: #23252F; padding: 2px 7px; border-radius: 4px; flex: 0 0 auto; }
			.am-badge-skill { color: #5B8DEF; }
			.am-meta { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #8B8D98; flex: 0 0 auto; margin-left: auto; }
			.am-children { background: #16171F; }
			.am-child-row { padding-left: 34px; position: relative; }
			.am-thread { position: absolute; left: 18px; top: 0; bottom: 0; width: 1px; background: #2A2C36; }
			.am-table { width: 100%; border-collapse: collapse; }
			.am-table th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px; color: #6C6E79; padding: 10px 14px; border-bottom: 1px solid #2A2C36; }
			.am-table td { padding: 12px 14px; font-size: 13px; border-bottom: 1px solid #23252F; }
			.am-wf-row { cursor: pointer; transition: background 120ms; }
			.am-wf-row:hover { background: #23252F; }
			.am-desc { color: #8B8D98; font-size: 12px; }
			.am-drawer { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; justify-content: flex-end; z-index: 999; }
			.am-drawer-panel { width: 380px; background: #1C1E26; border-left: 1px solid #2A2C36; height: 100%; padding: 20px; }
			.am-drawer-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
			.am-close { background: none; border: none; color: #8B8D98; font-size: 20px; cursor: pointer; }
			.am-kv { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #23252F; font-size: 13px; }
			.am-kv span { color: #8B8D98; }
			.am-open-link { display: block; margin-top: 18px; color: #5B8DEF; font-size: 13px; text-decoration: none; }
		`;
		document.head.appendChild(style);
	}
}