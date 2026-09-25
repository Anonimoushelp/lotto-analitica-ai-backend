from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import unquote, urljoin, urlparse

import httpx


@dataclass(frozen=True)
class SourceFetchResult:
    url: str
    status_code: int
    content: bytes
    content_type: str
    fetched_at: datetime


class SourceFetchError(RuntimeError):
    """Raised when a configured source cannot be fetched safely."""


class SourceFetcher(Protocol):
    def fetch(self, url: str) -> SourceFetchResult:
        """Fetch one source URL and return immutable response metadata."""


class HttpSourceFetcher:
    """HTTP fetcher kept independent from parsing and persistence."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        allowed_hosts: set[str] | None = None,
        max_response_bytes: int = 2_000_000,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be greater than zero")
        self.timeout = timeout
        self.user_agent = user_agent
        self.allowed_hosts = {host.casefold() for host in (allowed_hosts or set())}
        self.max_response_bytes = max_response_bytes
        self.transport = transport

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            raise SourceFetchError("Source URL must use HTTPS")
        if (
            not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise SourceFetchError(
                "Source URL must contain a valid hostname without credentials"
            )
        if self.allowed_hosts and parsed.hostname.casefold() not in self.allowed_hosts:
            raise SourceFetchError("Source URL host is not allowlisted")

    def fetch(self, url: str) -> SourceFetchResult:
        self._validate_url(url)
        try:
            with (
                httpx.Client(
                    timeout=self.timeout,
                    follow_redirects=True,
                    headers={"User-Agent": self.user_agent},
                    transport=self.transport,
                ) as client,
                client.stream("GET", url) as response,
            ):
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if (
                    content_length is not None
                    and int(content_length) > self.max_response_bytes
                ):
                    raise SourceFetchError(
                        "Source response exceeds configured size limit"
                    )

                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > self.max_response_bytes:
                        raise SourceFetchError(
                            "Source response exceeds configured size limit"
                        )
                    chunks.append(chunk)

                content = b"".join(chunks)
                final_url = str(response.url)
                final_host = urlparse(final_url).hostname
                if (
                    self.allowed_hosts
                    and (
                        final_host is None
                        or final_host.casefold() not in self.allowed_hosts
                    )
                ):
                    raise SourceFetchError(
                        "Redirected source host is not allowlisted"
                    )
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceFetchError(f"Source fetch failed for {url}") from exc

        return SourceFetchResult(
            url=final_url,
            status_code=response.status_code,
            content=content,
            content_type=response.headers.get("content-type", ""),
            fetched_at=datetime.now().astimezone(),
        )


class EmbeddedIframeSourceFetcher(HttpSourceFetcher):
    """Fetch a same-origin iframe embedded by an official result page.

    Some lottery operator sites publish the current result inside an iframe on
    the official home page. This keeps that navigation in the source-fetching
    layer so parsing remains focused on the final result document.
    """

    _IFRAME_RE = re.compile(
        r"<iframe\b[^>]*?(?:src|data-src)\s*=\s*"
        r"([\"'])(.*?)\1[^>]*>",
        re.IGNORECASE | re.DOTALL,
    )
    _HINTS = (
        "resultado",
        "resultados",
        "sorteo",
        "premio",
        "acta",
    )
    _RESULT_SIGNAL_RE = re.compile(
        r"\b(?:sorteo|resultado|premio|ganador)\b",
        re.IGNORECASE,
    )
    _FOUR_DIGIT_RE = re.compile(
        r"\b\d{4}\b|(?<!\d)(?:\d\s*){4}(?!\d)"
    )

    def fetch(self, url: str) -> SourceFetchResult:
        initial = super().fetch(url)
        if "html" not in initial.content_type.casefold():
            return initial

        host = urlparse(initial.url).hostname
        if not host:
            return initial

        candidates: list[tuple[int, str]] = []
        html = initial.content.decode("utf-8", errors="ignore")
        for match in self._IFRAME_RE.finditer(html):
            raw_url = match.group(2).strip()
            if not raw_url:
                continue
            iframe_url = urljoin(initial.url, raw_url)
            parsed = urlparse(iframe_url)
            if parsed.scheme.lower() != "https" or not parsed.hostname:
                continue
            if parsed.hostname.casefold() != host.casefold():
                continue
            haystack = f"{raw_url} {match.group(0)}".casefold()
            score = sum(haystack.count(hint) for hint in self._HINTS)
            candidates.append((score, iframe_url))

        if not candidates:
            return initial

        candidates.sort(key=lambda item: (-item[0], item[1]))
        nested_fetcher = HttpSourceFetcher(
            timeout=self.timeout,
            user_agent=self.user_agent,
            allowed_hosts={host.casefold()},
            max_response_bytes=self.max_response_bytes,
            transport=self.transport,
        )

        for _, iframe_url in candidates:
            try:
                nested = nested_fetcher.fetch(iframe_url)
            except SourceFetchError:
                continue

            nested_html = nested.content.decode("utf-8", errors="ignore")
            if (
                self._RESULT_SIGNAL_RE.search(nested_html)
                and self._FOUR_DIGIT_RE.search(nested_html)
            ):
                return nested

        raise SourceFetchError(
            f"Embedded result iframe could not be fetched for {initial.url}"
        )


class CundinamarcaActaSourceFetcher(HttpSourceFetcher):
    """Select and fetch the latest official Cundinamarca results acta.

    The official index has used more than one PDF path/naming convention.
    """

    _PDF_URL_RE = re.compile(
        r"""(?:href|data-href|src)\s*=\s*["']([^"']+\.pdf(?:\?[^"']*)?)["']""",
        re.IGNORECASE,
    )
    _DRAW_RE = re.compile(
        r"""(?:sorteo|resultado|acta)[^0-9]{0,60}(\d{3,6})(?!\d)""",
        re.IGNORECASE,
    )

    def fetch(self, url: str) -> SourceFetchResult:
        index = super().fetch(url)
        if "html" not in index.content_type.casefold():
            raise SourceFetchError(
                "Cundinamarca acta index must be an HTML document"
            )

        html = index.content.decode("utf-8", errors="ignore")
        matches: list[tuple[int, int, str]] = []
        for match in self._PDF_URL_RE.finditer(html):
            raw_url = html_lib.unescape(match.group(1))
            decoded_url = unquote(raw_url)
            lowered = decoded_url.casefold()
            if not any(
                keyword in lowered for keyword in ("acta", "sorteo", "resultado")
            ):
                continue
            draw_match = self._DRAW_RE.search(decoded_url)
            if draw_match is None:
                continue
            year_match = re.search(r"(20\d{2})", decoded_url)
            year = int(year_match.group(1)) if year_match else 0
            draw_number = int(draw_match.group(1))
            matches.append((year, draw_number, decoded_url))

        if not matches:
            raise SourceFetchError(
                f"No official Cundinamarca result acta links found in {index.url}"
            )

        _, _, latest_url = max(matches, key=lambda item: (item[0], item[1], item[2]))
        acta_url = urljoin(index.url, latest_url)
        host = urlparse(index.url).hostname
        nested_fetcher = HttpSourceFetcher(
            timeout=self.timeout,
            user_agent=self.user_agent,
            allowed_hosts={host.casefold()} if host else None,
            max_response_bytes=self.max_response_bytes,
            transport=self.transport,
        )
        result = nested_fetcher.fetch(acta_url)
        if "pdf" not in result.content_type.casefold() and not result.content.startswith(
            b"%PDF"
        ):
            raise SourceFetchError(
                f"Official Cundinamarca acta is not a PDF: {result.url}"
            )
        return result
