"""
Provider 注册表与统一入口。

用法:
    from providers import get_provider
    provider = get_provider("openai")
    result = provider.generate(prompt, aspect_ratio, output_dir, config)
"""

from importlib import import_module

# provider 名 → 模块路径映射
_PROVIDER_REGISTRY = {
    "runninghub": "providers.runninghub",
    "openai": "providers.openai_provider",
    "replicate": "providers.replicate_provider",
    "stability": "providers.stability_provider",
}

# 每个 provider 需要的环境变量
_PROVIDER_ENV_KEYS = {
    "runninghub": ["RUNNINGHUB_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "replicate": ["REPLICATE_API_TOKEN"],
    "stability": ["STABILITY_API_KEY"],
}

# 每个 provider 的默认模型
_PROVIDER_DEFAULT_MODEL = {
    "runninghub": "",  # RunningHub 用固定 endpoint，无独立 model 字段
    "openai": "gpt-image-1",
    "replicate": "black-forest-labs/flux-1.1-pro-ultra",
    "stability": "",  # Stability Core endpoint 固定
}


def list_providers() -> list[str]:
    """返回所有已注册的 provider 名。"""
    return list(_PROVIDER_REGISTRY.keys())


def get_provider(name: str):
    """根据名称加载 provider 模块。模块必须实现 generate() 函数。"""
    name = name.lower().strip()
    if name not in _PROVIDER_REGISTRY:
        raise ValueError(
            f"未知 provider: '{name}'。可选: {', '.join(list_providers())}"
        )
    module = import_module(_PROVIDER_REGISTRY[name])
    return module


def get_required_env_keys(name: str) -> list[str]:
    """返回该 provider 需要的环境变量列表。"""
    name = name.lower().strip()
    return _PROVIDER_ENV_KEYS.get(name, [])


def get_default_model(name: str) -> str:
    """返回该 provider 的默认模型名。"""
    name = name.lower().strip()
    return _PROVIDER_DEFAULT_MODEL.get(name, "")
