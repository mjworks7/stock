"""시장별 라우팅 공급자.

KR 종목은 정밀 공급자(예: KIS)로, US 종목은 기본(무료) 공급자로 보낸다.
거시 스냅샷은 지정된 거시 공급자(기본: 무료)가 담당한다.
정밀 공급자 호출이 실패하면 폴백 공급자로 자동 재시도한다.
"""
from __future__ import annotations

from typing import Optional

from ..domain import MacroSnapshot, Market, StockData, Ticker
from .provider import MarketDataProvider


class CompositeProvider(MarketDataProvider):
    def __init__(
        self,
        kr_provider: MarketDataProvider,
        us_provider: MarketDataProvider,
        macro_provider: MarketDataProvider,
        fallback: Optional[MarketDataProvider] = None,
        log=lambda *_a, **_k: None,
    ) -> None:
        self.kr_provider = kr_provider
        self.us_provider = us_provider
        self.macro_provider = macro_provider
        self.fallback = fallback
        self.log = log

    def get_stock_data(self, ticker: Ticker) -> StockData:
        primary = self.kr_provider if ticker.market is Market.KR else self.us_provider
        try:
            return primary.get_stock_data(ticker)
        except Exception as e:
            if self.fallback is not None and self.fallback is not primary:
                self.log(f"[폴백] {ticker.display()} 정밀 공급자 실패({e}) → 기본 공급자로 재시도")
                return self.fallback.get_stock_data(ticker)
            raise

    def get_macro(self, market: Market) -> MacroSnapshot:
        return self.macro_provider.get_macro(market)
