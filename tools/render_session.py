#!/usr/bin/env python3
"""Render a Claude Code session (.jsonl transcript) to a Quarto .qmd page.

Usage:
    python3 render_session.py <session.jsonl> <out.qmd> [--title "..."]

Produces prose for user/assistant turns, collapsible "thinking" callouts,
fenced code blocks for Bash/Write, and colored ```diff blocks for Edits.
"""
import json
import sys
import re
import argparse
import difflib
from pathlib import Path

HOME = str(Path.home())

# ANSI CSI / OSC escape sequences and bare control chars corrupt Quarto's
# markdown reader (and look like noise). Strip them from all rendered text.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(text):
    if not isinstance(text, str):
        return text
    text = _ANSI.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _CTRL.sub("", text)


def shorten_path(p: str) -> str:
    if not isinstance(p, str):
        return str(p)
    return p.replace(HOME, "~")


def load(path):
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def index_results(rows):
    """Map tool_use_id -> result text."""
    out = {}
    for d in rows:
        if d.get("type") != "user":
            continue
        c = d.get("message", {}).get("content")
        if not isinstance(c, list):
            continue
        for x in c:
            if isinstance(x, dict) and x.get("type") == "tool_result":
                tid = x.get("tool_use_id")
                cont = x.get("content")
                if isinstance(cont, list):
                    cont = "\n".join(
                        b.get("text", "") for b in cont
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                out[tid] = cont if isinstance(cont, str) else ""
    return out


def is_noise(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if t.startswith("<system-reminder") or t.startswith("<command-"):
        return True
    if t.startswith("Caveat:") or t.startswith("<local-command"):
        return True
    return False


def fence_ticks(*texts):
    """Pick a backtick run long enough to safely wrap content containing fences."""
    longest = 0
    for t in texts:
        run = 0
        for ch in t:
            if ch == "`":
                run += 1
                longest = max(longest, run)
            else:
                run = 0
    return "`" * max(3, longest + 1)


def fence(code, lang="", caption=None, max_lines=None):
    code = clean(code)
    lines = code.rstrip("\n").split("\n")
    truncated = False
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    body = "\n".join(lines)
    t = fence_ticks(body)
    out = f"{t}{lang}\n{body}\n"
    if truncated:
        out += f"... ({len(code.splitlines()) - max_lines} weitere Zeilen)\n"
    out += f"{t}\n"
    if caption:
        out = f"*{caption}*\n\n" + out
    return out


def make_diff(file_path, old, new):
    diff = difflib.unified_diff(
        clean(old).splitlines(), clean(new).splitlines(),
        lineterm="", n=2,
    )
    body = "\n".join(l for l in diff if not l.startswith(("+++", "---")))
    cap = f"Edit `{shorten_path(file_path)}`"
    if not body.strip():
        return f"*{cap}*\n\n"
    t = fence_ticks(body)
    return f"*{cap}*\n\n{t}diff\n{body}\n{t}\n"


def render_tool(x, results):
    name = x.get("name", "?")
    inp = x.get("input", {})
    tid = x.get("id")
    res = clean(results.get(tid, ""))
    out = []

    if name == "Bash":
        desc = inp.get("description", "")
        out.append(fence(inp.get("command", ""), "bash",
                         caption=f"Bash — {desc}" if desc else "Bash"))
        if res.strip():
            out.append("::: {.callout-note icon=false collapse=\"true\"}\n"
                       "## Ausgabe\n\n"
                       + fence(res, "text", max_lines=40)
                       + "\n:::\n")
    elif name == "Edit":
        out.append(make_diff(inp.get("file_path", ""),
                             inp.get("old_string", ""),
                             inp.get("new_string", "")))
    elif name == "Write":
        path = shorten_path(inp.get("file_path", ""))
        ext = Path(path).suffix.lstrip(".")
        out.append(fence(inp.get("content", ""), ext,
                         caption=f"Neue Datei `{path}`", max_lines=40))
    elif name == "Read":
        out.append(f"*Liest `{shorten_path(inp.get('file_path', ''))}`*\n")
    elif name in ("TaskCreate",):
        out.append(f"*Task angelegt: {inp.get('subject', '')}*\n")
    elif name in ("TaskUpdate",):
        out.append(f"*Task {inp.get('taskId', '')} → {inp.get('status', '')}*\n")
    elif name == "AskUserQuestion":
        for q in inp.get("questions", []):
            out.append(f"**Frage an Peter:** {q.get('question', '')}\n")
            for o in q.get("options", []):
                out.append(f"- **{o.get('label', '')}** — {o.get('description', '')}")
            out.append("")
            if res.strip():
                out.append(f"> Antwort: {res.strip()}\n")
    elif name == "ToolSearch":
        pass  # internal plumbing, skip
    else:
        out.append(f"*Tool `{name}`*\n")
    return "\n".join(out)


def render(rows, title, author):
    results = index_results(rows)
    has_thinking = False
    parts = []

    for d in rows:
        typ = d.get("type")
        if typ not in ("user", "assistant"):
            continue
        c = d.get("message", {}).get("content")

        # User plain-string prompts
        if typ == "user" and isinstance(c, str):
            if is_noise(c):
                continue
            parts.append("::: {.callout-tip icon=false}\n## Prompt (Peter)\n")
            parts.append(clean(c).strip() + "\n:::\n")
            continue

        if not isinstance(c, list):
            continue

        for x in c:
            if not isinstance(x, dict):
                continue
            bt = x.get("type")
            if bt == "text":
                txt = clean(x.get("text", ""))
                if is_noise(txt):
                    continue
                if typ == "user":
                    parts.append("::: {.callout-tip icon=false}\n## Prompt (Peter)\n")
                    parts.append(txt.strip() + "\n:::\n")
                else:
                    parts.append(txt.strip() + "\n")
            elif bt == "thinking":
                th = clean(x.get("thinking", ""))
                if th.strip():
                    has_thinking = True
                    parts.append(
                        "::: {.callout-note icon=false collapse=\"true\"}\n"
                        "## Claude denkt nach\n\n" + th.strip() + "\n:::\n"
                    )
            elif bt == "tool_use":
                rt = render_tool(x, results)
                if rt.strip():
                    parts.append(rt)
            # tool_result handled via index_results

    note = ("Automatisch aus einem Claude-Code-Session-Transkript gerendert. "
            "Prompts sind farblich hervorgehoben, Code-Änderungen erscheinen "
            "als farbiger Diff")
    note += (", „Claude denkt nach\"-Blöcke lassen sich aufklappen."
             if has_thinking else ".")
    head = [
        "---",
        f'title: "{title}"',
        f'author: "{author}"',
        "date: today",
        "---",
        "",
        "::: {.callout-note appearance=\"simple\"}",
        note,
        ":::",
        "",
    ]
    return "\n".join(head + parts) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl")
    ap.add_argument("out")
    ap.add_argument("--title", default="Claude-Code-Session")
    ap.add_argument("--author", default="Prof. Dr.-Ing. Peter Fröhlich")
    args = ap.parse_args()

    rows = load(args.jsonl)
    Path(args.out).write_text(render(rows, args.title, args.author), encoding="utf-8")
    print(f"geschrieben: {args.out}  ({len(rows)} Zeilen gelesen)")


if __name__ == "__main__":
    main()
