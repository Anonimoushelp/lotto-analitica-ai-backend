from app.sources.baloto import BalotoAdapter
from app.sources.loteria_bogota import BogotaLotteryAdapter
from app.sources.loteria_medellin import MedellinLotteryAdapter
from app.sources.selae import SelaeAdapter

OFFICIAL_SOURCE_ADAPTERS = {
    "baloto": BalotoAdapter,
    "bogota": BogotaLotteryAdapter,
    "medellin": MedellinLotteryAdapter,
    "selae-euromillones": SelaeAdapter,
}


def get_official_adapter(source: str):
    adapter_factory = OFFICIAL_SOURCE_ADAPTERS.get(source.lower())
    if adapter_factory is None:
        raise KeyError(source)
    return adapter_factory()
