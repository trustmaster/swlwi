"""Components for scraping the SWLW issues and their contents."""

import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup
from bs4.element import PageElement
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from flyde.io import Input, InputMode, Output, Requiredness
from flyde.node import Component
from swlwi.parser import clean_markdown, html_to_markdown

log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)


@dataclass
class Issue:
    """Represents a newsletter issue"""

    num: int
    url: str
    date: date
    item_of: tuple[int, int] = (0, 0)  # (current, total)


@dataclass
class Article:
    """Represents an article within an issue"""

    title: str
    url: str
    issue_num: int = 0
    reading_time: int = 0  # minutes
    summary: str = ""
    html: bytes = b""
    markdown: str = ""
    item_of: tuple[int, int] = (0, 0)  # (current, total)
    parent_item_of: tuple[int, int] = (0, 0)  # parent issue's item_of


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

        return Issue(num=issue_num, url=issue_url, date=issue_date, item_of=(item_count, total_issues))


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


def _extract_domain_from_url(url: str) -> str:
    m = re.findall(r"https?://(?:[^./]+\.)*([^./]+\.[a-zA-Z][^./:]+)(?:/|$|:)", url)
    return m[0] if m else "unknown"


class _RateLimiter:
    """Singleton class to handle rate limiting per domain."""

    _instance = None
    _last_request_time: dict[str, datetime] = {}
    _timeout: float = 2

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(_RateLimiter, cls).__new__(cls)
        return cls._instance

    def wait(self, domain: str):
        now = datetime.now()
        if domain in self._last_request_time:
            elapsed = (now - self._last_request_time[domain]).total_seconds()
            if elapsed < self._timeout:
                sleep_time = self._timeout - elapsed
                logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds before fetching from {domain}")
                time.sleep(sleep_time)
        self._last_request_time[domain] = datetime.now()


class FetchArticle(Component):
    """Fetches the article HTML from the Internet."""

    inputs = {
        "article": Input(description="Article", type=Article),
    }

    outputs = {
        "complete": Output(description="Article with HTML content", type=Article),
        "needs_javascript": Output(description="Article that needs JavaScript to fetch", type=Article),
    }

    _rate_limiter = _RateLimiter()

    def process(self, article: Article) -> dict[str, Article]:
        domain = _extract_domain_from_url(article.url)

        if domain in ["x.com", "youtube.com"]:
            return {"complete": article}

        if domain in ["medium.com", "substack.com"] or ".medium.com" in domain or "substack.com" in domain:
            logging.debug(f"Article '{article.title}' at {article.url} is on Medium and needs JavaScript to fetch")
            return {"needs_javascript": article}

        self._rate_limiter.wait(domain)

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            }

            response = requests.get(article.url, headers=headers)

            if response.status_code == 403 or "cloudflare" in response.text.lower():
                logging.warning(f"CloudFlare protection detected for '{article.title}' at {article.url}")
                return {"needs_javascript": article}

            if re.findall(r"enable.+javascript", response.text, re.IGNORECASE):
                logging.debug(f"Article '{article.title}' at {article.url} needs JavaScript to fetch")
                return {"needs_javascript": article}

            encoding = (
                response.encoding.lower() if response.encoding and response.encoding.lower() != "utf-8" else "utf-8"
            )

            article.html = (
                response.content.decode(encoding).encode("utf-8") if encoding != "utf-8" else response.content
            )

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

    _rate_limiter = _RateLimiter()

    def _wait_for_cloudflare(self, page):
        """Wait for CloudFlare challenge to complete."""
        try:
            # Wait for CloudFlare challenge iframe or challenge form
            challenge_selectors = [
                "iframe[src*='challenges']",
                "#challenge-form",
                "#cf-challenge-running",
                "[id*='challenge']",  # Generic challenge ID
                "[class*='cloudflare']",  # Generic cloudflare class
            ]

            for selector in challenge_selectors:
                if page.locator(selector).count() > 0:
                    logging.info("CloudFlare challenge detected, waiting for completion...")
                    # Wait for challenge to disappear
                    page.wait_for_selector(selector, state="detached", timeout=30000)
                    # Additional wait to ensure page is fully loaded
                    time.sleep(3)
                    return True
            return False

        except PlaywrightTimeoutError:
            logging.error("Timeout waiting for CloudFlare challenge")
            return False

    def _check_content_loaded(self, page):
        """Check if meaningful content is present on the page."""
        try:
            # Check for presence of common content elements
            content_present = any(
                [
                    page.locator("article").count() > 0,
                    page.locator("[data-testid='storyContent']").count() > 0,
                    page.locator(".story-content").count() > 0,
                    page.locator(".article-content").count() > 0,
                    # More generic content checks
                    len(page.query_selector_all("p")) > 3,  # At least 3 paragraphs
                    len(page.query_selector_all("h1,h2,h3")) > 0,  # At least one heading
                ]
            )

            return content_present
        except Exception:
            return False

    def _wait_for_content(self, page):
        """Wait for article content to load with multiple strategies."""
        max_attempts = 3
        attempt = 0

        while attempt < max_attempts:
            try:
                # First, wait for network requests to settle
                page.wait_for_load_state("networkidle", timeout=10000)

                # Then check for various content indicators
                selectors = [
                    "article",
                    "[data-testid='storyContent']",
                    ".story-content",
                    ".article-content",
                    "div[id*='content']",  # Generic content ID
                    "div[class*='content']",  # Generic content class
                    "div[class*='article']",  # Generic article class
                    "div > p",  # Any div containing paragraphs
                ]

                # Try each selector
                for selector in selectors:
                    try:
                        element = page.wait_for_selector(selector, timeout=5000)
                        if element:
                            # Verify content is meaningful
                            if self._check_content_loaded(page):
                                return True
                    except PlaywrightTimeoutError:
                        continue

                # If no selector worked, scroll and try again
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                time.sleep(2)

                # Final check for meaningful content
                if self._check_content_loaded(page):
                    return True

                attempt += 1
                if attempt < max_attempts:
                    logging.warning(f"Content not found, attempt {attempt + 1} of {max_attempts}")
                    time.sleep(2)

            except PlaywrightTimeoutError:
                attempt += 1
                if attempt < max_attempts:
                    logging.warning(f"Timeout on attempt {attempt} of {max_attempts}, retrying...")
                    time.sleep(2)

        logging.error("Failed to detect content after all attempts")
        return False

    def process(self, article: Article) -> dict[str, Article]:
        domain = _extract_domain_from_url(article.url)
        self._rate_limiter.wait(domain)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process",
                    ],
                )

                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
                    java_script_enabled=True,
                    bypass_csp=True,  # Bypass Content Security Policy
                )

                # Add stealth scripts
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)

                page = context.new_page()
                page.set_default_timeout(45000)  # 45 second timeout

                # Enable stealth mode
                page.set_extra_http_headers(
                    {
                        "Accept-Language": "en-US,en;q=0.9",
                        "DNT": "1",
                        "Sec-Ch-Ua": '"Chromium";v="120", "Google Chrome";v="120"',
                        "Sec-Ch-Ua-Mobile": "?0",
                        "Sec-Ch-Ua-Platform": '"Windows"',
                    }
                )

                response = page.goto(article.url, wait_until="domcontentloaded")

                if response is None:
                    raise Exception("Failed to fetch page: empty response")

                if response.status in [403, 503] or "cloudflare" in response.url.lower():
                    cloudflare_passed = self._wait_for_cloudflare(page)
                    if not cloudflare_passed:
                        logging.error("Failed to pass CloudFlare challenge")
                        browser.close()
                        return {"article": article}

                content_loaded = self._wait_for_content(page)

                if not content_loaded:
                    logging.error(f"Failed to load content for '{article.title}'")
                    browser.close()
                    return {"article": article}

                # Final wait to ensure all dynamic content is loaded
                time.sleep(2)

                # Get the final HTML after all JavaScript execution
                article.html = page.content().encode("utf-8")
                browser.close()

        except Exception as e:
            logging.error(f"Failed to fetch article '{article.title}' at {article.url}: {e}")
            return {"article": article}

        logging.info(f"Successfully fetched article '{article.title}' at {article.url} with Playwright")
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
