import re
from datetime import date

from app.sources.base import (
    NormalizedDraw,
    OfficialSourceAdapter,
    SourceValidationError,
)


class BalotoAdapter(OfficialSourceAdapter):
    lottery_code = "BALOTO"
    source_url = "https://baloto.com/resultados?page=0"

    def parse(self, payload: str) -> NormalizedDraw:
        pattern = re.compile(
            r"(?P<date>\d{1,2}\s+de\s+[A-Za-z]+\s+de\s+\d{4}).*?"
            r"(?P<n1>\d{2})\s*-\s*(?P<n2>\d{2})\s*-\s*(?P<n3>\d{2})"
            r"\s*-\s*(?P<n4>\d{2})\s*-\s*(?P<n5>\d{2})\s*-\s*"
            r"(?P<bonus>\d{2})",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(payload)
        if not match:
            raise SourceValidationError("Baloto result structure not found")
        months = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
        }
        day, month, year = match.group("date").lower().split(" de ")
        draw_date = date(int(year), months[month], int(day))
        main = [int(match.group(f"n{i}")) for i in range(1, 6)]
        bonus = [int(match.group("bonus"))]
        if len(set(main)) != 5 or any(n < 1 or n > 43 for n in main):
            raise SourceValidationError("invalid Baloto main numbers")
        if not 1 <= bonus[0] <= 16:
            raise SourceValidationError("invalid Baloto Superbalota")
        return NormalizedDraw(
            lottery_code=self.lottery_code,
            draw_number=draw_date.isoformat(),
            draw_date=draw_date,
            main_numbers=main,
            bonus_numbers=bonus,
            metadata_json={"game": "Baloto", "bonus_name": "Superbalota"},
            source=self.source_url,
        ).validate()
