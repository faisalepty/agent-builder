import json
import os
import yaml
import frappe
from .llm import LLM
from pathlib import Path
from typing import TypedDict, List, Dict, Any

class State(TypedDict):
    messages: List[Dict[str, Any]]

    
class Orch:
    def __init__(self, max_steps=10):
        self.max_steps = max_steps
        self.llm = LLM()
        self.state: State = {
            "messages": []
        }
    def parse_markdown(self, path):
        with open(path, "r") as f:
            content = f.read()
        # Split front matter and content
        if content.startswith("---"):
            _, front_matter, markdown_content = content.split("---", 2)
            metadata = yaml.safe_load(front_matter)
            return metadata, markdown_content.strip()
        else:
            return {}, content.strip()
        
    def get_agent(self, name=None):
        agents_path = "/home/faisa/Desktop/mft/manufacturing/apps/agent_builder/agent_builder/agent3/AGENTS/"
        if name:
            agent_path = os.path.join(agents_path, name, "AGENT.MD" )
            with open(agent_path, "r") as agent:
                metadata, _ = self.parse_markdown(agent_path)
                return metadata
        else:
            agent_names = [d for d in os.listdir(agents_path) if os.path.isdir(os.path.join(agents_path, d))]
            agents = []
            for name in agent_names:
                agent_path = os.path.join(agents_path, name, "AGENT.MD")
                metadata, _ = self.parse_markdown(agent_path)
                agents.append(metadata)
            return agents
        
    def get_tool_schema(self, agent_metadata):
        tools = agent_metadata.get("tools", [])
        tool_schemas = []
        for tool in tools:
            tool_path = os.path.join("/home/faisa/Desktop/mft/manufacturing/apps/agent_builder/agent_builder/agent3/TOOLS/", tool, tool + ".json")
            if os.path.exists(tool_path):
                with open(tool_path, "r") as f:
                    schema = json.load(f)
                    tool_schemas.append(schema)
            else:
                print(f"Tool schema not found for {tool} at {tool_path}")
        return tool_schemas
        
    
    def format_message(self, agent_metadata, prompt):
        name = agent_metadata.get("name", "Unknown Agent")
        description = agent_metadata.get("description", "").strip()
        
        # This is the System Instructions
        system_instructions = f"You are {name}. {description}\n"
        
        # You need to return a List of Messages for OpenRouter/OpenAI
        return [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": prompt} # <--- This ensures "hello" actually reaches the AI
        ]


    import json

    def execute(self, prompt, agent_name="delegation", depth=10):
        agent_metadata = self.get_agent(agent_name)
        tools = self.get_tool_schema(agent_metadata)
        formatted_prompt = self.format_message(agent_metadata, prompt)
        
        for step in range(depth):
            response = self.llm.generate(messages=formatted_prompt, tools=tools)
            print(response)
            break
            # 1. Handle Final Content (The JSON Plan)
            if not response.tool_calls:
                content = response.content
                
                # Check if this is the Planner returning a JSON plan
                try:
                    plan = json.loads(content)
                    if "tasks" in plan:
                        results = []
                        print(f"Plan received: {plan.get('summary')}")
                        
                        # Loop through assignments and delegate to workers
                        for task in plan["tasks"]:
                            worker = task["agent"]
                            requirement = task["user_requirement"]
                            
                            print(f"Executing Task: {worker} -> {requirement}")
                            res = self.execute(requirement, agent_name=worker, depth=depth-1)
                            results.append({"agent": worker, "result": res})
                        
                        return json.dumps(results) # Return all worker results
                except:
                    # Not JSON or not a plan, just return plain text
                    return content
            
            # 2. Handle Tool Calls (Delegation/Tools)
            for tool_call in response.tool_calls:
                tool_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else tool_call.function.arguments

                if tool_name == "delegation":
                    delegate_name = args.get("agent_name")
                    delegate_prompt = args.get("prompt")
                    return self.execute(delegate_prompt, agent_name=delegate_name, depth=depth-1)
                
                # Standard Tool Execution
                return self.execute_tool(tool_name, args)

        return "Max steps reached."


    def execute_tool(self, tool_name, tool_args):
        # run tool using cli python method and return result
        tool_path = os.path.join("/home/faisa/Desktop/mft/manufacturing/apps/agent_builder/agent_builder/agent3/TOOLS/", tool_name, tool_name + ".py")
        if os.path.exists(tool_path):
            command = f"python {tool_path} '{json.dumps(tool_args)}'"
            print(f"Executing tool with command: {command}")
            result = os.system(command)
        return result

@frappe.whitelist()
def execute_orch(prompt):
    orchestrator = Orch()
    return orchestrator.execute(prompt)