import re
from datetime import date

from app.sources.base import (
    NormalizedDraw,
    OfficialSourceAdapter,
    SourceValidationError,
)


class MedellinLotteryAdapter(OfficialSourceAdapter):
    lottery_code = "LOTERIA_MEDELLIN"
    source_url = "https://loteriademedellin.com.co/results-template/"

    def parse(self, payload: str) -> NormalizedDraw:
        pattern = re.compile(
            r"Sorteo\s+(?P<draw>\d+).*?"
            r"(?P<date>\d{1,2}/[A-Za-z]+/\d{4}).*?"
            r"Número\s+(?P<number>\d{4})\s+Serie\s+(?P<series>\d{3})",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(payload)
        if not match:
            raise SourceValidationError("Medellín result structure not found")
        months = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
        }
        day, month, year = match.group("date").lower().split("/")
        number = match.group("number")
        series = match.group("series")
        if number == "0000" or series == "000" or year == "0000":
            raise SourceValidationError("Medellín placeholder result rejected")
        draw_date = date(int(year), months[month], int(day))
        return NormalizedDraw(
            lottery_code=self.lottery_code,
            draw_number=match.group("draw"),
            draw_date=draw_date,
            main_numbers=[int(number)],
            metadata_json={
                "winning_number": number,
                "winning_series": series,
            },
            source=self.source_url,
        ).validate()
