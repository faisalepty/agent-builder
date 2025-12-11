

def clean_state(messages):
    new_hist = []
    for message in messages:
        if not message.get("role", None) == "system":
            new_hist.append(message)
    return new_hist