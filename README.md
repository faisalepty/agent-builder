# Agent Builder

A Frappe/ERPNext co-pilot and autonomous agents system. Build dynamic Dashboards, Workspaces, and DocTypes through intelligent conversation. Real-time chat interface with streaming AI responses and multi-tool orchestration.

## Features

- **Autonomous Agent Integration** — Advanced AI agent framework with streaming responses and reasoning
- **Frappe Tools Plugin** — Direct CRUD operations on Frappe documents (read, list, save, delete)
- **Real-time Chat** — WebSocket-powered conversation with live token streaming
- **Multi-agent Orchestration** — Supervisor agent routing to specialized workers
- **Dynamic Content Creation** — Generate Dashboards, Charts, Workspaces, and DocTypes via conversation
- **Skill-based Architecture** — Modular skills for Frappe Dashboard, Charts, and Workspaces management

## Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/unofaisal/agent-builder.git --branch develop
bench install-app agent_builder

# Install hermes-agent python package in your bench environment
./env/bin/pip3 install hermes-agent
```

## Configuration & Setup

Once installed, you need to configure the AI agent before the chat widget becomes active:

1. **Role Access**: Create a specific role (or use an existing one) for users who need access to the AI Chat. Assign this role to the desired users.
2. **Agent Setup**: In your ERPNext/Frappe workspace, search for the **Agent Setup** doctype and configure it:
   - **Allowed Role**: Select the role you created in step 1.
   - **Agent Name**: Give your AI a name (e.g., "ERPNext Copilot").
   - **API Key & Provider**: Create an `AI Provider` (e.g., openrouter, openai, anthropic) and paste your API key from the provider.
   - **Sync & Select Models**: Click the **Sync Models** button at the top to fetch all available models. You can then select a model from the dropdown. 
     *Tip: Check **Free Models Only** to easily find and select free models to use!*
3. **Hard Refresh**: Once saved, perform a hard refresh (`Ctrl + Shift + R` or `Cmd + Shift + R`) in your browser. The Chat icon will now appear in the bottom right corner of your screen!

## API Usage


### Send a Message
 ## This can be triggerd by email, or in any doctype event
```python
frappe.call({
  'method': 'agent_builder.api.agent.chat',
  'args': {
    'message': 'Add a number card showing total open orders',
    'chat_id': 'your-chat-id'
  },
  'callback': function(r) {
    console.log(r.message);
  }
})
```

## Architecture

### API Layer (`agent_builder/api/`)

- **`agent.py`** — Main chat endpoints using Hermes agent with Frappe tools
- **`agent_test.py`** — Testing endpoint for quick agent invocation


- **Frappe Tools Plugin** — Registers and manages Frappe CRUD tools
  - `frappe_get_doc` — Fetch single documents
  - `frappe_get_list` — Query with filters
  - `frappe_save_doc` — Create/update documents
  - `frappe_delete_doc` — Delete documents

- **Skills** — Documented agent behaviors
  - `frappe-dashboard` — Dashboard creation and management
  - `frappe-chart` — Dashboard Chart semantics
  - `frappe-workspace` — Workspace configuration and role-based visibility

### Legacy Agents (`agent_builder/agent2/`, `agent_builder/agent3/`)

- Experimental multi-agent orchestration systems

## License

MIT
