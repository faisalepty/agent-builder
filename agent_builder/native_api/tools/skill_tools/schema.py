CREATE_SKILL = {
	"name": "create_skill",
	"description": (
		"Create a new Skill document. For a top-level skill pass 'name' and "
		"'description'. For a nested (reference) skill pass 'parent_skill' and "
		"'reference_slug' instead of 'name' (the docname is derived as "
		"'{parent_skill}-{reference_slug}'). Optionally set 'content' (markdown "
		"instructions), 'domain', 'is_enabled', 'disable_model_invocation', "
		"'argument_hint', 'attach', 'server_script', or 'metadata' (JSON object)."
	),
	"parameters": {
		"type": "object",
		"properties": {
			"name": {
				"type": "string",
				"description": (
					"Display name for a top-level skill. Required when parent_skill "
					"is not set; ignored when parent_skill is set."
				),
			},
			"description": {
				"type": "string",
				"description": "A short, one-line summary of what this skill does (max 1000 chars, single line).",
			},
			"parent_skill": {
				"type": "string",
				"description": "Link to a top-level Skill to make this a nested/reference skill.",
			},
			"reference_slug": {
				"type": "string",
				"description": "Short identifier used to build '{parent_skill}-{slug}'. Required when parent_skill is set.",
			},
			"domain": {
				"type": "string",
				"enum": [
					"Finance",
					"Human Resources",
					"Legal",
					"Marketing",
					"Operations",
					"Sales",
					"Customer Support",
					"Data",
					"Design",
					"Engineering",
					"Product Management",
					"Productivity",
					"Small Business",
					"Other",
				],
				"description": "Business domain or function this skill belongs to.",
			},
			"content": {
				"type": "string",
				"description": "Markdown body — instructions, guidance, or reference material the AI sees when the skill is loaded.",
			},
			"is_enabled": {
				"type": "boolean",
				"description": "Whether the skill is available. Defaults to true.",
			},
			"disable_model_invocation": {
				"type": "boolean",
				"description": "If true, the skill won't appear in the system prompt; only shown when explicitly called (command-only / library skills).",
			},
			"argument_hint": {
				"type": "string",
				"description": "Placeholder text shown in the slash menu for command-type skills. Only used when disable_model_invocation is true.",
			},
			"attach": {
				"type": "string",
				"description": "URL of an already-uploaded attachment file (stored privately).",
			},
			"server_script": {
				"type": "string",
				"description": "Name of a Server Script DocType to make this skill executable.",
			},
			"metadata": {
				"type": "object",
				"description": "Extra key-value information (e.g. category, author, related DocTypes). Serialized to JSON.",
			},
		},
		"required": ["description"],
	},
}

VIEW_SKILL = {
	"name": "view_skill",
	"description": ("Fetch a Skill document by name. Returns all fields of the Skill document."),
	"parameters": {
		"type": "object",
		"properties": {
			"skill_name": {
				"type": "string",
				"description": "The name of the Skill document to fetch",
			},
		},
		"required": ["skill_name"],
	},
}

LIST_SKILLS = {
	"name": "list_skills",
	"description": ("List Skill documents with optional limit. Returns name and description of each Skill."),
	"parameters": {
		"type": "object",
		"properties": {
			"limit": {
				"type": "integer",
				"description": "Maximum number of Skill documents to return. Defaults to 20.",
			},
		},
		"required": [],
	},
}
