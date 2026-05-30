"""데이터 공급자 팩토리 — 설정/플래그에 따라 적절한 공급자 구성.

- offline            : 모의 공급자
- KIS 키 있음        : CompositeProvider(KR→KIS, US→free, macro→free, fallback→free)
- 그 외             : 무료 공급자 단독
"""
from __future__ import annotations

from ..config import Config
from .provider import MarketDataProvider


def build_provider(cfg: Config, offline: bool, log=lambda *_a, **_k: None) -> MarketDataProvider:
    if offline:
        from .mock_provider import MockMarketDataProvider

        return MockMarketDataProvider()

    from .free_provider import FreeMarketDataProvider

    free = FreeMarketDataProvider(lookback_days=cfg.price_lookback_days)

    if cfg.has_kis:
        try:
            from .composite_provider import CompositeProvider
            from .kis_provider import KisMarketDataProvider

            kis = KisMarketDataProvider(
                app_key=cfg.kis_app_key or "",
                app_secret=cfg.kis_app_secret or "",
                paper=cfg.kis_paper,
            )
            log("데이터 공급자: 국내=한국투자증권(KIS), 해외=무료(yfinance), 거시=무료")
            return CompositeProvider(
                kr_provider=kis,
                us_provider=free,
                macro_provider=free,
                fallback=free,
                log=log,
            )
        except Exception as e:
            log(f"[경고] KIS 공급자 초기화 실패({e}) → 무료 공급자로 대체")

    log("데이터 공급자: 무료(yfinance/FDR)")
    return free
