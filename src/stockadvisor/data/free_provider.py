"""무료 라이브러리 기반 데이터 공급자 (yfinance + FinanceDataReader).

가능한 한 방어적으로 구현한다. 일부 필드가 비어도 분석은 진행하되
StockData.warnings 에 누락 사실을 남긴다. 나중에 유료 API 공급자로
교체하려면 MarketDataProvider 를 구현한 새 클래스를 만들면 된다.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from ..domain import MacroSnapshot, Market, StockData, Ticker
from .provider import MarketDataProvider, ensure_kr_code as _ensure_kr_code


def _f(v: Any) -> Optional[float]:
    """안전한 float 변환. None/NaN/문자열 등은 None 으로."""
    try:
        if v is None:
            return None
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def _pct(v: Any) -> Optional[float]:
    """소수 비율(0.12)을 퍼센트(12.0)로. 이미 퍼센트면 그대로 두기 애매하므로
    yfinance 관례(소수)를 가정."""
    f = _f(v)
    return None if f is None else round(f * 100, 2)


class FreeMarketDataProvider(MarketDataProvider):
    def __init__(self, lookback_days: int = 400) -> None:
        self.lookback_days = lookback_days
        import yfinance as yf  # 지연 import (테스트 시 미설치 환경 허용)

        self._yf = yf

    # ----------------------------------------------------------------- stock
    def get_stock_data(self, ticker: Ticker) -> StockData:
        yf = self._yf
        ticker = _ensure_kr_code(ticker)
        data = StockData(ticker=ticker, currency=ticker.market.currency)
        if ticker.market is Market.KR and not ticker.yf_symbol:
            data.warnings.append(
                f"'{ticker.raw}' 을(를) KRX 코드로 변환하지 못했습니다 — 정확한 종목코드(예: 111770)를 입력하세요."
            )
            return data

        yf_symbol, info = self._resolve_symbol_info(ticker)
        if yf_symbol != ticker.yf_symbol:
            # KR .KS -> .KQ 보정 등
            ticker = Ticker(
                raw=ticker.raw, market=ticker.market, yf_symbol=yf_symbol, name=ticker.name
            )
            data.ticker = ticker

        if not info:
            data.warnings.append("기본 정보(info) 조회 실패 — 일부 지표가 비어 있을 수 있습니다.")
            info = {}

        # 종목명
        name = info.get("longName") or info.get("shortName") or ticker.raw
        data.ticker = Ticker(
            raw=ticker.raw, market=ticker.market, yf_symbol=ticker.yf_symbol, name=name
        )

        # 가격/시총
        data.price = _f(info.get("currentPrice")) or _f(info.get("regularMarketPrice"))
        data.market_cap = _f(info.get("marketCap"))

        # 밸류에이션
        data.per = _f(info.get("trailingPE"))
        data.forward_per = _f(info.get("forwardPE"))
        data.pbr = _f(info.get("priceToBook"))
        data.psr = _f(info.get("priceToSalesTrailing12Months"))
        data.ev_ebitda = _f(info.get("enterpriseToEbitda"))
        data.dividend_yield = _f(info.get("dividendYield"))

        # 성장성/수익성
        data.revenue_growth = _pct(info.get("revenueGrowth"))
        data.earnings_growth = _pct(info.get("earningsGrowth"))
        data.operating_margin = _pct(info.get("operatingMargins"))
        data.profit_margin = _pct(info.get("profitMargins"))
        data.roe = _pct(info.get("returnOnEquity"))
        data.debt_to_equity = _f(info.get("debtToEquity"))
        data.current_ratio = _f(info.get("currentRatio"))
        data.free_cashflow = _f(info.get("freeCashflow"))
        data.beta = _f(info.get("beta"))

        # 52주 고저
        data.week52_high = _f(info.get("fiftyTwoWeekHigh"))
        data.week52_low = _f(info.get("fiftyTwoWeekLow"))
        data.ma50 = _f(info.get("fiftyDayAverage"))
        data.ma200 = _f(info.get("twoHundredDayAverage"))

        # 분류
        data.sector = info.get("sector") or ""
        data.industry = info.get("industry") or ""

        # 가격 히스토리 기반 수익률
        self._fill_returns(yf, ticker.yf_symbol, data)

        return data

    def _resolve_symbol_info(self, ticker: Ticker) -> tuple[str, dict]:
        """KR 종목은 .KS -> .KQ 순으로 유효한 심볼을 찾는다."""
        yf = self._yf
        candidates = [ticker.yf_symbol]
        if ticker.market is Market.KR:
            base = ticker.raw
            for suffix in (".KS", ".KQ"):
                cand = f"{base}{suffix}"
                if cand not in candidates:
                    candidates.append(cand)
        for sym in candidates:
            try:
                info = yf.Ticker(sym).get_info()
            except Exception:
                info = {}
            if info and (info.get("currentPrice") or info.get("regularMarketPrice")):
                return sym, info
        # 못 찾으면 첫 후보 + 빈 정보
        return candidates[0], {}

    def _fill_returns(self, yf, symbol: str, data: StockData) -> None:
        try:
            hist = yf.Ticker(symbol).history(period=f"{self.lookback_days}d")
        except Exception:
            data.warnings.append("가격 히스토리 조회 실패 — 수익률/이동평균 일부 누락.")
            return
        if hist is None or hist.empty or "Close" not in hist:
            data.warnings.append("가격 히스토리가 비어 있습니다.")
            return

        close = hist["Close"].dropna()
        if close.empty:
            return
        last = float(close.iloc[-1])
        if data.price is None:
            data.price = round(last, 4)

        def ret_over(trading_days: int) -> Optional[float]:
            if len(close) <= trading_days:
                return None
            past = float(close.iloc[-1 - trading_days])
            if past == 0:
                return None
            return round((last / past - 1) * 100, 2)

        data.ret_1m = ret_over(21)
        data.ret_3m = ret_over(63)
        data.ret_6m = ret_over(126)
        data.ret_1y = ret_over(252)

        if data.ma50 is None and len(close) >= 50:
            data.ma50 = round(float(close.iloc[-50:].mean()), 4)
        if data.ma200 is None and len(close) >= 200:
            data.ma200 = round(float(close.iloc[-200:].mean()), 4)
        if data.week52_high is None:
            data.week52_high = round(float(close.iloc[-252:].max()), 4)
        if data.week52_low is None:
            data.week52_low = round(float(close.iloc[-252:].min()), 4)

    # ----------------------------------------------------------------- macro
    def get_macro(self, market: Market) -> MacroSnapshot:
        yf = self._yf
        today = _dt.date.today().isoformat()
        snap = MacroSnapshot(as_of=today, market=market)

        # 시장별 관심 지표 (yfinance 심볼)
        common = {
            "미국채 10년 금리(^TNX)": "^TNX",
            "변동성지수 VIX(^VIX)": "^VIX",
            "달러인덱스(DX-Y.NYB)": "DX-Y.NYB",
            "WTI 유가(CL=F)": "CL=F",
        }
        if market is Market.KR:
            indices = {"코스피(^KS11)": "^KS11", "코스닥(^KQ11)": "^KQ11", "원달러(USDKRW=X)": "USDKRW=X"}
        else:
            indices = {"S&P500(^GSPC)": "^GSPC", "나스닥(^IXIC)": "^IXIC"}

        for label, sym in {**indices, **common}.items():
            level, chg = self._level_and_trend(yf, sym)
            if level is not None:
                snap.indicators[label] = {
                    "level": level,
                    "change_3m_pct": chg,
                }
            else:
                snap.notes.append(f"{label} 조회 실패")
        return snap

    def get_fx_usdkrw(self) -> float:
        level, _ = self._level_and_trend(self._yf, "USDKRW=X")
        return level or 1350.0

    def _level_and_trend(self, yf, symbol: str):
        try:
            hist = yf.Ticker(symbol).history(period="6mo")
        except Exception:
            return None, None
        if hist is None or hist.empty or "Close" not in hist:
            return None, None
        close = hist["Close"].dropna()
        if close.empty:
            return None, None
        level = round(float(close.iloc[-1]), 4)
        chg = None
        if len(close) > 63:
            past = float(close.iloc[-64])
            if past:
                chg = round((level / past - 1) * 100, 2)
        return level, chg
