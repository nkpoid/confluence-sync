from confluence_sync.converter import (
    build_frontmatter,
    build_page_markdown,
    convert_html_to_markdown,
)


class TestConvertHtmlToMarkdown:
    def test_basic_paragraph(self):
        html = "<p>Hello world</p>"
        result = convert_html_to_markdown(html)
        assert "Hello world" in result

    def test_heading(self):
        html = "<h1>Title</h1><p>Body text</p>"
        result = convert_html_to_markdown(html)
        assert "# Title" in result
        assert "Body text" in result

    def test_table_conversion(self):
        html = (
            "<table><tr><th>Name</th><th>Value</th></tr>"
            "<tr><td>A</td><td>1</td></tr></table>"
        )
        result = convert_html_to_markdown(html)
        assert "Name" in result
        assert "Value" in result
        assert "|" in result

    def test_code_block_macro(self):
        html = (
            '<ac:structured-macro ac:name="code">'
            '<ac:parameter ac:name="language">python</ac:parameter>'
            "<ac:plain-text-body>print('hello')</ac:plain-text-body>"
            "</ac:structured-macro>"
        )
        result = convert_html_to_markdown(html)
        assert "```python" in result
        assert "print('hello')" in result

    def test_noformat_macro(self):
        html = (
            '<ac:structured-macro ac:name="noformat">'
            "<ac:plain-text-body>raw text here</ac:plain-text-body>"
            "</ac:structured-macro>"
        )
        result = convert_html_to_markdown(html)
        assert "```" in result
        assert "raw text here" in result

    def test_link_conversion(self):
        html = '<p>Visit <a href="https://example.com">Example</a></p>'
        result = convert_html_to_markdown(html)
        assert "[Example](https://example.com)" in result

    def test_list_conversion(self):
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        result = convert_html_to_markdown(html)
        assert "- Item 1" in result
        assert "- Item 2" in result

    def test_empty_html(self):
        result = convert_html_to_markdown("")
        assert result == ""

    def test_excessive_newlines_cleaned(self):
        html = "<p>A</p><p></p><p></p><p></p><p>B</p>"
        result = convert_html_to_markdown(html)
        assert "\n\n\n" not in result


class TestBuildFrontmatter:
    def test_basic_frontmatter(self):
        result = build_frontmatter(
            page_id="12345",
            title="My Page",
            space_key="DEV",
            base_url="https://confluence.example.com",
            version=42,
            last_modified="2025-04-01T10:30:00Z",
            labels=["api", "design"],
        )
        assert 'id: "12345"' in result
        assert 'title: "My Page"' in result
        assert 'space: "DEV"' in result
        assert "version: 42" in result
        assert 'last_modified: "2025-04-01T10:30:00Z"' in result
        assert '["api", "design"]' in result
        assert "https://confluence.example.com/spaces/DEV/pages/12345" in result
        assert result.startswith("---")
        assert result.endswith("---")

    def test_empty_labels(self):
        result = build_frontmatter(
            page_id="1",
            title="T",
            space_key="S",
            base_url="https://x.com",
            version=1,
            last_modified="2025-01-01T00:00:00Z",
            labels=[],
        )
        assert "labels: []" in result

    def test_title_with_quotes(self):
        result = build_frontmatter(
            page_id="1",
            title='Title with "quotes"',
            space_key="S",
            base_url="https://x.com",
            version=1,
            last_modified="2025-01-01T00:00:00Z",
            labels=[],
        )
        assert 'Title with \\"quotes\\"' in result


class TestBuildPageMarkdown:
    def test_full_page(self):
        result = build_page_markdown(
            page_id="12345",
            title="API Design",
            space_key="DEV",
            base_url="https://confluence.example.com",
            version=5,
            last_modified="2025-04-01T10:30:00Z",
            labels=["api"],
            body_html="<p>This is the body.</p>",
        )
        assert result.startswith("---")
        assert "# API Design" in result
        assert "This is the body." in result
