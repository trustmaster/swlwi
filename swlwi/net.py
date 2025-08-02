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
    _timeout: float = 1

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
        # Check status codes that indicate protection
        if response.status_code in [403, 503, 429]:
            return True

        # Check response headers for CloudFlare indicators
        cf_headers = ["cf-ray", "cf-cache-status", "cf-request-id", "server", "cf-bgj", "cf-polished"]
        for header in cf_headers:
            if header in response.headers:
                return True

        # Check response body for CloudFlare content
        response_text = response.text.lower()
        cf_indicators = [
            "cloudflare",
            "checking your browser",
            "ddos protection",
            "enable javascript",
            "browser check",
            "security check",
            "cf-browser-verification",
            "challenge-platform",
        ]

        return any(indicator in response_text for indicator in cf_indicators)

    def needs_javascript(self, response: requests.Response) -> bool:
        """Check if the response indicates JavaScript is required."""
        # Use the utility function for analysis
        analysis = analyze_response_quality(response.content)
        return analysis["needs_javascript"] or not has_meaningful_content(response.content)

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
        self._page: Optional[Page] = None

    def fetch(self, url: str, timeout: int = 5000) -> Optional[bytes]:
        """
        Fetch a URL using Playwright with CloudFlare bypass support.

        Args:
            url: The URL to fetch
            timeout: Timeout in milliseconds (reduced for performance)

        Returns:
            HTML content as bytes, or None if fetch failed
        """
        domain = extract_domain_from_url(url)
        logger.debug(f"Starting browser fetch for {url} (domain: {domain})")

        self.rate_limiter.wait(domain)
        logger.debug(f"Rate limiting passed for {domain}")

        try:
            # Initialize browser if not already done
            if self._browser is None:
                logger.debug("Initializing browser...")
                self._init_browser()
                logger.debug("Browser initialized successfully")

            # Reuse existing page or create new one
            if self._page is None:
                logger.debug("Creating new page...")
                self._page = self._context.new_page()  # type: ignore
                logger.debug("Page created successfully")

            page = self._page
            if page is None:
                raise Exception("Failed to create page")

            logger.debug(f"Setting timeout to {timeout}ms")
            page.set_default_timeout(timeout)

            # Enable stealth mode
            logger.debug("Setting stealth headers")
            page.set_extra_http_headers(
                {
                    "Accept-Language": "en-US,en;q=0.9",
                    "DNT": "1",
                    "Sec-Ch-Ua": '"Chromium";v="120", "Google Chrome";v="120"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                }
            )

            logger.debug(f"Navigating to {url}...")
            response = page.goto(url, wait_until="commit", timeout=timeout)
            logger.debug(f"Navigation completed, status: {response.status if response else 'None'}")

            if response is None:
                raise Exception("Failed to fetch page: empty response")

            # Quick CloudFlare check - only if clearly detected
            if response.status in [403, 503]:
                logger.debug(f"Potential CloudFlare challenge detected (status {response.status})")
                cloudflare_passed = self._wait_for_cloudflare(page)
                if not cloudflare_passed:
                    logger.error("Failed to pass CloudFlare challenge")
                    return None
                logger.debug("CloudFlare challenge passed")

            # Skip content waiting for fast loading - just ensure basic DOM is ready
            try:
                logger.debug("Waiting for DOM content loaded...")
                page.wait_for_load_state("domcontentloaded", timeout=1000)
                logger.debug("DOM content loaded")
            except PlaywrightTimeoutError:
                logger.debug("DOM content load timeout - continuing anyway")
                pass  # Continue anyway

            # Get the final HTML after all JavaScript execution
            logger.debug("Extracting page content...")
            html_content = page.content()
            logger.debug(f"Content extracted: {len(html_content)} characters")

            # Ensure proper UTF-8 encoding
            if isinstance(html_content, str):
                html_content = html_content.encode("utf-8", errors="replace")

            logger.debug(f"Successfully fetched {url} ({len(html_content)} bytes)")
            return html_content

        except Exception as e:
            logger.error(f"Failed to fetch {url} with browser: {e}")
            logger.debug(f"Exception details: {type(e).__name__}: {str(e)}")
            return None

    def _init_browser(self):
        """Initialize the browser and context for reuse."""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-extensions",
                "--disable-plugins",
                "--disable-images",  # Faster loading without images
                "--disable-javascript-harmony-shipping",
                "--disable-logging",
                "--disable-web-security",
                "--aggressive-cache-discard",
            ],
        )

        self._context = self._browser.new_context(  # type: ignore
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
            java_script_enabled=True,
            bypass_csp=True,  # Bypass Content Security Policy
            ignore_https_errors=True,
            reduced_motion="reduce",
            color_scheme="light",
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
        if self._page:
            self._page.close()  # type: ignore
            self._page = None
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
        """Fast CloudFlare challenge detection and handling."""
        try:
            # Very quick check for obvious CloudFlare challenges
            challenge_selectors = [
                "iframe[src*='challenges']",
                "#challenge-form",
            ]

            for selector in challenge_selectors:
                if page.locator(selector).count() > 0:
                    logger.info("CloudFlare challenge detected, waiting for completion...")
                    # Wait for challenge to disappear with much shorter timeout
                    page.wait_for_selector(selector, state="detached", timeout=8000)
                    return True
            return True  # No challenge detected

        except PlaywrightTimeoutError:
            logger.warning("CloudFlare challenge timeout - continuing anyway")
            return True  # Continue even if challenge doesn't complete

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
        """Ultra-fast content detection - minimal waiting."""
        # Skip all waiting and just check if content exists now
        return self._check_content_loaded(page)


def extract_domain_from_url(url: str) -> str:
    """Extract the domain from a URL."""
    m = re.findall(r"https?://(?:[^./]+\.)*([^./]+\.[a-zA-Z][^./:]+)(?:/|$|:)", url)
    return m[0] if m else "unknown"


def should_skip_domain(domain: str) -> bool:
    """Check if a domain should be skipped for fetching."""
    skip_domains = ["x.com", "youtube.com"]
    return domain in skip_domains


def is_content_blocked(content: bytes) -> bool:
    """Check if content appears to be blocked or restricted."""
    try:
        text = content.decode("utf-8", errors="ignore").lower()

        blocked_indicators = [
            "access denied",
            "403 forbidden",
            "404 not found",
            "page not found",
            "blocked",
            "restricted",
            "paywall",
            "subscription required",
            "login required",
            "sign in to continue",
            "premium content",
        ]

        return any(indicator in text for indicator in blocked_indicators)
    except Exception:
        return False


def get_content_type_from_response(response) -> str:
    """Get content type from response headers or content analysis."""
    try:
        # Check response headers first
        content_type = response.headers.get("content-type", "").lower()
        if content_type:
            return content_type.split(";")[0].strip()

        # Fallback to content analysis
        content = response.content[:1000]  # Check first 1KB
        text = content.decode("utf-8", errors="ignore").lower()

        if text.startswith("<!doctype html") or "<html" in text:
            return "text/html"
        elif text.startswith("{") or text.startswith("["):
            return "application/json"
        elif text.startswith("<?xml"):
            return "application/xml"
        else:
            return "text/plain"

    except Exception:
        return "unknown"


def analyze_response_quality(content: bytes, url: str = "") -> dict:
    """Analyze the quality and characteristics of response content."""
    try:
        text = content.decode("utf-8", errors="ignore").lower()

        analysis = {
            "content_length": len(content),
            "text_length": len(text),
            "has_html_structure": False,
            "has_article_content": False,
            "is_blocked": False,
            "needs_javascript": False,
            "quality_score": 0.0,
        }

        # Check HTML structure
        html_indicators = ["<!doctype html", "<html", "<head", "<body"]
        analysis["has_html_structure"] = any(indicator in text for indicator in html_indicators)

        # Check for article content
        content_indicators = [
            "<article",
            "<main",
            "article-content",
            "story-content",
            "post-content",
            "entry-content",
        ]
        analysis["has_article_content"] = any(indicator in text for indicator in content_indicators)

        # Check if blocked
        analysis["is_blocked"] = is_content_blocked(content)

        # Check if needs JavaScript with comprehensive detection
        import re

        js_indicators = [
            r"enable.+javascript",
            r"javascript.+required",
            r"javascript.+disabled",
            r"please.+enable.+javascript",
            r"turn.+on.+javascript",
            r"javascript.+must.+be.+enabled",
            r"requires.+javascript",
            r"<noscript",
            r'id=["\']root["\']',
            r'id=["\']app["\']',
            r"loading.*app",
            r"react.*app",
            r"vue.*app",
            r"angular.*app",
            r"bundle.*\.js",
            r"window\.__.*__",
        ]

        # Check for very short content without meaningful structure
        has_minimal_content = len(text) < 1000 and not any(
            tag in text for tag in ["<article", "<main", "<section", "<p>"]
        )

        js_detected = any(re.search(pattern, text, re.IGNORECASE) for pattern in js_indicators)
        analysis["needs_javascript"] = js_detected or has_minimal_content

        # Calculate quality score (0.0 to 1.0)
        score = 0.0
        if analysis["content_length"] > 1000:
            score += 0.2
        if analysis["has_html_structure"]:
            score += 0.2
        if analysis["has_article_content"]:
            score += 0.3
        if not analysis["is_blocked"]:
            score += 0.2
        if not analysis["needs_javascript"]:
            score += 0.1

        analysis["quality_score"] = min(score, 1.0)

        return analysis

    except Exception:
        return {
            "content_length": len(content),
            "text_length": 0,
            "has_html_structure": False,
            "has_article_content": False,
            "is_blocked": False,
            "needs_javascript": False,
            "quality_score": 0.0,
        }


def has_meaningful_content(content: bytes) -> bool:
    """Check if the fetched content appears to have meaningful article content."""
    try:
        text = content.decode("utf-8", errors="ignore").lower()

        # Check for minimum content length (more lenient)
        if len(text) < 200:
            return False

        # Check for article content indicators
        content_indicators = [
            "<article",
            "<main",
            "article-content",
            "story-content",
            "post-content",
            "entry-content",
            "<section",
            "<div",  # More lenient
        ]

        # Check for reasonable amount of text content
        import re

        paragraphs = re.findall(r"<p[^>]*>([^<]+)</p>", text)
        text_content = " ".join(paragraphs)

        # Check for basic HTML structure
        has_basic_html = any(tag in text for tag in ["<html", "<body", "<head"])

        # Check content structure (more lenient)
        has_content_structure = any(indicator in text for indicator in content_indicators)
        has_text_content = len(text_content.strip()) > 100  # More lenient
        has_multiple_paragraphs = len(paragraphs) >= 2  # At least 2 paragraphs

        # Return true if we have basic HTML and either content structure OR meaningful text
        return has_basic_html and (has_content_structure or has_text_content or has_multiple_paragraphs)

    except Exception:
        return False


def needs_javascript_domain(domain: str) -> bool:
    """Check if a domain typically needs JavaScript for content."""
    # Common patterns for JS-heavy sites
    js_patterns = [
        "medium.com",
        "substack.com",
        "ghost.io",
        "notion.site",
        "vercel.app",
        "netlify.app",
        "firebase.app",
        "web.app",
    ]

    return any(pattern in domain for pattern in js_patterns)
