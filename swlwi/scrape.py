"""Components for scraping the SWLW issues and their contents."""

import logging
import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from bs4.element import PageElement
from flyde.io import Input, InputMode, Output, Requiredness
from flyde.node import Component

from swlwi.net import BrowserClient, HTTPClient, extract_domain_from_url, needs_javascript_domain, should_skip_domain
from swlwi.parser import clean_markdown, html_to_markdown
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
        issue_elements = self._find_issue_elements(soup)
        total_issues = len(issue_elements)
        item_count = 0

        # Get the base URL
        base_url = "/".join(url.split("/")[:3])

        # Process each issue
        for element in issue_elements:
            issue = self._parse_issue_element(element, base_url, item_count, total_issues)

            # Send the issue to the next component
            self.send("issue", issue)
            logger.info(f"Processing issue #{issue.num}")

            # Increment the item count and exit if the limit is reached
            item_count += 1
            if limit > 0 and item_count >= limit:
                break

    def _find_issue_elements(self, soup: BeautifulSoup) -> list[PageElement]:
        return soup.find_all("div", class_="table-issue")

    def _parse_issue_element(self, element: PageElement, base_url: str, item_count: int, total_issues: int):
        title_element = element.find("p", class_="title-table-issue")  # type: ignore
        link_element = title_element.find("a")
        issue_url = link_element["href"]
        issue_num = int(issue_url.split("/")[-1])
        date_element = element.find("p", class_="text-table-issue")  # type: ignore
        issue_date_str = date_element.get_text(strip=True)

        logger.debug(f"Found issue #{issue_num} of {total_issues} from {issue_date_str}: {issue_url}")

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
        topic_sections = self._find_topic_sections(soup)
        # Count the total number of articles across all sections
        total_articles = self._count_total_articles(topic_sections)
        logger.debug(f"Found {total_articles} articles in issue #{issue.num}")

        # Loop through each topic section and extract articles
        item_count = 0
        for section in topic_sections:
            article_divs = section.find_next_siblings("div")
            for div in article_divs:
                article = self._extract_article(div, issue, item_count, total_articles)
                if article:
                    self.send("article", article)
                    item_count += 1

    def _find_topic_sections(self, soup: BeautifulSoup) -> list[PageElement]:
        return soup.find_all("h3", class_="topic-title")

    def _count_total_articles(self, topic_sections: list[PageElement]) -> int:
        total_articles = 0
        for section in topic_sections:
            article_divs = section.find_next_siblings("div")
            total_articles += len(article_divs)
        return total_articles

    def _extract_article(self, div: PageElement, issue: Issue, item_count: int, total_articles: int) -> Article | None:
        title_element = div.find("a", class_="post-title")  # type: ignore
        if not title_element:
            return None

        article_url = title_element["href"]
        article_title = title_element.get_text(strip=True)
        reading_time = self._extract_reading_time(div)
        summary = self._extract_summary(div)

        logger.info(
            f"Found article '{article_title}' at {article_url} in issue #{issue.num}. Reading time: {reading_time} minutes."
        )
        logger.debug(f"Summary:\n{summary}")

        return Article(
            title=article_title,
            url=article_url,
            issue_num=issue.num,
            reading_time=reading_time,
            summary=summary,
            item_of=(item_count, total_articles),
            parent_item_of=issue.item_of,
        )

    def _extract_reading_time(self, div: PageElement) -> int:
        reading_time_element = div.find(string=lambda t: "minutes read" in t)  # type: ignore
        return int(reading_time_element.split()[0]) if reading_time_element else 0

    def _extract_summary(self, div: PageElement) -> str:
        reading_time_element = div.find(string=lambda t: "minutes read" in t)  # type: ignore
        if not reading_time_element:
            return ""

        summary = ""
        summary_elements = reading_time_element.next_siblings
        br_count = 0
        for element in summary_elements:
            if element.name == "br":
                br_count += 1
                if br_count > 2:
                    break
                continue
            if element.name is None:
                summary += element.get_text(strip=True)
        return summary.strip()


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

        markdown = html_to_markdown(article.html)

        # Clean up the Markdown content
        markdown = clean_markdown(markdown)

        # Update the article with the Markdown content
        article.markdown = markdown
        logger.info(f"Extracted article content from '{article.title}' at {article.url}")

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

        with open(filename, "w") as file:
            file.write(header + article.markdown)
