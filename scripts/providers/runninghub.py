"""RunningHub provider — 异步任务型文生图。

工作流: POST 提交任务 → POST 轮询状态 → 下载图片 URL。
认证: Bearer RUNNINGHUB_API_KEY
"""

import json
import time
import random
from urllib.request import urlopen, Request
from urllib.error import HTTPError

from providers.base import GeneratedImage, validate_config

API_BASE = "https://www.runninghub.cn/openapi/v2"
TEXT_TO_IMAGE_PATH = "/rhart-image-n-g31-flash/text-to-image"
QUERY_PATH = "/query"
RESOLUTION = "2k"

MAX_RETRIES = 3
SUBMIT_MAX_RETRIES = 8
POLL_MAX_RETRIES = 5
POLL_INTERVAL_S = 5.0
RETRY_BASE_DELAY_S = 3.0


class _RetryableError(Exception):
    def __init__(self, message, *, is_rate_limit=False):
        super().__init__(message)
        self.is_rate_limit = is_rate_limit


class _FatalError(Exception):
    pass


def _classify_error(e):
    msg = str(e).lower()
    if isinstance(e, _FatalError):
        return False, False
    if "http 429" in msg or "rate" in msg or "too many" in msg:
        return True, True
    if "http 5" in msg:
        return True, False
    return True, False


def _calc_backoff(attempt, base=RETRY_BASE_DELAY_S, is_rate_limit=False):
    multiplier = 2.0 if is_rate_limit else 1.0
    delay = base * (2 ** (attempt - 1)) * multiplier
    jitter = random.uniform(0.5, 1.5)
    return delay * jitter


def _request_sync(method, url_path, body, api_key):
    url = API_BASE + url_path
    payload = json.dumps(body).encode("utf-8")
    req = Request(url, data=payload, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        if e.code in (400, 401, 403):
            raise _FatalError(f"HTTP {e.code}: {body_text}")
        if e.code == 429:
            raise _RetryableError(f"HTTP 429 (rate limited): {body_text}", is_rate_limit=True)
        raise _RetryableError(f"HTTP {e.code}: {body_text}")
    except json.JSONDecodeError as e:
        raise _RetryableError(f"Failed to parse response: {e}")
    except Exception as e:
        raise _RetryableError(str(e))


def _with_retry(fn, max_retries=MAX_RETRIES, context=""):
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except _FatalError:
            raise
        except _RetryableError as e:
            if attempt == max_retries:
                raise
            delay = _calc_backoff(attempt, is_rate_limit=e.is_rate_limit)
            print(f"{context}Attempt {attempt}/{max_retries} failed: {e}. Retrying in {delay:.1f}s...")
            time.sleep(delay)
        except Exception as e:
            retryable, is_rate_limit = _classify_error(e)
            if not retryable or attempt == max_retries:
                raise
            delay = _calc_backoff(attempt, is_rate_limit=is_rate_limit)
            print(f"{context}Attempt {attempt}/{max_retries} failed: {e}. Retrying in {delay:.1f}s...")
            time.sleep(delay)


def _submit_task(prompt, aspect_ratio, api_key):
    res = _request_sync("POST", TEXT_TO_IMAGE_PATH, {
        "prompt": prompt,
        "aspectRatio": aspect_ratio,
        "resolution": RESOLUTION,
    }, api_key)
    if not res.get("taskId"):
        raise _RetryableError(f"No taskId in response: {json.dumps(res)}")
    return res["taskId"]


def _poll_result(task_id, api_key, context=""):
    poll_errors = 0
    while True:
        try:
            res = _request_sync("POST", QUERY_PATH, {"taskId": task_id}, api_key)
            poll_errors = 0
            status = res.get("status")

            if status == "SUCCESS":
                results = res.get("results")
                if not results or len(results) == 0 or not results[0].get("url"):
                    raise _RetryableError(f"SUCCESS but no image URL: {json.dumps(res)}")
                return results[0]

            if status == "FAILED":
                return {"_failed": True, "res": res}

            print(f"{context}Status: {status}. Polling in {POLL_INTERVAL_S}s...")
            time.sleep(POLL_INTERVAL_S)

        except _FatalError:
            raise
        except _RetryableError as e:
            poll_errors += 1
            if poll_errors > POLL_MAX_RETRIES:
                raise
            delay = _calc_backoff(poll_errors, is_rate_limit=e.is_rate_limit)
            print(f"{context}Poll error (retry {poll_errors}/{POLL_MAX_RETRIES}): {e}. Waiting {delay:.1f}s...")
            time.sleep(delay)


def generate(prompt, aspect_ratio, output_dir, config, context=""):
    """生成单张图片，返回 GeneratedImage。

    config 需包含: RUNNINGHUB_API_KEY
    """
    validate_config(["RUNNINGHUB_API_KEY"], config, "RunningHub")
    api_key = config["RUNNINGHUB_API_KEY"]

    submit_retries = 0
    while submit_retries <= POLL_MAX_RETRIES:
        task_id = _with_retry(
            lambda: _submit_task(prompt, aspect_ratio, api_key),
            max_retries=SUBMIT_MAX_RETRIES, context=context,
        )
        result = _poll_result(task_id, api_key, context=context)

        if result.get("_failed"):
            submit_retries += 1
            if submit_retries > POLL_MAX_RETRIES:
                raise _RetryableError(f"{context}Max retries exceeded for task submission.")
            delay = _calc_backoff(submit_retries)
            print(f"{context}Re-submitting task (attempt {submit_retries}/{POLL_MAX_RETRIES}) in {delay:.1f}s...")
            time.sleep(delay)
            continue
        break

    ext = result.get("outputType", "png")
    return GeneratedImage(
        url=result["url"],
        ext=ext,
        metadata={"task_id": task_id},
    )
