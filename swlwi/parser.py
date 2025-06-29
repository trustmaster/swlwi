import re

from bs4 import BeautifulSoup, Tag
from markdownify import MarkdownConverter


class CustomMarkdownConverter(MarkdownConverter):
    def convert_heading(self, *args: tuple, **kwargs: dict) -> str:
        # Add double newlines after headings
        return super().convert_heading(*args, **kwargs) + "\n"  # type: ignore

    def convert_p(self, *args, **kwargs) -> str:
        # Add double newlines after paragraphs
        return super().convert_p(*args, **kwargs) + "\n"

    def convert_list(self, *args, **kwargs) -> str:
        # Handle list spacing
        converted = super().convert_list(*args, **kwargs)
        if converted.strip():
            return converted + "\n"
        return converted

    def convert_li(self, *args, **kwargs) -> str:
        # Ensure proper list item spacing
        return super().convert_li(*args, **kwargs).rstrip() + "\n"


def html_to_markdown(html: bytes) -> str:
    """
    Converts HTML to Markdown, focusing on main content while removing navigation,
    ads, and other non-essential elements.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    unwanted_tags = [
        "head",
        "nav",
        "footer",
        "script",
        "style",
        "iframe",
        "form",
        "header",
        "aside",
        "button",
        "noscript",
        "svg",
        "path",
        ".nav",
        ".footer",
        ".sidebar",
        ".ads",
        ".comments",
        ".social-share",
        ".related-posts",
        ".subscription",
        "[role='navigation']",
        "[role='complementary']",
    ]

    # Remove by tag name and CSS selectors
    for selector in unwanted_tags:
        elements = soup.select(selector) if "." in selector or "[" in selector else soup.find_all(selector)
        for element in elements:
            if isinstance(element, Tag):
                element.decompose()

    # Use custom converter with proper spacing
    md = CustomMarkdownConverter(
        heading_style="ATX",
        bullets="-",  # Standardize bullet points
        autolinks=True,
        convert=[
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "p",
            "a",
            "b",
            "strong",
            "em",
            "i",
            "img",
            "ul",
            "ol",
            "li",
            "blockquote",
            "code",
            "pre",
            "table",
            "thead",
            "tbody",
            "tr",
            "th",
            "td",
        ],
    )

    markdown = md.convert_soup(soup)
    return clean_markdown(markdown)


def clean_markdown(markdown: str) -> str:
    """
    Cleans up the article markdown by removing unnecessary elements and standardizing format.
    """
    # Split into lines for easier processing
    lines = markdown.split("\n")
    cleaned_lines = []
    skip_next = False

    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue

        # Skip social media and navigation patterns
        if re.match(r"\s*(?:Follow|Share|Like|Tweet|Subscribe|Sign up|Sign in|Log in|Register)", line, re.I):
            continue

        # Skip social media links
        if re.match(r"\s*\[(Facebook|Twitter|LinkedIn|Instagram|YouTube|GitHub|Pinterest)[^\]]*\]\(http[^\)]+\)", line):
            continue

        # Skip social media links via URL
        if re.match(
            r"http[s]?://.*?(?:facebook|twitter|x|linkedin|instagram|youtube|github|pinterest|medium|substack)\.com",
            line,
        ):
            continue

        # Skip relative links
        if re.match(r"\s*\[.*\]\(/.*\)", line):
            continue

        # Skip author and metadata
        if re.match(r"\s*(?:By|Published on|Written by|Author)", line, re.I):
            continue

        # Skip reading time
        if re.match(r"\s*(?:\d+\s*min(?:ute)?s?\s*read)", line, re.I):
            continue

        # Skip navigation links
        if re.match(r"\s*-\s*\[.*\]\(.*\)", line):
            continue

        # Remove horizontal rules
        if re.match(r"\s*[-—_]{3,}\s*$", line):
            skip_next = False
            continue

        # Preserve content lines
        if line.strip():
            cleaned_lines.append(line)
        elif cleaned_lines and cleaned_lines[-1].strip():
            cleaned_lines.append("")

    # Join lines and clean up
    markdown = "\n".join(cleaned_lines)

    # Final cleanup patterns
    cleanup_patterns = [
        # Remove empty links and their brackets
        (r"\[([^\]]*)\]\(\s*\)", r"\1"),
        # Remove empty images
        (r"!\[([^\]]*)\]\(\s*\)", ""),
        # Remove empty headers
        (r"^#+\s*$", "", re.MULTILINE),
        # Normalize spaces after headers
        (r"(^#+.*)\n(?!\n)", r"\1\n\n", re.MULTILINE),
        # Normalize multiple newlines
        (r"\n{3,}", "\n\n"),
        # Clean up remaining whitespace
        (r"[ \t]+$", "", re.MULTILINE),
    ]

    for pattern, replacement, *flags in cleanup_patterns:
        flag = flags[0] if flags else 0
        markdown = re.sub(pattern, replacement, markdown, flags=flag)

    return markdown.strip()


def is_likely_navigation(text: str) -> bool:
    """
    Helper function to identify navigation-like content with more precise matching.
    """
    nav_patterns = [
        r"^menu\b",
        r"^navigation\b",
        r"^skip to\b",
        r"^go to\b",
        r"^search\b",
        r"^home$",
        r"^about$",
        r"^contact\b",
        r"^main menu\b",
    ]
    text_lower = text.lower()
    # More lenient matching for navigation patterns
    return any(re.search(pattern, text_lower, re.I) for pattern in nav_patterns)
