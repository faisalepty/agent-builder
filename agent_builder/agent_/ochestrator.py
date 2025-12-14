from .ai_client import client
from .tools_plugin import agent_tools as tools
from .tools import tool_validate_payload, tool_agent_create, tool_doctype_exists, tool_role_exists
import json

def entry1(prompt):
    messages=[
        {"role":"system", "content":"You are an expert Frappe/ERPNext developer."},
        {"role":"user", "content":prompt}
    ]
    print("Generating JSON...")
    message, create_json_call = generate_json(prompt)
    json_payload = json.loads(create_json_call.choices[0].message.content)
    print("Generated JSON:", json_payload)
    print("Validating JSON...")
    validate_json_call = validate_json(json_payload, tools, messages=messages)
    print("Validation result:", validate_json_call.choices[0].message)
    for tool_call in validate_json_call.choices[0].message.tool_calls:
         print(tool_call.id, "ttool callllsss \n", tool_call.function.name)
         if tool_call.function.name == "tool_validate_payload":
            tool_result = tool_validate_payload(json_payload)
            print("Tool result:", tool_result,)
            messages.append({"role":"function", "tool_call_id":tool_call.id, "content": str(tool_result)})
            validate_json_call = validate_json(json_payload, tools, messages=messages)
            print("Post-tool Validation result:", validate_json_call.choices[0].message)
    print(messages)

    return

def entry(prompt):
    messages=[]
    
    while True:
        print("Generating JSON...")
        message, create_json_call = generate_json(prompt)
        json = create_json_call.choices[0].message.content
        messages.append({"role":"user", "content":prompt})
        messages.append({"role":"assistant", "content":json})
        print("Generated JSON:", json)
        print("Validating JSON...")
        validate_json_call = validate_json(json, tools, messages=messages)
        print("Validation result:", validate_json_call.choices[0].message)
        print("ttoooolllllllllsss \n", validate_json_call.choices[0].message.tool_calls)
        if validate_json_call.choices[0].message.tool_calls:
            for tool_call in validate_json_call.choices[0].message.tool_calls:
                if tool_call.function.name == "tool_validate_payload":
                    tool_result = tool_validate_payload(json)
                    messages.append({"role":"function", "tool_call_id":tool_call.id, "content": str(tool_result)})
                    validate_json_call = validate_json(json, tools, messages=messages)
                    if validate_json_call.choices[0].message.content == "Valid":
                        create_doctype_call = create_doctype(json, tools, messages=messages)
                        if create_doctype_call.choices[0].message.tool_calls:
                            for tool_call in create_doctype_call.choices[0].message.tool_calls:
                                if tool_call.function.name == "tool_agent_create":
                                    tool_result = tool_agent_create(json, dry_run=False)
                                    messages.append({"role":"function", "tool_call_id":tool_call.id, "content": str(tool_result)})
                                    create_doctype_call = create_doctype(json, tools, messages=messages)
                                    if create_doctype_call.choices[0].message.content == "success":
                                        print("Created DocType:", create_doctype_call.choices[0].message.content)
                                        return
                                    else:
                                        print("Error creating DocType:", create_doctype_call.choices[0].message.content)
                                        return
        elif validate_json_call.choices[0].message.content == "Valid":
                        create_doctype_call = create_doctype(json, tools, messages=messages)
                        if create_doctype_call.choices[0].message.tool_calls:
                            for tool_call in create_doctype_call.choices[0].message.tool_calls:
                                if tool_call.function.name == "tool_agent_create":
                                    tool_result = tool_agent_create(json, dry_run=False)
                                    messages.append({"role":"function", "tool_call_id":tool_call.id, "content": str(tool_result)})
                                    create_doctype_call = create_doctype(json, tools, messages=messages)
                                    if create_doctype_call.choices[0].message.content == "success":
                                        print("Created DocType:", create_doctype_call.choices[0].message.content)
                                        return
                                    else:
                                        print("Error creating DocType:", create_doctype_call.choices[0].message.content)
                                        return   

                        print("Created DocType:", create_doctype_call.choices[0].message.content)
                        return

    return

def validate_json(json, tools, messages=None):
    s_prompt = (
         
        "You are an expert Frappe/ERPNext developer.\n"
        "You also have access to a tool that can validate JSON payloads for creating Frappe DocTypes.\n"
        "### Rules:\n"
        "1. Ensure all required fields are present.\n"
        "2. Check that field types and options are valid.\n"
        "3. Verify naming conventions and structure.\n"
        "4. Respond with 'Valid' if the JSON is correct, otherwise list the errors.\n"
        "5. If the JSON is valid AND you already received tool results → DO NOT call tool_validate_payload again. Respond with 'Valid' only.\n"
    )
    prompt = f"Validate the following JSON payload for creating a Frappe DocType:{json}\n"
    messages.append(
        {"role": "system", "content": s_prompt}
    )
    messages.append(
        {"role": "user", "content": prompt}
    )
    response = client(prompt=prompt, s_prompt=s_prompt, tools=tools, messages=messages)
    return response

def create_doctype(json, tools, messages=None):
    s_prompt = (
        "You are an expert Frappe/ERPNext developer.\n"
        "you also have access to a tool that can create Frappe DocTypes from JSON payloads.\n"
        "### Rules:\n"
        "1. Follow the JSON structure strictly.\n"
        "2. Include all required fields and their properties.\n"
        "3. Do not add any extra fields or metadata.\n"
        "4. Confirm creation success with a 'success' if creation is unsuccessful respond with '[error, <error message>, [errors]]'. DO NOT INCLUDE ANYTHING ELSE\n"
    )
    prompt = f"Create the following Frappe DocType from this JSON payload:{json}\n"
    messages.append(
        {"role": "system", "content": s_prompt}
    )
    messages.append(
        {"role": "user", "content": prompt}
    )
    response = client(prompt=prompt, s_prompt=s_prompt, tools=tools, messages=messages)
    return response



def generate_json(prompt):
    s_prompt = (
    "You are an expert Frappe/ERPNext developer.\n"
    "Generate a JSON payload for creating a valid Frappe DocType.\n\n"
    "### Rules:\n"
    "1. Output strictly valid JSON only (no markdown, no explanations).\n"
    "2. JSON must include these top-level keys:\n"
    "   - doctype = \"DocType\"\n"
    "   - name = DocType name (Title Case)\n"
    "   - module = Module name (Title Case)\n"
    "   - custom = 1\n"
    "   - autoname: use 'field:<fieldname>' if the DocType has a unique name field, or 'naming_series' if it uses a series; ensure the field referenced exists in the fields array\n"
    "   - naming_rule (if relevant)\n"
    "   - fields = [array of field objects]\n"
    "   - permissions = [array of role permissions]\n"
    "3. Each field object must include:\n"
    "   - fieldname, label, fieldtype\n"
    "   - reqd (0 or 1)\n"
    "   - in_list_view (0 or 1 if relevant)\n"
    "   - in_standard_filter (0 or 1 if relevant)\n"
    "   - default (if applicable)\n"
    "   - options (required for Select, Link, Table, Data-with-validator)\n"
    "   - precision/width/depends_on if applicable\n"
    "4. Special fieldtype rules:\n"
    "   - Link: must include 'options' with target DocType\n"
    "   - Select: 'options' must be newline-separated values\n"
    "   - Table: 'options' must be the child DocType name\n"
    "   - Data: may use 'options' for validators like Email, Phone\n"
    "5. If the DocType represents a transactional record (like invoices, orders, service records), include:\n"
    "   - is_submittable = 1\n"
    "   - permissions may include submit, cancel, amend.\n"
    "6. Always include a 'permissions' list with System Manager having full rights (read, write, create, delete, submit, cancel, amend, report, import, export, email, print).\n"
    "7. Do not add explanations, comments, or text outside the JSON.\n\n"
)
    messages=[
        {"role": "system", "content": s_prompt},
        {"role": "user", "content": prompt}
    ]
    response = client(s_prompt, prompt, messages=messages)
    return messages, response
