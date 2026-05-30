"""오프라인/테스트용 모의 데이터 공급자.

네트워크 없이 파이프라인 전체를 점검할 수 있도록 종목 코드로부터
결정적(deterministic)인 그럴듯한 값을 생성한다. 실제 시세가 아니다.
"""
from __future__ import annotations

from ..domain import MacroSnapshot, Market, StockData, Ticker
from .provider import MarketDataProvider


def _seed(raw: str) -> int:
    return sum(ord(c) for c in raw)


class MockMarketDataProvider(MarketDataProvider):
    """결정적 더미 데이터. --offline 모드에서 사용."""

    def get_stock_data(self, ticker: Ticker) -> StockData:
        s = _seed(ticker.raw)
        base_price = 50 + (s % 450)
        if ticker.market is Market.KR:
            base_price *= 1000  # 원화 스케일

        name = ticker.name or f"[MOCK]{ticker.raw}"
        t = Ticker(
            raw=ticker.raw, market=ticker.market, yf_symbol=ticker.yf_symbol, name=name
        )
        return StockData(
            ticker=t,
            currency=ticker.market.currency,
            price=round(base_price, 2),
            market_cap=base_price * (1_000_000 + s * 7777),
            per=round(8 + (s % 35), 1),
            forward_per=round(7 + (s % 30), 1),
            pbr=round(0.6 + (s % 60) / 10, 2),
            psr=round(1 + (s % 12), 2),
            ev_ebitda=round(5 + (s % 25), 1),
            dividend_yield=round((s % 5) / 100, 4),
            revenue_growth=round(-5 + (s % 45), 1),
            earnings_growth=round(-10 + (s % 60), 1),
            operating_margin=round(3 + (s % 30), 1),
            profit_margin=round(1 + (s % 25), 1),
            roe=round(2 + (s % 35), 1),
            debt_to_equity=round((s % 200), 1),
            current_ratio=round(0.8 + (s % 30) / 10, 2),
            free_cashflow=base_price * (s % 50_000),
            week52_high=round(base_price * 1.3, 2),
            week52_low=round(base_price * 0.7, 2),
            ma50=round(base_price * 0.98, 2),
            ma200=round(base_price * 0.92, 2),
            ret_1m=round(-8 + (s % 20), 2),
            ret_3m=round(-15 + (s % 35), 2),
            ret_6m=round(-20 + (s % 55), 2),
            ret_1y=round(-30 + (s % 90), 2),
            beta=round(0.6 + (s % 12) / 10, 2),
            sector=["Technology", "Healthcare", "Financials", "Energy", "Consumer"][s % 5],
            industry="Mock Industry",
            warnings=["오프라인 모의 데이터입니다 (실제 시세 아님)."],
        )

    def get_macro(self, market: Market) -> MacroSnapshot:
        return MacroSnapshot(
            as_of="2026-01-01",
            market=market,
            indicators={
                "기준금리": {"level": 4.5, "change_3m_pct": -0.5},
                "변동성지수 VIX": {"level": 17.0, "change_3m_pct": -3.0},
            },
            notes=["오프라인 모의 거시 데이터입니다."],
        )
