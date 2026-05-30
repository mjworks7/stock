"""KIS 파싱 + 컴포지트 라우팅 단위 테스트 (네트워크/키 불필요).

실행:  python -m unittest tests.test_kis_and_routing  (프로젝트 루트에서, src 가 경로에 있어야 함)
또는:  python tests/test_kis_and_routing.py
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stockadvisor.data.composite_provider import CompositeProvider  # noqa: E402
from stockadvisor.data.kis_provider import KisMarketDataProvider  # noqa: E402
from stockadvisor.data.provider import (  # noqa: E402
    MarketDataProvider,
    detect_market,
    resolve_ticker,
)
from stockadvisor.domain import MacroSnapshot, Market, StockData, Ticker  # noqa: E402


# ----------------------------- 가짜 HTTP 계층 -----------------------------
class _FakeResp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeRequests:
    def post(self, url, json=None, timeout=None):
        return _FakeResp({"access_token": "tok", "expires_in": 86400})

    def get(self, url, headers=None, params=None, timeout=None):
        if "inquire-price" in url:
            return _FakeResp(
                {
                    "rt_cd": "0",
                    "output": {
                        "stck_prpr": "71000",
                        "per": "12.5",
                        "pbr": "1.3",
                        "w52_hgpr": "88000",
                        "w52_lwpr": "60000",
                        "hts_avls": "4200000",  # 억원
                        "bstp_kor_isnm": "전기전자",
                        "hts_kor_isnm": "삼성전자",
                    },
                }
            )
        if "financial-ratio" in url:
            return _FakeResp(
                {
                    "rt_cd": "0",
                    "output": [{"grs": "8.1", "ntin_inrt": "15.2", "roe_val": "9.4"}],
                }
            )
        if "profit-ratio" in url:
            return _FakeResp({"rt_cd": "0", "output": [{"sale_ntin_rate": "11.0"}]})
        if "stability-ratio" in url:
            return _FakeResp(
                {"rt_cd": "0", "output": [{"lblt_rate": "45.0", "crnt_rate": "180.0"}]}
            )
        if "income-statement" in url:
            return _FakeResp(
                {"rt_cd": "0", "output": [{"sale_account": "1000.0", "bsop_prti": "120.0"}]}
            )
        raise AssertionError(f"예상치 못한 URL: {url}")


# ----------------------------- 스텁 공급자 -----------------------------
class _StubProvider(MarketDataProvider):
    def __init__(self, tag, raises=False):
        self.tag = tag
        self.raises = raises
        self.calls = []

    def get_stock_data(self, ticker):
        self.calls.append(ticker.raw)
        if self.raises:
            raise RuntimeError(f"{self.tag} 실패")
        sd = StockData(ticker=ticker, currency=ticker.market.currency)
        sd.warnings.append(self.tag)
        return sd

    def get_macro(self, market):
        return MacroSnapshot(as_of="x", market=market, notes=[self.tag])


class TestTickerDetection(unittest.TestCase):
    def test_market_detection(self):
        self.assertIs(detect_market("005930"), Market.KR)
        self.assertIs(detect_market("000660.KQ"), Market.KR)
        self.assertIs(detect_market("AAPL"), Market.US)

    def test_resolve(self):
        self.assertEqual(resolve_ticker("005930").yf_symbol, "005930.KS")
        self.assertEqual(resolve_ticker("000660.KQ").yf_symbol, "000660.KQ")
        self.assertEqual(resolve_ticker("aapl").yf_symbol, "AAPL")


class TestKisParsing(unittest.TestCase):
    def _provider(self):
        tmp = Path(tempfile.mkdtemp()) / "tok.json"
        p = KisMarketDataProvider("k", "s", token_cache=tmp)
        p._requests = _FakeRequests()  # HTTP 주입
        return p

    def test_stock_data(self):
        p = self._provider()
        data = p.get_stock_data(resolve_ticker("005930"))
        self.assertEqual(data.currency, "KRW")
        self.assertEqual(data.price, 71000.0)
        self.assertEqual(data.per, 12.5)
        self.assertEqual(data.pbr, 1.3)
        self.assertEqual(data.week52_high, 88000.0)
        self.assertEqual(data.market_cap, 4200000 * 1e8)
        self.assertEqual(data.revenue_growth, 8.1)
        self.assertEqual(data.earnings_growth, 15.2)
        self.assertEqual(data.roe, 9.4)
        self.assertEqual(data.sector, "전기전자")
        self.assertEqual(data.ticker.name, "삼성전자")
        # 수익성·안정성·손익 보강 필드
        self.assertEqual(data.profit_margin, 11.0)        # sale_ntin_rate
        self.assertEqual(data.debt_to_equity, 45.0)       # lblt_rate
        self.assertEqual(data.current_ratio, 1.8)         # crnt_rate(180)/100
        self.assertEqual(data.operating_margin, 12.0)     # bsop_prti/sale_account

    def test_rejects_us(self):
        p = self._provider()
        with self.assertRaises(ValueError):
            p.get_stock_data(resolve_ticker("AAPL"))

    def test_token_cached(self):
        p = self._provider()
        t1 = p._access_token()
        t2 = p._access_token()
        self.assertEqual(t1, t2)


class TestCompositeRouting(unittest.TestCase):
    def test_routes_by_market(self):
        kr, us, macro = _StubProvider("KR"), _StubProvider("US"), _StubProvider("MACRO")
        c = CompositeProvider(kr, us, macro)
        c.get_stock_data(resolve_ticker("005930"))
        c.get_stock_data(resolve_ticker("AAPL"))
        self.assertEqual(kr.calls, ["005930"])
        self.assertEqual(us.calls, ["AAPL"])
        self.assertEqual(c.get_macro(Market.KR).notes, ["MACRO"])

    def test_fallback_on_failure(self):
        kr = _StubProvider("KR", raises=True)
        us = _StubProvider("US")
        fb = _StubProvider("FALLBACK")
        c = CompositeProvider(kr, us, us, fallback=fb)
        data = c.get_stock_data(resolve_ticker("005930"))
        self.assertIn("FALLBACK", data.warnings)
        self.assertEqual(fb.calls, ["005930"])


class TestHangulInput(unittest.TestCase):
    def test_hangul_detected_as_kr(self):
        self.assertIs(detect_market("영원무역"), Market.KR)
        t = resolve_ticker("영원무역")
        self.assertIs(t.market, Market.KR)
        self.assertEqual(t.yf_symbol, "")  # 코드는 공급자가 해석


class _NoDataProvider(MarketDataProvider):
    """가격이 없는(N/A) 종목을 흉내내는 스텁."""

    def get_stock_data(self, ticker):
        sd = StockData(ticker=ticker, currency=ticker.market.currency)
        sd.warnings.append("테스트: 데이터 없음")
        return sd  # price 등 전부 None

    def get_macro(self, market):
        return MacroSnapshot(as_of="x", market=market)


class TestNoDataGuard(unittest.TestCase):
    def test_no_data_verdict(self):
        from stockadvisor.agents.heuristic import HeuristicEngine
        from stockadvisor.application.service import AdvisorService
        from stockadvisor.config import load_config

        cfg = load_config()
        svc = AdvisorService(cfg, _NoDataProvider(), HeuristicEngine(cfg), log=lambda *_: None)
        res = svc.analyze(["AAPL"])
        self.assertEqual(len(res.verdicts), 1)
        v = res.verdicts[0]
        self.assertEqual(v.action, "분석불가")
        self.assertEqual(v.valuation_judgment, "데이터없음")
        self.assertIsNone(v.current_price)
        self.assertEqual(v.total_score, 0.0)
        # 가짜 0원 목표가가 아니라 None 이어야 함
        for b in v.target_prices.bands():
            self.assertIsNone(b.base)
        # 데이터 없는 종목은 순위에서 제외
        self.assertEqual(res.ranking, [])


class TestTemperatureGate(unittest.TestCase):
    def test_opus_4_8_excluded(self):
        from stockadvisor.agents.llm import _supports_temperature

        # opus-4-8 은 temperature 지원 안 함
        self.assertFalse(_supports_temperature("claude-opus-4-8"))
        self.assertFalse(_supports_temperature("claude-opus-4-8[1m]"))
        # 그 외 모델은 지원
        self.assertTrue(_supports_temperature("claude-sonnet-4-6"))
        self.assertTrue(_supports_temperature("claude-haiku-4-5-20251001"))


class _PricedStub(MarketDataProvider):
    """고정 현재가/섹터를 돌려주는 스텁 (환율 1500 고정)."""

    PRICES = {"005930": (90000.0, "전기전자"), "AAPL": (200.0, "Technology")}

    def get_stock_data(self, ticker):
        price, sector = self.PRICES[ticker.raw]
        sd = StockData(ticker=ticker, currency=ticker.market.currency)
        sd.price = price
        sd.sector = sector
        return sd

    def get_macro(self, market):
        return MacroSnapshot(as_of="x", market=market)

    def get_fx_usdkrw(self) -> float:
        return 1500.0


class TestMonitorMath(unittest.TestCase):
    def _review(self):
        from stockadvisor.agents.heuristic import HeuristicEngine
        from stockadvisor.application.monitor import MonitorService
        from stockadvisor.config import load_config
        from stockadvisor.domain import Holding

        cfg = load_config()
        svc = MonitorService(cfg, _PricedStub(), HeuristicEngine(cfg), log=lambda *_: None)
        holdings = [
            Holding("005930", shares=100, avg_price=70000),  # KR
            Holding("AAPL", shares=10, avg_price=150),        # US
        ]
        return svc.monitor(holdings, base_currency="KRW", cash=0.0)

    def test_pnl_and_weights(self):
        r = self._review()
        kr = next(p for p in r.positions if p.ticker.raw == "005930")
        us = next(p for p in r.positions if p.ticker.raw == "AAPL")
        # 수익률
        self.assertAlmostEqual(kr.pnl_pct, (90000 / 70000 - 1) * 100, places=4)
        self.assertAlmostEqual(us.pnl_pct, (200 / 150 - 1) * 100, places=4)
        # 기준통화(KRW) 환산 평가금액: KR=9,000,000 / US=10*200*1500=3,000,000
        self.assertAlmostEqual(kr.value_base, 9_000_000, places=2)
        self.assertAlmostEqual(us.value_base, 3_000_000, places=2)
        self.assertAlmostEqual(r.total_value_base, 12_000_000, places=2)
        # 비중 75% / 25%
        self.assertAlmostEqual(kr.weight_pct, 75.0, places=2)
        self.assertAlmostEqual(us.weight_pct, 25.0, places=2)
        # 집중 경고 + 조치(휴리스틱)가 채워졌는지
        self.assertTrue(kr.action)
        self.assertTrue(r.risk_alerts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
