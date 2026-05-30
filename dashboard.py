"""StockAdvisor 웹 대시보드 (Streamlit).

실행:
  pip install -r requirements.txt
  streamlit run dashboard.py

기존 서비스 계층(AdvisorService / MonitorService)을 그대로 재사용한다.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from stockadvisor.agents.engine import build_engine  # noqa: E402
from stockadvisor.application.monitor import MonitorService, load_portfolio  # noqa: E402
from stockadvisor.application.report import (  # noqa: E402
    build_markdown,
    build_portfolio_markdown,
)
from stockadvisor.application.service import AdvisorService  # noqa: E402
from stockadvisor.config import load_config  # noqa: E402
from stockadvisor.data.factory import build_provider  # noqa: E402
from stockadvisor.domain import Holding  # noqa: E402

st.set_page_config(page_title="StockAdvisor", page_icon="📊", layout="wide")

CFG = load_config()


# 사이드바에서 고를 수 있는 모델 (라벨 -> 모델 ID)
MODEL_CHOICES = {
    "Opus 4.8 — 최고 품질·고비용": "claude-opus-4-8",
    "Sonnet 4.6 — 균형·저비용": "claude-sonnet-4-6",
    "Haiku 4.5 — 가장 빠르고 저렴": "claude-haiku-4-5-20251001",
}


# --------------------------------------------------------------- 런타임
@st.cache_resource(show_spinner=False)
def get_provider(offline: bool):
    """데이터 공급자 캐시 (모델과 무관)."""
    return build_provider(CFG, offline=offline, log=lambda *_a, **_k: None)


@st.cache_resource(show_spinner=False)
def get_engine(offline: bool, model: str):
    """분석 엔진 캐시 (오프라인 여부 + 선택 모델별)."""
    cfg = dataclasses.replace(CFG, model=model)
    return build_engine(cfg, offline=offline)


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _money(v, cur: str) -> str:
    if v is None:
        return "N/A"
    sym = "₩" if cur == "KRW" else "$"
    return f"{sym}{v:,.0f}" if cur == "KRW" else f"{sym}{v:,.2f}"


# --------------------------------------------------------------- 사이드바
with st.sidebar:
    st.title("📊 StockAdvisor")
    st.caption("멀티 에이전트 국내·해외 주식 분석")

    offline = st.toggle("오프라인 모드 (모의 데이터)", value=False,
                        help="네트워크/API 없이 규칙기반 엔진으로 빠르게 점검")

    # 모델 선택 (Claude API 엔진에만 적용)
    _labels = list(MODEL_CHOICES.keys())
    _default_idx = next(
        (i for i, lbl in enumerate(_labels) if MODEL_CHOICES[lbl] == CFG.model), 0
    )
    _llm_disabled = offline or not CFG.has_api_key
    model_label = st.selectbox(
        "분석 모델",
        _labels,
        index=_default_idx,
        disabled=_llm_disabled,
        help="전문가 에이전트(Claude API) 분석에 사용할 모델. "
        "오프라인/키 미설정 시 규칙기반 엔진이 사용되어 적용되지 않습니다.",
    )
    selected_model = MODEL_CHOICES[model_label]
    if not _llm_disabled and selected_model != "claude-opus-4-8":
        st.caption("💡 비용↓ 모델 선택됨 (temperature 적용 모델)")

    st.divider()
    st.subheader("런타임 상태")
    if offline:
        st.info("🧪 오프라인: 모의 데이터 + 규칙기반 엔진")
    else:
        if CFG.has_api_key:
            st.success("🧠 전문가 에이전트 실시간 분석 (Claude API)")
        else:
            st.warning("규칙기반 엔진\n\n전문가 토론을 켜려면 .env 에 ANTHROPIC_API_KEY 설정")
        st.write("국내 데이터:", "한국투자증권(KIS)" if CFG.has_kis else "무료(yfinance)")
        st.write("해외 데이터:", "무료(yfinance)")
    st.caption(f"적용 모델: {selected_model if not _llm_disabled else '규칙기반(모델 미사용)'}")
    st.divider()
    st.caption("⚠️ 참고용 분석이며 투자 권유가 아닙니다.")


tab_analyze, tab_monitor = st.tabs(["📊 종목 분석", "💼 보유 모니터링"])


# =============================================================== 종목 분석
with tab_analyze:
    st.header("종목 분석")
    st.caption("종목 코드를 공백/쉼표로 구분해 입력하세요. 예: `AAPL MSFT 005930 000660`")
    tickers_str = st.text_input("종목", value="AAPL 005930", label_visibility="collapsed")
    run = st.button("🚀 분석 실행", type="primary")

    if run:
        tickers = [t for t in tickers_str.replace(",", " ").split() if t.strip()]
        if not tickers:
            st.error("종목을 1개 이상 입력하세요.")
        else:
            provider = get_provider(offline)
            engine = get_engine(offline, selected_model)
            with st.status("분석 진행 중...", expanded=True) as status:
                service = AdvisorService(CFG, provider, engine, log=status.write)
                result = service.analyze(tickers)
                status.update(label="분석 완료", state="complete", expanded=False)

            if not result.verdicts:
                st.error("분석 가능한 종목이 없습니다.")
                for e in result.errors:
                    st.write("- ", e)
            else:
                # 추천 순위
                if result.ranking:
                    st.subheader("🏆 추천 순위")
                    rank_df = pd.DataFrame(
                        [
                            {
                                "순위": e.rank,
                                "종목": e.ticker.display(),
                                "종합점수": round(e.total_score, 1),
                                "대응": e.action,
                                "한줄평": e.one_liner,
                            }
                            for e in result.ranking
                        ]
                    )
                    st.dataframe(rank_df, hide_index=True, use_container_width=True)
                    if result.ranking_summary:
                        st.info(result.ranking_summary)

                # 종목별 상세
                for v in result.verdicts:
                    st.divider()
                    st.subheader(v.ticker.display())
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("현재가", _money(v.current_price, v.currency))
                    c2.metric("적정성", v.valuation_judgment)
                    c3.metric("대응", v.action)
                    c4.metric("종합점수", f"{v.total_score:.0f}/100")

                    cc1, cc2 = st.columns(2)
                    if v.stop_loss is not None:
                        cc1.metric("손절 권고가", _money(v.stop_loss, v.currency))
                    if v.suggested_position_pct is not None:
                        cc2.metric("권고 비중 상한", f"{v.suggested_position_pct:.0f}%")

                    if v.thesis:
                        st.write(f"**투자 논리:** {v.thesis}")

                    st.markdown("**🎯 투자 기간별 목표가**")
                    tp_df = pd.DataFrame(
                        [
                            {
                                "기간": b.horizon,
                                "보수적": _money(b.low, v.currency),
                                "기준": _money(b.base, v.currency),
                                "낙관적": _money(b.high, v.currency),
                                "근거": b.rationale,
                            }
                            for b in v.target_prices.bands()
                        ]
                    )
                    st.dataframe(tp_df, hide_index=True, use_container_width=True)

                    with st.expander("🧠 전문가 의견 / 리스크"):
                        op_df = pd.DataFrame(
                            [
                                {
                                    "전문가": o.role,
                                    "입장": o.stance,
                                    "점수": round(o.score, 0),
                                    "확신": round(o.confidence, 2),
                                    "요약": o.summary,
                                }
                                for o in v.opinions
                            ]
                        )
                        st.dataframe(op_df, hide_index=True, use_container_width=True)
                        if v.key_risks:
                            st.markdown("**주요 리스크**")
                            for r in v.key_risks:
                                st.write("- ", r)
                        if v.catalysts:
                            st.markdown("**상승 촉매**")
                            for cat in v.catalysts:
                                st.write("- ", cat)

                # 다운로드
                md = build_markdown(result, CFG, _now())
                st.download_button(
                    "📄 마크다운 리포트 다운로드",
                    md,
                    file_name="analysis_report.md",
                    mime="text/markdown",
                )


# =============================================================== 보유 모니터링
with tab_monitor:
    st.header("보유 종목 모니터링")
    st.caption("보유 내역을 표에 입력하거나 포트폴리오 파일(YAML/JSON)을 업로드하세요.")

    colA, colB = st.columns([1, 1])
    base_currency = colA.selectbox("기준통화", ["KRW", "USD"], index=0)
    cash = colB.number_input("보유 현금(기준통화)", min_value=0.0, value=0.0, step=100000.0)

    uploaded = st.file_uploader("포트폴리오 파일 업로드(선택)", type=["yaml", "yml", "json"])

    default_rows = pd.DataFrame(
        {"ticker": ["005930", "AAPL"], "shares": [50.0, 20.0], "avg_price": [70000.0, 180.0]}
    )
    if uploaded is not None:
        tmp = Path("._uploaded_portfolio" + Path(uploaded.name).suffix)
        tmp.write_bytes(uploaded.getvalue())
        try:
            holds, base_currency, cash = load_portfolio(tmp)
            default_rows = pd.DataFrame(
                [{"ticker": h.raw_ticker, "shares": h.shares, "avg_price": h.avg_price} for h in holds]
            )
            st.success(f"업로드 반영: {len(holds)}종목, 기준통화 {base_currency}")
        except Exception as e:
            st.error(f"파일 파싱 실패: {e}")
        finally:
            tmp.unlink(missing_ok=True)

    st.markdown("**보유 종목 (편집 가능)**")
    edited = st.data_editor(
        default_rows,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "ticker": st.column_config.TextColumn("종목코드", help="국내 6자리 / 해외 심볼"),
            "shares": st.column_config.NumberColumn("보유수량", min_value=0.0),
            "avg_price": st.column_config.NumberColumn("평균단가", min_value=0.0),
        },
    )

    if st.button("🔍 모니터링 실행", type="primary"):
        holdings = []
        for _, row in edited.iterrows():
            tk = str(row.get("ticker", "")).strip()
            if not tk:
                continue
            try:
                holdings.append(
                    Holding(raw_ticker=tk, shares=float(row["shares"]), avg_price=float(row["avg_price"]))
                )
            except (TypeError, ValueError):
                continue
        if not holdings:
            st.error("보유 종목을 1개 이상 입력하세요.")
        else:
            provider = get_provider(offline)
            engine = get_engine(offline, selected_model)
            with st.status("모니터링 진행 중...", expanded=True) as status:
                review = MonitorService(CFG, provider, engine, log=status.write).monitor(
                    holdings, base_currency, float(cash)
                )
                status.update(label="점검 완료", state="complete", expanded=False)

            bc = review.base_currency
            m1, m2, m3 = st.columns(3)
            m1.metric("총 평가금액", _money(review.total_value_base, bc))
            m2.metric(
                "총 평가손익",
                _money(review.total_pnl_base, bc),
                delta=f"{review.total_pnl_pct:+.1f}%",
            )
            m3.metric("현금", _money(review.cash_base, bc))

            cc1, cc2 = st.columns(2)
            if review.market_weights:
                cc1.markdown("**시장 비중**")
                cc1.bar_chart(pd.Series(review.market_weights))
            if review.sector_weights:
                cc2.markdown("**섹터 비중**")
                cc2.bar_chart(pd.Series(review.sector_weights))

            st.subheader("📋 보유 종목별 점검")
            pos_df = pd.DataFrame(
                [
                    {
                        "종목": p.ticker.display(),
                        "수익률(%)": round(p.pnl_pct, 1),
                        "비중(%)": round(p.weight_pct, 1),
                        "평가금액": _money(p.market_value, p.currency),
                        "조치": p.action,
                        "손절가": _money(p.stop_loss, p.currency) if p.stop_loss else "-",
                        "코멘트": p.comment,
                    }
                    for p in review.positions
                ]
            )
            st.dataframe(pos_df, hide_index=True, use_container_width=True)

            if review.risk_alerts:
                st.subheader("⚠️ 리스크 경고")
                for a in review.risk_alerts:
                    st.warning(a)
            if review.rebalancing:
                st.subheader("⚖️ 리밸런싱 제안")
                for r in review.rebalancing:
                    st.write("- ", r)
            if review.summary:
                st.info(review.summary)
            if review.errors:
                for e in review.errors:
                    st.error(e)

            md = build_portfolio_markdown(review, CFG, _now(), type(engine).__name__)
            st.download_button(
                "📄 마크다운 리포트 다운로드",
                md,
                file_name="portfolio_report.md",
                mime="text/markdown",
            )
