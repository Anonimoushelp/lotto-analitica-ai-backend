from datetime import datetime
import re

from app.sources.base import NormalizedDraw, OfficialSourceAdapter, SourceValidationError


class SelaeAdapter(OfficialSourceAdapter):
    """Parser for SELAE's documented per-game result files."""

    def __init__(self, game_id: str = "EMIL", game_name: str = "euromillones"):
        self.game_id = game_id
        self.game_name = game_name
        self.lottery_code = f"SELAE_{game_id}"
        self.source_url = f"https://www.loteriasyapuestas.es/f/loterias/resultados/{game_name}.html?game_id={game_id}&fecha_sorteo=yyyymmdd"

    def parse(self, payload: str) -> NormalizedDraw:
        date_match = re.search(r"(?<!\\d)(\\d{2})[/-](\\d{2})[/-](\\d{4})(?!\\d)", payload)
        numbers_match = re.search(r"(?:NÚMEROS|NUMEROS|NUMBERS)\\s*[:\\-]?\\s*((?:\\d{1,2}\\s*){5})", payload, re.IGNORECASE)
        if not date_match or not numbers_match:
            raise SourceValidationError("SELAE result structure not found")
        day, month, year = map(int, date_match.groups())
        draw_date = datetime(year, month, day).date()
        main = [int(n) for n in re.findall(r"\\d{1,2}", numbers_match.group(1))]
        if len(main) != 5 or len(set(main)) != 5:
            raise SourceValidationError("invalid SELAE five-number result")
        return NormalizedDraw(
            lottery_code=self.lottery_code,
            draw_number=draw_date.isoformat(),
            draw_date=draw_date,
            main_numbers=main,
            metadata_json={"game_id": self.game_id, "game_name": self.game_name},
            source=self.source_url,
        ).validate()
