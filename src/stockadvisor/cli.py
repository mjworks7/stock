"""명령행 인터페이스.

종목 분석:
  python -m stockadvisor AAPL MSFT 005930
  python -m stockadvisor 005930 000660 --offline --json

보유 종목 모니터링:
  python -m stockadvisor monitor --file portfolio.yaml
  python -m stockadvisor monitor --file portfolio.yaml --offline
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys

from .agents.engine import build_engine
from .application.history import list_recent, load_markdown, save_analysis, save_portfolio
from .application.monitor import MonitorService, load_portfolio
from .application.report import build_markdown, build_portfolio_markdown
from .application.service import AdvisorService
from .config import Config, load_config
from .data.factory import build_provider


def _force_utf8() -> None:
    """Windows 콘솔(cp949 등)에서도 이모지/한글이 깨지지 않도록 UTF-8 강제."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def _logger(quiet: bool):
    return (lambda *_a, **_k: None) if quiet else (lambda m: print(m, file=sys.stderr))


def _make_provider_engine(cfg: Config, offline: bool, log):
    """공급자 + 엔진 구성(공통). 실패 시 (None, None, exit_code)."""
    if offline:
        log("실행 모드: 오프라인(모의 데이터 + 규칙기반 엔진)")
    try:
        provider = build_provider(cfg, offline=offline, log=log)
    except Exception as e:
        print(
            f"[오류] 데이터 라이브러리 로드 실패: {e}\n"
            "  pip install -r requirements.txt 를 먼저 실행하거나 --offline 로 시도하세요.",
            file=sys.stderr,
        )
        return None, None, 2
    if not offline and not cfg.has_api_key:
        log(
            "주의: ANTHROPIC_API_KEY 가 없어 규칙기반 엔진으로 분석합니다.\n"
            "      전문가 에이전트 실시간 분석을 원하면 .env 에 키를 설정하세요."
        )
    engine = build_engine(cfg, offline=offline)
    log(f"엔진: {type(engine).__name__}")
    return provider, engine, 0


# --------------------------------------------------------------- analyze
def _run_analyze(argv: list[str], cfg: Config) -> int:
    p = argparse.ArgumentParser(
        prog="stockadvisor", description="종목 분석 — 적정성/대응방향/기간별 목표가/추천순위."
    )
    p.add_argument("tickers", nargs="+", help="종목 코드/심볼 (예: AAPL 005930 000660)")
    p.add_argument("--offline", action="store_true", help="모의 데이터 + 규칙기반 엔진")
    p.add_argument("--no-save", action="store_true", help="리포트 파일 저장 생략")
    p.add_argument("--json", action="store_true", help="JSON 결과도 저장")
    p.add_argument("--quiet", action="store_true", help="진행 로그 숨김")
    args = p.parse_args(argv)
    log = _logger(args.quiet)

    provider, engine, code = _make_provider_engine(cfg, args.offline, log)
    if provider is None:
        return code

    result = AdvisorService(cfg, provider, engine, log=log).analyze(args.tickers)
    if not result.verdicts:
        print("분석 가능한 종목이 없습니다.", file=sys.stderr)
        for e in result.errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    now = _dt.datetime.now()
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")
    markdown = build_markdown(result, cfg, generated_at)
    print(markdown)

    if not args.no_save:
        entry = save_analysis(result, cfg, now, markdown)
        log(f"\n📄 리포트 저장: {entry.md_path}")
        log(f"📄 히스토리(JSON): {entry.json_path}")
    return 0


# --------------------------------------------------------------- monitor
def _run_monitor(argv: list[str], cfg: Config) -> int:
    p = argparse.ArgumentParser(
        prog="stockadvisor monitor",
        description="보유 종목 모니터링 — 평가손익/비중/집중도/손절·리밸런싱 가이드.",
    )
    p.add_argument("--file", "-f", required=True, help="포트폴리오 파일(YAML/JSON)")
    p.add_argument("--offline", action="store_true", help="모의 데이터 + 규칙기반 엔진")
    p.add_argument("--no-save", action="store_true", help="리포트 파일 저장 생략")
    p.add_argument("--json", action="store_true", help="JSON 결과도 저장")
    p.add_argument("--quiet", action="store_true", help="진행 로그 숨김")
    args = p.parse_args(argv)
    log = _logger(args.quiet)

    from pathlib import Path

    path = Path(args.file)
    if not path.exists():
        print(f"[오류] 포트폴리오 파일을 찾을 수 없습니다: {path}", file=sys.stderr)
        return 2
    try:
        holdings, base_currency, cash = load_portfolio(path)
    except Exception as e:
        print(f"[오류] 포트폴리오 파일 파싱 실패: {e}", file=sys.stderr)
        return 2

    provider, engine, code = _make_provider_engine(cfg, args.offline, log)
    if provider is None:
        return code

    review = MonitorService(cfg, provider, engine, log=log).monitor(
        holdings, base_currency, cash
    )

    now = _dt.datetime.now()
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")
    markdown = build_portfolio_markdown(review, cfg, generated_at, type(engine).__name__)
    print(markdown)

    if not args.no_save:
        entry = save_portfolio(review, cfg, now, type(engine).__name__, markdown)
        log(f"\n📄 리포트 저장: {entry.md_path}")
        log(f"📄 히스토리(JSON): {entry.json_path}")
    return 0


# --------------------------------------------------------------- history
def _run_history(argv: list[str], cfg: Config) -> int:
    p = argparse.ArgumentParser(
        prog="stockadvisor history", description="최근 분석/모니터링 기록 보기."
    )
    p.add_argument("--limit", type=int, default=20, help="표시 개수")
    p.add_argument("--show", type=int, default=None, help="목록 번호의 리포트 전체 출력")
    args = p.parse_args(argv)

    entries = list_recent(cfg, args.limit)
    if not entries:
        print("저장된 분석 기록이 없습니다. 먼저 분석을 실행하세요.")
        return 0
    if args.show is not None:
        idx = args.show - 1
        if 0 <= idx < len(entries):
            print(load_markdown(entries[idx].md_path))
            return 0
        print(f"잘못된 번호입니다 (1~{len(entries)}).", file=sys.stderr)
        return 1
    print(f"🕘 최근 분석 기록 ({len(entries)}건)\n")
    for i, e in enumerate(entries, 1):
        print(f"{i:>2}. [{e.generated_at}] {e.kind_label}  {e.title}  · {e.engine}")
        if e.summary:
            print(f"     └ {e.summary[:110]}")
    print("\n전체 리포트 보기:  python run.py history --show <번호>")
    return 0


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    cfg = load_config()

    # 서브커맨드 디스패치 (기본: analyze, 하위호환 유지)
    if argv and argv[0] == "monitor":
        return _run_monitor(argv[1:], cfg)
    if argv and argv[0] == "history":
        return _run_history(argv[1:], cfg)
    if argv and argv[0] == "analyze":
        return _run_analyze(argv[1:], cfg)
    return _run_analyze(argv, cfg)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
