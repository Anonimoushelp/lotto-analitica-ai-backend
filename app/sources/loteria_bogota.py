import re
from datetime import date

from app.sources.base import (
    NormalizedDraw,
    OfficialSourceAdapter,
    SourceValidationError,
)


class BogotaLotteryAdapter(OfficialSourceAdapter):
    lottery_code = "LOTERIA_BOGOTA"
    source_url = "https://institucional.loteriadebogota.com/resultados/"

    def parse(self, payload: str) -> NormalizedDraw:
        pattern = re.compile(
            r"Sorteo\s+(?P<draw>\d+).*?"
            r"(?P<date>\d{1,2}\s+de\s+[A-Za-z]+\s+\d{4}).*?"
            r"Número\s+(?P<number>\d{4}).*?Serie\s+(?P<series>\d+)",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(payload)
        if not match:
            raise SourceValidationError("Bogotá result structure not found")
        months = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
        }
        raw_date = re.sub(r"\s+de\s+", " de ", match.group("date").lower())
        day, _, month, year = raw_date.split()
        number = match.group("number")
        if number == "0000" or match.group("series") == "000":
            raise SourceValidationError("Bogotá placeholder result rejected")
        draw_date = date(int(year), months[month], int(day))
        return NormalizedDraw(
            lottery_code=self.lottery_code,
            draw_number=match.group("draw"),
            draw_date=draw_date,
            main_numbers=[int(number)],
            metadata_json={
                "winning_number": number,
                "winning_series": match.group("series"),
            },
            source=self.source_url,
        ).validate()
