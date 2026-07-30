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
    const workflowName = frappe.get_route()[1];
    if (frappe.workflow_builder) frappe.workflow_builder.load(workflowName);
};

const DRAWFLOW_JS = 'https://cdn.jsdelivr.net/gh/jerosoler/Drawflow/dist/drawflow.min.js';
const DRAWFLOW_CSS = 'https://cdn.jsdelivr.net/gh/jerosoler/Drawflow/dist/drawflow.min.css';
const MODULE_PATH = 'agent_builder.agent_builder.page.agent_builder.agent_builder';

// Control-flow step types (everything that ISN'T 'tool'). 'tool' steps
// get their look from TOOL_VISUALS below instead of a flat per-type color
// — that's the actual "different nodes look different" part.
const STEP_TYPE_LABEL = { branch: 'Branch', loop: 'Loop', note: 'Note', trigger: 'Trigger', workflow: 'Sub-workflow' };
const STEP_VISUAL = {
    branch: { icon: 'fa-code-fork', color: '#805ad5' },
    loop: { icon: 'fa-repeat', color: '#dd6b20' },
    trigger: { icon: 'fa-bolt', color: '#d69e2e' },
    workflow: { icon: 'fa-sitemap', color: '#319795' },
};

// Per-tool icon/color, keyed by exact name or prefix. This is the n8n
// "every node looks like its service" idea, scoped to the tools you
// actually have. Falls through to DEFAULT_TOOL_VISUAL for anything
// unlisted, so new tools never render broken — just generic.
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

function toolVisual(toolName) {
    if (!toolName) return DEFAULT_TOOL_VISUAL;
    if (TOOL_VISUALS[toolName]) return TOOL_VISUALS[toolName];
    const prefixKey = Object.keys(TOOL_VISUALS).find((k) => toolName.startsWith(k));
    return prefixKey ? TOOL_VISUALS[prefixKey] : DEFAULT_TOOL_VISUAL;
}

function esc(s) {
    return frappe.utils.escape_html(s == null ? '' : String(s));
}

function summarizeArgs(args) {
    if (!args || typeof args !== 'object') return 'No arguments set';
    const entries = Object.entries(args).filter(([, v]) => v !== '' && v != null && !(Array.isArray(v) && !v.length));
    if (!entries.length) return 'No arguments set';
    return entries.slice(0, 2).map(([k, v]) => `${k}: ${String(v).slice(0, 28)}`).join('  ·  ');
}

// Step types that participate in automatic sequential chaining when the
// user doesn't manually wire a connection (branch/loop wire explicitly).
const CHAINABLE_TYPES = ['tool', 'workflow', 'trigger'];

class WorkflowBuilder {
    constructor(page) {
        this.page = page;
        this.tools = [];
        this.agentSkills = [];
        this.workflowNames = [];
        this.errorWorkflow = null;
        this.workflowName = null;
        this.dirty = false;

        this.$root = $('<div class="wb-root"></div>').appendTo(page.main);
        this.injectStyles();
        this.renderShell();

        this.loadDrawflowLib().then(() => {
            this.initEditor();
            this.setToolbarEnabled(true);
            const workflowName = frappe.get_route()[1];
            this.load(workflowName);
        }).catch(() => {
            frappe.msgprint('Could not load the workflow canvas library.');
        });
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
        const offset = this.workflowName ? 1 : 0;
        const wfRes = this.workflowName ? results[0] : null;
        const toolsRes = results[offset];
        const skillsRes = results[offset + 1];
        const schemasRes = await schemasCall;
        const namesRes = await namesCall;

        // 'trigger' is a synthetic, non-tool-step entry in this list
        // (see agent_builder.py) — exclude it from the Tool step's own
        // picker since Trigger is already its own toolbar button/step type.
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
        steps.forEach((s, i) => {
            const pos = s.position || { x: 80 + (i % 4) * 260, y: 80 + Math.floor(i / 4) * 160 };
            const inputs = (s.type === 'note' || s.type === 'trigger') ? 0 : 1;
            const outputs = s.type === 'branch' ? 2 : (s.type === 'note' ? 0 : 1);
            const nodeId = this.editor.addNode(
                s.id, inputs, outputs, pos.x, pos.y, `wb-node-${s.type}`, { step: s }, this.nodeHtml(s)
            );
            idMap[s.id] = nodeId;
        });

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
    }

    hasOutgoing(stepId, steps) {
        return steps.some((s) => s.if_true === stepId || s.if_false === stepId || (s.body || []).includes(stepId));
    }

    // ── Node rendering ──

    stepTitle(step) {
        if (step.type === 'tool') return step.tool || 'Select a tool';
        return STEP_TYPE_LABEL[step.type] || step.type;
    }

    stepSubtitle(step) {
        if (step.type === 'tool') return step.tool ? summarizeArgs(step.args) : 'No tool selected';
        if (step.type === 'workflow') return step.workflow_name || 'No workflow selected';
        if (step.type === 'trigger') return step.trigger_kind || 'doctype_event';
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
        if (type === 'trigger') Object.assign(step, { trigger_kind: 'doctype_event' });
        if (type === 'workflow') Object.assign(step, { workflow_name: '', input_mapping: {}, continue_on_fail: false });

        const inputs = (type === 'note' || type === 'trigger') ? 0 : 1;
        const outputs = type === 'branch' ? 2 : (type === 'note' ? 0 : 1);
        const nodeId = this.editor.addNode(id, inputs, outputs, x, y, `wb-node-${type}`, { step }, this.nodeHtml(step));
        this.selectNode(nodeId);
        this.updateCanvasOverlay(false);
        this.markDirty();
    }

    selectNode(nodeId) {
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
        // Mirrors n8n's node-panel categories, scoped to what actually
        // exists here: AI (agent delegation), Approval (human_approval
        // needs its own bucket — it's neither AI nor a plain CRUD tool),
        // Core (everything else, mostly the frappe_* tools).
        const groups = { AI: [], Approval: [], Core: [] };
        this.tools.forEach((t) => {
            if (t === 'delegate_task') groups.AI.push(t);
            else if (t === 'human_approval') groups.Approval.push(t);
            else groups.Core.push(t);
        });
        return groups;
    }

    renderToolEditor($panel, step, node) {
        const groups = this.groupToolsForSelect();
        const optgroupsHtml = Object.entries(groups)
            .filter(([, tools]) => tools.length)
            .map(([label, tools]) => {
                const opts = tools.map((t) => `<option value="${t}" ${t === step.tool ? 'selected' : ''}>${t}</option>`).join('');
                return `<optgroup label="${label}">${opts}</optgroup>`;
            })
            .join('');
        $panel.append(`
            <div class="wb-field">
                <label>Tool</label>
                <select class="form-control wb-tool-select"><option value="">Choose a tool…</option>${optgroupsHtml}</select>
            </div>
        `);

        $panel.find('.wb-tool-select').on('change', (e) => {
            step.tool = e.target.value;
            const schema = this.toolSchemas && this.toolSchemas[step.tool];
            step.args = this.generateDefaultArgs(schema);
            this.updateNodeLabel(node, step);
            this.renderSidebar(node);
            this.markDirty();
        });

        // Known tools get a purpose-built editor instead of raw JSON args.
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

        $panel.append(`
            <div class="wb-field">
                <label>Args <span class="wb-hint-inline">supports {{output.field}}</span></label>
                <div class="wb-hint wb-hint-ok">${esc(paramHint)}</div>
                <textarea class="form-control wb-args wb-code" rows="8">${esc(JSON.stringify(step.args || {}, null, 2))}</textarea>
                <div class="wb-hint wb-hint-ok">Must be valid JSON.</div>
            </div>
            <div class="wb-field">
                <button class="btn btn-xs btn-default wb-test-step">
                    <i class="fa fa-play"></i> Test this step
                </button>
                <div class="wb-hint wb-test-output" style="display:none;"></div>
            </div>
        `);

        $panel.find('.wb-args').on('input', (e) => {
            try {
                step.args = JSON.parse(e.target.value);
                this.editor.updateNodeDataFromId(node.id, { step });
                this.updateNodeLabel(node, step);
                this.markDirty();
            } catch (err) {
                // invalid json — leave step.args as last-valid until fixed
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
                <label>Task <span class="wb-hint-inline">supports {{output.field}}</span></label>
                <textarea class="form-control wb-delegate-task-text" rows="5">${esc(step.args.task || '')}</textarea>
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

    async renderTriggerEditor($panel, step, node) {
        // step.agent_trigger holds the linked Agent Trigger's docname
        // once saved. Until then, the node is an unlinked placeholder —
        // it must be linked (existing or newly created) before the
        // workflow can actually be fired by anything.
        const $mount = $('<div class="wb-trigger-editor"></div>').appendTo($panel);
        $mount.html('<div class="wb-hint">Loading triggers…</div>');

        let existing = [];
        try {
            const res = await frappe.call(`${MODULE_PATH}.get_workflow_triggers`, { workflow_name: this.workflowName });
            existing = res.message || [];
        } catch (err) {
            existing = [];
        }

        if (step.agent_trigger) {
            await this.renderTriggerFormMode($mount, step, node, existing);
        } else {
            this.renderTriggerPickMode($mount, step, node, existing);
        }
    }

    renderTriggerPickMode($mount, step, node, existing) {
        const options = existing
            .map((t) => `<option value="${t.name}">${esc(t.trigger_name)} (${t.trigger_type})</option>`)
            .join('');
        $mount.html(`
            <div class="wb-field">
                <label>Agent Trigger</label>
                <select class="form-control wb-trigger-pick">
                    <option value="">+ Create new…</option>
                    ${options}
                </select>
                <div class="wb-hint">Not yet saved to Save the workflow — this node needs a linked Agent Trigger before anything can actually fire it.</div>
            </div>
        `);
        $mount.find('.wb-trigger-pick').on('change', async (e) => {
            const val = e.target.value;
            if (!val) {
                await this.renderTriggerFormMode($mount, step, node, existing);
                return;
            }
            step.agent_trigger = val;
            const detail = await frappe.call(`${MODULE_PATH}.get_trigger`, { trigger_name: val });
            step.trigger_kind = this.triggerTypeToKind(detail.message.trigger_type);
            this.editor.updateNodeDataFromId(node.id, { step });
            this.updateNodeLabel(node, step);
            this.markDirty();
            await this.renderTriggerFormMode($mount, step, node, existing, detail.message);
        });
    }

    triggerTypeToKind(triggerType) {
        return { 'DocType Event': 'doctype_event', Scheduled: 'schedule', Webhook: 'webhook', MCP: 'mcp' }[triggerType] || 'doctype_event';
    }

    kindToTriggerType(kind) {
        return { doctype_event: 'DocType Event', schedule: 'Scheduled', webhook: 'Webhook', mcp: 'MCP' }[kind] || 'DocType Event';
    }

    async renderTriggerFormMode($mount, step, node, existing, detail) {
        const isNew = !step.agent_trigger;
        const t = detail || {
            trigger_name: '',
            is_enabled: 1,
            trigger_type: 'DocType Event',
            doctype_name: '',
            doctype_event: 'after_insert',
            cron_expression: '',
            webhook_token: '',
            run_as_user: 'Administrator',
            input_template: '',
            condition: '',
        };

        const typeOptions = ['DocType Event', 'Scheduled', 'Webhook', 'MCP']
            .map((v) => `<option value="${v}" ${v === t.trigger_type ? 'selected' : ''}>${v}</option>`)
            .join('');
        const eventOptions = ['after_insert', 'on_update', 'on_submit', 'on_cancel', 'on_trash']
            .map((v) => `<option value="${v}" ${v === t.doctype_event ? 'selected' : ''}>${v}</option>`)
            .join('');

        $mount.html(`
            ${!isNew ? '<button class="btn btn-xs btn-default wb-trigger-unlink" style="margin-bottom:10px;"><i class="fa fa-chain-broken"></i> Pick a different trigger</button>' : ''}
            <div class="wb-field">
                <label>Trigger Name</label>
                <input class="form-control wb-t-name" value="${esc(t.trigger_name)}" ${isNew ? '' : 'disabled'} placeholder="e.g. new-lead-followup" />
            </div>
            <div class="wb-field">
                <div class="checkbox"><label><input type="checkbox" class="wb-t-enabled" ${t.is_enabled ? 'checked' : ''}> Enabled</label></div>
            </div>
            <div class="wb-field">
                <label>Trigger Type</label>
                <select class="form-control wb-t-type">${typeOptions}</select>
            </div>
            <div class="wb-t-doctype-fields" style="${t.trigger_type === 'DocType Event' ? '' : 'display:none;'}">
                <div class="wb-field">
                    <label>DocType</label>
                    <input class="form-control wb-t-doctype" value="${esc(t.doctype_name || '')}" placeholder="Start typing a DocType name…" list="wb-doctype-list" />
                    <datalist id="wb-doctype-list"></datalist>
                </div>
                <div class="wb-field">
                    <label>Event</label>
                    <select class="form-control wb-t-event">${eventOptions}</select>
                </div>
            </div>
            <div class="wb-t-cron-fields" style="${t.trigger_type === 'Scheduled' ? '' : 'display:none;'}">
                <div class="wb-field">
                    <label>Cron Expression</label>
                    <input class="form-control wb-t-cron wb-code" value="${esc(t.cron_expression || '')}" placeholder="0 * * * *" />
                </div>
            </div>
            <div class="wb-t-webhook-fields" style="${t.trigger_type === 'Webhook' ? '' : 'display:none;'}">
                <div class="wb-field">
                    <label>Webhook Token</label>
                    <input class="form-control wb-code" value="${esc(t.webhook_token || 'generated on save')}" readonly />
                    <div class="wb-hint">Required in the webhook call's payload to authorize it.</div>
                </div>
            </div>
            <div class="wb-field">
                <label>Run As User</label>
                <input class="form-control wb-t-user" value="${esc(t.run_as_user || 'Administrator')}" />
            </div>
            <div class="wb-field">
                <label>Input Template <span class="wb-hint-inline">Jinja, rendered into the workflow's initial_input</span></label>
                <textarea class="form-control wb-t-input-template wb-code" rows="4">${esc(t.input_template || '')}</textarea>
            </div>
            <div class="wb-field">
                <label>Condition (optional)</label>
                <input class="form-control wb-t-condition wb-code" value="${esc(t.condition || '')}" placeholder='e.g. doc.status == "Overdue"' />
            </div>
            <button class="btn btn-sm btn-primary wb-t-save"><i class="fa fa-check"></i> ${isNew ? 'Create Trigger' : 'Save Trigger'}</button>
        `);

        if (t.doctype_name === undefined) {
            // no-op — placeholder to keep lint happy about unused var patterns
        }

        // Lazy doctype search, debounced-ish via input event.
        $mount.find('.wb-t-doctype').on('input', async (e) => {
            const txt = e.target.value;
            if (txt.length < 2) return;
            const res = await frappe.call(`${MODULE_PATH}.search_doctypes`, { txt });
            const $list = $mount.find('#wb-doctype-list');
            $list.empty();
            (res.message || []).forEach((name) => $list.append(`<option value="${esc(name)}"></option>`));
        });

        $mount.find('.wb-t-type').on('change', (e) => {
            const val = e.target.value;
            $mount.find('.wb-t-doctype-fields').toggle(val === 'DocType Event');
            $mount.find('.wb-t-cron-fields').toggle(val === 'Scheduled');
            $mount.find('.wb-t-webhook-fields').toggle(val === 'Webhook');
        });

        if (!isNew) {
            $mount.find('.wb-trigger-unlink').on('click', () => {
                step.agent_trigger = null;
                this.editor.updateNodeDataFromId(node.id, { step });
                this.renderTriggerPickMode($mount, step, node, existing);
            });
        }

        $mount.find('.wb-t-save').on('click', async () => {
            const triggerType = $mount.find('.wb-t-type').val();
            const payload = {
                name: step.agent_trigger || undefined,
                trigger_name: $mount.find('.wb-t-name').val() || step.id,
                is_enabled: $mount.find('.wb-t-enabled').is(':checked') ? 1 : 0,
                trigger_type: triggerType,
                doctype_name: $mount.find('.wb-t-doctype').val() || null,
                doctype_event: $mount.find('.wb-t-event').val() || null,
                cron_expression: $mount.find('.wb-t-cron').val() || null,
                run_as_user: $mount.find('.wb-t-user').val() || 'Administrator',
                input_template: $mount.find('.wb-t-input-template').val() || '',
                condition: $mount.find('.wb-t-condition').val() || null,
            };
            try {
                const res = await frappe.call(`${MODULE_PATH}.save_workflow_trigger`, {
                    workflow_name: this.workflowName,
                    trigger_data: JSON.stringify(payload),
                });
                step.agent_trigger = res.message.name;
                step.trigger_kind = this.triggerTypeToKind(res.message.trigger_type);
                this.editor.updateNodeDataFromId(node.id, { step });
                this.updateNodeLabel(node, step);
                this.markDirty();
                frappe.show_alert({ message: 'Trigger saved', indicator: 'green' });
                const refreshed = await frappe.call(`${MODULE_PATH}.get_trigger`, { trigger_name: step.agent_trigger });
                await this.renderTriggerFormMode($mount, step, node, existing, refreshed.message);
            } catch (err) {
                frappe.msgprint('Could not save this trigger — check required fields (Trigger Name, Input Template).');
            }
        });
    }

    renderWorkflowStepEditor($panel, step, node) {
        const options = this.workflowNames
            .filter((w) => w.name !== this.workflowName)
            .map((w) => `<option value="${w.name}" ${w.name === step.workflow_name ? 'selected' : ''}>${esc(w.workflow_name || w.name)}</option>`)
            .join('');
        $panel.append(`
            <div class="wb-field">
                <label>Workflow to call</label>
                <select class="form-control wb-subworkflow-select"><option value="">Choose a workflow…</option>${options}</select>
                <div class="wb-hint">Depth-limited to 3 levels of nested sub-workflow calls.</div>
            </div>
            <div class="wb-field">
                <label>Input Mapping <span class="wb-hint-inline">supports {{output.field}}</span></label>
                <textarea class="form-control wb-input-mapping wb-code" rows="6">${esc(JSON.stringify(step.input_mapping || {}, null, 2))}</textarea>
                <div class="wb-hint">Leave as <code>{}</code> to pass this step's entire current output through unchanged.</div>
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
            try {
                step.input_mapping = JSON.parse(e.target.value);
                this.editor.updateNodeDataFromId(node.id, { step });
                this.markDirty();
            } catch (err) {
                // invalid json
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

    // ── Execution: Run button, per-node status pips, approval dialog ──

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
                options: options.join('\n'),
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
        const steps = nodes.map((n) => Object.assign({}, n.data.step, { position: { x: n.pos_x, y: n.pos_y } }));
        return steps;
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
                    await frappe.call(`${MODULE_PATH}.save_workflow_steps`, {
                        workflow_name: this.workflowName,
                        steps: JSON.stringify(steps),
                    });
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

        await frappe.call(`${MODULE_PATH}.save_workflow_steps`, {
            workflow_name: this.workflowName,
            steps: JSON.stringify(steps),
        });
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

            /* Node shell — n8n-style: the Drawflow node box is locked to
               EXACTLY the icon square's size (72x72). Labels are pulled
               out of that box via absolute positioning (top:100%) so
               they never affect how tall Drawflow thinks the node is —
               that's what previously made the ports drift depending on
               label text length. Ports can now just use top:50%,
               unconditionally correct regardless of label content. */
            #wb-drawflow .drawflow-node { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; width: 72px !important; height: 72px !important; }
            #wb-drawflow .drawflow-node .drawflow_content_node { background: transparent !important; border: none !important; width: 100% !important; height: 100% !important; padding: 0 !important; overflow: visible !important; }

            .wb-node-wrap { position: relative; width: 72px; height: 72px; }
            .wb-node-inner { position: relative; width: 100%; height: 100%; border-radius: 18px; background: var(--fg-color); border: 1px solid var(--border-color); box-shadow: 0 2px 5px rgba(0,0,0,0.10), 0 0 0 1px rgba(0,0,0,0.02); display: flex; align-items: center; justify-content: center; transition: box-shadow 150ms, border-color 150ms, transform 100ms; }
            #wb-drawflow .drawflow-node.selected .wb-node-inner { border-color: var(--primary) !important; box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 25%, transparent), 0 4px 14px rgba(36,144,239,0.25) !important; }
            #wb-drawflow .drawflow-node:hover .wb-node-inner { box-shadow: 0 4px 10px rgba(0,0,0,0.14); }

            .wb-node-icon-lg { width: 100%; height: 100%; border-radius: 18px; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 27px; box-shadow: inset 0 1px 0 rgba(255,255,255,0.18), inset 0 -6px 10px rgba(0,0,0,0.12); }

            /* Absolutely positioned below the fixed-size node box — out
               of Drawflow's own layout flow entirely, purely decorative. */
            .wb-node-labels { position: absolute; top: 100%; left: 50%; transform: translateX(-50%); width: 150px; margin-top: 8px; text-align: center; pointer-events: none; }
            .wb-node-label-below { font-size: 12.5px; font-weight: 600; color: var(--text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .wb-node-sub-below { font-size: 10.5px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 1px; }
            .wb-node-meta { margin-top: 4px; font-size: 10px; color: var(--text-muted); display: flex; align-items: center; justify-content: center; gap: 4px; }
            .wb-node-badges { position: absolute; bottom: -5px; right: -5px; display: flex; gap: 3px; }
            .wb-mini-badge { color: #fff; font-size: 8px; padding: 1px 4px; border-radius: 4px; font-weight: bold; }
            .wb-badge-err { background: var(--red-500); }
            .wb-badge-retry { background: var(--blue-500); }

            /* Corner status pip — set by markNodeStatus() after a Run */
            .wb-status-pip { position: absolute; top: -6px; left: -6px; width: 17px; height: 17px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 8px; border: 2px solid var(--fg-color, #fff); opacity: 0; transition: opacity 120ms; z-index: 2; }
            .wb-status-pip.wb-pip-success { opacity: 1; background: var(--green-500); }
            .wb-status-pip.wb-pip-error { opacity: 1; background: var(--red-500); }
            .wb-status-pip.wb-pip-paused { opacity: 1; background: var(--orange-500); }

            /* Trigger nodes get a distinct rounded-flag shape, no left port */
            .wb-node-trigger-shape { border-radius: 8px 26px 26px 8px; }
            #wb-drawflow .wb-node-trigger .input { display: none !important; }

            /* Branch — TRUE/FALSE tags shown as a small centered row under the subtitle */
            .wb-branch-rows { margin-top: 4px; display: flex; gap: 6px; justify-content: center; }
            .wb-branch-tag { font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: 4px; }
            .wb-branch-tag.wb-true { background: var(--green-100, #c6f6d5); color: var(--green-700, #276749); }
            .wb-branch-tag.wb-false { background: var(--red-100, #fed7d7); color: var(--red-700, #9b2c2c); }

            /* Note Node (n8n style) — unlike other nodes, this one keeps
               its full card body since it's freeform text, not a fixed icon. */
            #wb-drawflow .wb-node-note { width: 300px; background: var(--yellow-100, #fff9c4); border: 1px dashed var(--yellow-500, #ecc94b); border-radius: 8px; padding: 12px; font-size: 13px; color: var(--text-color); box-shadow: none; }
            #wb-drawflow .wb-node-note .wb-node-note-body { white-space: pre-wrap; word-wrap: break-word; }

            /* Ports — the node box is now exactly the icon's size, so
               top:50% is unconditionally correct; no more fixed-px math
               that broke depending on label length. */
            #wb-drawflow .drawflow-node .input, #wb-drawflow .drawflow-node .output { width: 14px !important; height: 14px !important; background: var(--fg-color) !important; border: 2px solid var(--text-muted) !important; border-radius: 50% !important; top: 50% !important; transform: translateY(-50%) !important; }
            #wb-drawflow .drawflow-node .input { left: -7px !important; }
            #wb-drawflow .drawflow-node .output { right: -7px !important; }
            #wb-drawflow .wb-node-branch .output_1 { top: 38% !important; }
            #wb-drawflow .wb-node-branch .output_2 { top: 62% !important; }
        `;
        document.head.appendChild(style);
    }
}