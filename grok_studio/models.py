"""쇼핑몰 모델 3인 + 기본 영상 프롬프트.

각 모델은 '고정된 외모 묘사'를 갖는다. 텍스트-투-이미지로 매번 같은 모델을
만들려면 묘사가 구체적일수록 일관성이 좋다. 여기 설명을 바꾸면 모델이 바뀐다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Model:
    id: str
    name: str          # 표시 이름
    emoji: str         # UI 아바타(참조 이미지 없을 때)
    tagline: str       # 한 줄 소개
    # 이미지 생성 프롬프트에 그대로 들어가는 '외모 고정' 묘사 (영어 권장 — 그록 이미지 품질)
    appearance: str


# ── 모델 카탈로그 ──────────────────────────────────────────────
MODELS: list[Model] = [
    Model(
        id="seoa",
        name="서아 (Seoa)",
        emoji="👩🏻",
        tagline="청초·러블리 · 여성복",
        appearance=(
            "a 23-year-old Korean female fashion model named Seoa, "
            "168cm tall, slim hourglass figure, long straight glossy black hair "
            "past the shoulders, clear fair skin, soft round eyes, gentle natural makeup, "
            "elegant and lovely vibe, professional studio e-commerce model"
        ),
    ),
    Model(
        id="jimin",
        name="지민 (Jimin)",
        emoji="💁🏻‍♀️",
        tagline="시크·모던 · 여성복",
        appearance=(
            "a 26-year-old Korean female fashion model named Jimin, "
            "170cm tall, tall slender figure, shoulder-length wavy brown hair, "
            "sharp confident eyes, matte chic makeup, high cheekbones, "
            "cool modern editorial vibe, professional studio e-commerce model"
        ),
    ),
    Model(
        id="haneul",
        name="하늘 (Haneul)",
        emoji="🧑🏻",
        tagline="깔끔·훈훈 · 남성복",
        appearance=(
            "a 27-year-old Korean male fashion model named Haneul, "
            "183cm tall, athletic lean build, short neat black hair, "
            "clean-cut handsome face, warm friendly expression, "
            "clean minimal vibe, professional studio e-commerce model"
        ),
    ),
]

MODELS_BY_ID = {m.id: m for m in MODELS}


def get_model(model_id: str) -> Model:
    m = MODELS_BY_ID.get(model_id)
    if not m:
        raise KeyError(f"알 수 없는 모델: {model_id}")
    return m


# ── 기본 영상 프롬프트 (사용자 제공 안무) ─────────────────────
# UI 에서 수정 가능. {motion} 자리에 이 안무가 들어간다.
DEFAULT_MOTION_PROMPT = (
    "The character performs a 40-degree rotation in place: pausing precisely for "
    "0.5 second, holding the pause with a natural, composed posture. Then keep "
    "rotating 40-degree in the same direction, pause 0.5 seconds. Then rotate back "
    "toward the camera and pause precisely for one full second. Then the model "
    "confidently walks to the left and leaves off-screen from the side."
)

# 영상 프롬프트를 만들 때 안무 앞에 붙는 촬영/스타일 지시.
# 일관성을 위해 카메라·구도·군더더기 동작을 강하게 고정한다.
VIDEO_STYLE_PREFIX = (
    "Full-body fashion e-commerce video of {model_name} wearing the outfit shown "
    "in the reference image. Clean bright studio, seamless light-gray backdrop, "
    "soft even lighting, sharp focus on the clothing, realistic fabric movement, "
    "vertical 9:16 framing. "
    "The camera is completely static and locked off — no zoom, no pan, no shake. "
    "The model stays centered in frame. Perform ONLY the exact motion described "
    "below with the specified timing, and add no extra gestures, expressions, "
    "or movements. Even, steady pacing. "
)


def build_video_prompt(model_name: str, motion: str) -> str:
    return VIDEO_STYLE_PREFIX.format(model_name=model_name) + motion.strip()


def build_portrait_prompt(appearance: str) -> str:
    """모델 선택 카드에 보여줄 프로필 사진 프롬프트 (상반신 인물)."""
    return (
        f"Professional studio profile portrait of {appearance}. "
        "Upper-body shot from the chest up, facing the camera with a warm, "
        "friendly natural expression, wearing simple neutral casual clothing, "
        "clean seamless light-gray studio background, soft even beauty lighting, "
        "ultra high resolution, ultra-detailed, tack-sharp crisp focus, "
        "professional DSLR photography, 8k, photorealistic skin texture, "
        "Korean fashion-model profile headshot."
    )


def build_tryon_prompt(appearance: str, garment_desc: str) -> str:
    """모델이 옷 입은 스틸컷 생성 프롬프트.

    핵심: 머리끝~발끝(신발 포함) 전신이 잘리지 않고 다 나오도록 강하게 지시.
    """
    return (
        f"Full-length head-to-toe studio fashion photograph of {appearance}, "
        f"wearing {garment_desc}. "
        "FULL BODY SHOT showing the ENTIRE figure from the top of the head all "
        "the way down to the shoes — the feet and footwear MUST be fully visible "
        "and NOTHING is cropped or cut off at the legs. "
        "The model stands upright facing the camera in a natural relaxed pose, "
        "the whole body centered in frame with clear empty margin space above the "
        "head and below the feet (do not crop the ankles or shoes). "
        "Clean seamless light-gray studio backdrop, soft even lighting, "
        "ultra high resolution, ultra-detailed, tack-sharp crisp focus, "
        "professional DSLR fashion photography, 8k, realistic fabric texture and fit, "
        "professional Korean online shopping-mall lookbook catalog style, "
        "tall vertical full-length fashion framing, photorealistic."
    )
