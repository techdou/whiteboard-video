#!/usr/bin/env python3
"""
文生图脚本 — 多 Provider 架构

支持 RunningHub / OpenAI / Replicate / Stability AI 四个文生图平台，
通过 .env 中的 IMAGE_PROVIDER 字段切换。

用法:
    python3 generate-image.py "<提示词>" "<宽高比>" "<输出目录>"
    python3 generate-image.py '["提示词1","提示词2"]' "16:9" "./output"

配置 (skill 根目录 .env):
    IMAGE_PROVIDER=runninghub|openai|replicate|stability  (默认 runninghub)
    RUNNINGHUB_API_KEY=...
    OPENAI_API_KEY=...
    REPLICATE_API_TOKEN=...
    STABILITY_API_KEY=...
"""

import asyncio
import json
import os
import random
import shutil
import sys
import time
from pathlib import Path
from urllib.request import urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import providers as provider_registry
from providers.base import GeneratedImage
from banana_prompt_template import whiteboard_prompt_template

BATCH_CONCURRENCY = 10
MAX_RETRIES = 3
RETRY_BASE_DELAY_S = 3.0


# ── .env 加载 ──────────────────────────────────────────────────────────

def load_env():
    """从 skill 根目录的 .env 加载环境变量（不覆盖已有的）。"""
    env_path = SCRIPT_DIR.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        eq_index = trimmed.find("=")
        if eq_index == -1:
            continue
        key = trimmed[:eq_index].strip()
        value = trimmed[eq_index + 1:].strip().strip('"').strip("'")
        if key and value and not os.environ.get(key):
            os.environ[key] = value


def get_provider_name() -> str:
    """从环境变量获取 provider 名，默认 runninghub。"""
    return os.environ.get("IMAGE_PROVIDER", "runninghub").lower().strip()


def build_provider_config(provider_name: str) -> dict:
    """从环境变量构建 provider 配置字典。"""
    # 把所有环境变量都放进 config，每个 provider 按需取用
    return dict(os.environ)


# ── 图片保存 ───────────────────────────────────────────────────────────

def save_generated_image(result: GeneratedImage, output_dir: str, index: int, total: int) -> str:
    """把 GeneratedImage 保存到本地文件，返回文件路径。"""
    timestamp = int(time.time() * 1000)
    suffix = f"_{str(index + 1).zfill(len(str(total)))}" if total > 1 else ""
    ext = result.ext or "png"
    filename = f"img_{timestamp}{suffix}.{ext}"
    filepath = str(Path(output_dir) / filename)

    if result.has_bytes:
        Path(filepath).write_bytes(result.image_bytes)
    elif result.has_url:
        _download_file(result.url, filepath)
    else:
        raise RuntimeError("GeneratedImage 既无 bytes 也无 url")

    return filepath


def _download_file(url: str, dest_path: str):
    """下载文件，支持重定向。"""
    with urlopen(url) as resp:
        if 300 <= resp.status < 400:
            location = resp.headers.get("Location")
            if location:
                _download_file(location, dest_path)
                return
        if resp.status != 200:
            raise RuntimeError(f"Download failed with status {resp.status}")
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(resp, f)


# ── 重试与批量 ─────────────────────────────────────────────────────────

def _calc_backoff(attempt, base=RETRY_BASE_DELAY_S, is_rate_limit=False):
    multiplier = 2.0 if is_rate_limit else 1.0
    delay = base * (2 ** (attempt - 1)) * multiplier
    jitter = random.uniform(0.5, 1.5)
    return delay * jitter


async def _generate_with_retry(provider_module, prompt, aspect_ratio, output_dir,
                               config, index, total):
    """带重试的单张生成。"""
    tag = f"[{index + 1}/{total}] " if total > 1 else ""
    full_prompt = whiteboard_prompt_template + prompt

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await asyncio.to_thread(
                provider_module.generate,
                full_prompt, aspect_ratio, output_dir, config, tag,
            )
            filepath = await asyncio.to_thread(
                save_generated_image, result, output_dir, index, total,
            )
            print(f"{tag}Image saved: {filepath}")
            return filepath
        except Exception as e:
            if attempt == MAX_RETRIES:
                raise
            delay = _calc_backoff(attempt)
            print(f"{tag}Attempt {attempt}/{MAX_RETRIES} failed: {e}. Retrying in {delay:.1f}s...")
            await asyncio.sleep(delay)


async def _run_batch(provider_module, tasks, concurrency):
    """并发批量生成，失败的在最后重试一次。"""
    semaphore = asyncio.Semaphore(concurrency)
    results = [None] * len(tasks)

    async def worker(i, task):
        async with semaphore:
            try:
                results[i] = await _generate_with_retry(
                    provider_module,
                    task["prompt"], task["aspect_ratio"],
                    task["output_dir"], task["config"],
                    task["index"], task["total"],
                )
            except Exception as e:
                results[i] = {"error": str(e), "task": task}

    await asyncio.gather(*(worker(i, t) for i, t in enumerate(tasks)))

    # 失败重试
    failed_indices = [i for i, r in enumerate(results)
                      if isinstance(r, dict) and r.get("error")]
    if failed_indices:
        print(f"\nRetrying {len(failed_indices)} failed tasks...")
        await asyncio.sleep(RETRY_BASE_DELAY_S)

        async def retry_worker(i):
            async with semaphore:
                task = results[i]["task"]
                try:
                    results[i] = await _generate_with_retry(
                        provider_module,
                        task["prompt"], task["aspect_ratio"],
                        task["output_dir"], task["config"],
                        task["index"], task["total"],
                    )
                except Exception as e:
                    results[i] = {"error": str(e)}

        await asyncio.gather(*(retry_worker(i) for i in failed_indices))

    return results


# ── 主入口 ─────────────────────────────────────────────────────────────

async def main():
    load_env()

    provider_name = get_provider_name()
    try:
        provider_module = provider_registry.get_provider(provider_name)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    required_keys = provider_registry.get_required_env_keys(provider_name)
    missing = [k for k in required_keys if not os.environ.get(k)]
    if missing:
        print(f"Error: provider '{provider_name}' 缺少环境变量: {', '.join(missing)}")
        print(f"请在 skill 根目录的 .env 文件中配置。")
        sys.exit(1)

    config = build_provider_config(provider_name)

    args = sys.argv[1:]
    prompt_arg = args[0] if len(args) > 0 else ""
    aspect_ratio = args[1] if len(args) > 1 else "16:9"
    output_dir = args[2] if len(args) > 2 else os.getcwd()

    if not prompt_arg.strip():
        print("Error: prompt is required and cannot be empty.")
        sys.exit(1)

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 检测批量模式
    prompts = None
    try:
        parsed = json.loads(prompt_arg)
        if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], str):
            prompts = parsed
    except (json.JSONDecodeError, ValueError):
        pass
    if not prompts:
        prompts = [prompt_arg]

    total = len(prompts)
    is_batch = total > 1
    if is_batch:
        print(f"Provider: {provider_name} | Batch mode: {total} images (concurrency: {BATCH_CONCURRENCY})...")
    else:
        print(f"Provider: {provider_name}")

    tasks = [
        {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "output_dir": output_dir,
            "config": config,
            "index": i,
            "total": total,
        }
        for i, prompt in enumerate(prompts)
    ]

    results = await _run_batch(provider_module, tasks, BATCH_CONCURRENCY)

    # 汇总
    succeeded = [r for r in results if isinstance(r, str)]
    failed = [r for r in results if isinstance(r, dict) and r.get("error")]
    if is_batch:
        print(f"\nBatch complete: {len(succeeded)} succeeded, {len(failed)} failed.")
    if failed:
        for f in failed:
            print(f"  Error: {f['error']}")

    print(f"\n__RESULTS__{json.dumps(results)}")


if __name__ == "__main__":
    asyncio.run(main())
