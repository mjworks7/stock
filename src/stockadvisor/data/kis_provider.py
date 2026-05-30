"""한국투자증권(KIS) OpenAPI 데이터 공급자 — 국내(KRX) 종목 정밀 데이터.

무료 yfinance 대비 국내 종목의 밸류에이션/재무 지표 정확도를 높인다.
공식 문서: https://apiportal.koreainvestment.com (REST, OAuth2 client_credentials)

필요 환경변수:
  KIS_APP_KEY, KIS_APP_SECRET  (개발자 포털에서 발급)
  KIS_PAPER=1                  (선택) 모의투자 도메인 사용

주의: 본 모듈은 공식 문서의 필드 규격에 맞춰 작성되었으며, 실제 키로
검증이 필요하다. 응답 필드가 누락되어도 분석은 진행되도록 방어적으로 파싱한다.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from ..domain import MacroSnapshot, Market, StockData, Ticker
from .provider import MarketDataProvider

REAL_BASE = "https://openapi.koreainvestment.com:9443"
PAPER_BASE = "https://openapivts.koreainvestment.com:29443"

# 시세/재무 조회 TR ID (국내주식)
TR_PRICE = "FHKST01010100"          # 주식현재가 시세
TR_FIN_RATIO = "FHKST66430300"      # 국내주식 재무비율


def _f(v: Any) -> Optional[float]:
    """KIS 응답 문자열을 안전하게 float 으로. 빈값/오류는 None."""
    try:
        if v is None:
            return None
        s = str(v).strip().replace(",", "")
        if s in ("", "-", "N/A"):
            return None
        return float(s)
    except (TypeError, ValueError):
        return None


class KisMarketDataProvider(MarketDataProvider):
    """국내 종목 전용 공급자. 해외/거시는 처리하지 않는다(컴포지트가 위임)."""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        paper: bool = False,
        token_cache: Optional[Path] = None,
        timeout: int = 10,
    ) -> None:
        import requests  # 지연 import

        self._requests = requests
        self.app_key = app_key
        self.app_secret = app_secret
        self.base = PAPER_BASE if paper else REAL_BASE
        self.timeout = timeout
        self._token_cache = token_cache or (Path.home() / ".kis_token.json")
        self._token: Optional[str] = None
        self._token_exp: float = 0.0
        # 이름 조회용 지연 캐시 (code -> name)
        self._name_cache: dict[str, str] = {}

    # ------------------------------------------------------------- 인증
    def _access_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_exp - 60:
            return self._token
        # 파일 캐시 재사용 (토큰 발급은 분당 1회로 제한됨)
        cached = self._read_cached_token()
        if cached and now < cached[1] - 60:
            self._token, self._token_exp = cached
            return self._token

        url = f"{self.base}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        resp = self._requests.post(url, json=body, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"KIS 토큰 발급 실패: {data}")
        expires_in = int(data.get("expires_in", 86400))
        self._token = token
        self._token_exp = now + expires_in
        self._write_cached_token(token, self._token_exp)
        return token

    def _read_cached_token(self) -> Optional[tuple[str, float]]:
        try:
            d = json.loads(self._token_cache.read_text(encoding="utf-8"))
            # 동일 app_key 로 발급된 토큰만 재사용
            if d.get("app_key") == self.app_key and d.get("base") == self.base:
                return d["token"], float(d["exp"])
        except Exception:
            pass
        return None

    def _write_cached_token(self, token: str, exp: float) -> None:
        try:
            self._token_cache.write_text(
                json.dumps(
                    {"app_key": self.app_key, "base": self.base, "token": token, "exp": exp}
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _headers(self, tr_id: str) -> dict[str, str]:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._access_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    def _get(self, path: str, tr_id: str, params: dict[str, str]) -> dict:
        url = f"{self.base}{path}"
        resp = self._requests.get(
            url, headers=self._headers(tr_id), params=params, timeout=self.timeout
        )
        resp.raise_for_status()
        data = resp.json()
        if str(data.get("rt_cd", "0")) not in ("0", ""):
            raise RuntimeError(f"KIS API 오류({path}): {data.get('msg1')}")
        return data

    # ------------------------------------------------------------- 종목
    def get_stock_data(self, ticker: Ticker) -> StockData:
        if ticker.market is not Market.KR:
            raise ValueError("KisMarketDataProvider 는 국내(KR) 종목만 지원합니다.")
        code = ticker.raw.split(".")[0]
        data = StockData(ticker=ticker, currency="KRW")

        self._fill_price(code, data)
        self._fill_financials(code, data)

        name = self._resolve_name(code) or data.ticker.name or code
        data.ticker = Ticker(
            raw=code, market=Market.KR, yf_symbol=ticker.yf_symbol, name=name
        )
        if not data.warnings:
            data.warnings.append("출처: 한국투자증권(KIS) OpenAPI")
        return data

    def _fill_price(self, code: str, data: StockData) -> None:
        try:
            res = self._get(
                "/uapi/domestic-stock/v1/quotations/inquire-price",
                TR_PRICE,
                {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": code},
            )
        except Exception as e:
            data.warnings.append(f"KIS 시세 조회 실패: {e}")
            return
        out = res.get("output", {}) or {}
        data.price = _f(out.get("stck_prpr"))
        data.per = _f(out.get("per"))
        data.pbr = _f(out.get("pbr"))
        data.week52_high = _f(out.get("w52_hgpr"))
        data.week52_low = _f(out.get("w52_lwpr"))
        # 시가총액: 억원 단위 -> 원
        avls = _f(out.get("hts_avls"))
        if avls is not None:
            data.market_cap = avls * 1e8
        # 업종명
        data.sector = out.get("bstp_kor_isnm") or data.sector
        # 종목명이 응답에 있으면 활용
        nm = out.get("hts_kor_isnm")
        if nm:
            self._name_cache[code] = nm

    def _fill_financials(self, code: str, data: StockData) -> None:
        try:
            res = self._get(
                "/uapi/domestic-stock/v1/finance/financial-ratio",
                TR_FIN_RATIO,
                {
                    "fid_cond_mrkt_div_code": "J",
                    "fid_input_iscd": code,
                    "fid_div_cls_code": "0",  # 0=연간, 1=분기
                },
            )
        except Exception as e:
            data.warnings.append(f"KIS 재무비율 조회 실패: {e}")
            return
        rows = res.get("output", []) or []
        if not rows:
            return
        latest = rows[0]  # 최신 결산 기준
        data.revenue_growth = _f(latest.get("grs"))            # 매출액 증가율
        data.earnings_growth = _f(latest.get("ntin_inrt"))     # 순이익 증가율
        data.roe = _f(latest.get("roe_val"))                   # ROE
        # 영업이익 증가율은 모멘텀 참고용으로 둘 수 있으나 직접 매핑 필드는 생략

    # ------------------------------------------------------------- 이름
    def _resolve_name(self, code: str) -> Optional[str]:
        if code in self._name_cache:
            return self._name_cache[code]
        # FinanceDataReader 가 있으면 종목명 조회 (지연/방어적)
        try:
            import FinanceDataReader as fdr  # type: ignore

            listing = fdr.StockListing("KRX")
            col = "Code" if "Code" in listing.columns else "Symbol"
            hit = listing.loc[listing[col] == code]
            if not hit.empty and "Name" in listing.columns:
                name = str(hit.iloc[0]["Name"])
                self._name_cache[code] = name
                return name
        except Exception:
            pass
        return None

    # ------------------------------------------------------------- 거시
    def get_macro(self, market: Market) -> MacroSnapshot:
        # KIS 는 거시 스냅샷 용도가 아니므로 컴포지트가 무료 공급자에 위임한다.
        raise NotImplementedError("거시 데이터는 KIS 공급자가 제공하지 않습니다.")
