"""Components for scraping the SWLW issues and their contents."""

import logging
import os

import requests
from bs4 import BeautifulSoup
from flyde.io import Input, InputMode, Output, Requiredness
from flyde.node import Component

from swlwi.net import BrowserClient, HTTPClient, extract_domain_from_url, needs_javascript_domain, should_skip_domain
from swlwi.parser import (
    SiteParser,
    clean_markdown,
    html_to_markdown,
)
from swlwi.schema import Article, Issue

log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)


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
        print(
            "Issue in SkipExistingIssues.inputs:",
            self.inputs["issue"].type,
            self.inputs["issue"].type.__module__,
        )
        print(
            "Issue in SkipExistingIssues.outputs:",
            self.outputs["issue"].type,
            self.outputs["issue"].type.__module__,
        )
        print("Type of value being sent:", type(issue), type(issue).__module__)
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

        if needs_javascript_domain(domain):
            logging.debug(f"Article '{article.title}' at {article.url} is on {domain} and needs JavaScript to fetch")
            return {"needs_javascript": article}

        try:
            response = self.http_client.get(article.url)

            if self.http_client.is_cloudflare_protected(response):
                logging.warning(f"CloudFlare protection detected for '{article.title}' at {article.url}")
                return {"needs_javascript": article}

            if self.http_client.needs_javascript(response):
                logging.debug(f"Article '{article.title}' at {article.url} needs JavaScript to fetch")
                return {"needs_javascript": article}

            article.html = self.http_client.decode_response_content(response)

        except Exception as e:
            logging.error(f"Failed to fetch article '{article.title}' at {article.url}: {e}")
            return {"needs_javascript": article}

        logging.info(f"Fetched article '{article.title}' at {article.url}")
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
        self.browser_client = BrowserClient()

    def process(self, article: Article) -> dict[str, Article]:
        try:
            html_content = self.browser_client.fetch(article.url)

            if html_content:
                article.html = html_content
                logging.info(f"Successfully fetched article '{article.title}' at {article.url} with Playwright")
            else:
                logging.error(f"Failed to load content for '{article.title}'")

        except Exception as e:
            logging.error(f"Failed to fetch article '{article.title}' at {article.url}: {e}")

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
            logger.error(f"No HTML content found for article '{article.title}' at {article.url}")
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

            # Update the article with the Markdown content
            article.markdown = markdown
            logger.info(
                f"Extracted article content from '{article.title}' at {article.url} ({len(markdown)} characters)"
            )

        except Exception as e:
            logger.error(f"Failed to process article content for '{article.title}' at {article.url}: {e}")
            article.markdown = f"Error processing content: {str(e)}"

        # Return the article
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
