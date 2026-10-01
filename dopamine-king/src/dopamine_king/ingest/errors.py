"""Errors raised by the ingest package."""
from __future__ import annotations

from ..net import FetchError


class BlockedByPolicy(FetchError):
    """A fetch or a piece of content was refused on legal or ethical grounds.

    ``reason`` is a short machine friendly string: ``"tdm-reservation"``, ``"crawl-delay-too-long"``
    or ``"robots: <human readable explanation>"``.
    """

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{url}: blocked by policy ({reason})")
        self.url = url
        self.reason = reason
