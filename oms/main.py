"""실행 진입점.

  python -m oms.main serve    # 웹 서버 (기본)
  python -m oms.main reset    # DB 초기화 후 재시드
"""
from __future__ import annotations

import sys

import uvicorn

from .web.app import DB_PATH, repo
from .seed import seed


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "serve"

    if cmd == "reset":
        if DB_PATH.exists():
            DB_PATH.unlink()
        # 새 저장소로 재시드
        from .repository.sqlite_repo import SQLiteRepository

        seed(SQLiteRepository(DB_PATH))
        print(f"DB 초기화 완료: {DB_PATH}")
        return 0

    if cmd == "serve":
        seed(repo)
        uvicorn.run("oms.web.app:app", host="127.0.0.1", port=8000, reload=False)
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
