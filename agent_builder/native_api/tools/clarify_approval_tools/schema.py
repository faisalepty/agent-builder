human_approval = {
    "name": "human_approval",
    "description": (
        "Pause the current workflow run for a human decision, notifying "
        "the approver via the selected channel. Only meaningful inside a "
        "workflow's Tool step — used from a plain agent conversation, "
        "this just sends the notification and returns a marker with no "
        "further effect (there's no workflow engine there to pause)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "enum": ["Desk", "Email", "Both"],
                "description": "Where to notify the approver(s).",
            },
            "message": {
                "type": "string",
                "description": "Shown to the approver alongside the current workflow output.",
            },
            "approvers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "User emails/ids to notify. Defaults to the running user if omitted.",
            },
        },
        "required": ["channel", "message"],
    },
}