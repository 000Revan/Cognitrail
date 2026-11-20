from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=3)
def load_prompt(name: str) -> str:
    """按代码指定的名称读取提示词，不接收用户提供的路径。"""
    return (Path(__file__).parent / f"{name}.md").read_text(encoding="utf-8")
