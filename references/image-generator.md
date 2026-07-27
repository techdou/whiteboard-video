# 文生图生成器（多 Provider）

## 前置条件

必须在 skill 目录的 `.env` 文件中配置好文生图 API。支持 4 个平台，通过 `IMAGE_PROVIDER` 切换：

| Provider | 环境变量 | 适用平台 |
|---|---|---|
| `runninghub` | `RUNNINGHUB_API_KEY` | RunningHub |
| `openai` | `OPENAI_API_KEY` + `OPENAI_BASE_URL` | OpenAI 官方 / 硅基流动 / OneAPI / New API 等所有 OpenAI Images API 兼容平台 |
| `replicate` | `REPLICATE_API_TOKEN` | Replicate (Flux) |
| `stability` | `STABILITY_API_KEY` | Stability AI (Stable Image Core) |

如果未配置，提示用户提供或参考 `.env.example`。

## 用法

运行内置脚本：

```bash
python3 <skill-dir>/scripts/generate-image.py "<提示词>" "<宽高比>" "<输出目录>"
```

**注意**：`<skill-dir>` 是 `whiteboard-video` skill 的绝对路径，由主 agent 在 subagent 指令中提供。

**参数：**
1. `prompt`（必填）— 图片生成提示词。支持两种模式：
   - **单张模式**：传入普通字符串，如 `"一只猫坐在窗台上"`。
   - **批量模式**：传入 JSON 编码的字符串数组，如 `'["提示词1","提示词2","提示词3"]'`。每个数组元素对应一张图片，脚本会以 10 个并发同时生成。
2. `aspect-ratio`（可选，默认值：`"16:9"`）— 图片宽高比（如 `"1:1"`、`"9:16"`、`"16:9"`、`"4:3"`）。
3. `output-dir`（可选，默认值：当前工作目录）— 生成图片的保存目录。

**示例：**

单张生成：
```bash
python3 <skill-dir>/scripts/generate-image.py "一只猫坐在窗台上，夕阳西下" "16:9" "./output"
```

批量生成：
```bash
python3 <skill-dir>/scripts/generate-image.py '["一只猫坐在窗台上","一只狗在草地上奔跑","日落时分的海边"]' "16:9" "./output"
```

## 工作流程

1. 验证 `prompt` 不为空。如果缺失，询问用户。
2. 检测 `prompt` 是否为 JSON 数组格式，自动区分单张/批量模式。
3. 读取 `.env` 中的 `IMAGE_PROVIDER`（默认 `runninghub`），加载对应 provider。
4. 使用三个参数运行 `scripts/generate-image.py`。
5. 脚本会自动处理：
   - 根据 provider 分发到对应的 API 调用逻辑
   - RunningHub/Replicate：提交任务 → 轮询状态 → 下载结果
   - OpenAI：同步请求 → 解码 base64
   - Stability AI：multipart 请求 → 直接读取二进制图片
   - 失败自动重试（最多 3 次，指数退避）
   - 下载结果图片，文件名基于时间戳命名
   - **批量模式**：以 10 个并发 worker 同时执行生成任务
6. 向用户报告保存的文件路径。

## Provider 配置详解

### RunningHub（默认）
```env
IMAGE_PROVIDER=runninghub
RUNNINGHUB_API_KEY=your_key
```

### OpenAI 兼容（官方 / 硅基流动 / OneAPI / New API 等）
所有兼容 OpenAI Images API (`/v1/images/generations`) 的平台都用这一个 provider，通过 `OPENAI_BASE_URL` 切换平台：

```env
IMAGE_PROVIDER=openai
OPENAI_API_KEY=your_key
# 可选:
# OPENAI_BASE_URL=https://api.openai.com/v1   # OpenAI 官方（默认）
# OPENAI_BASE_URL=https://api.siliconflow.cn/v1 # 硅基流动
# OPENAI_BASE_URL=https://your-gateway.com/v1   # OneAPI/New API 网关
# OPENAI_MODEL=gpt-image-1        # 默认 gpt-image-1，兼容平台可能用 flux 等
# OPENAI_QUALITY=auto              # low/medium/high/auto
# OPENAI_SIZE=                     # 留空自动按 aspect_ratio 映射，或手动指定 1024x1024
```

### Replicate (Flux)
```env
IMAGE_PROVIDER=replicate
REPLICATE_API_TOKEN=r8_your_token
# 可选:
# REPLICATE_MODEL=black-forest-labs/flux-1.1-pro-ultra
```

### Stability AI (Stable Image Core)
```env
IMAGE_PROVIDER=stability
STABILITY_API_KEY=your_key
# 可选:
# STABILITY_OUTPUT_FORMAT=png      # png/jpeg/webp
# STABILITY_STYLE_PRESET=          # 如 anime/photographic/digital-art 等
```

## 批量模式说明

- 当 `prompt` 参数是 JSON 字符串数组时自动进入批量模式
- 并发数固定为 10，即同时最多运行 10 个生成任务
- 每张图片独立处理，单张失败不影响其他图片
- 输出文件名格式：`img_<timestamp>_<序号>.<ext>`
- 执行结束后会输出汇总信息：成功数和失败数
- 脚本输出的最后一行以 `__RESULTS__` 前缀加上 JSON 数组，包含每张图片的保存路径或错误信息

## 资源文件

- `scripts/generate-image.py` — 多 provider 分发器，处理完整的生成-轮询-下载流程，支持单张和批量并发模式
- `scripts/providers/` — provider 适配层
  - `runninghub.py` — RunningHub 异步任务型
  - `openai_provider.py` — OpenAI gpt-image-1 同步
  - `replicate_provider.py` — Replicate 异步任务型
  - `stability_provider.py` — Stability AI 同步 multipart
