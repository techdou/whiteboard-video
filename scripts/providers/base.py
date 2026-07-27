"""
Provider 统一接口定义

每个 provider 模块必须实现:
    generate(prompt, aspect_ratio, output_dir, api_config) -> GeneratedImage

GeneratedImage 封装生成结果，可以是本地文件路径或待下载的 URL。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class GeneratedImage:
    """统一的图片生成结果。"""
    url: Optional[str] = None        # 远程图片 URL（需要下载时设置）
    image_bytes: Optional[bytes] = None  # 图片二进制数据（base64 解码后或直接二进制）
    filepath: Optional[str] = None   # 已下载到本地时的路径
    ext: str = "png"                 # 图片扩展名
    metadata: Optional[dict] = None  # 平台特有的元信息（seed、model 等）

    @property
    def has_bytes(self) -> bool:
        return self.image_bytes is not None

    @property
    def has_url(self) -> bool:
        return self.url is not None


def validate_config(required_keys: list[str], config: dict, provider_name: str):
    """校验 provider 配置是否包含所有必需的 key，缺失则抛 ValueError。"""
    missing = [k for k in required_keys if not config.get(k)]
    if missing:
        raise ValueError(
            f"[{provider_name}] 缺少必需配置: {', '.join(missing)}。"
            f"请在 skill 根目录的 .env 文件中配置对应的环境变量。"
        )
