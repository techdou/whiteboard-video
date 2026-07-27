"""Stability AI provider — 同步文生图 (Stable Image Core)。

工作流: POST multipart 请求 → 直接返回二进制图片字节。
认证: Bearer STABILITY_API_KEY

关键点:
- 用 multipart/form-data 提交 prompt 等字段。
- Accept: image/* → 响应体直接是原始图片二进制字节，无需 base64 解码。
- Core endpoint 是同步的（不需要轮询）。
"""

import uuid
from urllib.request import urlopen, Request
from urllib.error import HTTPError

from providers.base import GeneratedImage, validate_config

API_ENDPOINT = "https://api.stability.ai/v2beta/stable-image/generate/core"


def _build_multipart(fields: dict, boundary: str) -> bytes:
    """手工构建 multipart/form-data body（纯标准库，不依赖 requests）。"""
    lines = []
    for key, value in fields.items():
        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="{key}"'.encode("utf-8"))
        lines.append(b"")
        lines.append(str(value).encode("utf-8"))
    lines.append(f"--{boundary}--".encode("utf-8"))
    lines.append(b"")
    return b"\r\n".join(lines)


def generate(prompt, aspect_ratio, output_dir, config, context=""):
    """生成单张图片，返回 GeneratedImage。

    config 需包含: STABILITY_API_KEY
    config 可选: STABILITY_MODEL, STABILITY_STYLE_PRESET, STABILITY_OUTPUT_FORMAT
    """
    validate_config(["STABILITY_API_KEY"], config, "Stability AI")
    api_key = config["STABILITY_API_KEY"]
    output_format = config.get("STABILITY_OUTPUT_FORMAT", "png").strip() or "png"
    style_preset = config.get("STABILITY_STYLE_PRESET", "").strip()

    fields = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "output_format": output_format,
    }
    if style_preset:
        fields["style_preset"] = style_preset

    boundary = uuid.uuid4().hex
    body = _build_multipart(fields, boundary)

    req = Request(API_ENDPOINT, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Accept", "image/*")  # 关键: 让服务端直接返回二进制图片

    try:
        with urlopen(req, timeout=120) as resp:
            content_type = resp.headers.get("Content-Type", "")
            image_bytes = resp.read()
    except HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{context}Stability API error HTTP {e.code}: {body_text}") from e

    if not image_bytes:
        raise RuntimeError(f"{context}Stability AI returned empty response")

    return GeneratedImage(
        image_bytes=image_bytes,
        ext=output_format,
        metadata={"endpoint": "core"},
    )
