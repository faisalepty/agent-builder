from openai import OpenAI
import os
import json
from dotenv import load_dotenv
load_dotenv()

api = os.getenv("OPENAI_API_KEY")


Client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=api
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


