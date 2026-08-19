// agent_builder/agent_builder/page/agent_builder/agent_builder.js

frappe.pages['agent-builder'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Agent Control Center',
        single_column: true,
    });
    frappe.agent_management = new AgentManagement(page);
};

frappe.pages['agent-builder'].on_page_show = function (wrapper) {
    if (frappe.agent_management) {
        if (!frappe.agent_management.isDomAttached()) {
            // Frappe v15 cleared the DOM to save memory. Rebuild it.
            frappe.agent_management.setupDom();
        } else {
            // The DOM is intact, just refresh the data to keep it up to date
            frappe.agent_management.load();
        }
    }
};

const MODULE_PATH = 'agent_builder.agent_builder.page.agent_builder.agent_builder';

class AgentManagement {
    constructor(page) {
        this.page = page;
        this.setupDom();
    }

    setupDom() {
        // Clear out any existing root to prevent duplicates if called twice
        if (this.$root) this.$root.remove();

        this.state = { 
            tab: 'workflows', 
            workflows: [], 
            agents: [], 
            triggers: [],
            skills: []
        };

        this.$root = $('<div class="am-root"></div>').appendTo(this.page.main);
        this.injectStyles();
        this.renderShell();
        this.load();
    }

    isDomAttached() {
        return this.$root && $.contains(document, this.$root[0]);
    }

    async load() {
        if (!this.$body || !this.isDomAttached()) return;

        this.$body.html(`
            <div class="am-loading">
                <i class="fa fa-circle-o-notch fa-spin fa-2x"></i>
                <p>Loading automation hub…</p>
            </div>
        `);

        const [workflowsRes, agentsRes, triggersRes, skillsRes, toolGroupsRes] = await Promise.all([
            frappe.call(`${MODULE_PATH}.get_workflows`),
            frappe.call(`${MODULE_PATH}.get_agent_skills`),
            frappe.call(`${MODULE_PATH}.get_triggers`),
            frappe.db.get_list('Skill', {
                filters: { is_agent: 0 },
                fields: ['name', 'name_', 'description', 'is_enabled', 'modified'],
                limit: 100
            }),
            frappe.call(`${MODULE_PATH}.get_tool_groups`)
        ]);

        this.state.workflows = workflowsRes.message || [];
        this.state.agents = agentsRes.message || [];
        this.state.triggers = triggersRes.message || [];
        this.state.skills = skillsRes || [];
        this.state.toolGroups = toolGroupsRes.message || [];
        
        this.renderBody();
    }

    renderShell() {
        const $tabs = $(`
            <div class="am-header">
                <div class="am-tab-group">
                    <button class="am-tab am-tab-active" data-tab="workflows">
                        <i class="fa fa-sitemap"></i> Workflows
                    </button>
                    <button class="am-tab" data-tab="agents">
                        <i class="fa fa-user-secret"></i> Agents
                    </button>
                    <button class="am-tab" data-tab="skills">
                        <i class="fa fa-puzzle-piece"></i> Skills
                    </button>
                    <button class="am-tab" data-tab="triggers">
                        <i class="fa fa-bolt"></i> Triggers
                    </button>
                    <button class="am-tab" data-tab="tools">
                        <i class="fa fa-wrench"></i> Tools
                    </button>
                </div>
                <div class="am-header-actions">
                    <button class="btn btn-sm btn-primary am-new-btn" data-type="workflow">
                        <i class="fa fa-plus"></i> New Workflow
                    </button>
                </div>
            </div>
        `).appendTo(this.$root);

        $tabs.on('click', '.am-tab', (e) => {
            const tab = $(e.currentTarget).data('tab');
            this.state.tab = tab;
            $tabs.find('.am-tab').removeClass('am-tab-active');
            $(e.currentTarget).addClass('am-tab-active');
            
            const $btn = $tabs.find('.am-new-btn');
            if (tab === 'agents') {
                $btn.html('<i class="fa fa-plus"></i> New Agent').data('type', 'agent');
                $btn.show();
            } else if (tab === 'workflows') {
                $btn.html('<i class="fa fa-plus"></i> New Workflow').data('type', 'workflow');
                $btn.show();
            } else if (tab === 'skills') {
                $btn.html('<i class="fa fa-plus"></i> New Skill').data('type', 'skill');
                $btn.show();
            } else if (tab === 'tools') {
                // Tools are synced from disk, not hand-created — no "New" action.
                $btn.hide();
            } else {
                $btn.html('<i class="fa fa-plus"></i> New Trigger').data('type', 'trigger');
                $btn.show();
            }

            this.renderBody();
        });

        $tabs.on('click', '.am-new-btn', (e) => {
            const type = $(e.currentTarget).data('type');
            if (type === 'workflow') this.createWorkflow();
            else if (type === 'agent') this.createAgent();
            else if (type === 'skill') this.createSkill();
            else if (type === 'trigger') this.createTrigger();
        });

        this.$tabs = $tabs;
        this.$body = $('<div class="am-body"></div>').appendTo(this.$root);
    }

    renderBody() {
        this.$body.empty();
        if (this.state.tab === 'workflows') this.renderWorkflows();
        else if (this.state.tab === 'agents') this.renderAgents();
        else if (this.state.tab === 'skills') this.renderSkills();
        else if (this.state.tab === 'triggers') this.renderTriggers();
        else if (this.state.tab === 'tools') this.renderTools();
    }

    // --- WORKFLOWS ---
    renderWorkflows() {
        const { workflows } = this.state;
        if (!workflows.length) {
            this.$body.html(this.getEmptyState('workflow', 'Create your first workflow to automate tasks.'));
            return;
        }

        const $grid = $('<div class="am-card-grid"></div>').appendTo(this.$body);
        
        workflows.forEach((w) => {
            const statusColor = w.is_enabled ? 'green' : 'gray';
            const statusText = w.is_enabled ? 'Active' : 'Disabled';
            
            const $card = $(`
                <div class="am-card" data-id="${w.name}">
                    <div class="am-card-head">
                        <div class="am-card-icon"><i class="fa fa-sitemap"></i></div>
                        <div class="am-card-info">
                            <div class="am-card-title">${frappe.utils.escape_html(w.workflow_name)}</div>
                            <span class="indicator-pill ${statusColor} am-card-status">${statusText}</span>
                        </div>
                        <div class="am-card-menu">
                            <button class="btn btn-xs btn-default" data-action="toggle" title="${w.is_enabled ? 'Disable' : 'Enable'}">
                                <i class="fa fa-${w.is_enabled ? 'pause' : 'play'}"></i>
                            </button>
                        </div>
                    </div>
                    <div class="am-card-body">
                        ${frappe.utils.escape_html(w.description || 'No description provided')}
                    </div>
                    <div class="am-card-foot">
                        <span class="am-stat"><i class="fa fa-cubes"></i> ${w.step_count || 0} Steps</span>
                        <span class="am-stat"><i class="fa fa-clock-o"></i> ${frappe.datetime.comment_when(w.modified)}</span>
                    </div>
                    <div class="am-card-actions">
                        <button class="btn btn-sm btn-primary btn-block" data-action="run">
                            <i class="fa fa-flash"></i> Run Now
                        </button>
                        <button class="btn btn-sm btn-default" data-action="edit" title="Edit Workflow">
                            <i class="fa fa-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-default" data-action="trigger" title="Add Trigger">
                            <i class="fa fa-bolt"></i>
                        </button>
                    </div>
                </div>
            `).appendTo($grid);

            $card.on('click', '[data-action]', (e) => {
                e.stopPropagation();
                const action = $(e.currentTarget).data('action');
                if (action === 'edit') frappe.set_route('workflow-builder-1', w.name);
                else if (action === 'run') this.runWorkflow(w);
                else if (action === 'toggle') this.toggleWorkflow(w);
                else if (action === 'trigger') this.createTrigger(w.name);
            });
        });
    }

    // --- AGENTS ---
    renderAgents() {
        const { agents } = this.state;
        if (!agents.length) {
            this.$body.html(this.getEmptyState('agent', 'Create specialized agents with custom tools.'));
            return;
        }

        const $grid = $('<div class="am-card-grid"></div>').appendTo(this.$body);
        agents.forEach((a) => {
            
            const $card = $(`
                <div class="am-card" data-id="${a.name}">
                    <div class="am-card-head">
                        <div class="am-card-icon am-icon-agent"><i class="fa fa-user-secret"></i></div>
                        <div class="am-card-info">
                            <div class="am-card-title">${frappe.utils.escape_html(a.name_ ?? a.name)}</div>
                        </div>
                    </div>
                    <div class="am-card-body">
                        ${frappe.utils.escape_html(a.description || 'No description provided')}
                    </div>
                    <div class="am-card-actions">
                         <button class="btn btn-sm btn-default btn-block" data-action="edit_agent" title="Edit Agent">
                            <i class="fa fa-pencil"></i> Edit Prompt
                        </button>
                        
                    </div>
                </div>
            `).appendTo($grid);

            $card.on('click', '[data-action]', (e) => {
                e.stopPropagation();
                const action = $(e.currentTarget).data('action');
                if (action === 'chat') frappe.set_route('agent-chat', a.name); 
                else if (action === 'edit_agent') this.openSkillDialog(true, a);
            });
        });
    }

    // --- SKILLS ---
    renderSkills() {
        const { skills } = this.state;
        if (!skills.length) {
            this.$body.html(this.getEmptyState('skill', 'Create reusable skills and tools that your agents can utilize.'));
            return;
        }

        const $grid = $('<div class="am-card-grid"></div>').appendTo(this.$body);

        skills.forEach((s) => {
            const statusColor = s.is_enabled ? 'green' : 'gray';
            const statusText = s.is_enabled ? 'Active' : 'Disabled';

            const $card = $(`
                <div class="am-card" data-id="${s.name}">
                    <div class="am-card-head">
                        <div class="am-card-icon am-icon-skill"><i class="fa fa-puzzle-piece"></i></div>
                        <div class="am-card-info">
                            <div class="am-card-title">${frappe.utils.escape_html(s.name_)}</div>
                            <span class="indicator-pill ${statusColor} am-card-status">${statusText}</span>
                        </div>
                        <div class="am-card-menu">
                            <button class="btn btn-xs btn-default" data-action="toggle_skill" title="${s.is_enabled ? 'Disable' : 'Enable'}">
                                <i class="fa fa-${s.is_enabled ? 'pause' : 'play'}"></i>
                            </button>
                        </div>
                    </div>
                    <div class="am-card-body">
                        ${frappe.utils.escape_html(s.description || 'No description provided')}
                    </div>
                    <div class="am-card-foot">
                        <span class="am-stat"><i class="fa fa-cube"></i> Tool</span>
                        <span class="am-stat"><i class="fa fa-clock-o"></i> ${frappe.datetime.comment_when(s.modified)}</span>
                    </div>
                    <div class="am-card-actions">
                        <button class="btn btn-sm btn-default btn-block" data-action="edit_skill">
                            <i class="fa fa-pencil"></i> Edit Skill
                        </button>
                    </div>
                </div>
            `).appendTo($grid);

            $card.on('click', '[data-action]', (e) => {
                e.stopPropagation();
                const action = $(e.currentTarget).data('action');
                if (action === 'edit_skill') this.openSkillDialog(false, s);
                else if (action === 'toggle_skill') this.toggleSkill(s);
            });
        });
    }

    // --- TOOLS ---
    // Global on/off switches, grouped the same way tools/ is grouped on
    // disk. This is separate from an individual Agent Definition's own
    // allow/block list — a tool disabled here is hidden from every agent.
    renderTools() {
        const { toolGroups } = this.state;

        const $wrap = $('<div class="am-tools-wrap"></div>').appendTo(this.$body);

        const $toolbar = $(`
            <div class="am-tools-toolbar">
                <div class="am-tools-search">
                    <i class="fa fa-search"></i>
                    <input type="text" class="form-control input-sm am-tools-filter" placeholder="Filter tools…">
                </div>
                <button class="btn btn-xs btn-default am-tools-sync">
                    <i class="fa fa-refresh"></i> Sync Tools
                </button>
            </div>
        `).appendTo($wrap);

        $wrap.find('.am-tools-sync').on('click', async (e) => {
            const $btn = $(e.currentTarget);
            $btn.prop('disabled', true).html('<i class="fa fa-circle-o-notch fa-spin"></i> Syncing…');
            try {
                await frappe.call(`${MODULE_PATH}.resync_tools`);
                await this.load();
                frappe.show_alert({ message: 'Tools synced', indicator: 'green' });
            } finally {
                $btn.prop('disabled', false).html('<i class="fa fa-refresh"></i> Sync Tools');
            }
        });

        if (!toolGroups || !toolGroups.length) {
            $('<div></div>').appendTo($wrap).html(
                this.getEmptyState('tool', 'No tools have been synced yet. Click "Sync Tools" above.')
            );
            return;
        }

        const $list = $('<div class="am-tools-list"></div>').appendTo($wrap);

        const orphanedGroups = toolGroups.filter(g => g.is_orphaned);
        const orphanedTools = toolGroups.flatMap(g => (g.tools || []).filter(t => t.is_orphaned));
        if (orphanedGroups.length || orphanedTools.length) {
            $(`
                <div class="am-tools-orphan-banner">
                    <i class="fa fa-exclamation-triangle"></i>
                    ${orphanedGroups.length} group(s) and ${orphanedTools.length} tool(s) no longer found on disk.
                    <a href="#" class="am-clean-orphans">Clean up</a>
                </div>
            `).appendTo($wrap).on('click', '.am-clean-orphans', async (e) => {
                e.preventDefault();
                await frappe.call(`${MODULE_PATH}.delete_orphaned_tools`, { doctype: 'Agent Tool' });
                await frappe.call(`${MODULE_PATH}.delete_orphaned_tools`, { doctype: 'Tool Group' });
                this.load();
            });
        }

        toolGroups.forEach((g) => {
            const tools = g.tools || [];
            const enabledCount = tools.filter(t => t.is_enabled).length;
            const $group = $(`
                <div class="am-tool-group ${g.is_orphaned ? 'am-orphaned' : ''}" data-group="${frappe.utils.escape_html(g.group_name)}">
                    <div class="am-tool-group-head">
                        <i class="fa fa-chevron-down am-tool-collapse"></i>
                        <span class="am-tool-group-name">${frappe.utils.escape_html(g.group_name)}</span>
                        ${g.is_orphaned ? '<span class="indicator-pill gray">not on disk</span>' : ''}
                        <span class="am-tool-group-count">${enabledCount}/${tools.length} enabled</span>
                        <label class="am-toggle am-tool-group-toggle" title="${g.is_enabled ? 'Disable whole group' : 'Enable whole group'}">
                            <input type="checkbox" ${g.is_enabled ? 'checked' : ''}>
                            <span class="am-toggle-slider"></span>
                        </label>
                    </div>
                    <div class="am-tool-group-body"></div>
                </div>
            `).appendTo($list);

            const $body = $group.find('.am-tool-group-body');
            tools.forEach((t) => {
                $(`
                    <div class="am-tool-row ${t.is_orphaned ? 'am-orphaned' : ''}" data-tool="${frappe.utils.escape_html(t.tool_name)}">
                        <div class="am-tool-row-info">
                            <span class="am-tool-name">${frappe.utils.escape_html(t.tool_name)}</span>
                            ${t.is_orphaned ? '<span class="indicator-pill gray">not loaded</span>' : ''}
                            <span class="am-tool-desc">${frappe.utils.escape_html(t.description || 'No description')}</span>
                        </div>
                        <label class="am-toggle am-tool-toggle">
                            <input type="checkbox" ${t.is_enabled ? 'checked' : ''} ${!g.is_enabled ? 'disabled' : ''}>
                            <span class="am-toggle-slider"></span>
                        </label>
                    </div>
                `).appendTo($body);
            });

            $group.on('click', '.am-tool-group-head', (e) => {
                if ($(e.target).closest('.am-tool-group-toggle').length) return;
                $group.toggleClass('am-tool-group-collapsed');
            });

            $group.on('change', '.am-tool-group-toggle input', async (e) => {
                const checked = e.target.checked;
                await frappe.call(`${MODULE_PATH}.set_tool_group_enabled`, {
                    group_name: g.group_name, is_enabled: checked ? 1 : 0
                });
                this.load();
            });

            $group.on('change', '.am-tool-toggle input', async (e) => {
                const $row = $(e.target).closest('.am-tool-row');
                const toolName = $row.data('tool');
                const checked = e.target.checked;
                await frappe.call(`${MODULE_PATH}.set_tool_enabled`, {
                    tool_name: toolName, is_enabled: checked ? 1 : 0
                });
                this.load();
            });
        });

        $wrap.find('.am-tools-filter').on('input', (e) => {
            const q = e.target.value.trim().toLowerCase();
            $list.find('.am-tool-row').each(function () {
                const name = $(this).data('tool').toLowerCase();
                $(this).toggle(!q || name.includes(q));
            });
            $list.find('.am-tool-group').each(function () {
                const anyVisible = $(this).find('.am-tool-row:visible').length > 0;
                $(this).toggle(!q || anyVisible);
                if (q && anyVisible) $(this).removeClass('am-tool-group-collapsed');
            });
        });
    }

    // --- TRIGGERS ---
    renderTriggers() {
        const { triggers } = this.state;
        if (!triggers.length) {
            this.$body.html(this.getEmptyState('trigger', 'Automate workflows on Doctype events or schedules.'));
            return;
        }

        const $grid = $('<div class="am-card-grid"></div>').appendTo(this.$body);

        triggers.forEach((t) => {
            const icon = t.trigger_type === 'DocType Event' ? 'fa-file-text-o' : (t.trigger_type === 'Scheduled' ? 'fa-clock-o' : 'fa-webhook');
            const scheduleDetail = t.event_frequency === 'Cron' ? t.cron_expression : t.event_frequency;
            const detail = t.trigger_type === 'DocType Event' ? `${t.doctype_name} (${t.doctype_event})` : (t.trigger_type === 'Scheduled' ? scheduleDetail : 'Webhook');
            const target = t.workflow_name || t.agent_name || '';

            const $card = $(`
                <div class="am-card" data-id="${target}">
                    <div class="am-card-head">
                        <div class="am-card-icon am-icon-trigger"><i class="fa ${icon}"></i></div>
                        <div class="am-card-info">
                            <div class="am-card-title">${frappe.utils.escape_html(t.trigger_name)}</div>
                            <span class="indicator-pill ${t.is_enabled ? 'green' : 'gray'} am-card-status">${t.trigger_type}</span>
                        </div>
                    </div>
                    <div class="am-card-body am-trigger-detail">
                        <code>${frappe.utils.escape_html(detail || '')}</code>
                    </div>
                    <div class="am-card-actions">
                        <button class="btn btn-sm btn-default" data-action="edit_trigger" title="Edit">
                            <i class="fa fa-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-default btn-block" data-action="toggle_trigger">
                            ${t.is_enabled ? 'Disable' : 'Enable'}
                        </button>
                        <button class="btn btn-sm btn-default" data-action="delete_trigger" title="Delete">
                            <i class="fa fa-trash"></i>
                        </button>
                    </div>
                </div>
            `).appendTo($grid);

            $card.on('click', '[data-action]', (e) => {
                e.stopPropagation();
                const action = $(e.currentTarget).data('action');
                if (action === 'edit_trigger') this.createTrigger(null, t);
                else if (action === 'toggle_trigger') this.toggleTrigger(t);
                else if (action === 'delete_trigger') this.deleteTrigger(t);
            });
        });
    }

    // --- ACTIONS ---
    createWorkflow() {
        frappe.prompt(
            [
                { fieldname: 'workflow_name', label: 'Workflow Name', fieldtype: 'Data', reqd: 1 },
                { fieldname: 'description', label: 'Description', fieldtype: 'Small Text' },
            ],
            async (values) => {
                const res = await frappe.call(`${MODULE_PATH}.create_workflow`, {
                    workflow_name: values.workflow_name,
                    description: values.description,
                });
                if (res.message && res.message.name) {
                    frappe.set_route('workflow-builder-1', res.message.name);
                }
            },
            'New Workflow',
            'Create & Open'
        );
    }

    createAgent() {
        this.openSkillDialog(true);
    }

    createSkill() {
        this.openSkillDialog(false);
    }

    // Shared create/edit dialog for both Agents and Skills — an Agent is just
    // a Skill with is_agent=1 and disable_model_invocation=1. Only exposes
    // Name, Description, and Content; every other field is filled in via the
    // payload defaults below.
    async openSkillDialog(isAgent, existing = null) {
        const isEdit = !!existing;
        let doc = {};
        if (isEdit) {
            doc = await frappe.db.get_doc('Skill', existing.name);
        }

        const fields = [
            { fieldname: 'name_', label: 'Name', fieldtype: 'Data', reqd: 1, default: doc.name_ || doc.name, read_only: isEdit ? 1 : 0 },
            { fieldname: 'description', label: 'Description', fieldtype: 'Data', reqd: 1, default: doc.description },
            { fieldname: 'content', label: 'Content', fieldtype: 'Markdown Editor', default: doc.content },
        ];

        const typeLabel = isAgent ? 'Agent' : 'Skill';

        frappe.prompt(
            fields,
            async (values) => {
                try {
                    if (isEdit) {
                        await frappe.db.set_value('Skill', existing.name, {
                            description: values.description,
                            content: values.content
                        });
                        frappe.show_alert({ message: `${typeLabel} updated`, indicator: 'green' });
                    } else {
                        const payload = {
                            doctype: 'Skill',
                            name_: values.name_,
                            description: values.description,
                            content: values.content,
                            is_enabled: 1,
                            is_agent: isAgent ? 1 : 0
                        };
                        if (isAgent) {
                            payload.disable_model_invocation = 1;
                            payload.domain = 'Other';
                        }
                        await frappe.db.insert(payload);
                        frappe.show_alert({ message: `${typeLabel} created`, indicator: 'green' });
                    }
                    this.load();
                } catch (err) {
                    // Error is already shown via frappe.throw
                }
            },
            isEdit ? `Edit ${typeLabel}` : `New ${typeLabel}`,
            isEdit ? 'Save' : 'Create'
        );
    }

    async toggleSkill(s) {
        const enabled = s.is_enabled ? 0 : 1;
        await frappe.db.set_value('Skill', s.name, 'is_enabled', enabled);
        s.is_enabled = enabled;
        this.renderBody();
        frappe.show_alert(`Skill ${enabled ? 'enabled' : 'disabled'}`);
    }

    createTrigger(prefilledWorkflow = null, existingTrigger = null) {
        const isEdit = !!existingTrigger;
        const t = existingTrigger || {};
        const targetType = t.agent_name ? 'Agent' : 'Workflow';

        let fields = [
            { fieldname: 'trigger_name', label: 'Trigger Name', fieldtype: 'Data', reqd: 1, default: t.trigger_name, read_only: isEdit ? 1 : 0 },
            { fieldname: 'target_type', label: 'Runs', fieldtype: 'Select', options: 'Workflow\nAgent', reqd: 1, default: targetType },
            { fieldname: 'workflow_name', label: 'Workflow', fieldtype: 'Link', options: 'Agent Workflow', default: t.workflow_name || prefilledWorkflow, depends_on: "eval:doc.target_type=='Workflow'", mandatory_depends_on: "eval:doc.target_type=='Workflow'" },
            { fieldname: 'agent_name', label: 'Agent', fieldtype: 'Link', options: 'Skill', default: t.agent_name, depends_on: "eval:doc.target_type=='Agent'", mandatory_depends_on: "eval:doc.target_type=='Agent'",
            get_query: () => ({
                filters: { is_agent: 1, is_enabled: 1 }
            })
            },
            { fieldname: 'trigger_type', label: 'Trigger Type', fieldtype: 'Select', options: '\nDocType Event\nScheduled\nWebhook', reqd: 1, default: t.trigger_type },
            { fieldname: 'doctype_name', label: 'Target Doctype', fieldtype: 'Link', options: 'DocType', default: t.doctype_name, depends_on: "eval:doc.trigger_type=='DocType Event'" },
            { fieldname: 'doctype_event', label: 'Doc Event', fieldtype: 'Select', options: 'before_insert\nafter_insert\nbefore_save\non_update\nbefore_submit\non_submit\nbefore_cancel\non_cancel\non_update_after_submit\non_trash\nafter_delete\non_change', default: t.doctype_event, depends_on: "eval:doc.trigger_type=='DocType Event'" },
            { fieldname: 'event_frequency', label: 'Event Frequency', fieldtype: 'Select', options: 'Hourly\nDaily\nWeekly\nMonthly\nYearly\nHourly Long\nDaily Long\nWeekly Long\nMonthly Long\nCron', default: t.event_frequency || 'Daily', depends_on: "eval:doc.trigger_type=='Scheduled'", mandatory_depends_on: "eval:doc.trigger_type=='Scheduled'" },
            { fieldname: 'cron_expression', label: 'Cron Expression', fieldtype: 'Data', description: 'e.g., 0 * * * * (Every hour)', default: t.cron_expression, depends_on: "eval:doc.trigger_type=='Scheduled' && doc.event_frequency=='Cron'" },
            { fieldname: 'input_template', label: 'Input Template', fieldtype: 'Code', options: 'Jinja', default: t.input_template, description: "Becomes the agent's first message. Use {{ doc.field }} or {{ doc }} to reference the trigger context.", depends_on: "eval:doc.target_type=='Agent'", mandatory_depends_on: "eval:doc.target_type=='Agent'" }
        ];

        frappe.prompt(
            fields,
            async (values) => {
                const endpoint = isEdit ? 'update_trigger' : 'create_trigger';
                const args = isEdit ? { trigger_name: t.trigger_name, trigger_data: values } : { trigger_data: values };
                const res = await frappe.call(`${MODULE_PATH}.${endpoint}`, args);
                if (res.message && res.message.webhook_token) {
                    frappe.msgprint(`Webhook token: <code>${res.message.webhook_token}</code>`);
                }
                frappe.show_alert(isEdit ? 'Trigger updated' : 'Trigger created');
                this.load();
            },
            isEdit ? 'Edit Trigger' : 'Configure Trigger',
            'Save'
        );
    }

    async runWorkflow(w) {
        frappe.prompt(
            [
                { 
                    fieldname: 'input_data', 
                    label: 'Input Data (JSON)', 
                    fieldtype: 'Code', 
                    options: 'JSON',
                    default: '{}',
                    reqd: 1 
                }
            ],
            async (values) => {
                frappe.show_alert({ message: `Executing ${w.workflow_name}...`, indicator: 'blue' });
                
                try {
                    const res = await frappe.call({
                        method: `${MODULE_PATH}.execute_workflow`,
                        args: {
                            workflow_name: w.name,
                            input_data: values.input_data
                        },
                        freeze: true,
                        freeze_message: `Running ${w.workflow_name}...`
                    });

                    if (res.message && res.message.success) {
                        frappe.msgprint({
                            title: `Workflow Result: ${w.workflow_name}`,
                            message: `<pre style="max-height:400px;overflow-y:auto;background:var(--control-bg,#f8f8f8);color:var(--text-color,#333);border:1px solid var(--border-color,#ddd);padding:12px;border-radius:6px;font-size:12px;line-height:1.5;">${frappe.utils.escape_html(JSON.stringify(res.message.result, null, 2))}</pre>`,
                            indicator: 'green'
                        });
                    }
                } catch (err) {
                    // Error is already shown via frappe.throw
                }
            },
            `Run: ${w.workflow_name}`,
            'Execute'
        );
    }

    async toggleWorkflow(w) {
        const enabled = w.is_enabled ? 0 : 1;

        await frappe.call(`${MODULE_PATH}.toggle_workflow`, {
            workflow_name: w.name,
            enabled
        });

        w.is_enabled = enabled;
        this.renderBody();
    }

    async toggleTrigger(t) {
        await frappe.call(`${MODULE_PATH}.toggle_trigger`, {
            trigger_name: t.trigger_name,
            enabled: !t.is_enabled
        });
        t.is_enabled = !t.is_enabled;
        this.renderBody();
    }

    async deleteTrigger(t) {
        frappe.confirm(`Are you sure you want to delete this trigger?`, async () => {
            await frappe.call(`${MODULE_PATH}.delete_trigger`, { trigger_name: t.trigger_name });
            this.load();
        });
    }

    getEmptyState(type, message) {
        const icon = type === 'workflow' ? 'fa-sitemap' : (type === 'agent' ? 'fa-user-secret' : (type === 'skill' ? 'fa-puzzle-piece' : 'fa-bolt'));
        return `
            <div class="am-empty-state">
                <div class="am-empty-icon"><i class="fa ${icon}"></i></div>
                <h4>No ${type}s found</h4>
                <p>${message}</p>
            </div>
        `;
    }

    injectStyles() {
        if (document.getElementById('am-styles')) return;
        const style = document.createElement('style');
        style.id = 'am-styles';
        style.textContent = `
            /* ── Root container ── */
            .am-root { 
                padding-bottom: 48px; 
            }

            /* ── Header ── */
            .am-header { 
                display: flex; 
                align-items: center; 
                justify-content: space-between; 
                padding: 20px 24px 12px; 
                border-bottom: 1px solid var(--border-color); 
            }
            .am-tab-group { 
                display: flex; 
                gap: 4px; 
            }
            .am-tab { 
                background: transparent; 
                border: none; 
                color: var(--text-muted); 
                font-size: 13px; 
                font-weight: 500; 
                padding: 8px 14px; 
                cursor: pointer; 
                border-radius: 6px; 
                transition: all 150ms ease; 
                display: inline-flex; 
                align-items: center; 
                gap: 8px; 
            }
            .am-tab:hover { 
                background: var(--control-bg); 
                color: var(--text-color); 
            }
            .am-tab.am-tab-active { 
                color: var(--primary); 
                font-weight: 600; 
                background: #6f6f6f; 
            }
            .am-tab i { 
                font-size: 13px; 
            }

            /* ── Body ── */
            .am-body { 
                padding: 24px 24px 0; 
                min-height: 400px; 
            }

            /* ── Loading ── */
            .am-loading { 
                text-align: center; 
                padding: 80px 20px; 
                color: var(--text-muted); 
            }
            .am-loading i { 
                display: block; 
                margin-bottom: 16px; 
                color: var(--primary); 
            }
            .am-loading p { 
                font-size: 13px; 
            }

            /* ── Card grid ── */
            .am-card-grid { 
                display: grid; 
                grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); 
                gap: 16px; 
            }

            /* ── Cards ── */
            .am-card { 
                background: var(--fg-color); 
                border: 1px solid var(--border-color); 
                border-radius: 10px; 
                transition: box-shadow 150ms ease, border-color 150ms ease;
                display: flex; 
                flex-direction: column; 
                overflow: hidden;
            }
            .am-card:hover { 
                box-shadow: 0 4px 16px rgba(0,0,0,0.1); 
                border-color: var(--primary);
            }
            
            /* ── Card head ── */
            .am-card-head { 
                display: flex; 
                align-items: flex-start; 
                gap: 12px; 
                padding: 16px 16px 0; 
            }
            .am-card-icon { 
                width: 40px; 
                height: 40px; 
                border-radius: 10px; 
                background: var(--control-bg); 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                color: var(--text-muted); 
                font-size: 16px; 
                flex-shrink: 0; 
            }
            .am-icon-agent { 
                color: var(--blue-500, #2490ef); 
                background: var(--control-bg); 
            }
            .am-icon-skill { 
                color: var(--purple-500, #a837d8); 
                background: var(--control-bg); 
            }
            .am-icon-trigger { 
                color: var(--orange-500, #ff8b3b); 
                background: var(--control-bg); 
            }
            
            .am-card-info { 
                flex: 1; 
                min-width: 0; 
            }
            .am-card-title { 
                font-size: 14px; 
                font-weight: 600; 
                color: var(--text-color); 
                margin-bottom: 4px; 
                white-space: nowrap; 
                overflow: hidden; 
                text-overflow: ellipsis; 
            }
            .am-card-status { 
                font-size: 10px; 
                padding: 3px 8px; 
            }

            /* ── Card body ── */
            .am-card-body { 
                padding: 12px 16px; 
                font-size: 12px; 
                color: var(--text-muted); 
                line-height: 1.5; 
                flex: 1; 
                min-height: 45px; 
            }
            .am-trigger-detail code { 
                background: var(--control-bg); 
                color: var(--text-color); 
                padding: 4px 8px; 
                border-radius: 4px; 
                font-size: 11px; 
            }

            /* ── Card foot ── */
            .am-card-foot { 
                padding: 8px 16px 12px; 
                display: flex; 
                justify-content: space-between; 
            }
            .am-stat { 
                font-size: 11px; 
                color: var(--text-muted); 
                display: flex; 
                align-items: center; 
                gap: 4px; 
            }

            /* ── Card actions ── */
            .am-card-actions { 
                display: flex; 
                gap: 8px; 
                padding: 12px 16px; 
                border-top: 1px solid var(--border-color); 
            }
            .am-card-actions .btn-block { 
                flex: 1; 
            }

            /* ── Empty state ── */
            .am-empty-state { 
                text-align: center; 
                padding: 80px 20px; 
                color: var(--text-muted); 
            }
            .am-empty-icon { 
                font-size: 48px; 
                margin-bottom: 16px; 
                opacity: 0.3; 
            }
            .am-empty-state h4 { 
                font-size: 16px; 
                color: var(--text-color); 
                margin-bottom: 8px; 
            }
            .am-empty-state p { 
                font-size: 13px; 
            }

            /* ── Responsive ── */
            @media (max-width: 768px) {
                .am-header, .am-body {
                    padding-left: 16px;
                    padding-right: 16px;
                }
            }

            /* ── Tools tab ── */
            .am-tools-wrap { max-width: 900px; }
            .am-tools-toolbar {
                display: flex; align-items: center; justify-content: space-between;
                gap: 12px; margin-bottom: 14px;
            }
            .am-tools-search { position: relative; flex: 1; max-width: 320px; }
            .am-tools-search i {
                position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
                color: var(--text-muted); font-size: 12px;
            }
            .am-tools-filter { padding-left: 28px; }
            .am-tools-orphan-banner {
                background: rgba(255, 176, 32, 0.12); border: 1px solid rgba(255, 176, 32, 0.35);
                border-radius: 6px; padding: 8px 12px; font-size: 12px; margin-bottom: 14px;
                color: var(--text-color);
            }
            .am-tools-orphan-banner i { color: #e0a800; margin-right: 6px; }
            .am-clean-orphans { margin-left: 6px; font-weight: 600; }
            .am-tool-group {
                border: 1px solid var(--border-color); border-radius: 8px;
                margin-bottom: 10px; overflow: hidden; background: var(--card-bg, transparent);
            }
            .am-tool-group.am-orphaned { opacity: 0.55; }
            .am-tool-group-head {
                display: flex; align-items: center; gap: 10px; padding: 10px 14px;
                cursor: pointer; user-select: none;
            }
            .am-tool-collapse { transition: transform 150ms ease; color: var(--text-muted); font-size: 12px; }
            .am-tool-group-collapsed .am-tool-collapse { transform: rotate(-90deg); }
            .am-tool-group-collapsed .am-tool-group-body { display: none; }
            .am-tool-group-name { font-weight: 600; font-size: 13px; }
            .am-tool-group-count { margin-left: auto; font-size: 11px; color: var(--text-muted); }
            .am-tool-group-body { border-top: 1px solid var(--border-color); }
            .am-tool-row {
                display: flex; align-items: center; justify-content: space-between;
                gap: 10px; padding: 8px 14px 8px 32px;
                border-top: 1px solid var(--border-color);
            }
            .am-tool-row:first-child { border-top: none; }
            .am-tool-row.am-orphaned { opacity: 0.55; }
            .am-tool-row-info { display: flex; align-items: center; gap: 8px; min-width: 0; }
            .am-tool-name { font-size: 12px; font-weight: 500; font-family: var(--font-mono, monospace); flex-shrink: 0; }
            .am-tool-desc {
                font-size: 12px; color: var(--text-muted); overflow: hidden;
                text-overflow: ellipsis; white-space: nowrap;
            }
            .am-toggle { position: relative; display: inline-block; width: 34px; height: 18px; flex-shrink: 0; }
            .am-toggle input { opacity: 0; width: 0; height: 0; }
            .am-toggle-slider {
                position: absolute; cursor: pointer; inset: 0; background: #ccc;
                border-radius: 18px; transition: 150ms ease;
            }
            .am-toggle-slider::before {
                content: ""; position: absolute; height: 14px; width: 14px; left: 2px; top: 2px;
                background: white; border-radius: 50%; transition: 150ms ease;
            }
            .am-toggle input:checked + .am-toggle-slider { background: var(--primary); }
            .am-toggle input:checked + .am-toggle-slider::before { transform: translateX(16px); }
            .am-toggle input:disabled + .am-toggle-slider { opacity: 0.4; cursor: not-allowed; }
        `;
        document.head.appendChild(style);
    }
}