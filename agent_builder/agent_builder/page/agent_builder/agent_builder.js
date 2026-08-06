// agent_builder/agent_builder/page/agent_builder/agent_builder.js
frappe.pages['agent-builder'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Agent Control Center',
        single_column: true,
    });
    new AgentManagement(page);
};

const MODULE_PATH = 'agent_builder.agent_builder.page.agent_builder.agent_builder';

class AgentManagement {
    constructor(page) {
        this.page = page;
        this.state = { 
            tab: 'workflows', 
            workflows: [], 
            agents: [], 
            triggers: [],
            skills: []
        };

        this.$root = $('<div class="am-root"></div>').appendTo(page.main);
        this.injectStyles();
        this.renderShell();
        this.load();
    }

    async load() {
        this.$body.html(`
            <div class="am-loading">
                <i class="fa fa-circle-o-notch fa-spin fa-2x"></i>
                <p>Loading automation hub…</p>
            </div>
        `);

        // Using frappe.db.get_list for skills so no Python backend changes are required
        const [workflowsRes, agentsRes, triggersRes, skillsRes] = await Promise.all([
            frappe.call(`${MODULE_PATH}.get_workflows`),
            frappe.call(`${MODULE_PATH}.get_agent_skills`),
            frappe.call(`${MODULE_PATH}.get_triggers`),
            frappe.db.get_list('Skill', {
                filters: { is_agent: 0 },
                fields: ['name', 'description', 'is_enabled', 'modified'],
                limit: 100
            })
        ]);

        this.state.workflows = workflowsRes.message || [];
        this.state.agents = agentsRes.message || [];
        this.state.triggers = triggersRes.message || [];
        this.state.skills = skillsRes || [];
        
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
            } else if (tab === 'workflows') {
                $btn.html('<i class="fa fa-plus"></i> New Workflow').data('type', 'workflow');
            } else if (tab === 'skills') {
                $btn.html('<i class="fa fa-plus"></i> New Skill').data('type', 'skill');
            } else {
                $btn.html('<i class="fa fa-plus"></i> New Trigger').data('type', 'trigger');
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
                            <div class="am-card-title">${frappe.utils.escape_html(a.name)}</div>
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
                else if (action === 'edit_agent') frappe.set_route('Form', 'Skill', a.name);
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
                            <div class="am-card-title">${frappe.utils.escape_html(s.name)}</div>
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
                if (action === 'edit_skill') frappe.set_route('Form', 'Skill', s.name);
                else if (action === 'toggle_skill') this.toggleSkill(s);
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
            const icon = t.trigger_type === 'Document Event' ? 'fa-file-text-o' : (t.trigger_type === 'Cron' ? 'fa-clock-o' : 'fa-webhook');
            const detail = t.trigger_type === 'Document Event' ? `${t.doctype} (${t.event})` : (t.trigger_type === 'Cron' ? t.cron_format : 'Webhook');
            
            const $card = $(`
                <div class="am-card" data-id="${t.workflow_name}">
                    <div class="am-card-head">
                        <div class="am-card-icon am-icon-trigger"><i class="fa ${icon}"></i></div>
                        <div class="am-card-info">
                            <div class="am-card-title">${frappe.utils.escape_html(t.trigger_name)}</div>
                            <span class="indicator-pill ${t.is_enabled ? 'green' : 'gray'} am-card-status">${t.trigger_type}</span>
                        </div>
                    </div>
                    <div class="am-card-body am-trigger-detail">
                        <code>${frappe.utils.escape_html(detail)}</code>
                    </div>
                    <div class="am-card-actions">
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
                if (action === 'toggle_trigger') this.toggleTrigger(t);
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
        frappe.new_doc("Skill", {
            is_agent: 1,
            is_enabled: 1,
            disable_model_invocation: 1
        });
    }

    createSkill() {
        frappe.new_doc("Skill", {
            is_agent: 0,
            is_enabled: 1
        });
    }

    async toggleSkill(s) {
        const enabled = s.is_enabled ? 0 : 1;
        await frappe.db.set_value('Skill', s.name, 'is_enabled', enabled);
        s.is_enabled = enabled;
        this.renderBody();
        frappe.show_alert(`Skill ${enabled ? 'enabled' : 'disabled'}`);
    }

    createTrigger(prefilledWorkflow = null) {
        let fields = [
            { fieldname: 'trigger_name', label: 'Trigger Name', fieldtype: 'Data', reqd: 1 },
            { fieldname: 'workflow_name', label: 'Workflow', fieldtype: 'Link', options: 'Agent Workflow', reqd: 1, default: prefilledWorkflow },
            { fieldname: 'type', label: 'Trigger Type', fieldtype: 'Select', options: '\nDocument Event\nCron\nWebhook', reqd: 1 },
            { fieldname: 'doctype', label: 'Target Doctype', fieldtype: 'Link', options: 'DocType', depends_on: "eval:doc.type=='Document Event'" },
            { fieldname: 'event', label: 'Doc Event', fieldtype: 'Select', options: 'on_create\non_update\non_submit\non_cancel', depends_on: "eval:doc.type=='Document Event'" },
            { fieldname: 'cron_format', label: 'Cron Schedule', fieldtype: 'Data', description: 'e.g., 0 * * * * (Every hour)', depends_on: "eval:doc.type=='Cron'" }
        ];

        frappe.prompt(
            fields,
            async (values) => {
                await frappe.call(`${MODULE_PATH}.create_trigger`, { trigger_data: values });
                frappe.show_alert('Trigger created');
                this.load();
            },
            'Configure Trigger',
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
            await frappe.call(`${MODULE_PATH}.delete_trigger`, { trigger_name: t.name });
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
                padding: 20px 24px 12px; /* Added top padding, horizontal padding for content */
                border-bottom: 1px solid var(--border-color); /* Edge-to-edge border */
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
            /* Custom active class to prevent Frappe's default black-on-black button issue */
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
                padding: 24px 24px 0; /* Horizontal padding moved here so it doesn't break header border */
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
        `;
        document.head.appendChild(style);
    }
}