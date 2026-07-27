# Whiteboard Video — 白板手绘视频生成器 | Whiteboard Hand-drawn Video Generator

[English](#english) | [中文](#中文)

> **Provenance | 来源**：改编自 B 站 [YangAgent](https://space.bilibili.com/) 分享的白板动画生成思路，在原方案基础上扩展为三模式 + 多 provider 文生图架构。

---

<a id="english"></a>
## English

A portable Agent Skill for generating **whiteboard hand-drawn animation videos**. Supports three modes: SRT subtitle → complete whiteboard video, batch images → multiple animations, or single image → one animation.

**Animation pipeline**: line-art drawing (hand-held pen progressively sketches black-and-white outlines) → coloring (hand-held pen paints along contours to restore the original image).

| Mode | Input | Output | Needs API Key |
|------|-------|--------|:---:|
| **Full mode** | SRT subtitle file | Merged whiteboard video (storyboard → text-to-image → animation → merge) | ✅ (TTS/image API) |
| **Batch mode** | Multiple images + duration array | Multiple whiteboard animation clips | ❌ |
| **Single mode** | One image | One whiteboard animation video | ❌ |

Supports 4 text-to-image providers (RunningHub / OpenAI-compatible / Replicate / Stability AI), switched via `.env` `IMAGE_PROVIDER`. See full Chinese docs below for usage.

---

<a id="中文"></a>
## 中文

> 从 SRT 字幕一键生成完整白板动画视频，或把图片转成白板手绘动画。一个 skill 覆盖完整场景。

## 三种模式

| 模式 | 输入 | 输出 | 需要 API Key |
|------|------|------|:---:|
| **完整模式** | SRT 字幕文件 | 合并后的完整白板视频（分镜→文生图→动画→合并） | ✅ RunningHub |
| **批量动画** | 多张图片 + 时长数组 | 多个白板动画视频片段 | ❌ |
| **单图动画** | 单张图片 | 一个白板动画视频 | ❌ |

动画效果分两个阶段：**线稿绘制**（手持笔逐步画出黑白线稿）→ **上色**（手持笔沿轮廓涂色还原原图）。

## 安装配置

### 1. 放置 skill

将整个 `whiteboard-video/` 目录放到 Agent 的 skills 目录下：

```text
.agents/skills/whiteboard-video/
```

### 2. 配置 API Key（仅完整模式需要）

完整模式需要文生图 API 来生成白板图片。支持 4 个平台，通过 `.env` 中的 `IMAGE_PROVIDER` 切换：

| Provider | 环境变量 | 适用平台 |
|---|---|---|
| `runninghub`（默认） | `RUNNINGHUB_API_KEY` | RunningHub |
| `openai` | `OPENAI_API_KEY` + `OPENAI_BASE_URL` | OpenAI 官方 / 硅基流动 / OneAPI / New API 等**所有 OpenAI Images API 兼容平台** |
| `replicate` | `REPLICATE_API_TOKEN` | Replicate (Flux) |
| `stability` | `STABILITY_API_KEY` | Stability AI |

```bash
# 在 skill 根目录下创建 .env
cp .env.example .env
# 编辑 .env，设置 IMAGE_PROVIDER 和对应的 API Key
```

```text
IMAGE_PROVIDER=runninghub
RUNNINGHUB_API_KEY=your_api_key_here
```

切换平台只需改 `.env`，比如用 OpenAI 官方或兼容平台（硅基流动等）：
```text
IMAGE_PROVIDER=openai
OPENAI_BASE_URL=https://api.openai.com/v1   # 或 https://api.siliconflow.cn/v1
OPENAI_API_KEY=sk-your_key
OPENAI_MODEL=gpt-image-1                     # 兼容平台可能用 flux 等
```

单图/批量动画模式不需要 API Key，只需 Python 虚拟环境。

### 3. Python 环境（全自动）

首次运行时脚本会自动创建虚拟环境并安装依赖（OpenCV、NumPy、PyAV）。需要 **Python 3.9+**。

```bash
# 手动预检（可选）
python3 scripts/check_env.py --check-only
```

## 快速开始

### 完整模式：SRT → 白板视频

```bash
# 环境预检（获取 PYTHON_PATH）
python3 scripts/check_env.py

# 创建输出目录
python3 scripts/workflow_helper.py init-dirs "./output"

# 步骤 3-5 详见 SKILL.md（subagent 执行 SRT 解析和文生图）
# 步骤 7：批量生成动画片段
<PYTHON_PATH> scripts/batch_generate.py \
  --images img1.png img2.png img3.png \
  --durations 10000 15000 8000 \
  --output-dir ./output/video

# 步骤 8：合并视频
<PYTHON_PATH> scripts/workflow_helper.py merge-videos ./output video1.mp4 video2.mp4 video3.mp4
```

### 单图模式：图片 → 白板动画

```bash
# 准备环境
python3 scripts/setup_env.py

# 生成白板动画
<PYTHON_PATH> scripts/generate_whiteboard.py photo.png --output-dir ./output --duration 15000
```

### 批量模式：多张图片 → 多个白板动画

```bash
<PYTHON_PATH> scripts/batch_generate.py \
  --images img1.png img2.png img3.png \
  --durations 10000 15000 8000 \
  --output-dir ./output
```

## 目录结构

```text
whiteboard-video/
├── SKILL.md                         # Agent 技能定义（三模式路由 + 完整工作流）
├── README.md                        # 本文档
├── .env.example                     # API Key 配置模板
├── .gitignore
├── assets/
│   └── drawing-hand.png             # 手部覆盖效果素材
├── scripts/
│   ├── check_env.py                 # 环境预检（Python + provider API Key）
│   ├── setup_env.py                 # 虚拟环境创建与依赖安装
│   ├── generate_whiteboard.py       # 核心动画生成（OpenCV 线稿+上色+手部）
│   ├── batch_generate.py            # 批量串行调用单张生成
│   ├── workflow_helper.py           # 目录创建/提示词生成/视频合并
│   ├── generate-storyboard.py       # SRT + groups.json → storyboard.json
│   ├── generate-image.py            # 多 provider 文生图分发器
│   ├── banana_prompt_template.py    # 白板风格提示词模板
│   └── providers/                   # 文生图 provider 适配层
│       ├── __init__.py              # 注册表与统一入口
│       ├── base.py                  # GeneratedImage 数据结构
│       ├── runninghub.py            # RunningHub（异步任务型）
│       ├── openai_provider.py       # OpenAI gpt-image-1（同步 base64）
│       ├── replicate_provider.py    # Replicate Flux（异步轮询型）
│       └── stability_provider.py    # Stability AI（同步 multipart）
└── references/
    ├── storyboard-parser.md         # SRT 分镜解析工作流（subagent 执行）
    └── image-generator.md           # 文生图工作流（subagent 执行）
```

## 依赖

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| Python 3.9+ | 运行环境 | 系统自带 |
| OpenCV (`opencv-python`) | 图像处理、线稿检测、上色 | 自动安装到 `.venv` |
| NumPy (`numpy`) | 数值计算 | 自动安装到 `.venv` |
| PyAV (`av`) | 视频编解码（H.264 编码/合并） | 自动安装到 `.venv` |
| 文生图 API | 白板图片生成（仅完整模式） | 配置 `.env`（4 选 1） |

**支持的文生图平台**：RunningHub / OpenAI 兼容（官方、硅基流动、OneAPI/New API 等所有 OpenAI Images API 兼容平台）/ Replicate (Flux) / Stability AI — 通过 `.env` 的 `IMAGE_PROVIDER` 切换，详见 [.env.example](.env.example)。

## 技术细节

- **动画原理**：OpenCV 提取图片边缘轮廓生成线稿，按轮廓顺序逐步绘制模拟手写效果，再逐步上色还原原图
- **手部覆盖**：叠加手部素材模拟真实手绘
- **视频编码**：统一输出 H.264 MP4，合并时重新编码确保格式一致
- **时长单位**：全链路统一使用毫秒，避免浮点转换丢失精度

## 合并说明

本 skill 合并了原先独立的两个 skill：
- `whiteboard-animation`（图片 → 白板动画引擎）
- `whiteboard-video-workflow`（SRT → 完整视频编排）

合并后单图/批量动画能力作为子模式保留，完整模式不再跨 skill 调用，路径耦合消除。
