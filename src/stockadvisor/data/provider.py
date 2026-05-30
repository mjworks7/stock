"""데이터 공급자 인터페이스 + 종목 식별 유틸.

MarketDataProvider 를 구현하면 무료 라이브러리든 유료 API든
동일한 방식으로 끼워 넣을 수 있다 (의존성 역전).
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod

from ..domain import MacroSnapshot, Market, StockData, Ticker
from .krx import code_to_name, has_hangul, is_kr_code, name_to_code

_KR_CODE_RE = re.compile(r"^\d{6}$")


def detect_market(raw: str) -> Market:
    """입력 문자열로 시장 추정.

    6자리 숫자 또는 한글 종목명 -> 한국(KRX). 그 외 알파벳 -> 미국(US).
    명시적 접미사(.KS/.KQ)도 한국으로 인식.
    """
    s = raw.strip()
    if has_hangul(s):
        return Market.KR
    su = s.upper()
    if su.endswith(".KS") or su.endswith(".KQ"):
        return Market.KR
    code = su.split(".")[0]
    if _KR_CODE_RE.match(code):
        return Market.KR
    return Market.US


def resolve_ticker(raw: str) -> Ticker:
    """원본 입력 -> Ticker. yfinance 조회 심볼을 구성한다.

    - 6자리 코드: 한국 종목(KOSPI .KS 우선, 조회 시 .KQ 보정)
    - 한글 종목명: 한국 종목으로 인식하되 코드는 미정 — 공급자가 이름→코드 변환
    - 그 외: 미국 종목
    """
    s = raw.strip()
    market = detect_market(s)
    if market is Market.KR:
        if has_hangul(s) and not is_kr_code(s):
            # 한글 이름 입력 — 코드는 공급자에서 해석(yf_symbol 은 임시로 이름)
            return Ticker(raw=s, market=market, yf_symbol="", name="")
        su = s.upper()
        code = su.split(".")[0]
        yf = f"{code}.KQ" if su.endswith(".KQ") else f"{code}.KS"
        return Ticker(raw=code, market=market, yf_symbol=yf)
    su = s.upper()
    return Ticker(raw=su, market=market, yf_symbol=su)


def ensure_kr_code(ticker: Ticker) -> Ticker:
    """KR 종목인데 코드가 아직 없으면(한글 이름 입력) 이름→코드로 변환.

    변환 성공 시 raw=코드, name=종목명, yf_symbol=코드.KS 로 채운 Ticker 반환.
    실패하면 yf_symbol 이 비어 있는 원본 Ticker 를 그대로 반환(호출측이 경고 처리).
    """
    if ticker.market is not Market.KR:
        return ticker
    if is_kr_code(ticker.raw):
        # 코드인데 이름이 비었으면 이름 채우기(선택적)
        if not ticker.name:
            nm = code_to_name(ticker.raw) or ""
            if nm:
                return Ticker(ticker.raw, ticker.market, ticker.yf_symbol, nm)
        return ticker
    # 한글 이름 등 — 코드로 변환 시도
    code = name_to_code(ticker.raw)
    if code:
        name = ticker.name or ticker.raw
        return Ticker(raw=code, market=Market.KR, yf_symbol=f"{code}.KS", name=name)
    return ticker


class MarketDataProvider(ABC):
    """시세/재무/거시 데이터 공급자 추상 인터페이스."""

    @abstractmethod
    def get_stock_data(self, ticker: Ticker) -> StockData:
        """단일 종목의 정량 데이터 번들을 반환."""

    @abstractmethod
    def get_macro(self, market: Market) -> MacroSnapshot:
        """해당 시장의 거시/국면 스냅샷을 반환."""

    def get_fx_usdkrw(self) -> float:
        """USD/KRW 환율. 기본 구현은 보수적 상수(공급자가 오버라이드)."""
        return 1350.0
