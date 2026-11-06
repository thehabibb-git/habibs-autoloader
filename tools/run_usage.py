"""Token use and time per AI step for one Habib's Autoloader run.

Export a finished execution from n8n as JSON (with its data), then:
    python tools/run_usage.py execution.json
It prints each model call's tokens and run time, and totals for the writing model (Sonnet nodes)
and the planning/auditing model (Grok nodes). Multiply by OpenRouter's current prices for a cost.
"""
import json
import re
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
runs = (d.get("data") or d)["resultData"]["runData"]
totals = {}
for name, node_runs in runs.items():
    for r in node_runs:
        s = json.dumps(r.get("data", {}))
        prompt = sum(int(x) for x in re.findall(r'"promptTokens":\s*(\d+)', s))
        completion = sum(int(x) for x in re.findall(r'"completionTokens":\s*(\d+)', s))
        cost = re.findall(r'"cost":\s*([\d.]+)', s)
        if not (prompt or completion or cost):
            continue
        print(f"{name:32} {r.get('executionTime', 0) / 1000:6.1f}s  in {prompt:7,}  out {completion:6,}" + (f"  billed ${float(cost[0]):.4f}" if cost else ""))
        model = "writer (Sonnet)" if "Sonnet" in name else "planner/auditor (Grok)" if "Grok" in name else "web search"
        t = totals.setdefault(model, [0, 0])
        t[0] += prompt
        t[1] += completion
print()
for model, (i, o) in totals.items():
    print(f"{model:24} tokens in {i:8,}  out {o:7,}")
