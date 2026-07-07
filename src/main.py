"""진입점 — 인스타 자동화 CLI.

  python -m src.main post [--dry-run]     모델 컷(사진) 1장 기획→생성→게시
  python -m src.main insights [-n 10]     최근 게시물들의 반응(좋아요·댓글·도달·저장) 조회
  python -m src.main reel [--dry-run]     (예전) 릴스 영상 파이프라인

아무 서브커맨드도 없으면 `post` 를 실행합니다.
"""
from __future__ import annotations

import argparse
import sys


def _run_post(args: argparse.Namespace) -> int:
    from . import photo_pipeline

    result = photo_pipeline.run(dry_run=args.dry_run)
    print("─" * 50)
    print(f"소재        : {result.idea.topic}")
    print(f"컨셉        : {result.idea.concept}")
    print(f"이미지 프롬프트: {result.idea.image_prompt}")
    print(f"캡션        :\n{result.idea.full_caption}")
    print(f"이미지 파일 : {result.image_path}")
    if result.image_url:
        print(f"이미지 URL  : {result.image_url}")
    if result.published:
        print(f"✅ 게시 완료 (media_id={result.media_id})")
        if result.permalink:
            print(f"🔗 {result.permalink}")
    for note in result.notes:
        print(f"ℹ️  {note}")
    print("─" * 50)
    return 0


def _run_insights(args: argparse.Namespace) -> int:
    from . import insights, store

    if args.from_account:
        # 로컬 기록 대신 계정에서 최근 게시물을 직접 조회 (상태 없는 CI 등)
        media_ids = insights.fetch_recent_media_ids(args.number)
    else:
        posts = store.recent(args.number)
        if not posts:
            print("아직 기록된 게시물이 없습니다. 먼저 `post` 로 게시하거나 "
                  "`--from-account` 로 계정에서 직접 조회하세요.")
            return 0
        media_ids = [p["media_id"] for p in posts]

    print("─" * 60)
    print(f"최근 게시물 {len(media_ids)}건의 반응")
    print("─" * 60)
    total = 0
    for media_id in media_ids:
        try:
            r = insights.fetch_reactions(media_id)
            total += r.total_engagement
            print(r.summary_line())
            if r.permalink:
                print(f"    {r.permalink}")
        except Exception as e:
            print(f"{media_id[:32]:<32}  ⚠️ 조회 실패: {e}")
    print("─" * 60)
    print(f"합계 참여(좋아요+댓글+저장+공유): {total}")
    print("─" * 60)
    return 0


def _run_benchmark(args: argparse.Namespace) -> int:
    from . import benchmark

    usernames = [u.lstrip("@") for u in args.usernames]
    if not usernames:
        # config 에 적어둔 벤치마크 계정을 기본으로 사용
        from . import config as _cfg

        content = _cfg.load_content_config()
        usernames = [u.lstrip("@") for u in (content.get("benchmark", {}) or {}).get("accounts", [])]
    if not usernames:
        print("분석할 계정이 없습니다. 예) python -m src.main benchmark @account1 @account2")
        print("또는 config/content.yaml 의 benchmark.accounts 에 @아이디를 넣어두세요.")
        return 1

    print(f"벤치마크 분석 중: {', '.join('@'+u for u in usernames)} …")
    report = benchmark.build_report(usernames, limit=args.limit)
    benchmark.save(report)
    print("─" * 60)
    print(report.summary_text())
    print("─" * 60)
    print("✅ output/benchmark.json 저장 — 이제 `post` 가 이 패턴을 반영해 기획합니다.")
    return 0


def _run_reel(args: argparse.Namespace) -> int:
    from . import pipeline

    result = pipeline.run(dry_run=args.dry_run)
    print("─" * 50)
    print(f"소재      : {result.idea.topic}")
    print(f"컨셉      : {result.idea.concept}")
    print(f"영상 프롬프트: {result.idea.video_prompt}")
    print(f"캡션      :\n{result.idea.full_caption}")
    print(f"영상 파일 : {result.video_path}")
    if result.video_url:
        print(f"영상 URL  : {result.video_url}")
    if result.published:
        print(f"✅ 게시 완료 (media_id={result.media_id})")
    for note in result.notes:
        print(f"ℹ️  {note}")
    print("─" * 50)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Factory — 인스타 사진 자동화")
    sub = parser.add_subparsers(dest="command")

    p_post = sub.add_parser("post", help="모델 컷(사진) 기획→생성→게시")
    p_post.add_argument("--dry-run", action="store_true",
                        help="실제 게시 없이 기획·이미지 생성까지만")
    p_post.set_defaults(func=_run_post)

    p_ins = sub.add_parser("insights", help="최근 게시물 반응 조회")
    p_ins.add_argument("-n", "--number", type=int, default=10,
                       help="조회할 최근 게시물 수 (기본 10)")
    p_ins.add_argument("--from-account", action="store_true",
                       help="로컬 기록 대신 인스타 계정에서 최근 게시물을 직접 조회")
    p_ins.set_defaults(func=_run_insights)

    p_bm = sub.add_parser("benchmark", help="잘되는 채널 분석 → 기획에 반영")
    p_bm.add_argument("usernames", nargs="*",
                      help="분석할 계정 @아이디들 (비우면 content.yaml 의 benchmark.accounts 사용)")
    p_bm.add_argument("--limit", type=int, default=25,
                      help="계정당 분석할 최근 게시물 수 (기본 25)")
    p_bm.set_defaults(func=_run_benchmark)

    p_reel = sub.add_parser("reel", help="(예전) 릴스 영상 파이프라인")
    p_reel.add_argument("--dry-run", action="store_true")
    p_reel.set_defaults(func=_run_reel)

    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        # 서브커맨드 없으면 사진 게시 (자동화 기본 동작)
        args.dry_run = False
        return _run_post(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
