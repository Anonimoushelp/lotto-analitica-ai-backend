    def parse(
        self,
        result: SourceFetchResult,
        lottery_code: str | None = None,
    ) -> Iterable[Mapping[str, object]]:
        try:
            html = result.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceParseError("Traditional lottery HTML is not valid UTF-8") from exc

        text = " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", html)).split())
        text = re.sub(r"\s+", " ", text).strip()
        search_text = self._strip_accents(text)
        draw_match = self._DRAW_RE.search(search_text)
        code = (lottery_code or self.lottery_code).upper()
        if code == "LOTERIA_RISARALDA" and draw_match is None:
            # The official sales page has used several equivalent labels
            # (e.g. "Sorteo No.", "Sorteo Nro.", "Sorteo #").
            draw_match = re.search(
                r"\bsorteo\s*(?:n(?:o|ro)?\s*[°º.]?|numero\s*[°º.]?|#)?\s*(\d{3,6})\b",
                search_text,
                re.IGNORECASE,
            )
        date_matches = list(self._DATE_RE.finditer(search_text))
        month_first_date_matches = list(self._MONTH_FIRST_DATE_RE.finditer(search_text))