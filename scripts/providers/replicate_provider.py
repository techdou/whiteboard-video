"""Replicate provider — 异步任务型文生图。

工作流: POST 创建 prediction → GET 轮询 → output 是图片 URL。
认证: Bearer REPLICATE_API_TOKEN (token 格式 r8_xxx)

使用 model slug 方式（2025-08-05 起统一），而非旧 version 哈希。
默认模型: black-forest-labs/flux-1.1-pro-ultra
"""

import json
import time
from urllib.request import urlopen, Request
from urllib.error import HTTPError

from providers.base import GeneratedImage, validate_config

API_BASE = "https://api.replicate.com/v1"
PREDICTIONS_PATH = "/predictions"

POLL_INTERVAL_S = 2.0
POLL_TIMEOUT_S = 300.0  # 5 分钟超时


def generate(prompt, aspect_ratio, output_dir, config, context=""):
    """生成单张图片，返回 GeneratedImage。

    config 需包含: REPLICATE_API_TOKEN
    config 可选: REPLICATE_MODEL (默认 black-forest-labs/flux-1.1-pro-ultra)
    """
    validate_config(["REPLICATE_API_TOKEN"], config, "Replicate")
    api_token = config["REPLICATE_API_TOKEN"]
    model = config.get("REPLICATE_MODEL", "").strip() or "black-forest-labs/flux-1.1-pro-ultra"

    # 创建 prediction
    body = {
        "model": model,
        "input": {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
        },
    }

    req = Request(
        API_BASE + PREDICTIONS_PATH,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_token}")
    req.add_header("Prefer", "wait")  # 尽量让服务端等待完成

    try:
        with urlopen(req, timeout=30) as resp:
            prediction = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{context}Replicate create error HTTP {e.code}: {body_text}") from e

    prediction_id = prediction.get("id")
    if not prediction_id:
        raise RuntimeError(f"{context}Replicate returned no prediction id: {json.dumps(prediction)[:200]}")

    poll_url = prediction.get("urls", {}).get("get")
    if not poll_url:
        poll_url = f"{API_BASE}{PREDICTIONS_PATH}/{prediction_id}"

    # 轮询
    status = prediction.get("status", "starting")
    start_time = time.time()

    while status not in ("succeeded", "failed", "canceled"):
        if time.time() - start_time > POLL_TIMEOUT_S:
            raise RuntimeError(f"{context}Replicate prediction timed out after {POLL_TIMEOUT_S}s")

        time.sleep(POLL_INTERVAL_S)
        poll_req = Request(poll_url, method="GET")
        poll_req.add_header("Authorization", f"Bearer {api_token}")

        try:
            with urlopen(poll_req, timeout=30) as resp:
                prediction = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{context}Replicate poll error HTTP {e.code}: {body_text}") from e

        status = prediction.get("status", "processing")
        if status not in ("succeeded", "failed", "canceled"):
            print(f"{context}Replicate status: {status}. Polling in {POLL_INTERVAL_S}s...")

    if status != "succeeded":
        error_msg = prediction.get("error", f"status={status}")
        raise RuntimeError(f"{context}Replicate prediction {status}: {error_msg}")

    output = prediction.get("output")
    if not output:
        raise RuntimeError(f"{context}Replicate succeeded but no output: {json.dumps(prediction)[:200]}")

    # output 可能是字符串 URL 或 URL 列表
    if isinstance(output, list):
        url = output[0] if output else None
    else:
        url = output

    if not url:
        raise RuntimeError(f"{context}Replicate output is empty")

    # 从 URL 推断扩展名
    ext = "png"
    for candidate in ("png", "jpg", "jpeg", "webp"):
        if candidate in url.lower():
            ext = "jpg" if candidate == "jpeg" else candidate
            break

    return GeneratedImage(
        url=url,
        ext=ext,
        metadata={"prediction_id": prediction_id, "model": model},
    )
