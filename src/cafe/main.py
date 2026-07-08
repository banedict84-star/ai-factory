"""네이버 카페 자동 발행 CLI.

  python -m src.cafe.main login                 # 네이버 로그인 → refresh_token 받기
  python -m src.cafe.main draft                  # AI 초안 생성(검수 대기로 저장)
  python -m src.cafe.main draft -t "동네 맛집"     # 소재 지정해서 초안 생성
  python -m src.cafe.main draft --publish        # 생성 후 바로 확인/승인/발행(대화식)
  python -m src.cafe.main list                   # 저장된 초안 목록
  python -m src.cafe.main show <id>              # 초안 내용 출력
  python -m src.cafe.main approve <id>           # 초안 승인
  python -m src.cafe.main reject <id> -n "사유"   # 초안 반려
  python -m src.cafe.main publish <id>           # 승인된 초안 발행
"""
from __future__ import annotations

import argparse
import sys

from . import auth, pipeline, review


def _print_draft(d, full: bool = False) -> None:
    print("─" * 60)
    print(f"ID     : {d.id}   (상태: {d.status})")
    print(f"제목   : {d.post.subject}")
    print(f"요약   : {d.post.summary}")
    print(f"소재   : {d.post.topic}")
    if full:
        print(f"태그   : {', '.join(d.post.tags)}")
        print("본문   :")
        print(d.post.content)
    if d.article_url:
        print(f"발행URL: {d.article_url}")
    print("─" * 60)


def _cmd_draft(args) -> int:
    result = pipeline.draft(topic_hint=args.topic)
    d = result.draft
    _print_draft(d, full=True)
    print(f"🔎 미리보기(HTML): {result.preview_path}")
    print(f"   승인 후 발행: python -m src.cafe.main approve {d.id} && "
          f"python -m src.cafe.main publish {d.id}")

    if args.publish:
        answer = input("\n이 초안을 지금 발행할까요? (y/N): ").strip().lower()
        if answer == "y":
            review.approve(d.id, note="CLI 대화식 승인")
            published = pipeline.publish(d.id)
            print(f"✅ 발행 완료: {published.article_url or published.article_id or 'OK'}")
        else:
            print("보류했습니다. 나중에 approve/publish 로 발행할 수 있어요.")
    return 0


def _cmd_list(args) -> int:
    drafts = review.list_drafts(status=args.status)
    if not drafts:
        print("저장된 초안이 없습니다.")
        return 0
    for d in drafts:
        print(f"[{d.status:9}] {d.id}  {d.post.subject}")
    return 0


def _cmd_show(args) -> int:
    _print_draft(review.load_draft(args.id), full=True)
    return 0


def _cmd_approve(args) -> int:
    d = review.approve(args.id, note=args.note or "")
    print(f"✅ 승인됨: {d.id}")
    return 0


def _cmd_reject(args) -> int:
    d = review.reject(args.id, note=args.note or "")
    print(f"🚫 반려됨: {d.id} ({d.note})")
    return 0


def _cmd_publish(args) -> int:
    d = pipeline.publish(args.id, require_approved=not args.force)
    print(f"✅ 발행 완료: {d.id} → {d.article_url or d.article_id or 'OK'}")
    return 0


def _cmd_login(args) -> int:
    auth.login_cli()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AI Factory — 네이버 카페 자동 발행 (초안 AI + 검수 후 발행)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_draft = sub.add_parser("draft", help="AI 초안 생성(검수 대기로 저장)")
    p_draft.add_argument("-t", "--topic", help="소재 지정(없으면 설정 topics 에서 선택)")
    p_draft.add_argument(
        "--publish", action="store_true", help="생성 후 대화식으로 확인/승인/발행"
    )
    p_draft.set_defaults(func=_cmd_draft)

    p_list = sub.add_parser("list", help="저장된 초안 목록")
    p_list.add_argument(
        "-s", "--status", help="상태 필터(pending/approved/published/rejected)"
    )
    p_list.set_defaults(func=_cmd_list)

    p_show = sub.add_parser("show", help="초안 내용 출력")
    p_show.add_argument("id")
    p_show.set_defaults(func=_cmd_show)

    p_appr = sub.add_parser("approve", help="초안 승인")
    p_appr.add_argument("id")
    p_appr.add_argument("-n", "--note", help="검수 메모")
    p_appr.set_defaults(func=_cmd_approve)

    p_rej = sub.add_parser("reject", help="초안 반려")
    p_rej.add_argument("id")
    p_rej.add_argument("-n", "--note", help="반려 사유")
    p_rej.set_defaults(func=_cmd_reject)

    p_pub = sub.add_parser("publish", help="승인된 초안 발행")
    p_pub.add_argument("id")
    p_pub.add_argument(
        "--force", action="store_true", help="승인 없이 강제 발행(주의)"
    )
    p_pub.set_defaults(func=_cmd_publish)

    p_login = sub.add_parser("login", help="네이버 로그인 → refresh_token 받기")
    p_login.set_defaults(func=_cmd_login)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
