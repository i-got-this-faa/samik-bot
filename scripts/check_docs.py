"""Check local Markdown links and keep README setup references current."""

import re
from collections import Counter
from functools import cache
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = (ROOT / "README.md", ROOT / "docs/operations.md")
INLINE_LINK = re.compile(r"\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+[\"'][^\"']*[\"'])?\s*\)")


@cache
def markdown_prose(path):
    fence = None
    lines = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is None:
            if marker:
                fence = marker[1]
            else:
                lines.append((number, line))
        elif marker and marker[1].startswith(fence) and not marker[2].strip():
            fence = None
    return lines


@cache
def heading_ids(path):
    seen = Counter()
    anchors = set()
    for _, line in markdown_prose(path):
        heading = re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if heading:
            slug = re.sub(r"[^\w\s-]", "", heading[1].lower())
            slug = re.sub(r"\s", "-", slug)
            suffix = seen[slug]
            anchor = f"{slug}-{suffix}" if suffix else slug
            while anchor in anchors:
                suffix += 1
                anchor = f"{slug}-{suffix}"
            anchors.add(anchor)
            seen[slug] = suffix + 1
    return anchors


def check_local_links(path):
    for number, line in markdown_prose(path):
        for match in INLINE_LINK.finditer(line):
            link = match[1] or match[2]
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                continue
            relative = unquote(parsed.path)
            target = (path.parent / relative).resolve() if relative else path
            if not target.exists() or not target.is_relative_to(ROOT):
                yield f"{path.relative_to(ROOT)}:{number}: broken local link {link}"
            elif parsed.fragment and target.suffix.lower() == ".md":
                if unquote(parsed.fragment) not in heading_ids(target):
                    yield f"{path.relative_to(ROOT)}:{number}: missing heading for {link}"


def check_readme_setup():
    readme = DOCS[0].read_text(encoding="utf-8")
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    for name in re.findall(r"^([A-Z][A-Z0-9_]*)=", example, re.MULTILINE):
        if f"`{name}`" not in readme:
            yield f"README.md: missing configuration variable {name}"
    inline_code = [snippet for _, line in markdown_prose(DOCS[0])
                   for snippet in re.findall(r"`([^`]+)`", line)]
    shell_blocks = re.findall(r"^`{3}(?:bash|sh|shell)[ \t]*\n(.*?)^`{3}[ \t]*$",
                              readme, re.MULTILINE | re.DOTALL)
    commands = "\n".join(inline_code + shell_blocks)
    for target in sorted(set(re.findall(r"\bmake ([\w.-]+)", commands))):
        if not re.search(rf"^{re.escape(target)}\s*:", makefile, re.MULTILINE):
            yield f"README.md: unknown Make target {target}"


if __name__ == "__main__":
    errors = [error for path in DOCS for error in check_local_links(path)]
    errors.extend(check_readme_setup())
    if errors:
        raise SystemExit("\n".join(errors))
    print("Documentation links and README setup checks passed.")
