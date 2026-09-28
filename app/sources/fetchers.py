

class EmbeddedIframeSourceFetcher(HttpSourceFetcher):
    """Fetch an explicitly allowed iframe embedded by an official result page.

    Some lottery operator sites publish the current result inside an iframe on
    the official result page. The iframe may be same-origin or may use a
    distinct operator-controlled host; cross-origin hosts must be explicitly
    allowlisted by the caller.
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

    def __init__(
        self,
        *,
        allowed_iframe_hosts: set[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.allowed_iframe_hosts = {
            host.casefold() for host in (allowed_iframe_hosts or set())
        }

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
            iframe_host = parsed.hostname.casefold()
            if (
                iframe_host != host.casefold()
                and iframe_host not in self.allowed_iframe_hosts
            ):
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
            allowed_hosts={host.casefold(), *self.allowed_iframe_hosts},
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

    The official index has used more than one PDF path/naming convention,
    including links embedded in page scripts.
    """
