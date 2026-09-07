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

request_clarification = {
    "name": "request_clarification",
    "description": (
        "Pause the current turn to ask the user a genuine clarifying "
        "question before continuing — for real ambiguity a tool call "
        "can't resolve (two same-named records, an undefined date range, "
        "several plausible interpretations of the request), not as a "
        "substitute for looking things up. The user's answer comes back "
        "as this tool's result on the next turn; read it and continue."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": (
                    "The actual question, in plain language. One sentence, "
                    "naming the specific fork (e.g. 'Acme Ltd or Acme "
                    "Distribution Ltd — which customer?'), not a vague "
                    "'can you clarify?'."
                ),
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "2-5 short, concrete answers the user can tap instead "
                    "of typing. Provide these whenever the ambiguity has a "
                    "genuinely small set of resolutions. Omit entirely for "
                    "open-ended questions with no natural short list."
                ),
            },
            "allow_free_text": {
                "type": "boolean",
                "description": (
                    "Whether a typed answer is accepted alongside/instead "
                    "of the options. Defaults to true when options is "
                    "omitted, false when options are given — set true "
                    "explicitly if the options are just shortcuts and a "
                    "different typed answer should still work."
                ),
            },
        },
        "required": ["question"],
    },
}