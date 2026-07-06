"""업무 실행기 — '완료했습니다'가 아니라 실제로 산출물을 만든다.

교체 가능한 이음새 (DecisionEngine·DialogueEngine 과 같은 철학):
  - MockExecutor  : 시뮬레이션 (텍스트는 표시만, 이미지는 플레이스홀더 그림). 기본값.
  - ClaudeExecutor: 텍스트(기획/프롬프트/캡션)를 Claude 로 실제 생성
  - OpenAIExecutor: 텍스트(gpt-4o-mini) + 이미지(gpt-image-1)를 실제 생성. 키 하나로 둘 다.

영상 생성·업로드는 아직 미연결(→ mock). 키/패키지가 없으면 자동으로 mock 폴백한다.
"""
from __future__ import annotations

import base64
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..domain.models import Employee, Task
from .catalog import ARTIFACT_LABEL

# 실제 생성 가능한 '텍스트' 산출물
TEXT_NEEDS = {
    "concept", "prompt", "caption",
    "brand_definition", "audience_research", "direction_proposal",
}


@dataclass
class ExecutionContext:
    task: Task
    actor: Employee
    need: str
    brand: str = ""
    memories: list[str] = field(default_factory=list)
    artifacts: dict = field(default_factory=dict)
    persona: str = ""


class ExecutorEngine(Protocol):
    def execute(self, ctx: ExecutionContext) -> str: ...


def _text_prompt(ctx: ExecutionContext) -> str:
    label = ARTIFACT_LABEL.get(ctx.need, ctx.need)
    mem = "\n".join(f"- {m}" for m in ctx.memories) or "- (없음)"
    concept = ctx.artifacts.get("concept", "")
    head = (
        f"너는 인스타그램 콘텐츠 팀의 '{ctx.actor.name}'이다. 성격: {ctx.persona}.\n"
        f"브랜드/미션: {ctx.brand}\n참고 기억:\n{mem}\n\n"
    )
    if ctx.need == "concept":
        return head + "위 브랜드로 올릴 인스타 릴스 1개의 컨셉을 3~4문장으로 기획해줘. 장면과 무드를 구체적으로, 담백하고 감각적으로. 한국어."
    if ctx.need == "brand_definition":
        return head + "이 계정의 리브랜딩 방향(브랜드 정의)을 4줄 이내로 정리해줘. 한국어."
    if ctx.need == "prompt":
        return head + f"아래 컨셉으로 이미지 생성 AI에 넣을 영어 프롬프트 1개를 만들어줘. 장면·구도·조명·무드를 구체적으로.\n\n[컨셉]\n{concept}"
    if ctx.need == "caption":
        return head + f"아래 컨셉에 어울리는 인스타 캡션과 해시태그(최대 8개)를 써줘. 짧고 담백하게, 한국어.\n\n[컨셉]\n{concept}"
    if ctx.need in ("audience_research", "direction_proposal"):
        return head + "최근 성과를 가정해 간단한 인사이트와 다음 콘텐츠 방향 제안을 4줄 이내로 정리해줘. 한국어."
    return head + f"{label} 결과물을 간단히 작성해줘. 한국어."


def _image_prompt(ctx: ExecutionContext) -> str:
    # 리나가 만든 생성 프롬프트가 있으면 그걸 사용, 없으면 컨셉으로
    return (ctx.artifacts.get("prompt")
            or ctx.artifacts.get("concept")
            or ctx.brand
            or "minimal aesthetic instagram reel cover")


def _media_url(media_dir: Path, task_id, need: str) -> tuple[Path, str]:
    name = f"{task_id}_{need}.png"
    return media_dir / name, f"/media/{name}"


class MockExecutor:
    """시뮬레이션. 이미지는 실제 파일(플레이스홀더 그림)을 만들어 화면에 보이게 한다."""
    kind = "mock"

    def __init__(self, media_dir: Path | None = None):
        self.media_dir = Path(media_dir) if media_dir else None

    def execute(self, ctx: ExecutionContext) -> str:
        label = ARTIFACT_LABEL.get(ctx.need, ctx.need)
        if ctx.need == "image" and self.media_dir:
            path, url = _media_url(self.media_dir, ctx.task.id, ctx.need)
            _render_placeholder(path, ctx.task.title,
                                 ctx.artifacts.get("concept", "")[:60])
            return url
        return f"[{ctx.actor.name}] {label} 완료"


def _render_placeholder(path: Path, title: str, subtitle: str) -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    W, H = 1024, 1024
    img = Image.new("RGB", (W, H), (28, 32, 30))
    d = ImageDraw.Draw(img)
    d.multiline_text((W // 2, H // 2 - 40),
                     "\n".join(textwrap.wrap(title or "이미지", 12)),
                     fill=(240, 240, 235), anchor="mm", align="center", spacing=14)
    if subtitle:
        d.multiline_text((W // 2, H // 2 + 120),
                         "\n".join(textwrap.wrap(subtitle, 22)),
                         fill=(150, 155, 150), anchor="mm", align="center", spacing=8)
    d.text((W // 2, H - 70), "· placeholder ·", fill=(110, 115, 110), anchor="mm")
    img.save(path)


class ClaudeExecutor:
    """텍스트를 Claude 로 실제 생성. 이미지/그 외는 mock 폴백."""
    kind = "claude"

    def __init__(self, model: str = "claude-opus-4-8",
                 fallback: ExecutorEngine | None = None):
        self.model = model
        self.fallback = fallback or MockExecutor()
        self._client = None

    def _client_or_none(self):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic()
            except Exception:
                self._client = False
        return self._client or None

    def execute(self, ctx: ExecutionContext) -> str:
        if ctx.need not in TEXT_NEEDS:
            return self.fallback.execute(ctx)
        client = self._client_or_none()
        if client is None:
            return self.fallback.execute(ctx)
        try:
            resp = client.messages.create(
                model=self.model, max_tokens=1024,
                messages=[{"role": "user", "content": _text_prompt(ctx)}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            return text or self.fallback.execute(ctx)
        except Exception:
            return self.fallback.execute(ctx)


class OpenAIExecutor:
    """텍스트(chat) + 이미지(images)를 OpenAI 로 실제 생성. 키 하나로 둘 다."""
    kind = "openai"

    def __init__(self, text_model: str = "gpt-4o-mini",
                 image_model: str = "gpt-image-1",
                 media_dir: Path | None = None,
                 fallback: ExecutorEngine | None = None):
        self.text_model = text_model
        # 설정 모델 → dall-e-3 순서로 시도 (검증 안 된 계정도 되게)
        self.image_models = list(dict.fromkeys([image_model, "dall-e-3"]))
        self.media_dir = Path(media_dir) if media_dir else None
        self.fallback = fallback or MockExecutor(media_dir)
        self._client = None

    def _client_or_none(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI()
            except Exception as e:
                print(f"[executor] OpenAI 초기화 실패(키 확인): {e}", file=sys.stderr)
                self._client = False
        return self._client or None

    def _gen_image(self, client, prompt: str) -> tuple[bytes, str]:
        """이미지 바이트를 돌려준다.

        모델·SDK 버전에 따라 응답이 b64_json 이거나 url 이라서 둘 다 처리한다.
        (response_format 은 최신 API 에서 거부되므로 아예 보내지 않는다.)
        """
        last = None
        for m in self.image_models:
            try:
                res = client.images.generate(model=m, prompt=prompt, size="1024x1024")
                d = res.data[0]
                b64 = getattr(d, "b64_json", None)
                if b64:
                    return base64.b64decode(b64), m
                url = getattr(d, "url", None)
                if url:
                    import urllib.request
                    with urllib.request.urlopen(url, timeout=60) as r:
                        return r.read(), m
                raise RuntimeError("이미지 응답에 b64_json/url 이 없습니다")
            except Exception as e:
                last = e
                print(f"[executor] 이미지 모델 '{m}' 실패: {e}", file=sys.stderr)
        raise last or RuntimeError("이미지 생성 실패")

    def execute(self, ctx: ExecutionContext) -> str:
        client = self._client_or_none()
        if client is None:
            return self.fallback.execute(ctx)
        try:
            if ctx.need in TEXT_NEEDS:
                r = client.chat.completions.create(
                    model=self.text_model,
                    messages=[{"role": "user", "content": _text_prompt(ctx)}],
                )
                text = (r.choices[0].message.content or "").strip()
                return text or self.fallback.execute(ctx)
            if ctx.need == "image" and self.media_dir:
                data, used = self._gen_image(client, _image_prompt(ctx))
                path, url = _media_url(self.media_dir, ctx.task.id, ctx.need)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                print(f"[executor] 이미지 생성 성공: {used} → {url}", file=sys.stderr)
                return url
        except Exception as e:
            print(f"[executor] '{ctx.need}' 생성 실패 → 플레이스홀더로 대체: {e}",
                  file=sys.stderr)
            return self.fallback.execute(ctx)
        return self.fallback.execute(ctx)  # 영상/게시 등은 아직 미연결


def build_executor(kind: str = "mock", model: str | None = None,
                   media_dir: Path | None = None,
                   image_model: str = "gpt-image-1") -> ExecutorEngine:
    if kind == "claude":
        return ClaudeExecutor(model or "claude-opus-4-8", MockExecutor(media_dir))
    if kind == "openai":
        return OpenAIExecutor(model or "gpt-4o-mini", image_model, media_dir)
    return MockExecutor(media_dir)
