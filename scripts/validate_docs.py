"""Deterministic public navigation, parity, links and core code classification."""
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def pages(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "pages":
                yield from (x for x in item if isinstance(x, str))
            else:
                yield from pages(item)
    elif isinstance(value, list):
        for item in value:
            yield from pages(item)


def validate():
    errors = []
    config = json.loads((DOCS / "docs.json").read_text())
    languages = config["navigation"]["languages"]
    en = list(pages(languages[0]))
    zh = [p.removeprefix("zh/") for p in pages(languages[1])]
    if en != zh:
        errors.append("docs.json: language navigation order differs")
    for name in en:
        for prefix in ("", "zh/"):
            if not (DOCS / f"{prefix}{name}.mdx").is_file():
                errors.append(f"docs.json: missing {prefix}{name}")
    for page in sorted(DOCS.rglob("*.mdx")):
        text = page.read_text()
        text = re.sub(r"```[^\n]*\n.*?```", "", text, flags=re.S)
        links = re.findall(r'\]\(([^\s)]+)(?:\s+[^)]*)?\)|(?:href|src)=["\']([^"\']+)["\']', text)
        for pair in links:
            link = next(v for v in pair if v)
            parsed = urlsplit(link)
            if parsed.scheme or link.startswith("//"):
                continue
            target = unquote(parsed.path)
            base = DOCS / target.lstrip("/") if target.startswith("/") else page.parent / target
            if not target:
                base = page
            choices = [base, base.with_suffix(".mdx"), base.with_suffix(".md"), base / "index.mdx"]
            found = next((p for p in choices if p.is_file()), None)
            if found is None:
                errors.append(f"{page.relative_to(ROOT)}: missing link {link}")
            elif parsed.fragment and found.suffix in (".mdx", ".md"):
                content = found.read_text()
                headings = re.findall(r"^#{1,6}\s+(.+)$", content, re.M)
                slugs = {re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-") for h in headings}
                slugs.update(re.findall(r'id=["\']([^"\']+)', content))
                if unquote(parsed.fragment) not in slugs:
                    errors.append(f"{page.relative_to(ROOT)}: missing anchor {link}")
    return sorted(set(errors))


if __name__ == "__main__":
    errors = validate()
    print("\n".join(errors) if errors else "Public navigation, bilingual parity and local links passed.")
    sys.exit(bool(errors))
