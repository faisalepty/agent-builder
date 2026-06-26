VIEW_SKILL = {
    "name": "view_skill",
    "description": (
        "Fetch a Skill document by name. "
        "Returns all fields of the Skill document."
    ),
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
    "description": (
        "List Skill documents with optional limit. "
        "Returns name and description of each Skill."
    ),
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