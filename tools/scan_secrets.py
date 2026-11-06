"""Scans the files git would commit for things that should stay private: API keys, tokens,
Google Drive/Sheet IDs and personal email addresses. Run from the repo root before every push."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "out", "__pycache__"}
SKIP_FILES = {"test.html"}
PATTERNS = {
    "OpenRouter/OpenAI key": re.compile(r"(?<![A-Za-z0-9-])sk-(?:or-)?[A-Za-z0-9_-]{20,}"),
    "Bearer token": re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"),
    "Google OAuth secret": re.compile(r"GOCSPX-[A-Za-z0-9_-]+|ya29\.[A-Za-z0-9._-]+"),
    "Google Doc/Sheet/Drive link with ID": re.compile(r"docs\.google\.com/\w+/d/[A-Za-z0-9_-]{20,}|drive\.google\.com/\S*?[A-Za-z0-9_-]{25,}"),
    "Drive-style ID": re.compile(r"(?<![A-Za-z0-9_-])1[A-Za-z0-9_-]{32}(?![A-Za-z0-9_-])"),
    "Email address": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}"),
}
hits = 0
for d, dirs, files in os.walk(ROOT):
    dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
    for f in files:
        if f in SKIP_FILES or f.endswith((".png", ".pyc")):
            continue
        p = os.path.join(d, f)
        text = open(p, encoding="utf-8", errors="ignore").read()
        for label, rx in PATTERNS.items():
            for m in sorted(set(rx.findall(text))):
                hits += 1
                print(f"{label:38} {os.path.relpath(p, ROOT)}: {m[:90]}")
print(f"\n{hits} finding(s). Emails in the knowledge bases are the companies' public contact addresses; anything else should be removed.")
sys.exit(0)
