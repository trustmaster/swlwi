import unittest
from typing import List, Tuple
import re
from swlwi.parser import html_to_markdown, clean_markdown, is_likely_navigation


class TestHtmlToMarkdown(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None  # Show full diff in case of failure

    def test_html_to_markdown_basic_conversion(self):
        test_cases = [
            (b"<h1>Title</h1><p>Simple paragraph</p>", "# Title\n\nSimple paragraph"),
            (
                b"<div><h2>Subtitle</h2><p>Text with <strong>bold</strong></p></div>",
                "## Subtitle\n\nText with **bold**",
            ),
            (b"<article><ul><li>Item 1</li><li>Item 2</li></ul></article>", "- Item 1\n- Item 2"),
        ]

        for html, expected in test_cases:
            with self.subTest(html=html):
                result = html_to_markdown(html)
                # Add double newlines after headers if not present
                result = re.sub(r"(#.*)\n(?!\n)", r"\1\n\n", result)
                self.assertEqual(result.strip(), expected.strip())

    def test_removes_unwanted_elements(self):
        html = b"""
            <html>
                <nav>Navigation</nav>
                <header>Header</header>
                <main>
                    <h1>Main Content</h1>
                    <p>Important text</p>
                </main>
                <footer>Footer</footer>
                <script>console.log('test');</script>
            </html>
        """
        result = html_to_markdown(html)
        # Add double newlines after headers
        result = re.sub(r"(#.*)\n(?!\n)", r"\1\n\n", result)
        self.assertIn("# Main Content\n\n", result)
        self.assertIn("Important text", result)
        self.assertNotIn("Navigation", result)
        self.assertNotIn("Footer", result)
        self.assertNotIn("Header", result)
        self.assertNotIn("console.log", result)

    def test_handles_nested_content(self):
        html = b"""
            <div class="content">
                <h2>Section</h2>
                <div class="nested">
                    <p>Nested <em>emphasized</em> content</p>
                    <ul>
                        <li>Nested <strong>bold</strong> item</li>
                    </ul>
                </div>
            </div>
        """
        expected = """## Section

Nested *emphasized* content

- Nested **bold** item"""

        result = html_to_markdown(html)
        # Add double newlines after headers and paragraphs
        result = re.sub(r"(#.*|(?<![-*])\w.*)\n(?!\n)", r"\1\n\n", result)
        self.assertEqual(result.strip(), expected.strip())


class TestCleanMarkdown(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_clean_markdown_table_tests(self):
        test_cases: List[Tuple[str, str]] = [
            # Social media patterns
            ("Follow us on Twitter\nReal content", "Real content"),
            ("[Facebook](https://facebook.com)\nActual article", "Actual article"),
            # Navigation patterns - preserve content even with navigation-like elements
            ("- [Home](/)\n- [About](/about)\nContent", "Content"),
            # Author and metadata
            ("By John Doe\nPublished on 2024-01-01\nThe story", "The story"),
            # Reading time
            ("5 min read\n10 minutes read\nArticle text", "Article text"),
            # Empty elements
            ("# \n\nReal heading\n#", "Real heading"),
            # Multiple newlines
            ("First\n\n\n\nSecond", "First\n\nSecond"),
            # Common separators
            ("Text\n---\nMore text", "Text\nMore text"),
        ]

        for input_md, expected in test_cases:
            with self.subTest(input_md=input_md):
                result = clean_markdown(input_md)
                # Ensure proper spacing between elements
                result = re.sub(r"\n{3,}", "\n\n", result)
                self.assertEqual(result.strip(), expected.strip())

    def test_preserves_valid_content(self):
        valid_markdown = """# Main Title

## Section 1

This is a paragraph with **bold** and *italic* text.

- List item 1
- List item 2

> This is a blockquote"""

        result = clean_markdown(valid_markdown)
        # Normalize newlines
        result = re.sub(r"\n{3,}", "\n\n", result)
        expected = re.sub(r"\n{3,}", "\n\n", valid_markdown)
        self.assertEqual(result.strip(), expected.strip())


class TestIsLikelyNavigation(unittest.TestCase):
    def test_navigation_patterns(self):
        test_cases = [
            ("Main Menu", True),
            ("Skip to content", True),
            ("Navigation Links", True),
            ("Search our site", True),
            ("Contact Us", True),
            ("Regular content", False),
            ("Article about navigation", False),  # Should not match when 'navigation' is part of content
            ("How to navigate boats", False),
        ]

        for text, expected in test_cases:
            with self.subTest(text=text):
                self.assertEqual(is_likely_navigation(text), expected)


if __name__ == "__main__":
    unittest.main()
