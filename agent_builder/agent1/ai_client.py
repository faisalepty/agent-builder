from openai import OpenAI
import os
import json
from dotenv import load_dotenv
load_dotenv()

api = os.getenv("MY_SECRET_KEY")


Client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  # api_key="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",
  # api_key="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"
  # api_key="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"
  # api_key="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"
  api_key="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"
)



# model="google/gemini-2.0-flash-exp:free"
# model = "mistralai/devstral-2512:free"
model = "openai/gpt-oss-120b:free"

def client(tools=None, messages=None,model=model):
    response = Client.chat.completions.create(
      model=model,
      messages=messages,
    #   extra_body={"reasoning": {"enabled": True}},
      tool_choice="auto" if tools else None,
      tools=tools
    )
    print("***************************************************************************************8")
    print(f"CLIENT RESPONSE: {response}")

    print("***************************************************************************************8")

    choice = response.choices[0]
    msg = choice.message

    return {
        "role": msg.role,
        "content": msg.content,
        "tool_calls": normalize_tool_calls(msg.tool_calls) or []
    }

import json

def normalize_tool_calls(tool_calls):
    """
    Ensures tool calls match the OpenAI/Mistral spec:
    { "id": "...", "type": "function", "function": { "name": "...", "arguments": "..." } }
    """
    if not tool_calls:
        return []
    
    normalized = []
    for tc in tool_calls:
        # Extract name and arguments regardless of whether tc is an object or dict
        name = tc.function.name if hasattr(tc, 'function') else tc.get('name')
        args = tc.function.arguments if hasattr(tc, 'function') else tc.get('arguments')

        # Ensure arguments are a JSON string for the API
        if isinstance(args, dict):
            args = json.dumps(args)

        normalized.append({
            "id": tc.id if hasattr(tc, 'id') else tc.get('id'),
            "type": "function",
            "function": {
                "name": name,
                "arguments": args
            }
        })
    return normalized


