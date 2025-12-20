from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv()

api = os.getenv("MY_SECRET_KEY")


Client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key="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",
)

def client(tools=None, messages=None, model="nex-agi/deepseek-v3.1-nex-n1:free"):
    response = Client.chat.completions.create(
      model=model,
      messages=messages,
    #   extra_body={"reasoning": {"enabled": True}},
      tool_choice="auto" if tools else None,
      tools=tools
    )
    return response