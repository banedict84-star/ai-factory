"""설정 로딩 — .env 환경변수와 config/content.yaml 을 읽어옵니다."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "content.yaml"
CAFE_CONFIG_PATH = ROOT / "config" / "cafe.yaml"
OUTPUT_DIR = ROOT / "output"


def load_content_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """content.yaml 을 딕셔너리로 읽어옵니다."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_cafe_config(path: Path = CAFE_CONFIG_PATH) -> dict[str, Any]:
    """cafe.yaml (네이버 카페 설정) 을 딕셔너리로 읽어옵니다."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(key: str, default: str | None = None, required: bool = False) -> str | None:
    """환경변수 조회. required=True 인데 비어 있으면 에러."""
    value = os.getenv(key, default)
    if required and not value:
        raise RuntimeError(
            f"환경변수 {key} 가 설정되지 않았습니다. .env 또는 GitHub Secrets 를 확인하세요."
        )
    return value


def ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR
