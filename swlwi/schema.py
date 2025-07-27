"""Schema for messages used in the application."""

from dataclasses import dataclass
from datetime import date


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
