"""명령행 인터페이스.

사용 예:
  python -m stockadvisor AAPL MSFT 005930
  python -m stockadvisor 005930 000660 --offline
  python -m stockadvisor TSLA --json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys

from .agents.engine import build_engine
from .application.report import build_markdown, write_report
from .application.service import AdvisorService
from .config import load_config
from .data.factory import build_provider


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stockadvisor",
        description="멀티 에이전트 주식 종목 분석 — 적정성/대응방향/기간별 목표가/추천순위.",
    )
    p.add_argument("tickers", nargs="+", help="종목 코드/심볼 (예: AAPL 005930 000660)")
    p.add_argument(
        "--offline",
        action="store_true",
        help="네트워크/API 없이 모의 데이터 + 규칙기반 엔진으로 실행(스모크 테스트).",
    )
    p.add_argument("--config", default=None, help="config.yaml 경로 override")
    p.add_argument("--no-save", action="store_true", help="리포트 파일 저장 생략")
    p.add_argument("--json", action="store_true", help="JSON 결과도 함께 출력/저장")
    p.add_argument("--quiet", action="store_true", help="진행 로그 숨김")
    return p


def _force_utf8() -> None:
    """Windows 콘솔(cp949 등)에서도 이모지/한글이 깨지지 않도록 UTF-8 강제."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    args = _build_parser().parse_args(argv)
    cfg = load_config()

    log = (lambda *_a, **_k: None) if args.quiet else (lambda m: print(m, file=sys.stderr))

    # 데이터 공급자 + 엔진 선택
    if args.offline:
        log("실행 모드: 오프라인(모의 데이터 + 규칙기반 엔진)")
    try:
        provider = build_provider(cfg, offline=args.offline, log=log)
    except Exception as e:
        print(
            f"[오류] 데이터 라이브러리 로드 실패: {e}\n"
            "  pip install -r requirements.txt 를 먼저 실행하거나 --offline 로 시도하세요.",
            file=sys.stderr,
        )
        return 2
    if not args.offline and not cfg.has_api_key:
        log(
            "주의: ANTHROPIC_API_KEY 가 없어 규칙기반 엔진으로 분석합니다.\n"
            "      전문가 에이전트 실시간 토론을 원하면 .env 에 키를 설정하세요."
        )

    engine = build_engine(cfg, offline=args.offline)
    log(f"분석 엔진: {type(engine).__name__}")

    service = AdvisorService(cfg, provider, engine, log=log)
    result = service.analyze(args.tickers)

    if not result.verdicts:
        print("분석 가능한 종목이 없습니다.", file=sys.stderr)
        for e in result.errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    now = _dt.datetime.now()
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")
    markdown = build_markdown(result, cfg, generated_at)

    # 콘솔 출력
    print(markdown)

    # 저장
    if not args.no_save:
        stamp = now.strftime("%Y%m%d_%H%M%S")
        codes = "-".join(v.ticker.raw for v in result.verdicts)[:40]
        md_path = write_report(markdown, cfg, f"report_{stamp}_{codes}.md")
        log(f"\n📄 리포트 저장: {md_path}")
        if args.json:
            payload = {
                "generated_at": generated_at,
                "engine": result.engine_kind,
                "ranking": [e.to_dict() for e in result.ranking],
                "ranking_summary": result.ranking_summary,
                "verdicts": [v.to_dict() for v in result.verdicts],
                "macro": {k: s.to_dict() for k, s in result.macro.items()},
                "errors": result.errors,
            }
            json_path = cfg.report_path / f"report_{stamp}_{codes}.json"
            json_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log(f"📄 JSON 저장: {json_path}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
