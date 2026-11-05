"""为本地开发生成签名密钥；保留既有数据库配置，绝不输出密钥。"""

import os
import re
import secrets

from dotenv import dotenv_values

from app.config.settings import BACKEND_ROOT


def main() -> None:
    """已有非空密钥不覆盖，空值才生成并原子替换配置文件。"""
    path = BACKEND_ROOT / ".env"
    existing = dotenv_values(path) if path.exists() else {}
    key = existing.get("JWT_SECRET")
    if key:
        if len(key.encode("utf-8")) < 32:
            raise SystemExit("已有 JWT_SECRET 长度不足，请在本地配置至少 32 字节的随机密钥")
        print("JWT 配置已存在，未修改")
        return
    source = path.read_text(encoding="utf-8") if path.exists() else ""
    assignment = "JWT_SECRET=" + secrets.token_urlsafe(48)
    if re.search(r"(?m)^JWT_SECRET=.*$", source):
        source = re.sub(r"(?m)^JWT_SECRET=.*$", assignment, source)
    else:
        source = source.rstrip() + "\n\n# 本地随机签名密钥，不提交或输出\n" + assignment + "\n"
    temporary = path.with_name(".env.tmp")
    temporary.write_text(source, encoding="utf-8")
    os.replace(temporary, path)
    print("本地 JWT 密钥已配置，原数据库配置保留")


if __name__ == "__main__":
    main()
