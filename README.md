# Agent Builder

A Frappe/ERPNext co-pilot powered by **Hermes agent**. Build dynamic Dashboards, Workspaces, and DocTypes through intelligent conversation. Real-time chat interface with streaming AI responses and multi-tool orchestration.

## Features

- **Hermes Agent Integration** — Advanced AI agent framework with streaming responses and reasoning
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
```

## Configuration

### Environment Variables

Set these in your site's `site_config.json`:

```json
{
  "openrouter_api_key": "your-openrouter-key"
}
```

Or export as environment variable:
```bash
export OPENROUTER_API_KEY="your-openrouter-key"
```

## API Usage

### Start a New Chat

```python
frappe.call({
  'method': 'agent_builder.api.agent.new_chat',
  'args': {
    'title': 'Create Sales Dashboard',
    'message': 'Build me a dashboard showing monthly revenue'
  },
  'callback': function(r) {
    console.log(r.message.chat_id);
  }
})
```

### Send a Message

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

### Get Chat Messages

```python
frappe.call({
  'method': 'agent_builder.api.agent.get_messages',
  'args': {
    'chat_id': 'your-chat-id',
    'limit': 50
  },
  'callback': function(r) {
    console.log(r.message.messages);
  }
})
```

## Architecture

### API Layer (`agent_builder/api/`)

- **`agent.py`** — Main chat endpoints using Hermes agent with Frappe tools
- **`agent_test.py`** — Testing endpoint for quick agent invocation

### Hermes Integration (`.hermes/`)

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
- Use for reference; current production uses Hermes API

## Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it:

```bash
cd apps/agent_builder
pre-commit install
```

Pre-commit checks with:
- **ruff** — Python linting and formatting
- **eslint** — JavaScript linting
- **prettier** — Code formatting
- **pyupgrade** — Python syntax upgrades

## Technology Stack

- **Python 84.3%** — Frappe integration, agent orchestration
- **JavaScript 9.4%** — Desk UI and real-time updates
- **CSS 6.3%** — Chat interface styling

## License

MIT
