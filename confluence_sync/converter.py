from __future__ import annotations

import re

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter


def _preprocess_confluence_macros(html: str) -> str:
    """Confluenceマクロ(ac:structured-macro等)を標準HTMLに変換する前処理。"""
    soup = BeautifulSoup(html, "html.parser")

    for macro in soup.find_all("ac:structured-macro"):
        macro_name = macro.get("ac:name", "")

        if macro_name in ("code", "noformat"):
            language = ""
            lang_param = macro.find("ac:parameter", attrs={"ac:name": "language"})
            if lang_param:
                language = lang_param.get_text(strip=True)

            body = macro.find("ac:plain-text-body")
            code = body.get_text() if body else ""

            pre = soup.new_tag("pre")
            code_tag = soup.new_tag("code")
            if language:
                code_tag["class"] = f"language-{language}"
            code_tag.string = code
            pre.append(code_tag)
            macro.replace_with(pre)
        else:
            # その他のマクロはリッチテキスト本文があればそのまま展開
            rich_body = macro.find("ac:rich-text-body")
            if rich_body:
                rich_body.unwrap()
            macro.unwrap()

    return str(soup)


class ConfluenceMarkdownConverter(MarkdownConverter):
    """markdownify のカスタムコンバーター。"""

    def convert_pre(self, el, text, convert_as_inline):
        if not text:
            return ""

        code_tag = el.find("code")
        language = ""
        if code_tag:
            classes = code_tag.get("class", [])
            if isinstance(classes, list):
                for cls in classes:
                    if cls.startswith("language-"):
                        language = cls[len("language-"):]
                        break
            text = code_tag.get_text()

        code = text.strip()
        return f"\n\n```{language}\n{code}\n```\n\n"


def convert_html_to_markdown(html: str) -> str:
    """Confluence HTML本文をMarkdownに変換する。"""
    if not html:
        return ""

    preprocessed = _preprocess_confluence_macros(html)

    converter = ConfluenceMarkdownConverter(
        heading_style="atx",
        bullets="-",
        strip=["script", "style"],
    )
    md = converter.convert(preprocessed)
    # 過剰な空行を整理
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def build_frontmatter(
    page_id: str,
    title: str,
    space_key: str,
    base_url: str,
    version: int,
    last_modified: str,
    labels: list[str],
) -> str:
    """YAML frontmatter を生成する。"""
    labels_str = "[" + ", ".join(f'"{lbl}"' for lbl in labels) + "]"
    url = f"{base_url}/spaces/{space_key}/pages/{page_id}"
    return (
        f"---\n"
        f'id: "{page_id}"\n'
        f'title: "{_escape_yaml(title)}"\n'
        f'space: "{space_key}"\n'
        f'url: "{url}"\n'
        f"version: {version}\n"
        f'last_modified: "{last_modified}"\n'
        f"labels: {labels_str}\n"
        f"---"
    )


def build_page_markdown(
    page_id: str,
    title: str,
    space_key: str,
    base_url: str,
    version: int,
    last_modified: str,
    labels: list[str],
    body_html: str,
) -> str:
    """frontmatter + 本文の完全なMarkdownファイルコンテンツを生成する。"""
    frontmatter = build_frontmatter(
        page_id, title, space_key, base_url, version, last_modified, labels
    )
    body_md = convert_html_to_markdown(body_html)
    return f"{frontmatter}\n\n# {title}\n\n{body_md}\n"


def _escape_yaml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
