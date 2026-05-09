import os
from openai import OpenAI

class LLM:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1"
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate(self, messages, tools=None, model="openai/gpt-oss-120b:free", temperature=0.7):
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature
        )
        return response.choices[0].message