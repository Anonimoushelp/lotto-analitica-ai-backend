import collections
import itertools
from datetime import date, datetime
from numbers import Integral

from sqlalchemy import select

from app.models.lottery_draw import LotteryDraw

STATISTICAL_ALGORITHMS = (
    "number_frequency", "number_recency", "even_odd_distribution",
    "sum_distribution", "pair_frequency", "consecutive_numbers",
)
_MAX_ANALYZABLE_DRAWS=10_000
_MAX_NUMBERS_PER_DRAW=100
_MAX_PAIR_OPERATIONS=1_000_000
_MAX_UNIQUE_NUMBERS=10_000
_MAX_UNIQUE_PAIRS=100_000

class StatisticalInputLimitError(ValueError): pass

class StatisticalService:
    STATISTICAL_ALGORITHMS = STATISTICAL_ALGORITHMS

    @staticmethod
    def _validate_lottery_id(lottery_id):
        if lottery_id is not None and (isinstance(lottery_id,bool) or not isinstance(lottery_id,Integral) or lottery_id<=0):
            raise ValueError("lottery_id must be a positive integer or null")

    @staticmethod
    def _validate_draws(draws):
        if len(draws)>_MAX_ANALYZABLE_DRAWS: raise StatisticalInputLimitError("Statistical analysis input is too large")
        unique_numbers=set(); unique_pairs=set(); pair_operations=0
        for draw in draws:
            if isinstance(draw.draw_date,datetime) or not isinstance(draw.draw_date,date): raise TypeError("Each draw must have a valid draw_date")
            numbers=draw.main_numbers or []
            if not isinstance(numbers,list): raise TypeError("main_numbers must be a list or null")
            if len(numbers)>_MAX_NUMBERS_PER_DRAW: raise StatisticalInputLimitError("A draw contains too many numbers")
            if any(isinstance(n,bool) or not isinstance(n,Integral) or n<=0 for n in numbers): raise ValueError("main_numbers must contain positive integers")
            if len(numbers)!=len(set(numbers)): raise ValueError("main_numbers cannot contain duplicate values")
            unique_numbers.update(numbers)
            if len(unique_numbers)>_MAX_UNIQUE_NUMBERS: raise StatisticalInputLimitError("Statistical number cardinality is too large")
            pair_operations += len(numbers)*(len(numbers)-1)//2
            if pair_operations>_MAX_PAIR_OPERATIONS: raise StatisticalInputLimitError("Statistical pair analysis input is too large")
            unique_pairs.update(itertools.combinations(sorted(numbers),2))
            if len(unique_pairs)>_MAX_UNIQUE_PAIRS: raise StatisticalInputLimitError("Statistical pair cardinality is too large")

    @staticmethod
    def _draw_key(draw):
        return (draw.draw_date,getattr(draw,"id",0) or 0,str(getattr(draw,"source","") or ""),str(getattr(draw,"draw_number","") or ""))

    @staticmethod
    def _load_draws(db, lottery_id, source=None):
        statement=select(LotteryDraw).where(LotteryDraw.lottery_id==lottery_id).order_by(LotteryDraw.draw_date.asc(),LotteryDraw.id.asc())
        if source is not None: statement=statement.where(LotteryDraw.source==source.strip())
        return list(db.scalars(statement.limit(_MAX_ANALYZABLE_DRAWS+1)).all())

    @staticmethod
    def analyze(draws, lottery_id=None, source=None):
        StatisticalService._validate_lottery_id(lottery_id)
        normalized_source=source.strip() if source is not None else None
        if source is not None and (not normalized_source or len(normalized_source)>255): raise ValueError("source must be a non-empty string or null")
        scoped=[d for d in draws if (lottery_id is None or d.lottery_id==lottery_id) and (normalized_source is None or d.source==normalized_source)]
        StatisticalService._validate_draws(scoped)
        ordered=sorted((d for d in scoped if d.main_numbers),key=StatisticalService._draw_key)
        frequency=collections.Counter(n for d in ordered for n in d.main_numbers)
        parity=collections.Counter(f"{sum(n%2==0 for n in d.main_numbers)}-{sum(n%2!=0 for n in d.main_numbers)}" for d in ordered)
        sums=[sum(d.main_numbers) for d in ordered]
        pairs=collections.Counter(p for d in ordered for p in itertools.combinations(sorted(set(d.main_numbers)),2))
        consecutive=[sum(r==l+1 for l,r in itertools.pairwise(sorted(set(d.main_numbers)))) for d in ordered]
        recency={}
        for index,draw in enumerate(ordered,1):
            for number in set(draw.main_numbers): recency[number]={"last_seen_draw":index,"draws_since_seen":len(ordered)-index}
        return {"number_frequency":dict(sorted(frequency.items())),"number_recency":dict(sorted(recency.items())),"even_odd_distribution":dict(sorted(parity.items())),"sum_distribution":{"count":len(sums),"minimum":min(sums) if sums else None,"maximum":max(sums) if sums else None,"average":round(sum(sums)/len(sums),2) if sums else None},"pair_frequency":{f"{a}-{b}":c for (a,b),c in sorted(pairs.items())},"consecutive_numbers":{"draws_with_consecutive":sum(c>0 for c in consecutive),"total_consecutive_pairs":sum(consecutive),"maximum_consecutive_pairs":max(consecutive) if consecutive else 0}}

    @staticmethod
    def analysis_response(db, lottery_id, source=None):
        StatisticalService._validate_lottery_id(lottery_id)
        draws = StatisticalService._load_draws(db, lottery_id, source)
        if len(draws) > _MAX_ANALYZABLE_DRAWS:
            raise StatisticalInputLimitError("Statistical analysis input is too large")
        analyzable = [d for d in draws if d.main_numbers]
        if not analyzable:
            return {
                "module_status": "STANDBY",
                "lottery_id": lottery_id,
                "draws_analyzed": 0,
                "algorithms_count": 0,
                "number_frequency": {},
                "number_recency": {},
                "even_odd_distribution": {},
                "sum_distribution": {"count": 0, "minimum": None, "maximum": None, "average": None},
                "pair_frequency": {},
                "consecutive_numbers": {
                    "draws_with_consecutive": 0,
                    "total_consecutive_pairs": 0,
                    "maximum_consecutive_pairs": 0,
                },
            }
        result = StatisticalService.analyze(
            analyzable, lottery_id=lottery_id, source=source
        )
        return {
            "module_status": "READY",
            "lottery_id": lottery_id,
            "draws_analyzed": len(analyzable),
            "algorithms_count": len(STATISTICAL_ALGORITHMS),
            **result,
        }

    @staticmethod
    def overview(db,lottery_id=None,source=None):
        StatisticalService._validate_lottery_id(lottery_id)
        draws=StatisticalService._load_draws(db,lottery_id,source) if lottery_id else list(db.scalars(select(LotteryDraw).limit(_MAX_ANALYZABLE_DRAWS+1)).all())
        if len(draws)>_MAX_ANALYZABLE_DRAWS: raise StatisticalInputLimitError("Statistical analysis input is too large")
        analyzable=[d for d in draws if d.main_numbers]
        if not analyzable: return {"module_status":"STANDBY","algorithms_count":0,"draws_analyzed":0}
        return {"module_status":"READY","algorithms_count":len(STATISTICAL_ALGORITHMS),"draws_analyzed":len(analyzable)}
