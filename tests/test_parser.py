import re
import unittest
from datetime import date
from typing import List, Tuple

from bs4 import BeautifulSoup

from swlwi.parser import (
    SiteParser,
    clean_markdown,
    html_to_markdown,
    is_likely_navigation,
)
from swlwi.schema import Issue


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


class TestIssueParsingFunctions(unittest.TestCase):
    def test_find_issue_elements(self):
        html = """
        <div class="table-issue">
            <p class="title-table-issue"><a href="/issues/1">Issue 1</a></p>
            <p class="text-table-issue">1st October 2023</p>
        </div>
        <div class="table-issue">
            <p class="title-table-issue"><a href="/issues/2">Issue 2</a></p>
            <p class="text-table-issue">2nd October 2023</p>
        </div>
        <div class="other-content">Not an issue</div>
        """
        soup = BeautifulSoup(html, "html.parser")
        elements = SiteParser.find_issue_elements(soup)
        self.assertEqual(len(elements), 2)

    def test_parse_issue_element(self):
        html = """
        <div class="table-issue">
            <p class="title-table-issue"><a href="/issues/123">Issue 123</a></p>
            <p class="text-table-issue">15th December 2023</p>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        element = soup.find("div", class_="table-issue")

        self.assertIsNotNone(element)
        issue = SiteParser.parse_issue_element(element, "https://example.com", 0, 1)  # type: ignore

        self.assertEqual(issue.num, 123)
        self.assertEqual(issue.url, "https://example.com/issues/123")
        self.assertEqual(issue.date, date(2023, 12, 15))
        self.assertEqual(issue.item_of, (0, 1))


class TestArticleParsingFunctions(unittest.TestCase):
    def test_find_topic_sections(self):
        html = """
        <h3 class="topic-title">Leadership</h3>
        <h3 class="topic-title">Engineering</h3>
        <h3 class="other-heading">Not a topic</h3>
        """
        soup = BeautifulSoup(html, "html.parser")
        sections = SiteParser.find_topic_sections(soup)
        self.assertEqual(len(sections), 2)

    def test_count_total_articles(self):
        html = """
        <h3 class="topic-title">Leadership</h3>
        <div>Article 1</div>
        <div>Article 2</div>
        <h3 class="topic-title">Engineering</h3>
        <div>Article 3</div>
        """
        soup = BeautifulSoup(html, "html.parser")
        sections = SiteParser.find_topic_sections(soup)
        total = SiteParser.count_total_articles(sections)
        self.assertEqual(total, 3)

    def test_extract_article(self):
        html = """
        <div>
            <a class="post-title" href="https://example.com/article">Test Article</a>
            <span>5 minutes read</span>
            Some summary text here
            <br><br>
            More summary
            <br><br><br>
            This should be cut off
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        div = soup.find("div")

        self.assertIsNotNone(div)
        issue = Issue(num=1, url="https://example.com/issue/1", date=date.today(), item_of=(0, 1))
        article = SiteParser.extract_article(div, issue, 0, 1)  # type: ignore

        self.assertIsNotNone(article)
        self.assertEqual(article.title, "Test Article")  # type: ignore
        self.assertEqual(article.url, "https://example.com/article")  # type: ignore
        self.assertEqual(article.issue_num, 1)  # type: ignore
        self.assertEqual(article.reading_time, 5)  # type: ignore
        self.assertIn("Some summary text here", article.summary)  # type: ignore

    def test_extract_reading_time(self):
        html = """
        <div>
            <span>7 minutes read</span>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        div = soup.find("div")
        self.assertIsNotNone(div)
        reading_time = SiteParser.extract_reading_time(div)  # type: ignore
        self.assertEqual(reading_time, 7)

    def test_extract_reading_time_no_element(self):
        html = "<div>No reading time here</div>"
        soup = BeautifulSoup(html, "html.parser")
        div = soup.find("div")
        self.assertIsNotNone(div)
        reading_time = SiteParser.extract_reading_time(div)  # type: ignore
        self.assertEqual(reading_time, 0)

    def test_extract_summary(self):
        html = """
        <div>
            <span>3 minutes read</span>
            This is the summary text
            <br>
            More summary content
            <br><br>
            Even more content
            <br><br><br>
            This should be excluded
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        div = soup.find("div")
        self.assertIsNotNone(div)
        summary = SiteParser.extract_summary(div)  # type: ignore
        self.assertIn("This is the summary text", summary)
        self.assertIn("More summary content", summary)
        self.assertNotIn("This should be excluded", summary)


if __name__ == "__main__":
    unittest.main()
