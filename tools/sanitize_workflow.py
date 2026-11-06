"""Turns an n8n export of your Habib's Autoloader workflow into a JSON that is safe to share: credential IDs,
Drive and Sheet IDs, the form's webhook ID and instance metadata are removed or replaced with
placeholders. Prompts, code and connections stay as they are.

Usage: python tools/sanitize_workflow.py <your export.json> <shareable.json>
"""
import json
import re
import sys

src = json.load(open(sys.argv[1], encoding="utf-8"))
wf = src.get("workflow", src)
changes = []
DRIVE_ID = re.compile(r"\b[0-9A-Za-z_-]{25,60}\b")

nodes = []
for n in wf["nodes"]:
    n = json.loads(json.dumps(n))
    if n.pop("webhookId", None):
        changes.append(f"{n['name']}: removed webhookId (n8n makes a new form URL on import)")
    if n.get("credentials"):
        for kind, cred in n["credentials"].items():
            n["credentials"][kind] = {"name": cred.get("name", kind)}
        changes.append(f"{n['name']}: credential IDs removed (names kept)")
    p = n.get("parameters", {})
    if n["name"] == "Config":
        for a in p.get("assignments", {}).get("assignments", []):
            new = {"sheet_url": "PASTE_YOUR_GOOGLE_SHEET_URL_HERE"}.get(a["name"], "PASTE_DRIVE_ID" if a["name"].endswith("_id") else a["value"])
            if new != a["value"]:
                changes.append(f"Config: {a['name']} -> {new}")
                a["value"] = new
    # The Project node keeps each project's Drive file IDs inside its code
    if "jsCode" in p:
        code, k = re.subn(r"((?:kb|link_map)_file_id:\s*')([^']*)(')", lambda m: m.group(1) + ("PASTE_DRIVE_FILE_ID" if m.group(2) and not m.group(2).startswith("PASTE") else m.group(2)) + m.group(3), p["jsCode"])
        if code != p["jsCode"]:
            p["jsCode"] = code
            changes.append(f"{n['name']}: project file IDs replaced")

    # Google pickers keep the chosen document as {"__rl": true, "value": "<id or url>", ...}
    def scrub(obj, path):
        if isinstance(obj, dict):
            v = obj.get("value")
            if obj.get("__rl") and isinstance(v, str) and v and not v.startswith("=") and not re.fullmatch(r"gid=\d+", v):
                changes.append(f"{n['name']}: {path} -> placeholder")
                obj["value"] = "PASTE_ID"
                for k in ("cachedResultName", "cachedResultUrl"):
                    obj.pop(k, None)
            for k, val in obj.items():
                scrub(val, f"{path}/{k}")
        elif isinstance(obj, list):
            for i, val in enumerate(obj):
                scrub(val, f"{path}/{i}")
    scrub(p, "")
    nodes.append(n)

out = {
    "name": wf["name"],
    "nodes": nodes,
    "connections": wf["connections"],
    "settings": {k: v for k, v in (wf.get("settings") or {}).items() if k in ("executionOrder", "saveManualExecutions")},
    "pinData": {},
    "tags": [],
}
text = json.dumps(out, ensure_ascii=False, indent=2)
suspects = sorted({m for m in DRIVE_ID.findall(text) if re.search(r"\d", m) and re.search(r"[A-Z]", m) and re.search(r"[a-z]", m)})
open(sys.argv[2], "w", encoding="utf-8", newline="\n").write(text)
print("\n".join(changes))
print(f"\nnodes: {len(nodes)} | ID-like strings left: {len(suspects)}")
for s in suspects:
    print("  CHECK", s)
