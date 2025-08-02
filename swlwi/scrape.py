"""Components for scraping the SWLW issues and their contents."""

import atexit
import logging
import os
import signal
import sys

import requests
from bs4 import BeautifulSoup
from flyde.io import Input, InputMode, Output, Requiredness
from flyde.node import Component

from swlwi.net import (
    BrowserClient,
    HTTPClient,
    extract_domain_from_url,
    has_meaningful_content,
    needs_javascript_domain,
    should_skip_domain,
)
from swlwi.parser import (
    SiteParser,
    clean_markdown,
    html_to_markdown,
)
from swlwi.schema import Article, Issue

log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

# Shared browser client instance to avoid initialization overhead
_shared_browser_client = None


def get_shared_browser_client():
    """Get or create a shared browser client instance."""
    global _shared_browser_client
    if _shared_browser_client is None:
        try:
            logger.info("Initializing shared browser client...")
            _shared_browser_client = BrowserClient()
            logger.info("Shared browser client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize shared browser client: {e}")
            # Return None instead of crashing - calling code should handle this
            return None
    return _shared_browser_client


def cleanup_shared_browser_client():
    """Cleanup the shared browser client when shutting down."""
    global _shared_browser_client
    if _shared_browser_client is not None:
        try:
            logger.info("Closing shared browser client...")
            _shared_browser_client.close()
            logger.info("Shared browser client closed successfully")
        except Exception as e:
            logger.error(f"Error closing shared browser client: {e}")
        finally:
            _shared_browser_client = None


def _signal_handler(signum, frame):
    """Handle interrupt signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    cleanup_shared_browser_client()
    sys.exit(0)


# Register signal handlers and cleanup function
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)
atexit.register(cleanup_shared_browser_client)


class ListIssues(Component):
    """Fetches the index by the URL, parses it and returns a stream of issues and their URLs."""

    inputs = {
        "url": Input(description="URL of the index page", type=str),
        "limit": Input(description="Limit the number of issues to fetch", type=int, mode=InputMode.STICKY),  # type: ignore
    }

    outputs = {
        "issue": Output(description="List of issues", type=Issue),
    }

    def process(self, url: str, limit: int):
        logger.debug(f"Fetching the index page at {url}")

        # Get the page content using the requests library
        response = requests.get(url)

        # Parse the HTML content using BeautifulSoup
        soup = BeautifulSoup(response.content, "html.parser")
        issue_elements = SiteParser.find_issue_elements(soup)
        total_issues = len(issue_elements)
        item_count = 0

        # Get the base URL
        base_url = "/".join(url.split("/")[:3])

        # Process each issue
        for element in issue_elements:
            issue = SiteParser.parse_issue_element(element, base_url, item_count, total_issues)

            # Send the issue to the next component
            self.send("issue", issue)
            logger.info(f"Processing issue #{issue.num}")

            # Increment the item count and exit if the limit is reached
            item_count += 1
            if limit > 0 and item_count >= limit:
                break


class SkipExistingIssues(Component):
    """Checks if an issue already exists in the index and skips it if it does."""

    inputs = {
        "issue": Input(description="Issue", type=Issue),
        "path": Input(description="Path to the index", type=str, mode=InputMode.STICKY),
        "force_all": Input(
            description="Force processing all issues",
            type=bool,
            mode=InputMode.STICKY,
            value=False,
            required=Requiredness.REQUIRED_IF_CONNECTED,
        ),
    }

    outputs = {
        "issue": Output(description="Issue", type=Issue),
    }

    def process(self, issue: Issue, path: str, force_all: bool = False):
        logger.debug(f"Checking if issue #{issue.num} exists. Force all: {force_all}")
        if force_all:
            logger.info(f"Force processing issue #{issue.num}")
            self.send("issue", issue)
            return

        # Check if the issue exists
        issue_path = os.path.join(path, f"issue-{issue.num}")
        if not os.path.exists(issue_path):
            logger.info(f"Issue #{issue.num} not found at path '{issue_path}'. Processing.")
            self.send("issue", issue)
        else:
            logger.info(f"Issue #{issue.num} already exists. Skipping.")


class ExtractArticles(Component):
    """Extracts articles from the issue page."""

    inputs = {
        "issue": Input(description="Issue", type=Issue),
    }

    outputs = {
        "article": Output(description="Article", type=Article),
    }

    def process(self, issue: Issue):
        logger.debug(f"Fetching issue #{issue.num} at {issue.url}")

        # Get the page content and parse it
        response = requests.get(issue.url)
        soup = BeautifulSoup(response.content, "html.parser")

        # Find the topic sections
        topic_sections = SiteParser.find_topic_sections(soup)
        # Count the total number of articles across all sections
        total_articles = SiteParser.count_total_articles(topic_sections)
        logger.debug(f"Found {total_articles} articles in issue #{issue.num}")

        # Loop through each topic section and extract articles
        item_count = 0
        for i, section in enumerate(topic_sections):
            next_section = topic_sections[i + 1] if i + 1 < len(topic_sections) else None
            article_divs = SiteParser.get_articles_for_section(section, next_section)

            for div in article_divs:
                article = SiteParser.extract_article(div, issue, item_count, total_articles)
                if article:
                    logger.info(
                        f"Found article '{article.title}' at {article.url} in issue #{issue.num}. Reading time: {article.reading_time} minutes."
                    )
                    logger.debug(f"Summary:\n{article.summary}")
                    self.send("article", article)
                    item_count += 1


class FetchArticle(Component):
    """Fetches the article HTML from the Internet."""

    inputs = {
        "article": Input(description="Article", type=Article),
    }

    outputs = {
        "complete": Output(description="Article with HTML content", type=Article),
        "needs_javascript": Output(description="Article that needs JavaScript to fetch", type=Article),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.http_client = HTTPClient()

    def process(self, article: Article) -> dict[str, Article]:
        domain = extract_domain_from_url(article.url)

        if should_skip_domain(domain):
            return {"complete": article}

        # Try HTTP first regardless of domain - let content analysis decide
        try:
            response = self.http_client.get(article.url, timeout=10)

            # Check for various protection/JS requirements
            if self.http_client.is_cloudflare_protected(response):
                logger.warning(
                    f"CloudFlare protection detected for '{article.title}' at {article.url} - routing to browser client"
                )
                return {"needs_javascript": article}

            if self.http_client.needs_javascript(response):
                logger.debug(
                    f"Article '{article.title}' at {article.url} needs JavaScript based on content - routing to browser client"
                )
                return {"needs_javascript": article}

            # Additional content quality check
            decoded_content = self.http_client.decode_response_content(response)
            if not has_meaningful_content(decoded_content):
                logger.debug(
                    f"Article '{article.title}' at {article.url} has poor content quality - trying browser client"
                )
                return {"needs_javascript": article}

            # Domain-based fallback check (only after content analysis)
            if needs_javascript_domain(domain):
                logger.debug(
                    f"Article '{article.title}' at {article.url} is on JS-heavy domain {domain} - trying browser client"
                )
                return {"needs_javascript": article}

            article.html = decoded_content

        except Exception as e:
            logger.error(f"Failed to fetch article '{article.title}' at {article.url}: {e} - routing to browser client")
            return {"needs_javascript": article}

        logger.info(f"Fetched article '{article.title}' at {article.url} via HTTP")
        return {"complete": article}


class FetchArticleWithJavaScript(Component):
    """Fetches the article SPA contents using Playwright with CloudFlare bypass support."""

    inputs = {
        "article": Input(description="Article", type=Article),
    }

    outputs = {
        "article": Output(description="Article with content", type=Article),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        try:
            self.browser_client = get_shared_browser_client()
            logger.info("Browser client initialized successfully for JavaScript fetching")
        except Exception as e:
            logger.error(f"Failed to initialize browser client: {e}")
            self.browser_client = None

    def process(self, article: Article) -> dict[str, Article]:
        logger.info(f"Starting browser fetch for '{article.title}' at {article.url}")

        # Check if browser client is available
        if not self.browser_client:
            logger.error(f"Browser client not available for '{article.title}' - setting empty content")
            article.html = b""
            return {"article": article}

        try:
            # Add timeout to prevent hanging - use shorter timeout for faster failure
            html_content = self.browser_client.fetch(article.url, timeout=10000)  # 10 seconds

            if html_content:
                article.html = html_content
                logger.info(
                    f"Successfully fetched article '{article.title}' at {article.url} with Playwright ({len(html_content)} bytes)"
                )
            else:
                logger.warning(f"Browser returned no content for '{article.title}' - continuing with empty HTML")
                # Continue processing even if no content - don't block the pipeline
                article.html = b""

        except Exception as e:
            logger.error(f"Failed to fetch article '{article.title}' at {article.url}: {e}")
            logger.debug(f"Exception type: {type(e).__name__}")
            # Set empty HTML to ensure pipeline continues
            article.html = b""

        logger.info(f"Completed browser fetch for '{article.title}' - continuing pipeline")
        return {"article": article}


class ExtractArticleContent(Component):
    """Extracts the article content from the HTML and converts it to Markdown."""

    inputs = {
        "article": Input(description="Article", type=Article),
    }

    outputs = {
        "article": Output(description="Article with content", type=Article),
    }

    def process(self, article: Article) -> dict[str, Article]:
        if not article.html:
            logger.warning(
                f"No HTML content found for article '{article.title}' at {article.url} - setting placeholder content"
            )
            article.markdown = f"Content could not be fetched for this article. Please visit the source: {article.url}"
            return {"article": article}

        try:
            markdown = html_to_markdown(article.html)

            # Clean up the Markdown content
            markdown = clean_markdown(markdown)

            # Validate that we have meaningful content
            if len(markdown.strip()) < 50:
                logger.warning(
                    f"Article content seems too short ({len(markdown)} chars) for '{article.title}' at {article.url}"
                )
                # If content is too short, add a note but don't fail
                if not markdown.strip():
                    markdown = (
                        f"Content could not be extracted for this article. Please visit the source: {article.url}"
                    )

            # Update the article with the Markdown content
            article.markdown = markdown
            logger.info(
                f"Extracted article content from '{article.title}' at {article.url} ({len(markdown)} characters)"
            )

        except Exception as e:
            logger.error(f"Failed to process article content for '{article.title}' at {article.url}: {e}")
            article.markdown = f"Error processing content: {str(e)}\n\nPlease visit the source: {article.url}"

        # Return the article - always continue the pipeline
        return {"article": article}


class SaveArticle(Component):
    """Saves the article to a file."""

    inputs = {
        "article": Input(description="Article", type=Article),
        "path": Input(description="Path prefix to save the article", type=str, mode=InputMode.STICKY),  # type: ignore
    }

    def process(self, article: Article, path: str):
        # Save the article to a file
        dir_name = f"{path}/issue-{article.issue_num}"
        os.makedirs(dir_name, exist_ok=True)
        filename = f"{dir_name}/article-{article.item_of[0]}.md"

        logger.info(f"Saving article '{article.title}' to {filename}")

        header = f"""# {article.title}

Source: [{article.url}]({article.url})
Reading time: {article.reading_time} minutes

{article.summary}

---

"""

        try:
            with open(filename, "w", encoding="utf-8") as file:
                content = header + (article.markdown or "")
                file.write(content)
                logger.debug(f"Successfully wrote {len(content)} characters to {filename}")
        except UnicodeEncodeError as e:
            logger.error(f"Unicode encoding error writing {filename}: {e}")
            # Try with error replacement
            with open(filename, "w", encoding="utf-8", errors="replace") as file:
                content = header + (article.markdown or "")
                file.write(content)
                logger.warning("Wrote file with character replacements due to encoding issues")
        except Exception as e:
            logger.error(f"Failed to write article file {filename}: {e}")
