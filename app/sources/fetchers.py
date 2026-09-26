        fetcher = HttpSourceFetcher(
            timeout=self.timeout,
            user_agent=self.user_agent,
            allowed_hosts={host.casefold()},
            max_response_bytes=self.max_response_bytes,
            transport=self.transport,
        )

        def probe(draw_number: int) -> str | None:
            candidate_path = f"{prefix}{draw_number}{suffix}"
            candidate = parsed._replace(
                path=candidate_path,
                query="",
                fragment="",
            ).geturl()
            try:
                result = fetcher.fetch(candidate)
            except SourceFetchError:
                return None
            if not (
                "pdf" in result.content_type.casefold()
                or result.content.startswith(b"%PDF")
            ):
                return None

            # The official host may return a valid PDF/placeholder for a
            # future filename even when that draw has not been published.
            # A probe is therefore valid only when the PDF itself identifies
            # the same draw number.
            try:
                reader = PdfReader(BytesIO(result.content))
                pdf_text = " ".join(
                    (page.extract_text() or "") for page in reader.pages[:3]
                )
            except (PdfReadError, ValueError):
                # Test doubles and some legacy wrappers may expose the draw
                # marker as plain PDF-like bytes. They can still be validated
                # by the same identity check without accepting a bare PDF
                # signature as sufficient evidence.
                pdf_text = result.content.decode("latin-1", errors="ignore")
            normalized = re.sub(r"\s+", " ", pdf_text)
            draw_digits = str(draw_number)
            draw_pattern = re.compile(
                rf"\bsorteo\b.{{0,80}}?"
                rf"{''.join(f'[\s._:/-]*{digit}' for digit in draw_digits)}\b",
                re.IGNORECASE,
            )
            if draw_pattern.search(normalized) is None:
                return None
            return result.url

        first = latest_draw + 1
        if probe(first) is None:
            return None

        low = first
        step = 1
        high = first
        while step < 32:
            candidate = latest_draw + step * 2
            if probe(candidate) is None:
                high = candidate
                break
            low = candidate
            high = candidate
            step *= 2
        else:
            return probe(low)

        left, right = low, high - 1
        best = probe(low)
        while left <= right:
            mid = (left + right) // 2
            candidate = probe(mid)
            if candidate is not None:
                best = candidate
                left = mid + 1
            else:
                right = mid - 1
        return best

    def fetch(self, url: str) -> SourceFetchResult:
        index = super().fetch(url)
        if "html" not in index.content_type.casefold():
            raise SourceFetchError(
                "Cundinamarca acta index must be an HTML document"
            )

        html = index.content.decode("utf-8", errors="ignore")
        matches: list[tuple[int, int, str]] = []
        raw_urls = [match.group(1) for match in self._PDF_URL_RE.finditer(html)]