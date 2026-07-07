#!/usr/bin/env python3

import re
import sys
from collections import defaultdict

PATTERN = re.compile(
    r"\[(?P<session>[^\]]+)\].*?API call #\d+:.*?"
    r"in=(?P<input>\d+)\s+"
    r"out=(?P<output>\d+)\s+"
    r"total=(?P<total>\d+).*?"
    r"cache=(?P<cached>\d+)/(?P<cache_total>\d+)"
)

sessions = defaultdict(lambda: {
    "calls": 0,
    "input": 0,
    "output": 0,
    "total": 0,
    "cached": 0,
    "uncached": 0,
})

if len(sys.argv) != 2:
    print(f"Usage: {sys.argv[0]} logfile")
    sys.exit(1)

with open(sys.argv[1], "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        m = PATTERN.search(line)
        if not m:
            continue

        session = m.group("session")

        input_tokens = int(m.group("input"))
        output_tokens = int(m.group("output"))
        total_tokens = int(m.group("total"))
        cached_tokens = int(m.group("cached"))

        sessions[session]["calls"] += 1
        sessions[session]["input"] += input_tokens
        sessions[session]["output"] += output_tokens
        sessions[session]["total"] += total_tokens
        sessions[session]["cached"] += cached_tokens
        sessions[session]["uncached"] += max(0, input_tokens - cached_tokens)

print("\n=== HERMES TOKEN USAGE ===\n")

grand = {
    "calls": 0,
    "input": 0,
    "output": 0,
    "total": 0,
    "cached": 0,
    "uncached": 0,
}

for session, data in sorted(sessions.items()):
    print(f"Session: {session}")
    print(f"  API Calls            : {data['calls']}")
    print(f"  Input Tokens         : {data['input']:,}")
    print(f"  Output Tokens        : {data['output']:,}")
    print(f"  Total Tokens         : {data['total']:,}")
    print(f"  Cached Prompt Tokens : {data['cached']:,}")
    print(f"  Actual Prompt Tokens : {data['uncached']:,}")

    if data["input"]:
        hit_rate = data["cached"] / data["input"] * 100
        print(f"  Cache Hit Rate       : {hit_rate:.2f}%")

    print()

    for k in grand:
        grand[k] += data[k]

print("=== GRAND TOTAL ===")
print(f"API Calls            : {grand['calls']}")
print(f"Input Tokens         : {grand['input']:,}")
print(f"Output Tokens        : {grand['output']:,}")
print(f"Total Tokens         : {grand['total']:,}")
print(f"Cached Prompt Tokens : {grand['cached']:,}")
print(f"Actual Prompt Tokens : {grand['uncached']:,}")

if grand["input"]:
    print(
        f"Cache Hit Rate       : "
        f"{grand['cached']/grand['input']*100:.2f}%"
    )


{
  "name_": "Kenyan Audit Support",
  "domain": "Finance",
  "description": "Supports ICFR, CMA Kenya, and statutory audit compliance with control testing methodology, sample selection, and documentation standards for Frappe/ERPNext, including tool-driven evidence gathering.",
  "is_enabled": 1,
  "disable_model_invocation": 1,
  "argument_hint": "control area or account to test (e.g. 'revenue cut-off', 'VAT/eTIMS controls', 'JE approval', 'AR aging')",
  "parent_skill": "",
  "reference_slug": "",
  "attach": "",
  "server_script": "",
  "metadata": {
    "country": "Kenya",
    "regulatory_bodies": ["CMA", "ICPAK", "KRA", "ODPC", "SHA"],
    "frameworks": ["IFRS", "Companies Act 2015", "CMA Code of Corporate Governance"],
    "platform": "Frappe/ERPNext",
    "required_tools": ["frappe_get_list", "frappe_get_doc"],
    "excluded_tools": ["frappe_save_doc", "frappe_execute_action"],
    "excluded_tools_reason": "Audit testing must be non-destructive and independent of the process under test"
  }
}