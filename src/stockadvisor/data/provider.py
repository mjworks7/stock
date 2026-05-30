"""데이터 공급자 인터페이스 + 종목 식별 유틸.

MarketDataProvider 를 구현하면 무료 라이브러리든 유료 API든
동일한 방식으로 끼워 넣을 수 있다 (의존성 역전).
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod

from ..domain import MacroSnapshot, Market, StockData, Ticker

_KR_CODE_RE = re.compile(r"^\d{6}$")


def detect_market(raw: str) -> Market:
    """입력 문자열로 시장 추정.

    6자리 숫자 -> 한국(KRX). 그 외 알파벳 -> 미국(US).
    명시적 접미사(.KS/.KQ)도 한국으로 인식.
    """
    s = raw.strip().upper()
    if s.endswith(".KS") or s.endswith(".KQ"):
        return Market.KR
    code = s.split(".")[0]
    if _KR_CODE_RE.match(code):
        return Market.KR
    return Market.US


def resolve_ticker(raw: str) -> Ticker:
    """원본 입력 -> Ticker. yfinance 조회 심볼을 구성한다.

    한국 종목은 KOSPI(.KS)를 우선 가정하되, 실제 조회 시
    free_provider 가 .KS/.KQ 를 순차 시도해 보정한다.
    """
    s = raw.strip().upper()
    market = detect_market(s)
    if market is Market.KR:
        code = s.split(".")[0]
        if s.endswith(".KQ"):
            yf = f"{code}.KQ"
        else:
            yf = f"{code}.KS"
        return Ticker(raw=code, market=market, yf_symbol=yf)
    return Ticker(raw=s, market=market, yf_symbol=s)


class MarketDataProvider(ABC):
    """시세/재무/거시 데이터 공급자 추상 인터페이스."""

    @abstractmethod
    def get_stock_data(self, ticker: Ticker) -> StockData:
        """단일 종목의 정량 데이터 번들을 반환."""

    @abstractmethod
    def get_macro(self, market: Market) -> MacroSnapshot:
        """해당 시장의 거시/국면 스냅샷을 반환."""
