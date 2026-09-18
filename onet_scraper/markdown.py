"""A markdown subset renderer, sized to METHODOLOGY.md and nothing more.

Pulling a dependency in to render one known file is not worth it, and a general
markdown library would accept constructs this file never uses. This handles
exactly what the methodology contains: headings, paragraphs, unordered and
ordered lists, fenced code, pipe tables, blockquotes, and inline emphasis,
links and code. Anything else passes through escaped.
"""

from __future__ import annotations

import html
import re

_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITAL = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\*)")
_CODE = re.compile(r"`([^`]+)`")


def _inline(text: str) -> str:
    # Code first: its contents must not then be scanned for emphasis.
    parts, out = [], ""
    for i, chunk in enumerate(_CODE.split(text)):
        if i % 2:
            parts.append(f"<code>{html.escape(chunk)}</code>")
        else:
            esc = html.escape(chunk)
            # Park backslash-escaped asterisks before matching emphasis. "O\*NET"
            # inside a **bold** run would otherwise leave a literal * in the
            # content and the bold pattern, which forbids one, fails silently.
            esc = esc.replace("\\*", "\x00").replace("\\_", "\x01")
            esc = _LINK.sub(r'<a href="\2">\1</a>', esc)
            esc = _BOLD.sub(r"<strong>\1</strong>", esc)
            esc = _ITAL.sub(r"<em>\1</em>", esc)
            esc = esc.replace("\x00", "*").replace("\x01", "_")
            parts.append(esc)
    return "".join(parts)



# A column of figures that is left-aligned cannot be read down, which is the
# only reason to put figures in a column. Markdown's own `---:` syntax sets
# alignment explicitly and is honoured first; where the author did not use it we
# fall back to detecting a wholly numeric column, so existing documents get the
# right result without every separator row being rewritten.
_NUMERIC = re.compile(
    r"^[(\s]*[+\u2212-]?[\d,]+(?:\.\d+)?\s*%?\s*\)?$")


def _cls(align: str) -> str:
    return f' class="{align}"' if align else ""


def _align(sep_line: str, head: list[str], body: list[list[str]]) -> list[str]:
    """One alignment per column: explicit if given, else numeric detection."""
    marks = [c.strip() for c in sep_line.strip().strip("|").split("|")]
    out: list[str] = []
    for idx in range(len(head)):
        mark = marks[idx] if idx < len(marks) else ""
        if mark.endswith(":") and not mark.startswith(":"):
            out.append("num")
            continue
        if mark.startswith(":") and mark.endswith(":"):
            out.append("mid")
            continue
        if mark.startswith(":"):
            out.append("")
            continue
        cells = [r[idx].strip() for r in body if idx < len(r) and r[idx].strip()]
        # Require more than one value before calling a column numeric, so a
        # single-row table of labels is not right-aligned on a coincidence.
        numeric = [c for c in cells if _NUMERIC.match(_strip_tags(c))]
        out.append("num" if len(cells) > 1 and len(numeric) == len(cells) else "")
    return out


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()

def _row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [_inline(c.strip()) for c in cells]


def render(md: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(html.escape(lines[i]))
                i += 1
            i += 1
            out.append("<pre><code>" + "\n".join(block) + "</code></pre>")
            continue

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            text = _inline(stripped[level:].strip())
            slug = re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", text).lower()).strip("-")
            out.append(f'<h{level} id="{slug}">{text}</h{level}>')
            i += 1
            continue

        # pipe table: header, separator, rows
        if stripped.startswith("|") and i + 1 < len(lines) and set(
                lines[i + 1].strip().replace("|", "").replace(" ", "")) <= {"-", ":"}:
            head = _row(line)
            sep = lines[i + 1]          # capture before i moves past it
            i += 2
            body = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                body.append(_row(lines[i]))
                i += 1
            align = _align(sep, head, body)
            th = "".join(f'<th{_cls(a)}>{c}</th>' for c, a in zip(head, align))
            tr = "".join(
                "<tr>" + "".join(f'<td{_cls(a)}>{c}</td>'
                                 for c, a in zip(r, align + [""] * len(r))) + "</tr>"
                for r in body)
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>")
            continue

        if stripped.startswith("> "):
            block = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                block.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote><p>" + _inline(" ".join(block)) + "</p></blockquote>")
            continue

        ordered = re.match(r"^\d+\.\s", stripped)
        if stripped.startswith(("- ", "* ")) or ordered:
            tag = "ol" if ordered else "ul"
            items: list[str] = []
            while i < len(lines):
                cur = lines[i].strip()
                if cur.startswith(("- ", "* ")) or re.match(r"^\d+\.\s", cur):
                    items.append(re.sub(r"^(?:[-*]|\d+\.)\s+", "", cur))
                elif cur and lines[i].startswith((" ", "\t")) and items:
                    items[-1] += " " + cur          # continuation of the last item
                else:
                    break
                i += 1
            li = "".join(f"<li>{_inline(x)}</li>" for x in items)
            out.append(f"<{tag}>{li}</{tag}>")
            continue

        para = []
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(
                ("#", "|", "> ", "- ", "* ", "```")) and not re.match(r"^\d+\.\s", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        out.append("<p>" + _inline(" ".join(para)) + "</p>")

    return "\n".join(out)


def toc(md: str) -> str:
    """Two levels, because one was not enough to reach anything.

    The document has grown to thirty-odd subsections and the sidebar listed only
    the ten top-level ones, so a reader could not navigate to 4.4 or 7.1 at all -
    the sections carrying the optional-file provenance and the reliability
    result. Subsections are nested under their parent and keep their own
    number, since "7.1" is how the prose cross-references them.
    """
    items: list[str] = []
    open_sub = False
    for line in md.split("\n"):
        s = line.strip()
        if s.startswith("## "):
            if open_sub:
                items.append("</ol>")
                open_sub = False
            text = re.sub(r"<[^>]+>", "", _inline(s[3:].strip()))
            label = re.sub(r"^\d+\.\s*", "", text)   # heading supplies the number
            slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
            items.append(f'<li><a href="#{slug}">{label}</a>')
        elif s.startswith("### ") and items:
            text = re.sub(r"<[^>]+>", "", _inline(s[4:].strip()))
            slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
            num = re.match(r"^([\d.]+)", text)
            label = re.sub(r"^[\d.]+\s*", "", text)
            if not open_sub:
                items.append("<ol class='sub'>")
                open_sub = True
            items.append(f'<li><a href="#{slug}">'
                         f'<span class="n">{num.group(1) if num else ""}</span>'
                         f'{label}</a></li>')
    if open_sub:
        items.append("</ol>")
    return "<ol class='toc'>" + "".join(items) + "</ol>"
