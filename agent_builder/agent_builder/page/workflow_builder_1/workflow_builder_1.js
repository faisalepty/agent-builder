// agent_builder/agent_builder/agent_builder/page/workflow_builder_1/workflow_builder_1.js

frappe.pages['workflow-builder-1'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Workflow Builder',
        single_column: true,
    });
    frappe.workflow_builder = new WorkflowBuilder(page);
};

frappe.pages['workflow-builder-1'].on_page_show = function (wrapper) {
    if (frappe.workflow_builder) {
        if (!frappe.workflow_builder.isDomAttached()) {
            // Frappe v15 cleared the DOM to save memory. Rebuild it.
            frappe.workflow_builder.setupDom();
        } else {
            const workflowName = frappe.get_route()[1];
            frappe.workflow_builder.load(workflowName);
        }
    }
};

const DRAWFLOW_JS = 'https://cdn.jsdelivr.net/gh/jerosoler/Drawflow/dist/drawflow.min.js';
const DRAWFLOW_CSS = 'https://cdn.jsdelivr.net/gh/jerosoler/Drawflow/dist/drawflow.min.css';
const MODULE_PATH = 'agent_builder.agent_builder.page.agent_builder.agent_builder';

const STEP_TYPE_LABEL = { branch: 'Branch', loop: 'Loop', note: 'Note', trigger: 'Trigger', workflow: 'Sub-workflow' };
const STEP_VISUAL = {
    branch: { icon: 'fa-code-fork', color: '#805ad5' },
    loop: { icon: 'fa-repeat', color: '#dd6b20' },
    trigger: { icon: 'fa-bolt', color: '#d69e2e' },
    workflow: { icon: 'fa-sitemap', color: '#319795' },
};

const TOOL_VISUALS = {
    frappe_get_list: { icon: 'fa-list', color: '#3182ce' },
    frappe_get_doc: { icon: 'fa-file-text-o', color: '#3182ce' },
    frappe_create_doc: { icon: 'fa-plus-square-o', color: '#38a169' },
    frappe_save_doc: { icon: 'fa-floppy-o', color: '#3182ce' },
    frappe_delete_doc: { icon: 'fa-trash-o', color: '#e53e3e' },
    frappe_generate_report: { icon: 'fa-bar-chart', color: '#6b46c1' },
    delegate_task: { icon: 'fa-share-square-o', color: '#d53f8c' },
    human_approval: { icon: 'fa-check-circle-o', color: '#dd6b20' },
};
const DEFAULT_TOOL_VISUAL = { icon: 'fa-wrench', color: '#4c51bf' };

// Matches strings containing Jinja syntax like {{ output }} or {{ doc.field }}
// Uses [\s\S] instead of the s flag for older JS engine compatibility.
const jinjaRegex = /\{\{[\s\S]*?\}\}/;

function toolVisual(toolName) {
    if (!toolName) return DEFAULT_TOOL_VISUAL;
    if (TOOL_VISUALS[toolName]) return TOOL_VISUALS[toolName];
    const prefixKey = Object.keys(TOOL_VISUALS).find((k) => toolName.startsWith(k));
    return prefixKey ? TOOL_VISUALS[prefixKey] : DEFAULT_TOOL_VISUAL;
}

function esc(s) {
    return frappe.utils.escape_html(s == null ? '' : String(s));
}

function humanizeToolName(name) {
    if (!name) return '';
    const stripped = name.replace(/^frappe_/, '');
    return stripped.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function summarizeArgs(args) {
    if (!args) return 'No arguments set';
    if (typeof args === 'string') {
        const trimmed = args.replace(/\s+/g, ' ').trim();
        if (!trimmed) return 'No arguments set';
        return trimmed.length > 30 ? trimmed.slice(0, 30) + '…' : trimmed;
    }
    if (typeof args !== 'object') return 'No arguments set';
    const entries = Object.entries(args).filter(([, v]) => v !== '' && v != null && !(Array.isArray(v) && !v.length));
    if (!entries.length) return 'No arguments set';
    return entries.slice(0, 2).map(([k, v]) => `${k}: ${String(v).slice(0, 28)}`).join('  ·  ');
}

const CHAINABLE_TYPES = ['tool', 'workflow', 'trigger'];

class WorkflowBuilder {
    constructor(page) {
        this.page = page;
        this.setupDom();
    }

    setupDom() {
        this.tools = [];
        this.agentSkills = [];
        this.workflowNames = [];
        this.errorWorkflow = null;
        this.workflowName = null;
        this.dirty = false;
        this._loadId = 0; // Guard against stale loads
        
        this.$root = $('<div class="wb-root"></div>').appendTo(this.page.main);
        this.injectStyles();
        this.renderShell();

        this.loadDrawflowLib().then(() => {
            this.initEditor();
            this.setToolbarEnabled(true);
            this.load(frappe.get_route()[1]);
        }).catch(() => {
            frappe.msgprint('Could not load the workflow canvas library.');
        });
    }

    isDomAttached() {
        return this.$root && $.contains(document, this.$root[0]);
    }

    loadDrawflowLib() {
        if (window.Drawflow) return Promise.resolve();
        if (!document.getElementById('drawflow-css')) {
            $(`<link id="drawflow-css" rel="stylesheet" href="${DRAWFLOW_CSS}">`).appendTo('head');
        }
        return new Promise((resolve, reject) => {
            $.getScript(DRAWFLOW_JS).done(resolve).fail(reject);
        });
    }

    renderShell() {
        const $toolbar = $(`
            <div class="wb-toolbar">
                <div class="wb-toolbar-group">
                    <button class="btn btn-sm btn-default wb-new" disabled title="Create a new workflow">
                        <i class="fa fa-plus"></i> New
                    </button>
                </div>
                <span class="wb-toolbar-divider"></span>
                <div class="wb-toolbar-group">
                    <span class="wb-toolbar-label">Add</span>
                    <button class="btn btn-sm btn-default wb-add-btn" data-add="trigger" disabled title="Declarative entry point">
                        <span class="wb-step-dot" style="background:${STEP_VISUAL.trigger.color}"></span> Trigger
                    </button>
                    <button class="btn btn-sm btn-default wb-add-btn" data-add="tool" disabled>
                        <span class="wb-step-dot" style="background:#3182ce"></span> Tool
                    </button>
                    <button class="btn btn-sm btn-default wb-add-btn" data-add="branch" disabled>
                        <span class="wb-step-dot" style="background:${STEP_VISUAL.branch.color}"></span> Branch
                    </button>
                    <button class="btn btn-sm btn-default wb-add-btn" data-add="loop" disabled>
                        <span class="wb-step-dot" style="background:${STEP_VISUAL.loop.color}"></span> Loop
                    </button>
                    <button class="btn btn-sm btn-default wb-add-btn" data-add="workflow" disabled title="Call another workflow">
                        <span class="wb-step-dot" style="background:${STEP_VISUAL.workflow.color}"></span> Sub-workflow
                    </button>
                    <button class="btn btn-sm btn-default wb-add-btn" data-add="note" disabled>
                        <i class="fa fa-sticky-note-o" style="font-size: 10px; color: var(--yellow-500, #ecc94b);"></i> Note
                    </button>
                </div>
                <span class="wb-toolbar-spacer"></span>
                <div class="wb-toolbar-group wb-toolbar-status">
                    <span class="wb-status-dot"></span>
                    <span class="wb-current-name text-muted">No workflow loaded</span>
                </div>
                <span class="wb-toolbar-divider"></span>
                <button class="btn btn-sm btn-default wb-settings" disabled title="Workflow settings (error workflow)">
                    <i class="fa fa-cog"></i>
                </button>
                <button class="btn btn-sm btn-default wb-run" disabled title="Run this workflow">
                    <i class="fa fa-play"></i> Run
                </button>
                <button class="btn btn-sm btn-primary wb-save" disabled>
                    <i class="fa fa-check"></i> Save
                </button>
            </div>
        `).appendTo(this.$root);

        $toolbar.on('click', '[data-add]:not(:disabled)', (e) => this.addStep($(e.currentTarget).data('add')));
        $toolbar.on('click', '.wb-save:not(:disabled)', () => this.save());
        $toolbar.on('click', '.wb-new:not(:disabled)', () => this.promptNewWorkflow());
        $toolbar.on('click', '.wb-run:not(:disabled)', () => this.runWorkflow());
        $toolbar.on('click', '.wb-settings:not(:disabled)', () => this.openSettings());
        this.$toolbar = $toolbar;

        const $body = $('<div class="wb-body"></div>').appendTo(this.$root);
        this.$canvasWrap = $('<div class="wb-canvas"></div>').appendTo($body);
        this.$canvasOverlay = $('<div class="wb-canvas-overlay"></div>').appendTo(this.$canvasWrap);
        this.$canvas = $('<div id="wb-drawflow" class="wb-canvas-inner"></div>').appendTo(this.$canvasWrap);
        this.$sidebar = $('<div class="wb-sidebar"></div>').appendTo($body);
        this.renderSidebarEmpty();
    }

    renderSidebarEmpty() {
        this.$sidebar.html(`
            <div class="wb-empty">
                <div class="wb-empty-icon"><i class="fa fa-hand-pointer-o"></i></div>
                <div class="wb-empty-title">No step selected</div>
                <div class="wb-empty-text">Click a node on the canvas to edit its properties, or use the toolbar above to add a new step.</div>
            </div>
        `);
    }

    setToolbarEnabled(enabled) {
        this.$toolbar.find('button').prop('disabled', !enabled);
    }

    initEditor() {
        this.editor = new Drawflow(document.getElementById('wb-drawflow'));
        this.editor.reroute = true;
        this.editor.reroute_fix_curvature = true;
        this.editor.start();

        this.editor.on('nodeSelected', (id) => this.selectNode(id));
        this.editor.on('nodeUnselected', () => this.selectNode(null));
        this.editor.on('nodeRemoved', () => { this.selectNode(null); this.markDirty(); });
        this.editor.on('connectionCreated', () => this.markDirty());
        this.editor.on('connectionDeleted', () => this.markDirty());
        this.editor.on('nodeCreated', () => this.markDirty());
    }

    markDirty() {
        this.dirty = true;
        this.updateStatusBadge();
    }

    updateStatusBadge() {
        const $dot = this.$toolbar.find('.wb-status-dot');
        $dot.removeClass('wb-status-clean wb-status-dirty wb-status-new');
        if (!this.workflowName) $dot.addClass('wb-status-new');
        else if (this.dirty) $dot.addClass('wb-status-dirty');
        else $dot.addClass('wb-status-clean');
    }

    async load(workflowName) {
        if (!this.editor) return;
        const loadId = ++this._loadId;
        this.workflowName = workflowName || null;
        this.dirty = false;
        this.page.set_title(this.workflowName ? `Workflow: ${this.workflowName}` : 'Workflow Builder');
        this.$toolbar.find('.wb-current-name').text(this.workflowName || 'Unsaved workflow');
        this.editor.clear();
        this.renderSidebarEmpty();
        this.updateStatusBadge();

        const calls = [
            frappe.call(`${MODULE_PATH}.get_available_tools`),
            frappe.call(`${MODULE_PATH}.get_agent_skills`),
        ];
        if (this.workflowName) {
            calls.unshift(frappe.call(`${MODULE_PATH}.get_workflow`, { workflow_name: this.workflowName }));
        }
        const schemasCall = frappe.call(`${MODULE_PATH}.get_tool_schemas`).catch(() => ({ message: [] }));
        const namesCall = frappe.call(`${MODULE_PATH}.get_workflow_names`).catch(() => ({ message: [] }));

        const results = await Promise.all(calls);
        if (loadId !== this._loadId) return; // Stale load

        const offset = this.workflowName ? 1 : 0;
        const wfRes = this.workflowName ? results[0] : null;
        const toolsRes = results[offset];
        const skillsRes = results[offset + 1];
        const schemasRes = await schemasCall;
        const namesRes = await namesCall;

        if (loadId !== this._loadId) return; // Stale load

        this.tools = (toolsRes.message || []).filter((t) => t !== 'trigger');
        this.toolSchemas = {};
        (schemasRes.message || []).forEach((s) => { this.toolSchemas[s.name] = s; });
        this.agentSkills = skillsRes.message || [];
        this.workflowNames = namesRes.message || [];
        this.errorWorkflow = wfRes ? (wfRes.message.error_workflow || null) : null;
        const steps = wfRes ? (wfRes.message.steps || []) : [];
        this.stepsIn(steps);
        this.updateCanvasOverlay(steps.length === 0);
    }

    updateCanvasOverlay(empty) {
        if (empty) {
            this.$canvasOverlay.html(`
                <div class="wb-canvas-hint">
                    <div class="wb-canvas-hint-icon"><i class="fa fa-sitemap"></i></div>
                    <div class="wb-canvas-hint-title">Empty canvas</div>
                    <div class="wb-canvas-hint-text">Start with a Trigger, then add Tool/Branch/Loop/Sub-workflow steps.</div>
                </div>
            `).show();
        } else {
            this.$canvasOverlay.empty().hide();
        }
    }

    stepsIn(steps) {
        const idMap = {};
        
        // Phase 1: Add all nodes synchronously
        steps.forEach((s, i) => {
            const pos = s.position || { x: 80 + (i % 4) * 260, y: 80 + Math.floor(i / 4) * 160 };
            const inputs = (s.type === 'note' || s.type === 'trigger') ? 0 : 1;
            const outputs = s.type === 'branch' ? 2 : (s.type === 'note' ? 0 : 1);
            const nodeId = this.editor.addNode(
                s.id, inputs, outputs, pos.x, pos.y, `wb-node-${s.type}`, { step: s }, this.nodeHtml(s)
            );
            idMap[s.id] = nodeId;
        });

        // Phase 2: Defer connection creation to the next frame.
        // In Frappe v15 the node DOM elements are not fully laid out immediately
        // after addNode(), so Drawflow calculates connection paths with wrong
        // coordinates (especially with reroute=true). Waiting one animation frame
        // ensures the browser has completed layout before we draw connections.
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                steps.forEach((s) => {
                    if (s.type === 'branch') {
                        if (s.if_true && idMap[s.if_true]) this.editor.addConnection(idMap[s.id], idMap[s.if_true], 'output_1', 'input_1');
                        if (s.if_false && idMap[s.if_false]) this.editor.addConnection(idMap[s.id], idMap[s.if_false], 'output_2', 'input_1');
                    }
                    if (s.type === 'loop') {
                        (s.body || []).forEach((bodyId) => {
                            if (idMap[bodyId]) this.editor.addConnection(idMap[s.id], idMap[bodyId], 'output_1', 'input_1');
                        });
                    }
                });

                for (let i = 0; i < steps.length - 1; i++) {
                    const cur = steps[i], next = steps[i + 1];
                    if (CHAINABLE_TYPES.includes(cur.type) && !this.hasOutgoing(cur.id, steps)) {
                        this.editor.addConnection(idMap[cur.id], idMap[next.id], 'output_1', 'input_1');
                    }
                }
            });
        });
    }

    hasOutgoing(stepId, steps) {
        return steps.some((s) => s.if_true === stepId || s.if_false === stepId || (s.body || []).includes(stepId));
    }

    stepTitle(step) {
        if (step.type === 'tool') return step.tool || 'Select a tool';
        return STEP_TYPE_LABEL[step.type] || step.type;
    }

    stepSubtitle(step) {
        if (step.type === 'tool') return step.tool ? summarizeArgs(step.args) : 'No tool selected';
        if (step.type === 'workflow') return step.workflow_name || 'No workflow selected';
        if (step.type === 'trigger') return step.trigger_type || 'DocType Event';
        return step.condition || 'No condition set';
    }

    nodeHtml(step) {
        if (step.type === 'note') {
            return `
                <div class="wb-node-note">
                    <div class="wb-node-note-body">${esc(step.description || 'Enter note text...')}</div>
                </div>
            `;
        }

        const visual = step.type === 'tool' ? toolVisual(step.tool) : (STEP_VISUAL[step.type] || DEFAULT_TOOL_VISUAL);
        const title = this.stepTitle(step);
        const subtitle = this.stepSubtitle(step);

        let extra = '';
        if (step.type === 'branch') {
            extra = `
                <div class="wb-branch-rows">
                    <span class="wb-branch-tag wb-true">TRUE</span>
                    <span class="wb-branch-tag wb-false">FALSE</span>
                </div>
            `;
        } else if (step.type === 'loop') {
            extra = `<div class="wb-node-meta"><i class="fa fa-repeat"></i> max ${step.max_iterations || 10}×</div>`;
        } else if (step.type === 'trigger') {
            extra = `<div class="wb-node-meta"><i class="fa fa-bolt"></i> entry point</div>`;
        } else if (step.type === 'tool' && step.tool === 'human_approval') {
            extra = `<div class="wb-node-meta"><i class="fa fa-pause"></i> pauses the run</div>`;
        }

        const badges = [
            step.continue_on_fail ? '<span class="wb-mini-badge wb-badge-err" title="Continue on Fail">ERR</span>' : '',
            step.retry_on_fail ? '<span class="wb-mini-badge wb-badge-retry" title="Retry on Fail">R</span>' : '',
        ].join('');

        const shapeClass = step.type === 'trigger' ? 'wb-node-trigger-shape' : '';

        return `
            <div class="wb-node-wrap">
                <div class="wb-node-inner ${shapeClass}">
                    <div class="wb-status-pip"></div>
                    <span class="wb-node-icon-lg" style="background:${visual.color}"><i class="fa ${visual.icon}"></i></span>
                    <div class="wb-node-badges">${badges}</div>
                </div>
                <div class="wb-node-labels">
                    <div class="wb-node-label-below">${esc(title)}</div>
                    <div class="wb-node-sub-below">${esc(subtitle)}</div>
                    ${extra}
                </div>
            </div>
        `;
    }

    addStep(type) {
        const existing = this.editor.export().drawflow.Home.data;
        const count = Object.keys(existing).length;
        const x = 120 + (count % 4) * 280;
        const y = 120 + Math.floor(count / 4) * 160;

        const id = 's' + Date.now().toString(36);
        const step = { id, type };
        if (type === 'tool') Object.assign(step, { tool: '', args: {}, continue_on_fail: false });
        if (type === 'branch') Object.assign(step, { condition: 'output.status == "ok"', if_true: '', if_false: '' });
        if (type === 'loop') Object.assign(step, { condition: 'output.remaining > 0', body: [], max_iterations: 10 });
        if (type === 'note') Object.assign(step, { description: 'New Note' });
        if (type === 'trigger') Object.assign(step, { trigger_type: 'DocType Event', is_enabled: true, run_as_user: 'Administrator' });
        if (type === 'workflow') Object.assign(step, { workflow_name: '', input_mapping: {}, continue_on_fail: false });

        const inputs = (type === 'note' || type === 'trigger') ? 0 : 1;
        const outputs = type === 'branch' ? 2 : (type === 'note' ? 0 : 1);
        const nodeId = this.editor.addNode(id, inputs, outputs, x, y, `wb-node-${type}`, { step }, this.nodeHtml(step));
        this.selectNode(nodeId);
        this.updateCanvasOverlay(false);
        this.markDirty();
    }

    selectNode(nodeId) {
        this.selectedNodeId = nodeId;
        if (nodeId == null) {
            this.renderSidebarEmpty();
            return;
        }
        const node = this.editor.getNodeFromId(nodeId);
        this.renderSidebar(node);
    }

    renderSidebar(node) {
        const step = node.data.step;
        this.$sidebar.empty();
        const $panel = $(`<div class="wb-editor"></div>`).appendTo(this.$sidebar);

        if (step.type !== 'note') {
            const visual = step.type === 'tool' ? toolVisual(step.tool) : (STEP_VISUAL[step.type] || DEFAULT_TOOL_VISUAL);
            $panel.append(`
                <div class="wb-editor-head">
                    <div class="wb-editor-title">
                        <span class="wb-editor-type" style="background:${visual.color}"><i class="fa ${visual.icon}"></i> ${STEP_TYPE_LABEL[step.type] || 'Tool'}</span>
                        <span class="wb-id text-muted">${step.id}</span>
                    </div>
                    <button class="btn btn-xs btn-default wb-delete" title="Delete step">
                        <i class="fa fa-trash"></i>
                    </button>
                </div>
            `);
            $panel.find('.wb-delete').on('click', () => {
                this.editor.removeNodeId('node-' + node.id);
                this.selectNode(null);
            });
        }

        if (step.type === 'tool') this.renderToolEditor($panel, step, node);
        if (step.type === 'branch') this.renderBranchEditor($panel, step, node);
        if (step.type === 'loop') this.renderLoopEditor($panel, step, node);
        if (step.type === 'note') this.renderNoteEditor($panel, step, node);
        if (step.type === 'trigger') this.renderTriggerEditor($panel, step, node);
        if (step.type === 'workflow') this.renderWorkflowStepEditor($panel, step, node);
    }

    updateNodeLabel(node, step) {
        this.editor.updateNodeDataFromId(node.id, { step });
        $(`#node-${node.id} .wb-node-label-below`).text(this.stepTitle(step));
        $(`#node-${node.id} .wb-node-sub-below`).text(this.stepSubtitle(step));
        const visual = step.type === 'tool' ? toolVisual(step.tool) : (STEP_VISUAL[step.type] || DEFAULT_TOOL_VISUAL);
        $(`#node-${node.id} .wb-node-icon-lg`).css('background', visual.color).html(`<i class="fa ${visual.icon}"></i>`);
    }

    generateDefaultArgs(schema) {
        if (!schema || !schema.parameters || !schema.parameters.properties) return {};
        const defaultArgs = {};
        for (const [name, spec] of Object.entries(schema.parameters.properties)) {
            if (spec.type === 'object') defaultArgs[name] = {};
            else if (spec.type === 'array') defaultArgs[name] = [];
            else if (spec.type === 'boolean') defaultArgs[name] = false;
            else if (spec.type === 'integer') defaultArgs[name] = 0;
            else if (spec.type === 'string') defaultArgs[name] = "";
            else defaultArgs[name] = null;
        }
        return defaultArgs;
    }

    groupToolsForSelect() {
        const groups = { AI: [], Approval: [], Core: [] };
        this.tools.forEach((t) => {
            if (t === 'delegate_task') groups.AI.push(t);
            else if (t === 'human_approval') groups.Approval.push(t);
            else groups.Core.push(t);
        });
        return groups;
    }

    renderToolPicker($panel, step, node) {
        const groups = this.groupToolsForSelect();
        const current = step.tool ? toolVisual(step.tool) : null;

        const $wrap = $(`
            <div class="wb-field">
                <label>Tool</label>
                <div class="wb-combo">
                    <button type="button" class="wb-combo-trigger">
                        ${step.tool
                            ? `<span class="wb-combo-icon" style="background:${current.color}"><i class="fa ${current.icon}"></i></span><span class="wb-combo-label">${esc(humanizeToolName(step.tool))}</span>`
                            : `<span class="wb-combo-placeholder">Choose a tool…</span>`}
                        <i class="fa fa-caret-down wb-combo-caret"></i>
                    </button>
                    <div class="wb-combo-menu">
                        <input type="text" class="form-control wb-combo-search" placeholder="Search tools…" />
                        <div class="wb-combo-list"></div>
                    </div>
                </div>
            </div>
        `);
        $panel.append($wrap);

        const $menu = $wrap.find('.wb-combo-menu');
        const $list = $wrap.find('.wb-combo-list');
        const $search = $wrap.find('.wb-combo-search');
        const $trigger = $wrap.find('.wb-combo-trigger');

        const renderList = (filterText) => {
            $list.empty();
            const ft = (filterText || '').toLowerCase();
            let anyMatch = false;
            Object.entries(groups).forEach(([label, tools]) => {
                const filtered = tools.filter((t) => t.toLowerCase().includes(ft) || humanizeToolName(t).toLowerCase().includes(ft));
                if (!filtered.length) return;
                anyMatch = true;
                $list.append(`<div class="wb-combo-group-label">${label}</div>`);
                filtered.forEach((t) => {
                    const v = toolVisual(t);
                    const $item = $(`
                        <div class="wb-combo-item ${t === step.tool ? 'wb-combo-item-active' : ''}" data-tool="${t}">
                            <span class="wb-combo-icon" style="background:${v.color}"><i class="fa ${v.icon}"></i></span>
                            <div class="wb-combo-item-text">
                                <div class="wb-combo-item-title">${esc(humanizeToolName(t))}</div>
                                <div class="wb-combo-item-sub">${esc(t)}</div>
                            </div>
                        </div>
                    `);
                    $item.on('click', () => {
                        step.tool = t;
                        const schema = this.toolSchemas && this.toolSchemas[step.tool];
                        step.args = this.generateDefaultArgs(schema);
                        step.args_invalid = null; // Reset invalid state on tool change
                        this.updateNodeLabel(node, step);
                        this.renderSidebar(node);
                        this.markDirty();
                    });
                    $list.append($item);
                });
            });
            if (!anyMatch) $list.append(`<div class="wb-combo-empty">No tools match "${esc(filterText)}".</div>`);
        };

        $trigger.on('click', (e) => {
            e.stopPropagation();
            const opening = !$menu.hasClass('wb-combo-open');
            $('.wb-combo-menu').removeClass('wb-combo-open');
            if (opening) {
                $menu.addClass('wb-combo-open');
                renderList('');
                $search.val('').focus();
            }
        });
        $search.on('input', (e) => renderList(e.target.value));
        $search.on('click', (e) => e.stopPropagation());
        $menu.on('click', (e) => e.stopPropagation());

        $(document).off('click.wbCombo').on('click.wbCombo', () => $('.wb-combo-menu').removeClass('wb-combo-open'));
    }

    renderToolEditor($panel, step, node) {
        this.renderToolPicker($panel, step, node);

        if (step.tool === 'delegate_task') {
            this.renderDelegateFields($panel, step, node);
        } else if (step.tool === 'human_approval') {
            this.renderApprovalFields($panel, step, node);
        } else {
            this.renderGenericArgsFields($panel, step, node);
        }

        $panel.append(`
            <div class="wb-field">
                <label>Error Handling</label>
                <div class="checkbox">
                    <label><input type="checkbox" class="wb-err-toggle" ${step.continue_on_fail ? 'checked' : ''}> Continue on Fail</label>
                </div>
                <div class="wb-hint">If checked, errors are passed as output to the next step instead of crashing the workflow.</div>
            </div>
        `);
        $panel.find('.wb-err-toggle').on('change', (e) => {
            step.continue_on_fail = e.target.checked;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.renderSidebar(node);
            this.markDirty();
        });

        this.renderRetryFields($panel, step, node);
    }

    renderGenericArgsFields($panel, step, node) {
        const schema = this.toolSchemas && this.toolSchemas[step.tool];
        const paramHint = schema ? schema.description : 'No schema loaded.';

        const argsText = step.args_invalid 
            ? step.args_invalid 
            : (typeof step.args === 'string' ? step.args : JSON.stringify(step.args || {}, null, 2));
        const hasInvalid = !!step.args_invalid;

        $panel.append(`
            <div class="wb-field">
                <label>Args <span class="wb-hint-inline">supports {{output.field}} and {{output}}</span></label>
                <div class="wb-hint wb-hint-ok">${esc(paramHint)}</div>
                <textarea class="form-control wb-args wb-code ${hasInvalid ? 'wb-json-error' : ''}" rows="8">${esc(argsText)}</textarea>
                <div class="wb-json-error-msg" style="display:${hasInvalid ? 'block' : 'none'};">Invalid JSON — fix the syntax or ensure Jinja braces are balanced.</div>
                <div class="wb-hint wb-hint-ok">Must be valid JSON or a Jinja template. Use {{output.field}} to inject a field, or {{output}} to pass the entire previous output.</div>
            </div>
            <div class="wb-field">
                <button class="btn btn-xs btn-default wb-test-step">
                    <i class="fa fa-play"></i> Test this step
                </button>
                <div class="wb-hint wb-test-output" style="display:none;"></div>
            </div>
        `);

        $panel.find('.wb-args').on('input', (e) => {
            const val = e.target.value;
            try {
                step.args = JSON.parse(val);
                step.args_invalid = null; // Clear invalid state
                this.editor.updateNodeDataFromId(node.id, { step });
                this.updateNodeLabel(node, step);
                this.markDirty();
                
                $panel.find('.wb-args').removeClass('wb-json-error');
                $panel.find('.wb-json-error-msg').hide();
            } catch (err) {
                if (jinjaRegex.test(val)) {
                    step.args = val; 
                    step.args_invalid = null;
                    this.editor.updateNodeDataFromId(node.id, { step });
                    this.updateNodeLabel(node, step);
                    this.markDirty();
                    
                    $panel.find('.wb-args').removeClass('wb-json-error');
                    $panel.find('.wb-json-error-msg').hide();
                } else {
                    step.args_invalid = val;
                    this.editor.updateNodeDataFromId(node.id, { step });
                    
                    $panel.find('.wb-args').addClass('wb-json-error');
                    $panel.find('.wb-json-error-msg').show();
                }
            }
        });

        $panel.find('.wb-test-step').on('click', async () => {
            const $out = $panel.find('.wb-test-output');
            $out.show().text('Running...');
            try {
                const res = await frappe.call(`${MODULE_PATH}.test_step`, {
                    tool: step.tool,
                    args: JSON.stringify(step.args || {}),
                });
                $out.html(`<strong>Output:</strong><br><code>${esc(JSON.stringify(res.message.output, null, 2))}</code>`);
            } catch (err) {
                $out.text('Test run failed.');
            }
        });
    }

    renderDelegateFields($panel, step, node) {
        step.args = step.args || {};
        const options = this.agentSkills
            .map((s) => `<option value="${s.name}" ${s.name === step.args.agent_name ? 'selected' : ''}>${esc(s.name)}</option>`)
            .join('');
        $panel.append(`
            <div class="wb-field">
                <label>Agent</label>
                <select class="form-control wb-delegate-agent"><option value="">Choose an agent…</option>${options}</select>
                <div class="wb-hint">Skills marked is_agent=1. Depth-limited to 2 levels of nested delegation.</div>
            </div>
            <div class="wb-field">
                <label>Task <span class="wb-hint-inline">supports {{output.field}} and {{output}}</span></label>
                <textarea class="form-control wb-delegate-task-text" rows="5">${esc(step.args.task || '')}</textarea>
                <div class="wb-hint">Use {{output.field}} to inject a specific field, or {{output}} to include the entire previous step's output in the task description.</div>
            </div>
        `);
        $panel.find('.wb-delegate-agent').on('change', (e) => {
            step.args.agent_name = e.target.value;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.markDirty();
        });
        $panel.find('.wb-delegate-task-text').on('input', (e) => {
            step.args.task = e.target.value;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.updateNodeLabel(node, step);
            this.markDirty();
        });
    }

    renderApprovalFields($panel, step, node) {
        step.args = step.args || {};
        const channels = ['Desk', 'Email', 'Both'];
        const options = channels.map((c) => `<option value="${c}" ${c === step.args.channel ? 'selected' : ''}>${c}</option>`).join('');
        $panel.append(`
            <div class="wb-field">
                <label>Channel</label>
                <select class="form-control wb-approval-channel"><option value="">Choose a channel…</option>${options}</select>
            </div>
            <div class="wb-field">
                <label>Approvers <span class="wb-hint-inline">comma-separated user emails, optional</span></label>
                <input class="form-control wb-approval-approvers" value="${esc((step.args.approvers || []).join(', '))}" placeholder="defaults to the running user" />
            </div>
            <div class="wb-field">
                <label>Message</label>
                <textarea class="form-control wb-approval-msg" rows="4">${esc(step.args.message || '')}</textarea>
                <div class="wb-hint">Shown to the approver alongside the current workflow output. Pauses the entire run — resume/reject from the run dialog or the Agent Workflow Run list.</div>
            </div>
        `);
        $panel.find('.wb-approval-channel').on('change', (e) => {
            step.args.channel = e.target.value;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.markDirty();
        });
        $panel.find('.wb-approval-approvers').on('input', (e) => {
            step.args.approvers = e.target.value.split(',').map((s) => s.trim()).filter(Boolean);
            this.editor.updateNodeDataFromId(node.id, { step });
            this.markDirty();
        });
        $panel.find('.wb-approval-msg').on('input', (e) => {
            step.args.message = e.target.value;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.markDirty();
        });
    }

    renderNoteEditor($panel, step, node) {
        $panel.append(`
            <div class="wb-field">
                <label>Note Text</label>
                <textarea class="form-control wb-note-text" rows="6">${esc(step.description || '')}</textarea>
            </div>
            <button class="btn btn-xs btn-default wb-delete-note">Delete Note</button>
        `);
        $panel.find('.wb-note-text').on('input', (e) => {
            step.description = e.target.value;
            this.editor.updateNodeDataFromId(node.id, { step });
            $(`#node-${node.id} .wb-node-note-body`).text(step.description);
            this.markDirty();
        });
        $panel.find('.wb-delete-note').on('click', () => {
            this.editor.removeNodeId('node-' + node.id);
            this.selectNode(null);
        });
    }

    renderBranchEditor($panel, step, node) {
        $panel.append(`
            <div class="wb-field">
                <label>Condition</label>
                <input class="form-control wb-code wb-cond" value="${esc(step.condition || '')}" />
                <div class="wb-hint">Expression evaluated against <code>output</code>.</div>
            </div>
        `);
        $panel.find('.wb-cond').on('input', (e) => {
            step.condition = e.target.value;
            this.updateNodeLabel(node, step);
            this.markDirty();
        });
    }

    renderLoopEditor($panel, step, node) {
        $panel.append(`
            <div class="wb-field">
                <label>Condition</label>
                <input class="form-control wb-code wb-cond" value="${esc(step.condition || '')}" />
            </div>
            <div class="wb-field">
                <label>Max iterations</label>
                <input class="form-control wb-max" type="number" min="1" value="${step.max_iterations || 10}" />
            </div>
        `);
        $panel.find('.wb-cond').on('input', (e) => {
            step.condition = e.target.value;
            this.updateNodeLabel(node, step);
            this.markDirty();
        });
        $panel.find('.wb-max').on('input', (e) => {
            step.max_iterations = parseInt(e.target.value) || 10;
            this.updateNodeLabel(node, step);
            this.markDirty();
        });
    }

    renderTriggerEditor($panel, step, node) {
        step.trigger_type = step.trigger_type || 'DocType Event';
        step.run_as_user = step.run_as_user || 'Administrator';
        step.event_frequency = step.event_frequency || 'Daily';
        if (step.is_enabled === undefined) step.is_enabled = true;

        const typeOptions = ['DocType Event', 'Scheduled', 'Webhook', 'MCP']
            .map((v) => `<option value="${v}" ${v === step.trigger_type ? 'selected' : ''}>${v}</option>`)
            .join('');
        const eventOptions = ["before_insert", "after_insert", "before_save", "on_update", "before_submit", "on_submit", "before_cancel", "on_cancel", "on_update_after_submit", "on_trash", "after_delete", "on_change"]
            .map((v) => `<option value="${v}" ${v === step.doctype_event ? 'selected' : ''}>${v}</option>`)
            .join('');
        const frequencyOptions = ['Hourly', 'Daily', 'Weekly', 'Monthly', 'Yearly', 'Hourly Long', 'Daily Long', 'Weekly Long', 'Monthly Long', 'Cron']
            .map((v) => `<option value="${v}" ${v === step.event_frequency ? 'selected' : ''}>${v}</option>`)
            .join('');
        const doctypeListId = `wb-doctype-list-${step.id}`;

        $panel.append(`
            <div class="wb-field">
                <div class="checkbox"><label><input type="checkbox" class="wb-t-enabled" ${step.is_enabled ? 'checked' : ''}> Enabled</label></div>
            </div>
            <div class="wb-field">
                <label>Trigger Type</label>
                <select class="form-control wb-t-type">${typeOptions}</select>
            </div>
            <div class="wb-t-doctype-fields" style="${step.trigger_type === 'DocType Event' ? '' : 'display:none;'}">
                <div class="wb-field">
                    <label>DocType</label>
                    <input class="form-control wb-t-doctype" value="${esc(step.doctype_name || '')}" placeholder="Start typing a DocType name…" list="${doctypeListId}" />
                    <datalist id="${doctypeListId}"></datalist>
                </div>
                <div class="wb-field">
                    <label>Event</label>
                    <select class="form-control wb-t-event">${eventOptions}</select>
                </div>
            </div>
            <div class="wb-t-cron-fields" style="${step.trigger_type === 'Scheduled' ? '' : 'display:none;'}">
                <div class="wb-field">
                    <label>Event Frequency</label>
                    <select class="form-control wb-t-frequency">${frequencyOptions}</select>
                </div>
                <div class="wb-field wb-t-cron-input" style="${step.event_frequency === 'Cron' ? '' : 'display:none;'}">
                    <label>Cron Expression</label>
                    <input class="form-control wb-t-cron wb-code" value="${esc(step.cron_expression || '')}" placeholder="0 * * * *" />
                </div>
            </div>
            <div class="wb-t-webhook-fields" style="${step.trigger_type === 'Webhook' ? '' : 'display:none;'}">
                <div class="wb-field">
                    <label>Webhook Token</label>
                    <input class="form-control wb-code" value="${esc(step.webhook_token || 'generated the first time you Save')}" readonly />
                    <div class="wb-hint">Required in the webhook call's payload to authorize it. Filled in automatically after Save.</div>
                </div>
            </div>
            <div class="wb-field">
                <label>Run As User</label>
                <input class="form-control wb-t-user" value="${esc(step.run_as_user)}" />
            </div>
            <div class="wb-field">
                <label>Input Template <span class="wb-hint-inline">Jinja, optional</span></label>
                <textarea class="form-control wb-t-input-template wb-code" rows="4">${esc(step.input_template || '')}</textarea>
                <div class="wb-hint">Leave blank to pass the whole trigger context — including the full <code>doc</code> — straight through as the workflow's input, unchanged. Use <code>{{ doc.field }}</code> to inject a specific field, or <code>{{ doc }}</code> to pass the whole doc as JSON. Rendered as Jinja, then parsed as JSON, e.g. <code>{"customer": "{{ doc.customer }}"}</code>.</div>
            </div>
            <div class="wb-field">
                <label>Condition (optional)</label>
                <input class="form-control wb-t-condition wb-code" value="${esc(step.condition || '')}" placeholder='e.g. doc.status == "Overdue"' />
            </div>
        `);

        $panel.find('.wb-t-enabled').on('change', (e) => {
            step.is_enabled = e.target.checked;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.markDirty();
        });

        $panel.find('.wb-t-type').on('change', (e) => {
            step.trigger_type = e.target.value;
            $panel.find('.wb-t-doctype-fields').toggle(step.trigger_type === 'DocType Event');
            $panel.find('.wb-t-cron-fields').toggle(step.trigger_type === 'Scheduled');
            $panel.find('.wb-t-webhook-fields').toggle(step.trigger_type === 'Webhook');
            this.updateNodeLabel(node, step);
            this.markDirty();
        });

        $panel.find('.wb-t-doctype').on('input', async (e) => {
            step.doctype_name = e.target.value;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.markDirty();
            const txt = e.target.value;
            if (txt.length < 2) return;
            try {
                const res = await frappe.call(`${MODULE_PATH}.search_doctypes`, { txt });
                const $list = $panel.find(`#${doctypeListId}`);
                $list.empty();
                (res.message || []).forEach((name) => $list.append(`<option value="${esc(name)}"></option>`));
            } catch (err) {}
        });

        $panel.find('.wb-t-event').on('change', (e) => {
            step.doctype_event = e.target.value;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.markDirty();
        });
        $panel.find('.wb-t-cron').on('input', (e) => {
            step.cron_expression = e.target.value;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.markDirty();
        });
        $panel.find('.wb-t-frequency').on('change', (e) => {
            step.event_frequency = e.target.value;
            $panel.find('.wb-t-cron-input').toggle(step.event_frequency === 'Cron');
            this.editor.updateNodeDataFromId(node.id, { step });
            this.markDirty();
        });
        $panel.find('.wb-t-user').on('input', (e) => {
            step.run_as_user = e.target.value;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.markDirty();
        });
        $panel.find('.wb-t-input-template').on('input', (e) => {
            step.input_template = e.target.value;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.markDirty();
        });
        $panel.find('.wb-t-condition').on('input', (e) => {
            step.condition = e.target.value;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.markDirty();
        });
    }

    renderWorkflowStepEditor($panel, step, node) {
        const options = this.workflowNames
            .filter((w) => w.name !== this.workflowName)
            .map((w) => `<option value="${w.name}" ${w.name === step.workflow_name ? 'selected' : ''}>${esc(w.workflow_name || w.name)}</option>`)
            .join('');
            
        const mappingText = step.input_mapping_invalid 
            ? step.input_mapping_invalid 
            : (typeof step.input_mapping === 'string' ? step.input_mapping : JSON.stringify(step.input_mapping || {}, null, 2));
        const hasInvalidMapping = !!step.input_mapping_invalid;

        $panel.append(`
            <div class="wb-field">
                <label>Workflow to call</label>
                <select class="form-control wb-subworkflow-select"><option value="">Choose a workflow…</option>${options}</select>
                <div class="wb-hint">Depth-limited to 3 levels of nested sub-workflow calls.</div>
            </div>
            <div class="wb-field">
                <label>Input Mapping <span class="wb-hint-inline">supports {{output.field}} and {{output}}</span></label>
                <textarea class="form-control wb-input-mapping wb-code ${hasInvalidMapping ? 'wb-json-error' : ''}" rows="6">${esc(mappingText)}</textarea>
                <div class="wb-json-error-msg" style="display:${hasInvalidMapping ? 'block' : 'none'};">Invalid JSON — fix the syntax or ensure Jinja braces are balanced.</div>
                <div class="wb-hint">Leave as <code>{}</code> to pass this step's entire current output through unchanged. Use <code>{{output.field}}</code> to map a specific field, or <code>{{output}}</code> to pass the whole previous output.</div>
            </div>
            <div class="wb-field">
                <div class="checkbox">
                    <label><input type="checkbox" class="wb-err-toggle" ${step.continue_on_fail ? 'checked' : ''}> Continue on Fail</label>
                </div>
            </div>
        `);
        $panel.find('.wb-subworkflow-select').on('change', (e) => {
            step.workflow_name = e.target.value;
            this.updateNodeLabel(node, step);
            this.markDirty();
        });
        $panel.find('.wb-input-mapping').on('input', (e) => {
            const val = e.target.value;
            try {
                step.input_mapping = JSON.parse(val);
                step.input_mapping_invalid = null;
                this.editor.updateNodeDataFromId(node.id, { step });
                this.markDirty();
                
                $panel.find('.wb-input-mapping').removeClass('wb-json-error');
                $panel.find('.wb-json-error-msg').hide();
            } catch (err) {
                if (jinjaRegex.test(val)) {
                    step.input_mapping = val;
                    step.input_mapping_invalid = null;
                    this.editor.updateNodeDataFromId(node.id, { step });
                    this.markDirty();
                    
                    $panel.find('.wb-input-mapping').removeClass('wb-json-error');
                    $panel.find('.wb-json-error-msg').hide();
                } else {
                    step.input_mapping_invalid = val;
                    this.editor.updateNodeDataFromId(node.id, { step });
                    
                    $panel.find('.wb-input-mapping').addClass('wb-json-error');
                    $panel.find('.wb-json-error-msg').show();
                }
            }
        });
        $panel.find('.wb-err-toggle').on('change', (e) => {
            step.continue_on_fail = e.target.checked;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.renderSidebar(node);
            this.markDirty();
        });

        this.renderRetryFields($panel, step, node);
    }

    renderRetryFields($panel, step, node) {
        $panel.append(`
            <div class="wb-field">
                <label>Retry / Wait</label>
                <div class="checkbox">
                    <label><input type="checkbox" class="wb-retry-toggle" ${step.retry_on_fail ? 'checked' : ''}> Retry on fail</label>
                </div>
                <div class="wb-retry-sub" style="${step.retry_on_fail ? '' : 'display:none;'} margin-top:6px;">
                    <input class="form-control wb-max-retries" type="number" min="1" value="${step.max_retries || 2}" placeholder="Max retries" style="margin-bottom:6px;" />
                    <input class="form-control wb-wait-between" type="number" min="0" value="${step.wait_between_ms || 1000}" placeholder="Wait between retries (ms)" />
                </div>
                <input class="form-control wb-wait-seconds" type="number" min="0" value="${step.wait_seconds || 0}" placeholder="Wait before running (seconds)" style="margin-top:8px;" />
                <div class="wb-hint">Step-level retry re-runs the whole step (separate from a tool's own internal retry).</div>
            </div>
        `);

        $panel.find('.wb-retry-toggle').on('change', (e) => {
            step.retry_on_fail = e.target.checked;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.renderSidebar(node);
            this.markDirty();
        });
        $panel.find('.wb-max-retries').on('input', (e) => {
            step.max_retries = parseInt(e.target.value) || 2;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.markDirty();
        });
        $panel.find('.wb-wait-between').on('input', (e) => {
            step.wait_between_ms = parseInt(e.target.value) || 1000;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.markDirty();
        });
        $panel.find('.wb-wait-seconds').on('input', (e) => {
            step.wait_seconds = parseInt(e.target.value) || 0;
            this.editor.updateNodeDataFromId(node.id, { step });
            this.markDirty();
        });
    }

    clearRunOverlay() {
        $('#wb-drawflow .wb-status-pip').removeClass('wb-pip-success wb-pip-error wb-pip-paused').empty();
    }

    markNodeStatus(stepId, status) {
        const data = this.editor.export().drawflow.Home.data;
        const match = Object.entries(data).find(([, n]) => n.data && n.data.step && n.data.step.id === stepId);
        if (!match) return;
        const [nodeId] = match;
        const $pip = $(`#node-${nodeId} .wb-status-pip`);
        $pip.removeClass('wb-pip-success wb-pip-error wb-pip-paused').empty();
        if (status === 'success') $pip.addClass('wb-pip-success').html('<i class="fa fa-check"></i>');
        else if (status === 'error') $pip.addClass('wb-pip-error').html('<i class="fa fa-times"></i>');
        else if (status === 'paused') $pip.addClass('wb-pip-paused').html('<i class="fa fa-pause"></i>');
    }

    runWorkflow() {
        if (!this.workflowName) {
            frappe.msgprint('Save the workflow first.');
            return;
        }
        frappe.prompt(
            [{ fieldname: 'input_data', label: 'Input JSON', fieldtype: 'Code', options: 'JSON', default: '{}' }],
            async (values) => {
                this.clearRunOverlay();
                frappe.show_alert({ message: 'Running workflow…', indicator: 'blue' });
                try {
                    const res = await frappe.call(`${MODULE_PATH}.execute_workflow`, {
                        workflow_name: this.workflowName,
                        input_data: values.input_data || '{}',
                    });
                    this.applyRunResult(res.message.result);
                } catch (err) {
                    frappe.msgprint('Workflow execution failed — check the Error Log for details.');
                }
            },
            'Run Workflow',
            'Run'
        );
    }

    applyRunResult(result) {
        (result.log || []).forEach((entry) => {
            const isError = entry.output && typeof entry.output === 'object' && entry.output.error;
            this.markNodeStatus(entry.step, isError ? 'error' : 'success');
        });

        if (result.status === 'Paused') {
            this.markNodeStatus(result.paused_step, 'paused');
            this.showApprovalDialog(result);
        } else if (result.status === 'Success') {
            frappe.show_alert({ message: 'Workflow completed', indicator: 'green' });
        } else if (result.status === 'Failed') {
            frappe.show_alert({ message: 'Workflow failed', indicator: 'red' });
        }
    }

    showApprovalDialog(result) {
        const d = new frappe.ui.Dialog({
            title: 'Human Approval Required',
            fields: [
                {
                    fieldname: 'info',
                    fieldtype: 'HTML',
                    options: `<p>${esc(result.message || 'Workflow paused for approval.')}</p>
                        <pre class="wb-code">${esc(JSON.stringify(result.final_output, null, 2))}</pre>`,
                },
                { fieldname: 'edited_output', label: 'Edited Output (optional, JSON)', fieldtype: 'Code', options: 'JSON' },
            ],
            primary_action_label: 'Approve',
            primary_action: async (values) => {
                await frappe.call(`${MODULE_PATH}.resume_workflow`, {
                    run_name: result.run_name,
                    decision: 'approve',
                    edited_output: values.edited_output || null,
                });
                frappe.show_alert({ message: 'Approved — workflow resumed', indicator: 'green' });
                d.hide();
            },
            secondary_action_label: 'Reject',
            secondary_action: async () => {
                await frappe.call(`${MODULE_PATH}.resume_workflow`, {
                    run_name: result.run_name,
                    decision: 'reject',
                });
                frappe.show_alert({ message: 'Rejected', indicator: 'red' });
                d.hide();
            },
        });
        d.show();
    }

    openSettings() {
        if (!this.workflowName) {
            frappe.msgprint('Save the workflow first.');
            return;
        }
        const options = ['', ...this.workflowNames.filter((w) => w.name !== this.workflowName).map((w) => w.name)];
        frappe.prompt(
            [{
                fieldname: 'error_workflow',
                label: 'Error Workflow',
                fieldtype: 'Select',
                options: options.join('", "'),
                default: this.errorWorkflow || '',
                description: 'If this workflow fails, the selected workflow is enqueued with {failed_workflow, failed_run, error, log} as input.',
            }],
            async (values) => {
                await frappe.call(`${MODULE_PATH}.set_error_workflow`, {
                    workflow_name: this.workflowName,
                    error_workflow: values.error_workflow || null,
                });
                this.errorWorkflow = values.error_workflow || null;
                frappe.show_alert({ message: 'Settings saved', indicator: 'green' });
            },
            'Workflow Settings',
            'Save'
        );
    }

    stepsOut() {
        const exported = this.editor.export().drawflow.Home.data;
        const nodes = Object.values(exported);
        const steps = nodes.map((n) => {
            const step = Object.assign({}, n.data.step, { position: { x: n.pos_x, y: n.pos_y } });
            delete step.args_invalid;
            delete step.input_mapping_invalid;
            return step;
        });
        return steps;
    }

    applyWebhookTokens(tokens) {
        if (!tokens) return;
        const data = this.editor.export().drawflow.Home.data;
        Object.entries(data).forEach(([nodeId, n]) => {
            const step = n.data && n.data.step;
            if (!step || step.type !== 'trigger') return;
            if (tokens[step.id] === undefined) return;
            step.webhook_token = tokens[step.id];
            this.editor.updateNodeDataFromId(nodeId, { step });
            if (this.selectedNodeId === nodeId) this.renderSidebar(this.editor.getNodeFromId(nodeId));
        });
    }

    async save() {
        const steps = this.stepsOut();
        const invalidTool = steps.find((s) => s.type === 'tool' && !s.tool);
        if (invalidTool) {
            frappe.msgprint(`Step "${invalidTool.id}" has no tool selected.`);
            return;
        }
        const invalidSubworkflow = steps.find((s) => s.type === 'workflow' && !s.workflow_name);
        if (invalidSubworkflow) {
            frappe.msgprint(`Step "${invalidSubworkflow.id}" has no workflow selected.`);
            return;
        }

        if (!this.workflowName) {
            frappe.prompt(
                [
                    { fieldname: 'workflow_name', label: 'Workflow Name', fieldtype: 'Data', reqd: 1 },
                    { fieldname: 'description', label: 'Description', fieldtype: 'Small Text' },
                ],
                async (values) => {
                    const createRes = await frappe.call(`${MODULE_PATH}.create_workflow`, {
                        workflow_name: values.workflow_name,
                        description: values.description,
                    });
                    if (!createRes.message || !createRes.message.name) return;

                    this.workflowName = createRes.message.name;
                    const saveRes = await frappe.call(`${MODULE_PATH}.save_workflow_steps`, {
                        workflow_name: this.workflowName,
                        steps: JSON.stringify(steps),
                    });
                    this.applyWebhookTokens(saveRes.message && saveRes.message.webhook_tokens);
                    this.dirty = false;
                    this.updateStatusBadge();
                    frappe.show_alert({ message: 'Workflow created and saved', indicator: 'green' });
                    window.history.pushState(null, '', `/app/workflow-builder-1/${this.workflowName}`);
                    this.page.set_title(`Workflow: ${this.workflowName}`);
                    this.$toolbar.find('.wb-current-name').text(this.workflowName);
                },
                'Name this Workflow',
                'Create & Save'
            );
            return;
        }

        const saveRes = await frappe.call(`${MODULE_PATH}.save_workflow_steps`, {
            workflow_name: this.workflowName,
            steps: JSON.stringify(steps),
        });
        this.applyWebhookTokens(saveRes.message && saveRes.message.webhook_tokens);
        this.dirty = false;
        this.updateStatusBadge();
        frappe.show_alert({ message: 'Workflow saved', indicator: 'green' });
    }

    injectStyles() {
        if (document.getElementById('wb-styles')) return;
        const style = document.createElement('style');
        style.id = 'wb-styles';
        style.textContent = `
            .wb-root { margin: 0 -15px -15px -15px; height: calc(100vh - 105px); display: flex; flex-direction: column; background: var(--bg-color, #f8f8f8); overflow: hidden; }
            .wb-toolbar { display: flex; gap: 10px; align-items: center; padding: 10px 16px; border-bottom: 1px solid var(--border-color, #d1d8dd); background: var(--fg-color, #fff); flex-shrink: 0; flex-wrap: wrap; }
            .wb-toolbar-group { display: flex; gap: 6px; align-items: center; }
            .wb-toolbar-label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-right: 2px; }
            .wb-toolbar-divider { width: 1px; height: 22px; background: var(--border-color); }
            .wb-toolbar-spacer { flex: 1; }
            .wb-toolbar-status { font-size: 12px; gap: 8px; }
            .wb-status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); transition: background 150ms; }
            .wb-status-dot.wb-status-clean { background: var(--green-500); }
            .wb-status-dot.wb-status-dirty { background: var(--orange-500); }
            .wb-status-dot.wb-status-new { background: var(--blue-500); }
            .wb-current-name { font-family: var(--font-monospace); font-size: 12px; }
            .wb-add-btn { display: inline-flex !important; align-items: center; gap: 6px; }
            .wb-step-dot { display: inline-block; width: 8px; height: 8px; border-radius: 2px; }

            .wb-body { display: flex; flex: 1; min-height: 0; }
            .wb-canvas { flex: 1; position: relative; overflow: hidden; background: var(--bg-color); }
            #wb-drawflow, .wb-canvas-inner { width: 100%; height: 100%; position: relative; background-color: var(--bg-color) !important; background-image: radial-gradient(circle, var(--gray-400) 1px, transparent 1px) !important; background-size: 22px 22px !important; }
            .wb-canvas-overlay { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; pointer-events: none; z-index: 0; }

            .wb-sidebar { width: 360px; border-left: 1px solid var(--border-color); background: var(--fg-color); padding: 16px; overflow-y: auto; flex-shrink: 0; }
            .wb-empty { text-align: center; margin-top: 80px; color: var(--text-muted); }
            .wb-editor-head { display: flex; justify-content: space-between; align-items: center; padding-bottom: 12px; margin-bottom: 14px; border-bottom: 1px solid var(--border-color); }
            .wb-editor-type { display: inline-flex; align-items: center; gap: 6px; color: #fff; font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 5px; text-transform: uppercase; letter-spacing: 0.3px; }
            .wb-field { margin-bottom: 14px; }
            .wb-code { font-family: var(--font-monospace) !important; font-size: 11.5px !important; }
            .wb-hint-inline { font-weight: normal; font-size: 10.5px; color: var(--text-muted); text-transform: none; }
            .wb-hint-warn { color: var(--orange-600, #c05621); display: flex; gap: 6px; align-items: flex-start; }
            
            .wb-json-error { border-color: var(--red-500, #e53e3e) !important; background-color: var(--red-50, #fff5f5); }
            .wb-json-error-msg { color: var(--red-600, #c53030); font-size: 11px; margin-top: 4px; display: none; }

            .wb-combo { position: relative; }
            .wb-combo-trigger { width: 100%; display: flex; align-items: center; gap: 8px; padding: 6px 10px; background: var(--control-bg, var(--fg-color)); border: 1px solid var(--border-color); border-radius: 6px; cursor: pointer; text-align: left; font-size: 13px; color: var(--text-color); }
            .wb-combo-trigger:hover { border-color: var(--text-muted); }
            .wb-combo-placeholder { color: var(--text-muted); flex: 1; }
            .wb-combo-label { flex: 1; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .wb-combo-caret { color: var(--text-muted); font-size: 11px; }
            .wb-combo-icon { flex-shrink: 0; width: 22px; height: 22px; border-radius: 6px; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 11px; }

            .wb-combo-menu { display: none; position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 50; background: var(--fg-color); border: 1px solid var(--border-color); border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.16); max-height: 320px; display: none; flex-direction: column; }
            .wb-combo-menu.wb-combo-open { display: flex; }
            .wb-combo-search { margin: 8px; width: calc(100% - 16px); }
            .wb-combo-list { overflow-y: auto; padding: 0 4px 6px; }
            .wb-combo-group-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); padding: 6px 8px 3px; }
            .wb-combo-item { display: flex; align-items: center; gap: 9px; padding: 6px 8px; border-radius: 6px; cursor: pointer; }
            .wb-combo-item:hover { background: var(--control-bg, var(--gray-100, #f3f4f6)); }
            .wb-combo-item-active { background: var(--gray-100, #f3f4f6); }
            .wb-combo-item-text { min-width: 0; flex: 1; }
            .wb-combo-item-title { font-size: 12.5px; font-weight: 500; color: var(--text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .wb-combo-item-sub { font-size: 10.5px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .wb-combo-empty { padding: 10px 8px; font-size: 12px; color: var(--text-muted); text-align: center; }

            #wb-drawflow .drawflow-node { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; width: 72px !important; height: 72px !important; }
            #wb-drawflow .drawflow-node .drawflow_content_node { background: transparent !important; border: none !important; width: 100% !important; height: 100% !important; padding: 0 !important; overflow: visible !important; }

            .wb-node-wrap { position: relative; width: 72px; height: 72px; }
            .wb-node-inner { position: relative; width: 100%; height: 100%; border-radius: 18px; background: var(--fg-color); border: 1px solid var(--border-color); box-shadow: 0 2px 5px rgba(0,0,0,0.10), 0 0 0 1px rgba(0,0,0,0.02); display: flex; align-items: center; justify-content: center; transition: box-shadow 150ms, border-color 150ms, transform 100ms; }
            #wb-drawflow .drawflow-node.selected .wb-node-inner { border-color: var(--primary) !important; box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 25%, transparent), 0 4px 14px rgba(36,144,239,0.25) !important; }
            #wb-drawflow .drawflow-node:hover .wb-node-inner { box-shadow: 0 4px 10px rgba(0,0,0,0.14); }

            .wb-node-icon-lg { width: 100%; height: 100%; border-radius: 18px; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 27px; box-shadow: inset 0 1px 0 rgba(255,255,255,0.18), inset 0 -6px 10px rgba(0,0,0,0.12); }

            .wb-node-labels { position: absolute; top: 100%; left: 50%; transform: translateX(-50%); width: 150px; margin-top: 8px; text-align: center; pointer-events: none; }
            .wb-node-label-below { font-size: 12.5px; font-weight: 600; color: var(--text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .wb-node-sub-below { font-size: 10.5px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 1px; }
            .wb-node-meta { margin-top: 4px; font-size: 10px; color: var(--text-muted); display: flex; align-items: center; justify-content: center; gap: 4px; }
            .wb-node-badges { position: absolute; bottom: -5px; right: -5px; display: flex; gap: 3px; }
            .wb-mini-badge { color: #fff; font-size: 8px; padding: 1px 4px; border-radius: 4px; font-weight: bold; }
            .wb-badge-err { background: var(--red-500); }
            .wb-badge-retry { background: var(--blue-500); }

            .wb-status-pip { position: absolute; top: -6px; left: -6px; width: 17px; height: 17px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 8px; border: 2px solid var(--fg-color, #fff); opacity: 0; transition: opacity 120ms; z-index: 2; }
            .wb-status-pip.wb-pip-success { opacity: 1; background: var(--green-500); }
            .wb-status-pip.wb-pip-error { opacity: 1; background: var(--red-500); }
            .wb-status-pip.wb-pip-paused { opacity: 1; background: var(--orange-500); }

            .wb-node-trigger-shape { border-radius: 8px 26px 26px 8px; }
            #wb-drawflow .wb-node-trigger .input { display: none !important; }

            .wb-branch-rows { margin-top: 4px; display: flex; gap: 6px; justify-content: center; }
            .wb-branch-tag { font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: 4px; }
            .wb-branch-tag.wb-true { background: var(--green-100, #c6f6d5); color: var(--green-700, #276749); }
            .wb-branch-tag.wb-false { background: var(--red-100, #fed7d7); color: var(--red-700, #9b2c2c); }

            #wb-drawflow .wb-node-note { width: 300px; background: var(--yellow-100, #fff9c4); border: 1px dashed var(--yellow-500, #ecc94b); border-radius: 8px; padding: 12px; font-size: 13px; color: var(--text-color); box-shadow: none; }
            #wb-drawflow .wb-node-note .wb-node-note-body { white-space: pre-wrap; word-wrap: break-word; }

            #wb-drawflow .drawflow-node .input, #wb-drawflow .drawflow-node .output { width: 14px !important; height: 14px !important; background: var(--fg-color) !important; border: 2px solid var(--text-muted) !important; border-radius: 50% !important; top: 50% !important; transform: translateY(-50%) !important; }
            #wb-drawflow .drawflow-node .input { left: -7px !important; }
            #wb-drawflow .drawflow-node .output { right: -7px !important; }
            #wb-drawflow .wb-node-branch .output_1 { top: 38% !important; }
            #wb-drawflow .wb-node-branch .output_2 { top: 62% !important; }
        `;
        document.head.appendChild(style);
    }
}