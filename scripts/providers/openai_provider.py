"""OpenAI 兼容 provider — 同步文生图。

支持任何兼容 OpenAI Images API 的平台（OpenAI 官方 / 硅基流动 / OneAPI / New API /
Azure OpenAI 等），通过 OPENAI_BASE_URL 切换平台，请求/响应格式统一。

工作流: POST /v1/images/generations → 返回 base64 图片。
认证: Bearer OPENAI_API_KEY

注意:
- gpt-image-1 强制返回 b64_json，不支持 response_format="url"。
- 不传 response_format 参数（gpt-image-1 会报错或忽略）。
- 兼容平台可能用不同 model 名（如 flux/dall-e-3/stable-diffusion 等），通过 OPENAI_MODEL 配置。
"""

import base64
import json
from urllib.request import urlopen, Request
from urllib.error import HTTPError

from providers.base import GeneratedImage, validate_config

DEFAULT_BASE_URL = "https://api.openai.com/v1"
IMAGES_PATH = "/images/generations"

# aspect_ratio → OpenAI size 映射
# OpenAI gpt-image-1 支持的 size: 1024x1024, 1536x1024(横), 1024x1536(竖), auto
_SIZE_MAP = {
    "1:1": "1024x1024",
    "16:9": "1536x1024",
    "9:16": "1024x1536",
    "4:3": "1536x1024",
    "3:4": "1024x1536",
}


def _map_size(aspect_ratio: str, config: dict) -> str:
    """将通用 aspect_ratio 映射为 OpenAI 的 size 参数。支持用户直接传 size 覆盖。"""
    custom_size = config.get("OPENAI_SIZE", "").strip()
    if custom_size:
        return custom_size
    return _SIZE_MAP.get(aspect_ratio, "1024x1024")


def generate(prompt, aspect_ratio, output_dir, config, context=""):
    """生成单张图片，返回 GeneratedImage。

    config 需包含: OPENAI_API_KEY
    config 可选: OPENAI_MODEL (默认 gpt-image-1), OPENAI_SIZE, OPENAI_QUALITY
    """
    validate_config(["OPENAI_API_KEY"], config, "OpenAI")
    api_key = config["OPENAI_API_KEY"]
    base_url = config.get("OPENAI_BASE_URL", "").strip().rstrip("/") or DEFAULT_BASE_URL
    model = config.get("OPENAI_MODEL", "gpt-image-1").strip() or "gpt-image-1"
    size = _map_size(aspect_ratio, config)
    quality = config.get("OPENAI_QUALITY", "auto").strip() or "auto"

    body = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
    }

    url = base_url + IMAGES_PATH
    req = Request(url, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{context}OpenAI API error HTTP {e.code}: {body_text}") from e

    images = data.get("data", [])
    if not images or not images[0].get("b64_json"):
        raise RuntimeError(f"{context}OpenAI returned no image data: {json.dumps(data)[:200]}")

    image_bytes = base64.b64decode(images[0]["b64_json"])

    return GeneratedImage(
        image_bytes=image_bytes,
        ext="png",
        metadata={"model": model, "size": size, "base_url": base_url},
    )
