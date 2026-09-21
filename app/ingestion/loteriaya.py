from datetime import date, timedelta
from typing import Any

import httpx

from app.ingestion.contracts import IngestionDraw

MAX_PROVIDER_RANGE_DAYS = 366


class LoteriaYaClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://www.loteriaya.com.co",
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch_draw(
        self,
        lottery_code: str,
        start: date,
        end: date,
    ) -> list[IngestionDraw]:
        if start > end:
            raise ValueError("start date cannot be after end date")

        results: list[IngestionDraw] = []
        current = start

        with httpx.Client(
            base_url=self.base_url,
            headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
            timeout=self.timeout,
        ) as client:
            while current <= end:
                chunk_end = min(
                    end,
                    current + timedelta(days=MAX_PROVIDER_RANGE_DAYS - 1),
                )
                response = client.get(
                    f"/v1/results/{lottery_code}",
                    params={
                        "from": current.isoformat(),
                        "to": chunk_end.isoformat(),
                    },
                )
                response.raise_for_status()
                payload = response.json()

                for item in payload.get("results", []):
                    parsed = self._parse_result(lottery_code, item)
                    if parsed is not None:
                        results.append(parsed)

                current = chunk_end + timedelta(days=1)

        return results

    @staticmethod
    def _parse_result(
        lottery_code: str,
        item: dict[str, Any],
    ) -> IngestionDraw | None:
        status = item.get("status")
        if status == "disputed" or item.get("no_draw") is True:
            return None

        balls = item.get("balls")
        if not isinstance(balls, list) or not balls:
            return None

        draw_date = date.fromisoformat(item["draw_date"])
        draw_number = item.get("draw_number")
        if draw_number is None:
            draw_number = f"{lottery_code}-{draw_date.isoformat()}"

        main_numbers = [int(value) for value in balls]
        super_ball = item.get("super_ball")
        bonus_numbers = [int(super_ball)] if super_ball is not None else None

        return IngestionDraw(
            lottery_code=lottery_code,
            draw_number=str(draw_number),
            draw_date=draw_date,
            main_numbers=main_numbers,
            bonus_numbers=bonus_numbers,
            source="loteriaya",
            metadata_json={
                "provider": "loteriaya",
                "provider_draw": item.get("draw"),
                "provider_name": item.get("name"),
                "category": item.get("category"),
                "status": status,
                "published_at": item.get("published_at"),
                "winning_number": item.get("winning_number"),
                "winning_series": item.get("winning_series"),
            },
        )
