"""설치 없이 바로 실행하는 래퍼.

  python run.py AAPL 005930 --offline

(pip install -e . 로 설치하면 `stockadvisor ...` 또는
 `python -m stockadvisor ...` 로도 실행 가능)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from stockadvisor.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
