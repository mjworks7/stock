"""분석 히스토리 저장/조회.

분석·모니터링 결과를 reports/ 폴더에 마크다운(.md) + 구조화(.json) 사이드카로
영구 저장하고, 최근 기록을 목록으로 조회한다. CLI와 웹 대시보드가 공유한다.
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..config import Config
from .report import build_markdown, build_portfolio_markdown
from .service import AnalysisResult


@dataclass
class HistoryEntry:
    kind: str            # 'analysis' | 'portfolio'
    generated_at: str    # 표시용 시각 문자열
    title: str           # 분석: 종목 나열 / 모니터링: 'N종목 포트폴리오'
    engine: str
    summary: str
    md_path: str
    json_path: Optional[str] = None

    @property
    def kind_label(self) -> str:
        return "📊 종목분석" if self.kind == "analysis" else "💼 모니터링"


def _safe(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in "-_가-힣")[:40]


def _stamp(now: _dt.datetime) -> str:
    return now.strftime("%Y%m%d_%H%M%S")


# ------------------------------------------------------------------- 저장
def save_analysis(
    result: AnalysisResult, cfg: Config, now: _dt.datetime, markdown: Optional[str] = None
) -> HistoryEntry:
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")
    md = markdown if markdown is not None else build_markdown(result, cfg, generated_at)

    codes = "-".join(v.ticker.raw for v in result.verdicts)
    stamp = _stamp(now)
    base = cfg.report_path / f"report_{stamp}_{_safe(codes)}"
    md_path = base.with_suffix(".md")
    json_path = base.with_suffix(".json")

    md_path.write_text(md, encoding="utf-8")
    title = ", ".join(v.ticker.display() for v in result.verdicts)
    summary = result.ranking_summary or (
        result.ranking[0].one_liner if result.ranking else ""
    )
    payload = {
        "kind": "analysis",
        "generated_at": generated_at,
        "title": title,
        "engine": result.engine_kind,
        "summary": summary,
        "ranking": [e.to_dict() for e in result.ranking],
        "ranking_summary": result.ranking_summary,
        "verdicts": [v.to_dict() for v in result.verdicts],
        "macro": {k: s.to_dict() for k, s in result.macro.items()},
        "errors": result.errors,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return HistoryEntry(
        kind="analysis",
        generated_at=generated_at,
        title=title,
        engine=result.engine_kind,
        summary=summary,
        md_path=str(md_path),
        json_path=str(json_path),
    )


def save_portfolio(
    review, cfg: Config, now: _dt.datetime, engine_kind: str, markdown: Optional[str] = None
) -> HistoryEntry:
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")
    md = (
        markdown
        if markdown is not None
        else build_portfolio_markdown(review, cfg, generated_at, engine_kind)
    )
    stamp = _stamp(now)
    base = cfg.report_path / f"portfolio_{stamp}"
    md_path = base.with_suffix(".md")
    json_path = base.with_suffix(".json")

    md_path.write_text(md, encoding="utf-8")
    title = f"{len(review.positions)}종목 포트폴리오"
    summary = (
        f"평가손익 {review.total_pnl_pct:+.1f}% · "
        + (review.summary or "")
    ).strip(" ·")
    payload = dict(review.to_dict())
    payload.update(
        {"kind": "portfolio", "generated_at": generated_at, "engine": engine_kind,
         "title": title, "summary": summary}
    )
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return HistoryEntry(
        kind="portfolio",
        generated_at=generated_at,
        title=title,
        engine=engine_kind,
        summary=summary,
        md_path=str(md_path),
        json_path=str(json_path),
    )


# ------------------------------------------------------------------- 조회
def list_recent(cfg: Config, limit: int = 30) -> list[HistoryEntry]:
    entries: list[HistoryEntry] = []
    report_dir = cfg.report_path
    for jp in report_dir.glob("*.json"):
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            continue
        kind = data.get("kind") or ("portfolio" if "positions" in data else "analysis")
        md = jp.with_suffix(".md")
        entries.append(
            HistoryEntry(
                kind=kind,
                generated_at=data.get("generated_at", ""),
                title=data.get("title", jp.stem),
                engine=data.get("engine", ""),
                summary=data.get("summary", ""),
                md_path=str(md) if md.exists() else "",
                json_path=str(jp),
            )
        )
    entries.sort(key=lambda e: e.generated_at, reverse=True)
    return entries[:limit]


def load_markdown(md_path: str) -> str:
    try:
        return Path(md_path).read_text(encoding="utf-8")
    except Exception as e:
        return f"리포트를 불러올 수 없습니다: {e}"


def latest_analysis_for(cfg: Config, raw_ticker: str, max_scan: int = 100) -> Optional[dict]:
    """해당 종목의 가장 최근 분석 요약을 히스토리에서 찾는다.

    종목 코드(111770) 또는 종목명(영원무역) 어느 쪽으로 입력해도 매칭한다.
    반환: {generated_at, valuation_judgment, action, total_score, current_price,
           currency, target_mid, thesis, name} 또는 None.
    """
    key = (raw_ticker or "").strip()
    code_key = key.upper().split(".")[0]
    for e in list_recent(cfg, max_scan):
        if e.kind != "analysis" or not e.json_path:
            continue
        try:
            data = json.loads(Path(e.json_path).read_text(encoding="utf-8"))
        except Exception:
            continue
        for v in data.get("verdicts", []):
            t = v.get("ticker", {}) or {}
            raw = str(t.get("raw", "")).upper().split(".")[0]
            name = str(t.get("name", ""))
            if code_key == raw or key == name or key == str(t.get("raw", "")):
                tp = v.get("target_prices", {}) or {}
                mid = (tp.get("mid_term") or {}).get("base")
                return {
                    "generated_at": e.generated_at,
                    "valuation_judgment": v.get("valuation_judgment"),
                    "action": v.get("action"),
                    "total_score": v.get("total_score"),
                    "current_price": v.get("current_price"),
                    "currency": v.get("currency"),
                    "target_mid": mid,
                    "thesis": v.get("thesis", ""),
                    "name": name or raw,
                }
    return None
