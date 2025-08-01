"""Network client utilities for web scraping with HTTP and browser automation."""

import logging
import re
import time
from datetime import datetime
from typing import Any, Optional

import chardet
import requests
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


class RateLimiter:
    """Singleton class to handle rate limiting per domain."""

    _instance = None
    _last_request_time: dict[str, datetime] = {}
    _timeout: float = 2

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RateLimiter, cls).__new__(cls)
        return cls._instance

    def wait(self, domain: str):
        """Wait if necessary to respect rate limiting for the given domain."""
        now = datetime.now()
        if domain in self._last_request_time:
            elapsed = (now - self._last_request_time[domain]).total_seconds()
            if elapsed < self._timeout:
                sleep_time = self._timeout - elapsed
                logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds before fetching from {domain}")
                time.sleep(sleep_time)
        self._last_request_time[domain] = datetime.now()


class HTTPClient:
    """HTTP client with proper headers and rate limiting."""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.rate_limiter = rate_limiter or RateLimiter()
        self.session = requests.Session()
        self._setup_default_headers()

    def _setup_default_headers(self):
        """Set up default headers to mimic a real browser."""
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            }
        )

    def get(self, url: str, use_rate_limiting: bool = True, **kwargs) -> requests.Response:
        """
        Perform a GET request with rate limiting and proper error handling.

        Args:
            url: The URL to fetch
            use_rate_limiting: Whether to apply rate limiting
            **kwargs: Additional arguments to pass to requests.get

        Returns:
            requests.Response object

        Raises:
            requests.RequestException: On HTTP errors
        """
        if use_rate_limiting:
            domain = extract_domain_from_url(url)
            self.rate_limiter.wait(domain)

        # Ensure proper handling of compressed content
        if "stream" not in kwargs:
            kwargs["stream"] = False

        response = self.session.get(url, **kwargs)

        # Force decompression of content if it's compressed
        _ = response.content  # This triggers decompression

        return response

    def is_cloudflare_protected(self, response: requests.Response) -> bool:
        """Check if the response indicates CloudFlare protection."""
        return response.status_code == 403 or "cloudflare" in response.text.lower()

    def needs_javascript(self, response: requests.Response) -> bool:
        """Check if the response indicates JavaScript is required."""
        import re

        return bool(re.findall(r"enable.+javascript", response.text, re.IGNORECASE))

    def decode_response_content(self, response: requests.Response) -> bytes:
        """
        Decode response content with proper encoding handling.

        Args:
            response: The requests.Response object

        Returns:
            Decoded content as UTF-8 bytes
        """
        # Ensure content is decompressed by accessing it
        content = response.content
        logger.debug(f"Raw content length: {len(content)} bytes")

        # Check if content appears to be compressed but wasn't decompressed
        if content.startswith(b"\x1f\x8b"):  # gzip magic number
            logger.warning("Content appears to be gzip compressed but wasn't decompressed")
        elif content.startswith(b"BZh"):  # bzip2 magic number
            logger.warning("Content appears to be bzip2 compressed but wasn't decompressed")
        elif len(content) > 0 and content[0:2] in [b"\x78\x9c", b"\x78\x01", b"\x78\xda"]:  # zlib
            logger.warning("Content appears to be zlib compressed but wasn't decompressed")

        # Get the encoding from response headers or detect it
        encoding = response.encoding
        logger.debug(f"Response encoding from headers: {encoding}")

        # If no encoding is specified or it's invalid, try to detect it
        if not encoding or encoding.lower() == "iso-8859-1":
            # requests defaults to ISO-8859-1 when no charset is specified
            # Try to detect the actual encoding from content
            try:
                detected = chardet.detect(content[:10000])  # Only check first 10KB for speed
                if detected and detected["encoding"] and detected["confidence"] > 0.7:
                    encoding = detected["encoding"]
                    logger.debug(f"Detected encoding: {encoding} (confidence: {detected['confidence']:.2f})")
                else:
                    encoding = "utf-8"
                    logger.debug("Using UTF-8 fallback (low confidence or no detection)")
            except ImportError:
                # chardet not available, fallback to utf-8
                encoding = "utf-8"
                logger.debug("chardet not available, using UTF-8 fallback")

        # Ensure we have a valid encoding
        if not encoding:
            encoding = "utf-8"

        try:
            # Decode content using detected/specified encoding and re-encode as UTF-8
            if encoding.lower() != "utf-8":
                decoded_content = content.decode(encoding, errors="replace")
                result = decoded_content.encode("utf-8")
                logger.debug(f"Successfully decoded {len(content)} bytes using {encoding}")
                return result
            else:
                # Even if encoding is UTF-8, validate and clean the content
                try:
                    # Try to decode as UTF-8 to validate
                    content.decode("utf-8")
                    logger.debug(f"Content already in UTF-8, returning {len(content)} bytes")
                    return content
                except UnicodeDecodeError:
                    # Content is not valid UTF-8, decode with error replacement
                    decoded_content = content.decode("utf-8", errors="replace")
                    result = decoded_content.encode("utf-8")
                    logger.debug(f"Fixed invalid UTF-8 content, returning {len(result)} bytes")
                    return result
        except (UnicodeDecodeError, LookupError) as e:
            logger.warning(f"Encoding error with {encoding}: {e}, falling back to UTF-8")
            # Fallback to UTF-8 with error replacement if encoding fails
            try:
                decoded_content = content.decode("utf-8", errors="replace")
                return decoded_content.encode("utf-8")
            except UnicodeDecodeError:
                logger.warning("UTF-8 fallback failed, using latin-1 as last resort")
                # Last resort: use latin-1 which can decode any byte sequence
                decoded_content = content.decode("latin-1", errors="replace")
                return decoded_content.encode("utf-8")


class BrowserClient:
    """Browser client for fetching JavaScript-heavy websites with CloudFlare bypass support."""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.rate_limiter = rate_limiter or RateLimiter()
        self._browser: Optional[Any] = None
        self._context: Optional[Any] = None
        self._playwright: Optional[Any] = None

    def fetch(self, url: str, timeout: int = 45000) -> Optional[bytes]:
        """
        Fetch a URL using Playwright with CloudFlare bypass support.

        Args:
            url: The URL to fetch
            timeout: Timeout in milliseconds

        Returns:
            HTML content as bytes, or None if fetch failed
        """
        domain = extract_domain_from_url(url)
        self.rate_limiter.wait(domain)

        try:
            # Initialize browser if not already done
            if self._browser is None:
                self._init_browser()

            page = self._context.new_page()  # type: ignore
            page.set_default_timeout(timeout)

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

            response = page.goto(url, wait_until="domcontentloaded")

            if response is None:
                raise Exception("Failed to fetch page: empty response")

            if response.status in [403, 503] or "cloudflare" in response.url.lower():
                cloudflare_passed = self._wait_for_cloudflare(page)
                if not cloudflare_passed:
                    logger.error("Failed to pass CloudFlare challenge")
                    page.close()
                    return None

            content_loaded = self._wait_for_content(page)

            if not content_loaded:
                logger.error(f"Failed to load content for {url}")
                page.close()
                return None

            # Final wait to ensure all dynamic content is loaded
            time.sleep(2)

            # Get the final HTML after all JavaScript execution
            html_content = page.content()

            # Ensure proper UTF-8 encoding
            if isinstance(html_content, str):
                html_content = html_content.encode("utf-8", errors="replace")

            page.close()
            return html_content

        except Exception as e:
            logger.error(f"Failed to fetch {url} with browser: {e}")
            return None

    def _init_browser(self):
        """Initialize the browser and context for reuse."""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )

        self._context = self._browser.new_context(  # type: ignore
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
            java_script_enabled=True,
            bypass_csp=True,  # Bypass Content Security Policy
        )

        # Add stealth scripts
        self._context.add_init_script(  # type: ignore
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """
        )

    def close(self):
        """Close the browser and cleanup resources."""
        if self._context:
            self._context.close()  # type: ignore
            self._context = None
        if self._browser:
            self._browser.close()  # type: ignore
            self._browser = None
        if hasattr(self, "_playwright") and self._playwright:
            self._playwright.stop()  # type: ignore

    def __del__(self):
        """Cleanup resources when the object is destroyed."""
        self.close()

    def _wait_for_cloudflare(self, page: Page) -> bool:
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
                    logger.info("CloudFlare challenge detected, waiting for completion...")
                    # Wait for challenge to disappear
                    page.wait_for_selector(selector, state="detached", timeout=30000)
                    # Additional wait to ensure page is fully loaded
                    time.sleep(3)
                    return True
            return False

        except PlaywrightTimeoutError:
            logger.error("Timeout waiting for CloudFlare challenge")
            return False

    def _check_content_loaded(self, page: Page) -> bool:
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

    def _wait_for_content(self, page: Page) -> bool:
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
                    logger.warning(f"Content not found, attempt {attempt + 1} of {max_attempts}")
                    time.sleep(2)

            except PlaywrightTimeoutError:
                attempt += 1
                if attempt < max_attempts:
                    logger.warning(f"Timeout on attempt {attempt} of {max_attempts}, retrying...")
                    time.sleep(2)

        logger.error("Failed to detect content after all attempts")
        return False


def extract_domain_from_url(url: str) -> str:
    """Extract the domain from a URL."""
    m = re.findall(r"https?://(?:[^./]+\.)*([^./]+\.[a-zA-Z][^./:]+)(?:/|$|:)", url)
    return m[0] if m else "unknown"


def should_skip_domain(domain: str) -> bool:
    """Check if a domain should be skipped for fetching."""
    skip_domains = ["x.com", "youtube.com"]
    return domain in skip_domains


def needs_javascript_domain(domain: str) -> bool:
    """Check if a domain typically needs JavaScript for content."""
    js_domains = ["medium.com", "substack.com"]
    return domain in js_domains or ".medium.com" in domain or "substack.com" in domain
