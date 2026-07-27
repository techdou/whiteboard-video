---
name: whiteboard-video
description: 白板手绘视频生成工具。支持三种模式：从 SRT 字幕文件一键生成完整白板动画视频（分镜→文生图→动画→合并）、批量将多张图片转为白板动画、单张图片转白板动画。当用户说"白板动画"、"白板视频"、"把图片做成白板动画"、"从字幕生成白板视频"、"批量白板动画"、"手绘动画视频"、"whiteboard animation"、"whiteboard video"时触发。
---

# Whiteboard Video — 白板手绘视频生成器

从一个统一的入口处理所有白板动画视频需求。根据用户输入自动判断模式：

## 模式判断

| 用户输入 | 模式 | 说明 |
|---|---|---|
| SRT 字幕文件 | **完整模式** | SRT → 语义分镜 → AI 文生图 → 白板动画 → 合并为完整视频 |
| 多张图片 + 对应时长 | **批量动画模式** | 每张图片 → 白板手绘动画，串行生成多个视频片段 |
| 单张图片 | **单图动画模式** | 一张图片 → 白板手绘动画视频 |

动画分两个阶段：**线稿绘制**（手持笔逐步画出黑白线稿）→ **上色**（手持笔沿轮廓逐步涂色还原原图）。

---

## 完整模式：SRT → 白板视频

### 输入参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `srtPath` | 是 | SRT 字幕文件的绝对路径 |
| `outputDir` | 否 | 输出根目录，默认为 SRT 文件所在目录 |

### 工作流（10 步，严格按顺序）

步骤 3、5、7 使用 subagent，其余由主 agent 执行。

#### 步骤 0: 环境预检

运行本 skill 的 `scripts/check_env.py`，一次性检查所有依赖（Python 虚拟环境、RUNNINGHUB_API_KEY）：

```bash
python3 <skill-dir>/scripts/check_env.py
```

- 成功（退出码 0）：从输出中捕获 `PYTHON_PATH=<路径>`，**记录该路径用于步骤 7 和 8**，继续
- 失败（退出码 1）：从输出的 `ENV_RESULT=...` JSON 中解析各项检查结果，**向用户展示清晰易懂的错误说明和修复指引**（见下方故障排查指引），终止工作流

**注意：脚本会自动检测并安装可修复的依赖，只将无法自动修复的问题报告给大模型。**

##### 故障排查指引

当环境预检失败时，必须向用户清晰解释原因并给出具体修复步骤。

**API Key 未配置（根据选择的 provider）：**

> 白板动画视频生成需要文生图 API 来调用 AI 模型先生成图片。你需要在 skill 目录下的 `.env` 文件中配置 API Key。
>
> 修复方法：
> 1. 在 `<skill-dir>/.env` 文件中设置 `IMAGE_PROVIDER`（可选: `runninghub` / `openai` / `replicate` / `stability`）
> 2. 配置对应平台的 API Key（参考 `.env.example`）：
>    - **RunningHub**: `RUNNINGHUB_API_KEY`（在 [runninghub.cn](https://www.runninghub.cn/) 获取）
>    - **OpenAI 兼容**: `OPENAI_API_KEY` + `OPENAI_BASE_URL`（兼容 OpenAI Images API 的平台，如 OpenAI 官方、硅基流动、OneAPI/New API 网关；在对应平台获取）
>    - **Replicate**: `REPLICATE_API_TOKEN`（在 [replicate.com](https://replicate.com/account/api-tokens) 获取）
>    - **Stability AI**: `STABILITY_API_KEY`（在 [platform.stability.ai](https://platform.stability.ai/) 获取）
> 3. 如果文件不存在，先 `cp .env.example .env` 创建
> 4. 配置完成后重新运行即可

**Python 依赖安装失败：**

> 白板动画依赖 OpenCV、NumPy、PyAV 等 Python 库来处理视频。自动安装未能成功。
>
> 修复方法：
> 1. 请确认你的 Python 版本为 3.9 或更高版本
> 2. 然后重新运行本工作流，脚本会再次尝试自动安装

多项检查同时失败时，逐条列出每个失败项及对应修复方法。

#### 步骤 1: 确定输出目录

- 如果用户未指定 `outputDir`，则使用 `srtPath` 所在目录作为输出根目录
- 将 `outputDir` 转换为绝对路径

#### 步骤 2: 创建输出目录结构

```bash
python3 <skill-dir>/scripts/workflow_helper.py init-dirs "<outputDir>"
```

输出 JSON 含 `storyboardDir`、`imageDir`、`videoDir` 三个绝对路径，保存备用。

#### 步骤 3: 解析 SRT 生成分镜脚本（subagent）

启动一个 **subagent**，指令为：

> 使用 Read 工具读取文件 `<skill-dir 的绝对路径>/references/storyboard-parser.md`，按照其中的工作流步骤执行。
>
> 输入参数：
> - srtPath = `<srtPath 绝对路径>`
> - projectRoot = `<storyboardDir 绝对路径>`
> - skill-dir = `<skill-dir 绝对路径>`（用于定位脚本）
>
> 完成后返回 storyboard.json 的绝对路径和场景数量。
>
> **注意：主 agent 必须将实际路径值填入指令中，不要传递变量名，subagent 无法访问主 agent 的上下文。**

**必须等待 subagent 完成并获取 storyboard.json 路径后才继续。**

#### 步骤 4: 解析 storyboard 生成图片提示词

```bash
python3 <skill-dir>/scripts/workflow_helper.py gen-prompts "<storyboardJsonPath>"
```

输出一个 JSON 字符串数组，每个元素是带白板风格前缀的图片生成提示词，索引与 scenes 一一对应。

同时从 storyboard.json 中提取每个 scene 的 `duration` 值（毫秒），按顺序记录为数组备用。

#### 步骤 5: 批量生成白板图片（subagent）

启动一个 **subagent**，指令为：

> 使用 Read 工具读取文件 `<skill-dir 的绝对路径>/references/image-generator.md`，按照其中的工作流步骤执行。
>
> 使用批量模式，将以下 JSON 字符串数组作为 prompt 参数传入：
> `<步骤4输出的提示词JSON数组的实际内容>`
>
> 参数：
> - skill-dir = `<skill-dir 绝对路径>`
> - 输出目录 = `<imageDir 绝对路径>`
> - 宽高比 = "16:9"
>
> **注意：主 agent 必须将实际提示词内容和路径值填入指令中，不要传递变量名。**
>
> **重要：** 返回所有生成图片的路径列表，顺序必须与提示词数组顺序一致。

**必须等待 subagent 完成并获取所有图片路径后才继续。**

#### 步骤 6: 校验图片顺序

确认步骤 5 返回的图片路径数组长度与 storyboard 的 scenes 数量一致，顺序正确（第 i 张图片对应第 i 个 scene）。

#### 步骤 7: 批量生成白板动画视频片段（subagent）

启动一个 **subagent**，指令为：

> **跳过环境预检**（主 agent 已确认环境就绪），直接运行批量生成脚本：
>
> ```
> <PYTHON_PATH 的实际值> <skill-dir 的绝对路径>/scripts/batch_generate.py \
>   --images <imagePaths[0]> <imagePaths[1]> ... \
>   --durations <durations[0]> <durations[1]> ... \
>   --output-dir <videoDir 绝对路径>
> ```
>
> **主 agent 必须将 `PYTHON_PATH` 和 skill-dir 的实际绝对路径填入指令中。**
>
> 参数：
> - `--images`：按分镜顺序排列的图片路径列表（空格分隔）
> - `--durations`：与图片一一对应的时长列表（毫秒）
> - `--output-dir`：`<videoDir 绝对路径>`
>
> **重要：** 完成后，收集 `<videoDir>` 目录下所有生成的视频文件路径，按文件名排序，返回完整的视频路径列表。顺序必须与输入图片顺序一致。

**必须等待 subagent 完成并获取所有视频路径后才继续。**

#### 步骤 8: 合并视频片段

**必须使用步骤 0 获取的 `PYTHON_PATH`**（PyAV 依赖在虚拟环境中）：

```bash
<PYTHON_PATH> <skill-dir>/scripts/workflow_helper.py merge-videos "<outputDir>" <videoPath1> <videoPath2> ...
```

输出 JSON 含 `mergedVideo`（合并后的视频绝对路径）、`totalSegments`、`sizeMB`。

#### 步骤 9: 输出结果

```json
{
  "mergedVideo": "/path/to/output/whiteboard_20260329_120000.mp4",
  "videoSegments": [
    "/path/to/video/vid_20260329_120000_h264.mp4",
    "/path/to/video/vid_20260329_120010_h264.mp4"
  ],
  "totalSegments": 2,
  "sizeMB": 15.3,
  "outputDir": "/path/to/output"
}
```

---

## 批量动画模式：多张图片 → 白板动画

当用户提供多张图片（图片路径数组）和对应的时长数组时使用。

### 第一步：准备环境

```bash
python <skill-dir>/scripts/setup_env.py --check
```

- 成功（退出码 0）：最后一行输出 `PYTHON_PATH=<路径>`，**捕获该路径**
- 失败（退出码 1）：运行完整安装：

```bash
python <skill-dir>/scripts/setup_env.py
```

### 第二步：校验输入

从用户请求中获取：
- **图片路径数组**：多张图片的路径列表（必填）
- **时长数组**：与图片一一对应的时长列表（毫秒，必填）

**必须满足**：两个数组长度相同、每张图片存在、每个时长为正整数。

### 第三步：运行批量生成脚本

```bash
<PYTHON_PATH> <skill-dir>/scripts/batch_generate.py \
  --images /path/to/img1.png /path/to/img2.png /path/to/img3.png \
  --durations 10000 15000 8000 \
  [--output-dir ./output] [--no-hand]
```

脚本串行调用单张生成脚本，每完成一个打印进度。单个失败不影响后续任务。

### 第四步：返回结果

告知用户：总共生成多少个视频、成功几个失败几个、输出目录路径、失败项列表。

---

## 单图动画模式：一张图片 → 白板动画

### 第一步：准备环境

与批量模式相同，先运行 `setup_env.py` 获取 `PYTHON_PATH`。

### 第二步：确认输入图片

从用户请求中获取图片路径，确认文件存在。支持格式：PNG、JPG、JPEG、BMP、TIFF。白色或浅色背景效果最佳。

### 第三步：确定参数

| 参数 | 标志 | 默认值 | 说明 |
|------|------|--------|------|
| 图片路径 | 位置参数（必填） | -- | 输入的彩色图片路径 |
| 输出目录 | `--output-dir` | `./output` | 视频输出目录 |
| 时长 | `--duration` | `10000` | 视频总时长（毫秒） |
| 无手部 | `--no-hand` | 默认显示手 | 禁用手部覆盖效果 |

### 第四步：运行生成脚本

```bash
<PYTHON_PATH> <skill-dir>/scripts/generate_whiteboard.py <图片路径> [--output-dir <目录>] [--duration <毫秒>] [--no-hand]
```

### 第五步：返回结果

脚本会将最终视频路径打印到 stdout，将该路径告知用户。输出文件命名格式：`vid_YYYYMMDD_HHMMSS_h264.mp4`。

---

## 关键约束

- 完整模式的步骤 0 必须在任何工作开始前执行，步骤 0 获取的 `PYTHON_PATH` 必须传递给步骤 7 的 subagent，**也用于步骤 8 的视频合并**
- 步骤 3、5、7 必须使用 subagent 执行，主 agent 等待结果
- 图片和视频的顺序必须与 storyboard 的 scenes 顺序严格对应
- duration 贯穿全链路使用毫秒，从 storyboard 到 batch_generate.py 再到 generate_whiteboard.py 统一为毫秒
- 完整模式仅在需要文生图时才需要 `RUNNINGHUB_API_KEY`；单图/批量动画模式只需 Python 虚拟环境（OpenCV/NumPy/PyAV），不需要 API Key

## 故障排除

- **`ModuleNotFoundError`**：重新运行 `setup_env.py` 确保依赖完整安装
- **虚拟环境创建失败**：确认系统已安装 Python 3.9+，且 `python3` 命令可用
- **批量模式单个任务失败**：不影响后续任务继续执行，最终汇总会列出所有失败项

## Resources

### references/

- `storyboard-parser.md` — SRT 分镜解析工作流指令，由完整模式步骤 3 的 subagent 读取执行
- `image-generator.md` — Banana2 图片生成工作流指令，由完整模式步骤 5 的 subagent 读取执行

### scripts/

- `check_env.py` — 一次性环境预检（Python 虚拟环境 + API Key），自动安装可修复的依赖
- `setup_env.py` — Python 虚拟环境创建与依赖安装（opencv/numpy/av）
- `generate_whiteboard.py` — 核心白板动画生成（OpenCV 线稿绘制 + 上色 + 手部覆盖）
- `batch_generate.py` — 批量调用单张生成，串行处理多张图片
- `workflow_helper.py` — init-dirs（创建目录）、gen-prompts（生成提示词）、merge-videos（合并视频）
- `generate-storyboard.py` — 解析 SRT + groups.json 生成 storyboard.json
- `generate-image.py` — Banana2 模型文生图，支持单张和批量并发模式
- `banana_prompt_template.py` — 白板风格提示词模板

### assets/

- `drawing-hand.png` — 手部覆盖效果素材
