import re
from datetime import datetime

from bs4 import BeautifulSoup, Tag
from bs4.element import PageElement
from markdownify import MarkdownConverter

from swlwi.schema import Article, Issue


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


class SiteParser:
    """
    Parser class for extracting issues and articles from Software Lead Weekly site content.

    This class provides static methods for parsing HTML content from the SWLW website,
    extracting structured data about issues and articles. It handles the specific HTML
    structure and CSS classes used by the site.

    The class is organized into two main areas:
    - Issue parsing: extracting issue metadata from the issues index page
    - Article parsing: extracting article details from individual issue pages

    All methods are static, making this a utility class that doesn't require instantiation.
    """

    @staticmethod
    def find_issue_elements(soup: BeautifulSoup) -> list[PageElement]:
        """
        Find issue elements in the HTML soup.

        Args:
            soup: BeautifulSoup object containing the issues index page HTML

        Returns:
            List of PageElement objects representing individual issues
        """
        return soup.find_all("div", class_="table-issue")

    @staticmethod
    def parse_issue_element(element: PageElement, base_url: str, item_count: int, total_issues: int) -> Issue:
        """
        Parse an individual issue element and return an Issue object.

        Args:
            element: PageElement containing issue HTML structure
            base_url: Base URL for constructing absolute URLs
            item_count: Current item index (0-based)
            total_issues: Total number of issues being processed

        Returns:
            Issue object with parsed metadata
        """
        title_element = element.find("p", class_="title-table-issue")  # type: ignore
        link_element = title_element.find("a")
        issue_url = link_element["href"]
        issue_num = int(issue_url.split("/")[-1])
        date_element = element.find("p", class_="text-table-issue")  # type: ignore
        issue_date_str = date_element.get_text(strip=True)

        # Parse the date string
        issue_date_str = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", issue_date_str)
        issue_date = datetime.strptime(issue_date_str, "%d %B %Y").date()

        # Make the url absolute
        if not issue_url.startswith("http"):
            # Add a forward slash to issue url if needed
            if not issue_url.startswith("/"):
                issue_url = "/" + issue_url
            issue_url = base_url + issue_url

        return Issue(
            num=issue_num,
            url=issue_url,
            date=issue_date,
            item_of=(item_count, total_issues),
        )

    @staticmethod
    def find_topic_sections(soup: BeautifulSoup) -> list[PageElement]:
        """
        Find topic sections in the HTML soup.

        Args:
            soup: BeautifulSoup object containing an issue page HTML

        Returns:
            List of PageElement objects representing topic section headers
        """
        return soup.find_all("h3", class_="topic-title")

    @staticmethod
    def get_articles_for_section(section: PageElement, next_section: PageElement | None = None) -> list[PageElement]:
        """
        Get article divs for a specific topic section until the next section.

        Args:
            section: PageElement representing a topic section header
            next_section: Next topic section header, or None if this is the last section

        Returns:
            List of PageElement objects representing article divs in this section
        """
        next_siblings = list(section.next_siblings)

        # Find the next topic section (if any)
        next_section_index = None
        if next_section:
            try:
                next_section_index = next_siblings.index(next_section)
            except ValueError:
                next_section_index = None

        # Get divs until the next section (or end if it's the last section)
        article_divs = []
        for sibling in next_siblings[:next_section_index]:
            if isinstance(sibling, Tag) and sibling.name == "div":
                article_divs.append(sibling)

        return article_divs

    @staticmethod
    def count_total_articles(topic_sections: list[PageElement]) -> int:
        """
        Count the total number of articles across all topic sections.

        Args:
            topic_sections: List of topic section PageElements

        Returns:
            Total count of articles across all sections
        """
        total_articles = 0
        for i, section in enumerate(topic_sections):
            next_section = topic_sections[i + 1] if i + 1 < len(topic_sections) else None
            article_divs = SiteParser.get_articles_for_section(section, next_section)
            total_articles += len(article_divs)
        return total_articles

    @staticmethod
    def extract_article(div: PageElement, issue: Issue, item_count: int, total_articles: int) -> Article | None:
        """
        Extract article data from a div element.

        Args:
            div: PageElement containing article HTML structure
            issue: Issue object this article belongs to
            item_count: Current article index (0-based)
            total_articles: Total number of articles in this issue

        Returns:
            Article object with parsed data, or None if parsing fails
        """
        title_element = div.find("a", class_="post-title")  # type: ignore
        if not title_element:
            return None

        article_url = title_element["href"]
        article_title = title_element.get_text(strip=True)
        reading_time = SiteParser.extract_reading_time(div)
        summary = SiteParser.extract_summary(div)

        return Article(
            title=article_title,
            url=article_url,
            issue_num=issue.num,
            reading_time=reading_time,
            summary=summary,
            item_of=(item_count, total_articles),
            parent_item_of=issue.item_of,
        )

    @staticmethod
    def extract_reading_time(div: PageElement) -> int:
        """
        Extract reading time from a div element.

        Args:
            div: PageElement containing article HTML structure

        Returns:
            Reading time in minutes, or 0 if not found
        """
        reading_time_element = div.find(string=lambda t: "minutes read" in t)  # type: ignore
        return int(reading_time_element.split()[0]) if reading_time_element else 0

    @staticmethod
    def extract_summary(div: PageElement) -> str:
        """
        Extract summary text from a div element.

        Parses the article div to find summary text that appears after the
        reading time indicator but before social sharing links.

        Args:
            div: PageElement containing article HTML structure

        Returns:
            Summary text, or empty string if not found
        """
        reading_time_element = div.find(string=lambda t: "minutes read" in t)  # type: ignore
        if not reading_time_element:
            return ""

        summary = ""
        br_count = 0
        found_reading_time = False

        # Iterate through all children of the div
        for element in getattr(div, "children", []):
            # Check if this element contains the reading time text
            if hasattr(element, "strip") and "minutes read" in str(element):
                found_reading_time = True
                continue
            elif hasattr(element, "get_text") and "minutes read" in element.get_text():
                found_reading_time = True
                continue

            # Only start collecting summary after we've found the reading time
            if not found_reading_time:
                continue

            # Handle BR tags
            if hasattr(element, "name") and element.name == "br":
                br_count += 1
                if br_count > 2:
                    break
                continue

            # Handle text nodes
            if hasattr(element, "name") and element.name is None:
                text = str(element).strip()
                if text:
                    summary += text + " "
            elif hasattr(element, "get_text"):
                # This is an HTML element, get its text
                text = element.get_text(strip=True)
                if text and not any(
                    keyword in text.lower() for keyword in ["read", "share", "pocket", "instapaper", "twitter", "email"]
                ):
                    summary += text + " "

        return summary.strip()
