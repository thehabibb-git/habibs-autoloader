"""Builds the Habib's Autoloader workflow (an importable n8n workflow JSON)."""
import json
import sys
import uuid

import js_code as js
import js_v3 as js3
import prompts as p

OUT = sys.argv[1]

CHEAP_MODEL = "x-ai/grok-4.3"
WRITER_MODEL = "anthropic/claude-sonnet-5.5"
SHEET_TAB = {"__rl": True, "value": "gid=0", "mode": "list", "cachedResultName": "Sheet1"}
SHEET_DOC = {"__rl": True, "value": "={{ $('Config').first().json.sheet_url }}", "mode": "url"}
SHEET_DOC_STATIC = {"__rl": True, "value": "PASTE_YOUR_GOOGLE_SHEET_URL_HERE", "mode": "url"}

nodes = []
connections = {}


def nid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "habibs-autoloader/" + name))


def node(name, type_, version, pos, params, **extra):
    n = {"parameters": params, "type": type_, "typeVersion": version, "position": list(pos), "id": nid(name), "name": name}
    n.update(extra)
    nodes.append(n)
    return name


def link(src, dst, out_index=0, kind="main"):
    outs = connections.setdefault(src, {}).setdefault(kind, [])
    while len(outs) <= out_index:
        outs.append([])
    outs[out_index].append({"node": dst, "type": kind, "index": 0})


def chain(*names):
    for a, b in zip(names, names[1:]):
        link(a, b)


def sticky(name, pos, content, width, height, color=None):
    params = {"content": content, "height": height, "width": width}
    if color:
        params["color"] = color
    node(name, "n8n-nodes-base.stickyNote", 1, pos, params)


def set_node(name, pos, fields):
    return node(name, "n8n-nodes-base.set", 3.4, pos, {
        "assignments": {"assignments": [
            {"id": nid(name + k), "name": k, "value": v, "type": t} for k, v, t in fields
        ]},
        "options": {},
    })


def code(name, pos, js_src, **extra):
    return node(name, "n8n-nodes-base.code", 2, pos, {"jsCode": js_src}, **extra)


def openrouter(name, pos, model, root, temperature, max_tokens):
    node(name, "@n8n/n8n-nodes-langchain.lmChatOpenRouter", 1, pos,
         {"model": model, "options": {"temperature": temperature, "maxTokens": max_tokens}})
    link(name, root, kind="ai_languageModel")


def parser(name, pos, example, root):
    node(name, "@n8n/n8n-nodes-langchain.outputParserStructured", 1.3, pos, {"jsonSchemaExample": example})
    link(name, root, kind="ai_outputParser")


def llm_chain(name, pos, text, has_parser):
    return node(name, "@n8n/n8n-nodes-langchain.chainLlm", 1.5, pos,
                {"promptType": "define", "text": text, "hasOutputParser": has_parser},
                retryOnFail=True, maxTries=3, waitBetweenTries=3000)


def drive_download(name, pos, field):
    return node(name, "n8n-nodes-base.googleDrive", 3, pos, {
        "operation": "download",
        "fileId": {"__rl": True, "value": "={{ $('Project').first().json." + field + " }}", "mode": "id"},
        "options": {},
    })


def extract_text(name, pos, key):
    return node(name, "n8n-nodes-base.extractFromFile", 1, pos,
                {"operation": "text", "destinationKey": key, "options": {}})


SHEET_COLUMNS = ["Request ID", "Date", "Project", "SEO name", "Title", "Main keyword", "Note from SEO", "Status", "Blog file",
                 "Word count", "Meta title", "Meta description", "Slug", "Notes", "Info gain %"]


def sheets(name, pos, operation, values, doc=SHEET_DOC):
    params = {
        "operation": operation,
        "documentId": doc,
        "sheetName": SHEET_TAB,
        "columns": {
            "mappingMode": "defineBelow",
            "value": values,
            "schema": [{"id": c, "displayName": c, "required": False, "defaultMatch": False, "display": True,
                        "type": "string", "canBeUsedToMatch": True, "removed": c not in values}
                       for c in SHEET_COLUMNS],
        },
        "options": {},
    }
    if operation in ("update", "appendOrUpdate"):
        params["columns"]["matchingColumns"] = ["Request ID"]
    return node(name, "n8n-nodes-base.googleSheets", 4.5, pos, params)


# ---------------------------------------------------------------- sticky notes
sticky("Setup", (-900, -620), """# Habib's Autoloader: setup
1. **Google Sheet**: row 1 headers exactly:
`Request ID | Date | Project | SEO name | Title | Main keyword | Note from SEO | Status | Blog file | Word count | Meta title | Meta description | Slug | Notes | Info gain %`
2. **Projects**: open the **Project** node and fill in up to 5 projects (brand, domain, market, terminology...). Set `enabled: true` on each one you use.
3. **Drive**: for each project, upload its `knowledge-base.md` and `link-map.json` as plain files (not Google Docs) and paste their file IDs into its entry in the **Project** node. Make one folder for finished blog Docs.
4. **Config** node: paste the Sheet URL and the Docs folder ID.
5. **Form**: in **Blog Request Form**, make the **Project** dropdown options match each enabled project's `name`.
6. **Credentials**:
   - OpenRouter on the model nodes and on **Web Search**.
   - Google Drive OAuth2 on the 2 Drive downloads, **Create Google Doc** and **Share: Anyone Can Edit**.
   - Google Sheets OAuth2 on the Sheets nodes. **Mark Failed** has its own Sheet URL field, so paste the URL there too.
7. Save, then **Settings > Error workflow**: pick this same workflow, so failed runs are marked `Failed`.
8. Publish, open the form's Production URL and share it with your writers.

Each form submission is one execution and one finished Google Doc.""", 700, 600)
sticky("Note SERP", (520, -260), "## Search research\nPerplexity Sonar (through your OpenRouter key) searches the live web as a user in the project's market and lists the pages most likely to rank, plus 'People also ask' questions. **Fetch Page** reads the top 5 article pages, skipping social sites, forums and your own projects. The digest keeps each page's H1-H3 outline and main text.", 900, 140, 7)
sticky("Note Plan", (1660, -260), "## Plan\nA low-cost model finds the commodity content, plans the information gain from your own pages (every point checked word for word against its source) and outlines the post. **Validate Outline** enforces structure, allow-listed links, verified external links and an exact word count.", 900, 120, 7)
sticky("Note Write", (-420, 300), "## Write\nClaude Sonnet writes the whole post in one call from the outline, the knowledge base and the verified first-hand evidence.", 700, 100, 7)
sticky("Note QA", (720, 300), "## Check, edit, sign off\nUp to three code-and-AI check rounds, each followed by an edit only when something needs fixing, then a surgical sign-off pass that may only touch flagged sentences. No loops. Then the meta data, the Google Doc and the Sheet row.", 1620, 100, 7)
sticky("Note Error", (-900, 780), "## Failure logging\nRuns when a production execution fails. It marks the request's row `Failed` with the node and error message.", 520, 100, 3)

# ---------------------------------------------------------------- 1. intake
# The form's Project options: each must match a project's `name` in the Project node
PROJECT_OPTIONS = ["Northwind Solar", "Project 2", "Project 3", "Project 4", "Project 5"]
Y0 = 0
node("Blog Request Form", "n8n-nodes-base.formTrigger", 2.2, (-900, Y0), {
    "formTitle": "New blog request",
    "formDescription": "Fill this in to have a researched, fact-checked blog post written for one of your projects. The Google Doc link appears in the request sheet in about 6 to 10 minutes.",
    "formFields": {"values": [
        {"fieldLabel": "Project", "fieldType": "dropdown", "requiredField": True,
         "fieldOptions": {"values": [{"option": o} for o in PROJECT_OPTIONS]}},
        {"fieldLabel": "Title idea", "placeholder": "e.g. How much does solar panel installation cost in Bristol?", "requiredField": True},
        {"fieldLabel": "Main keyword", "placeholder": "e.g. solar panel installation Bristol", "requiredField": True},
        {"fieldLabel": "SEO name", "placeholder": "Your name", "requiredField": True},
        {"fieldLabel": "Post format", "fieldType": "dropdown", "requiredField": True,
         "fieldOptions": {"values": [{"option": "Standard guide"}, {"option": "Listicle"}, {"option": "How-to steps"}, {"option": "Comparison"}]}},
        {"fieldLabel": "Use case studies?", "fieldType": "dropdown", "requiredField": True,
         "fieldOptions": {"values": [{"option": "Yes"}, {"option": "No"}]}},
        {"fieldLabel": "Reference link", "placeholder": "Optional: a competitor post to outrank. We cover everything it does, better, without copying it"},
        {"fieldLabel": "Approximate word count", "fieldType": "number", "placeholder": "Optional, e.g. 2000 (leave blank to match what ranks, 1500-3000)"},
        {"fieldLabel": "Special requirements", "fieldType": "textarea", "placeholder": "Optional: angle, audience, points to include or avoid, services to mention, extra keywords..."},
    ]},
    "responseMode": "onReceived",
    "options": {
        "appendAttribution": False,
        "respondWithOptions": {"values": {"formSubmittedText": "Thanks! The blog is being written. The Google Doc link will appear in the request sheet in about 6 to 10 minutes."}},
    },
}, webhookId=nid("form-webhook"))

set_node("Config", (-680, Y0), [
    ("sheet_url", "PASTE_YOUR_GOOGLE_SHEET_URL_HERE", "string"),
    ("docs_folder_id", "PASTE_DRIVE_FOLDER_ID_FOR_FINISHED_BLOGS", "string"),
])

set_node("Start", (-460, Y0), [
    ("title_idea", "={{ $('Blog Request Form').first().json['Title idea'].trim() }}", "string"),
    ("keyword", "={{ $('Blog Request Form').first().json['Main keyword'].trim() }}", "string"),
    ("seo_name", "={{ $('Blog Request Form').first().json['SEO name'].trim() }}", "string"),
    ("word_count", "={{ Number($('Blog Request Form').first().json['Approximate word count']) || 0 }}", "number"),
    ("notes", "={{ String($('Blog Request Form').first().json['Special requirements'] || '').trim() }}", "string"),
    ("reference_url", "={{ String($('Blog Request Form').first().json['Reference link'] || '').trim() }}", "string"),
    ("date", "={{ $now.toFormat('d LLL yyyy') }}", "string"),
])

code("Project", (-460, Y0 + 160), js.PROJECT)
code("Post Settings", (-350, Y0 + 160), js.POST_SETTINGS)
code("Reference Page", (-300, Y0 + 320), js.REFERENCE_PAGE)

# Log the request as a new row inside the Sheet's table (Sheets API appendCells on the table)
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets/"
node("Find Sheet Table", "n8n-nodes-base.httpRequest", 4.2, (-240, Y0 - 160), {
    "url": "=" + SHEETS_API + "{{ ($('Config').first().json.sheet_url.match(/\\/spreadsheets\\/d\\/([a-zA-Z0-9_-]+)/) || [])[1] }}"
           "?fields=sheets(properties(sheetId,title),tables(tableId,name,range,columnProperties))",
    "authentication": "predefinedCredentialType",
    "nodeCredentialType": "googleSheetsOAuth2Api",
    "options": {"timeout": 30000},
}, retryOnFail=True, maxTries=2, waitBetweenTries=2000)
code("Build Request Row", (-20, Y0 - 160), js.BUILD_REQUEST_ROW)
node("Add Request Row", "n8n-nodes-base.httpRequest", 4.2, (200, Y0 - 160), {
    "method": "POST",
    "url": "=" + SHEETS_API + "{{ $json.spreadsheet_id }}:batchUpdate",
    "authentication": "predefinedCredentialType",
    "nodeCredentialType": "googleSheetsOAuth2Api",
    "sendBody": True,
    "specifyBody": "json",
    "jsonBody": "={{ JSON.stringify($json.body) }}",
    "options": {"timeout": 30000},
}, retryOnFail=True, maxTries=2, waitBetweenTries=2000)

drive_download("Download Knowledge Base", (-20, Y0), "kb_file_id")
extract_text("Read Knowledge Base File", (200, Y0), "kb")
code("Knowledge Base", (420, Y0 + 160), js.CLEAN_KB)
drive_download("Download Link Map", (420, Y0), "link_map_file_id")
extract_text("Link Map Text", (640, Y0), "link_map_text")

# ---------------------------------------------------------------- 2. SERP research
node("Web Search", "n8n-nodes-base.httpRequest", 4.2, (860, Y0 - 120), {
    "method": "POST",
    "url": "https://openrouter.ai/api/v1/chat/completions",
    "authentication": "predefinedCredentialType",
    "nodeCredentialType": "openRouterApi",
    "sendBody": True,
    "specifyBody": "json",
    "jsonBody": p.WEB_SEARCH_BODY,
    "options": {"timeout": 180000},
}, retryOnFail=True, maxTries=3, waitBetweenTries=5000)
code("Pick Competitors", (1080, Y0 - 120), js.PICK_COMPETITORS)
node("Fetch Page", "n8n-nodes-base.httpRequest", 4.2, (1300, Y0 - 120), {
    "url": "={{ $json.url }}",
    "sendHeaders": True,
    "headerParameters": {"parameters": [
        {"name": "User-Agent", "value": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"},
        {"name": "Accept", "value": "text/html,application/xhtml+xml"},
        {"name": "Accept-Language", "value": "en,en-GB;q=0.9,en-US;q=0.8"},
    ]},
    "options": {
        "timeout": 30000,
        "response": {"response": {"responseFormat": "text", "outputPropertyName": "data"}},
        "batching": {"batch": {"batchSize": 1, "batchInterval": 300}},
    },
}, retryOnFail=True, maxTries=2, waitBetweenTries=2000, onError="continueRegularOutput")
code("Competitor Digest", (1520, Y0 - 120), js.COMPETITOR_DIGEST)

# ---------------------------------------------------------------- 3. information gain protocol
def fetch_text(name, pos, url_expr):
    return node(name, "n8n-nodes-base.httpRequest", 4.2, pos, {
        "url": url_expr,
        "sendHeaders": True,
        "headerParameters": {"parameters": [
            {"name": "User-Agent", "value": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"},
            {"name": "Accept-Language", "value": "en,en-GB;q=0.9,en-US;q=0.8"},
        ]},
        "options": {
            "timeout": 30000,
            "response": {"response": {"responseFormat": "text", "outputPropertyName": "data"}},
            "batching": {"batch": {"batchSize": 1, "batchInterval": 200}},
        },
    }, retryOnFail=True, maxTries=2, waitBetweenTries=2000, onError="continueRegularOutput")


# Step 1: commodity audit of the ranking pages
llm_chain("Commodity Audit", (1740, Y0 - 120), p.COMMODITY_AUDIT, True)
openrouter("Grok Commodity", (1700, Y0 + 80), CHEAP_MODEL, "Commodity Audit", 0.2, 6000)
parser("Commodity Parser", (1840, Y0 + 80), p.COMMODITY_SCHEMA, "Commodity Audit")
code("Score Commodity", (1960, Y0 - 120), js3.SCORE_COMMODITY)

# Step 2: first-hand evidence from the project's own live site (sitemap -> case studies and service pages)
fetch_text("Fetch Sitemap Index", (2180, Y0 - 120), "={{ $('Project').first().json.sitemap }}")
code("Sitemap Files", (2400, Y0 - 120), js3.SITEMAP_FILES)
fetch_text("Fetch Sitemaps", (2620, Y0 - 120), "={{ $json.url }}")
code("Pick Own Pages", (2840, Y0 - 120), js3.PICK_OWN_PAGES)
fetch_text("Fetch Own Pages", (3060, Y0 - 120), "={{ $json.url }}")
code("Own Evidence", (3280, Y0 - 120), js3.OWN_EVIDENCE)

llm_chain("Gain Planner", (3500, Y0 - 120), p.GAIN_PLANNER, True)
openrouter("Grok Analyst", (3460, Y0 + 80), CHEAP_MODEL, "Gain Planner", 0.3, 6000)
parser("Analysis Parser", (3600, Y0 + 80), p.GAIN_PLANNER_SCHEMA, "Gain Planner")
code("Verify Gain", (3720, Y0 - 120), js3.VERIFY_GAIN)

code("Brief", (3940, Y0 - 120), js.BRIEF)

llm_chain("Outline Planner", (4160, Y0 - 120), p.OUTLINE_PLANNER, True)
openrouter("Grok Outline", (4120, Y0 + 80), CHEAP_MODEL, "Outline Planner", 0.4, 6000)
parser("Outline Parser", (4260, Y0 + 80), p.OUTLINE_SCHEMA, "Outline Planner")

code("Validate Outline", (4480, Y0 - 120), js.VALIDATE_OUTLINE)

# ---------------------------------------------------------------- 4. write the whole post in one call
Y1 = 520
llm_chain("Blog Writer", (-420, Y1 - 100), p.BLOG_WRITER, False)
openrouter("Sonnet Writer", (-420, Y1 + 100), WRITER_MODEL, "Blog Writer", 0.7, 24000)
code("Assemble Blog", (-200, Y1 - 100), js.ASSEMBLE_BLOG)

# ---------------------------------------------------------------- 5. QA, edit, meta, output
code("QA Check", (20, Y1 - 100), js.QA)


def gain_audit(prefix, pos, qa_node):
    """Gain Auditor (Grok labels paragraphs) + Gain Score (code turns labels into gain % and issues)."""
    x, y = pos
    llm_chain(f"{prefix}Gain Auditor", (x, y), p.GAIN_AUDITOR, True)
    openrouter(f"Grok {prefix}Auditor", (x - 40, y + 200), CHEAP_MODEL, f"{prefix}Gain Auditor", 0.1, 4000)
    parser(f"{prefix}Gain Auditor Parser", (x + 100, y + 200), p.GAIN_AUDITOR_SCHEMA, f"{prefix}Gain Auditor")
    code(f"{prefix}Gain Score", (x + 220, y), js3.GAIN_SCORE.replace("__QA_NODE__", qa_node))


gain_audit("", (120, Y1 - 300), "QA Check")


def needs_edit(name, pos, test="$json.has_issues"):
    node(name, "n8n-nodes-base.if", 2.2, pos, {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
            "conditions": [{
                "id": nid(name + "-cond") if name != "Needs Edit?" else nid("needs-edit-cond"),
                "leftValue": "={{ " + test + " }}",
                "rightValue": "",
                "operator": {"type": "boolean", "operation": "true", "singleValue": True},
            }],
            "combinator": "and",
        },
        "options": {},
    })


needs_edit("Needs Edit?", (240, Y1 - 100))
llm_chain("Editor", (460, Y1 - 200), p.EDITOR, False)
openrouter("Sonnet Editor", (460, Y1 - 20), WRITER_MODEL, "Editor", 0.2, 24000)
code("Clean Editor Output", (680, Y1 - 200), js.CLEAN_EDITOR.replace("__QA_NODE__", "QA Check"))
# Second round: the first edit is checked again and whatever it left is fixed once more
code("Recheck QA", (680, Y1 + 700), js.QA)
gain_audit("Recheck ", (780, Y1 + 700), "Recheck QA")
needs_edit("Needs Edit 2?", (1100, Y1 + 700))
llm_chain("Editor 2", (1320, Y1 + 600), p.EDITOR, False)
openrouter("Sonnet Editor 2", (1320, Y1 + 800), WRITER_MODEL, "Editor 2", 0.2, 24000)
code("Clean Editor Output 2", (1540, Y1 + 600), js.CLEAN_EDITOR.replace("__QA_NODE__", "Recheck QA"))
code("Final QA", (900, Y1 - 100), js.QA)
gain_audit("Final ", (900, Y1 + 300), "Final QA")
# Sign-off: one surgical pass on whatever the final audit still finds, then one last audit whose
# remaining issues go to the Sheet. No connection leads back, so it can never loop.
needs_edit("Needs Final Fix?", (1400, Y1 + 300),
           "$json.issues.some(x => !/^Readability|^Sentence rhythm|% of sentences run over 30/.test(x))")
llm_chain("Surgical Editor", (1600, Y1 + 200), p.SURGICAL_EDITOR, False)
openrouter("Sonnet Surgical Editor", (1600, Y1 + 400), WRITER_MODEL, "Surgical Editor", 0.1, 24000)
code("Clean Surgical Output", (1820, Y1 + 200), js.SURGICAL_CLEAN)
code("Sign-off QA", (2040, Y1 + 200), js.QA)
gain_audit("Sign-off ", (2140, Y1 + 200), "Sign-off QA")
code("Sign-off Result", (2480, Y1 + 300), js.SIGNOFF_RESULT)

llm_chain("Meta Generator", (1120, Y1 - 100), p.META, True)
openrouter("Grok Meta", (1080, Y1 + 100), CHEAP_MODEL, "Meta Generator", 0.3, 1000)
parser("Meta Parser", (1220, Y1 + 100), p.META_SCHEMA, "Meta Generator")

node("Markdown to HTML", "n8n-nodes-base.markdown", 1, (1340, Y1 - 100), {
    "mode": "markdownToHtml",
    "markdown": "={{ $('Sign-off Result').first().json.blog_doc }}",
    "destinationKey": "html",
    "options": {"tables": True, "simplifiedAutoLink": True, "openLinksInNewWindow": False},
})
code("Build Doc Upload", (1560, Y1 - 100), js.BUILD_DOC)
node("Create Google Doc", "n8n-nodes-base.httpRequest", 4.2, (1780, Y1 - 100), {
    "method": "POST",
    "url": "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id,webViewLink",
    "authentication": "predefinedCredentialType",
    "nodeCredentialType": "googleDriveOAuth2Api",
    "sendBody": True,
    "contentType": "raw",
    "rawContentType": "=multipart/related; boundary={{ $json.boundary }}",
    "body": "={{ $json.multipart_body }}",
    "options": {"timeout": 60000},
}, retryOnFail=True, maxTries=3, waitBetweenTries=3000)
node("Share: Anyone Can Edit", "n8n-nodes-base.httpRequest", 4.2, (2000, Y1 - 100), {
    "method": "POST",
    "url": "=https://www.googleapis.com/drive/v3/files/{{ $json.id }}/permissions?supportsAllDrives=true",
    "authentication": "predefinedCredentialType",
    "nodeCredentialType": "googleDriveOAuth2Api",
    "sendBody": True,
    "specifyBody": "json",
    "jsonBody": '{ "role": "writer", "type": "anyone", "allowFileDiscovery": false }',
    "options": {"timeout": 30000},
}, retryOnFail=True, maxTries=3, waitBetweenTries=3000)
sheets("Mark Done", (2220, Y1 - 100), "update", {
    "Request ID": "={{ $execution.id }}",
    "Title": "={{ $('Brief').first().json.final_title }}",
    "Status": "={{ $('Build Doc Upload').first().json.status }}",
    "Blog file": "={{ $('Create Google Doc').first().json.webViewLink || ('https://docs.google.com/document/d/' + $('Create Google Doc').first().json.id + '/edit') }}",
    "Word count": "={{ $('Build Doc Upload').first().json.word_count }}",
    "Meta title": "={{ $('Build Doc Upload').first().json.meta_title }}",
    "Meta description": "={{ $('Build Doc Upload').first().json.meta_description }}",
    "Slug": "={{ '/' + $('Build Doc Upload').first().json.slug }}",
    "Notes": "={{ $('Build Doc Upload').first().json.notes }}",
    "Info gain %": "={{ $('Build Doc Upload').first().json.gain_pct + '%' }}",
})

# ---------------------------------------------------------------- 6. failure logging
node("On Failure", "n8n-nodes-base.errorTrigger", 1, (-900, 920), {})
sheets("Mark Failed", (-680, 920), "appendOrUpdate", {
    "Request ID": "={{ $json.execution.id }}",
    "Date": "={{ $now.toFormat('d LLL yyyy') }}",
    "Status": "Failed",
    "Notes": "={{ ($json.execution.lastNodeExecuted || 'unknown node') + ': ' + ($json.execution.error?.message || 'unknown error') }}",
}, doc=SHEET_DOC_STATIC)

# ---------------------------------------------------------------- connections
chain("Blog Request Form", "Config", "Start", "Project", "Post Settings", "Reference Page", "Find Sheet Table", "Build Request Row", "Add Request Row", "Download Knowledge Base", "Read Knowledge Base File", "Knowledge Base",
      "Download Link Map", "Link Map Text", "Web Search", "Pick Competitors", "Fetch Page",
      "Competitor Digest", "Commodity Audit", "Score Commodity", "Fetch Sitemap Index", "Sitemap Files",
      "Fetch Sitemaps", "Pick Own Pages", "Fetch Own Pages", "Own Evidence", "Gain Planner", "Verify Gain",
      "Brief", "Outline Planner", "Validate Outline", "Blog Writer",
      "Assemble Blog", "QA Check", "Gain Auditor", "Gain Score", "Needs Edit?")
link("Needs Edit?", "Editor", 0)
link("Needs Edit?", "Final QA", 1)
chain("Editor", "Clean Editor Output", "Recheck QA", "Recheck Gain Auditor", "Recheck Gain Score", "Needs Edit 2?")
link("Needs Edit 2?", "Editor 2", 0)
link("Needs Edit 2?", "Final QA", 1)
chain("Editor 2", "Clean Editor Output 2", "Final QA")
chain("Final QA", "Final Gain Auditor", "Final Gain Score", "Needs Final Fix?")
link("Needs Final Fix?", "Surgical Editor", 0)
link("Needs Final Fix?", "Sign-off Result", 1)
chain("Surgical Editor", "Clean Surgical Output", "Sign-off QA", "Sign-off Gain Auditor", "Sign-off Gain Score", "Sign-off Result")
chain("Sign-off Result", "Meta Generator", "Markdown to HTML", "Build Doc Upload",
      "Create Google Doc", "Share: Anyone Can Edit", "Mark Done")
chain("On Failure", "Mark Failed")

workflow = {
    "name": "Habib's Autoloader: multi-project SEO blog writer",
    "nodes": nodes,
    "pinData": {},
    "connections": connections,
    "active": False,
    "settings": {"executionOrder": "v1", "saveManualExecutions": True},
    "tags": [],
}

names = {n["name"] for n in nodes}
for src, kinds in connections.items():
    assert src in names, src
    for outs in kinds.values():
        for out in outs:
            for c in out:
                assert c["node"] in names, c["node"]

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(workflow, f, indent=2, ensure_ascii=False)
print(f"wrote {len(nodes)} nodes to {OUT}")

