"""头像文件校验、重编码与本地存储，不接受客户端文件路径。"""

import re
from collections.abc import AsyncIterable
from io import BytesIO
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from app.config.settings import Settings
from app.core.exceptions import AppError

AVATAR_PREFIX = "/api/v1/users/avatars/"
AVATAR_FILENAME = re.compile(r"[a-f0-9]{32}\.png")


class AvatarStore:
    """将有限大小的静态图片转换成无元数据PNG，文件名由服务端生成。"""

    def __init__(self, settings: Settings):
        self.root = settings.avatar_storage_dir.resolve()
        self.max_bytes = settings.avatar_max_bytes
        self.max_pixels = settings.avatar_max_pixels
        self.size = settings.avatar_size

    async def save(self, stream: AsyncIterable[bytes]) -> str:
        """边读边限制请求大小，再在线程池内执行图片处理和磁盘写入。"""
        content = bytearray()
        async for chunk in stream:
            if len(content) + len(chunk) > self.max_bytes:
                raise AppError(413, "AVATAR_TOO_LARGE", "头像文件超过大小限制")
            content.extend(chunk)
        return await run_in_threadpool(self._save, bytes(content))

    def _save(self, content: bytes) -> str:
        try:
            with Image.open(BytesIO(content), formats=("PNG", "JPEG", "WEBP")) as source:
                if (
                    source.width * source.height > self.max_pixels
                    or getattr(source, "n_frames", 1) != 1
                ):
                    raise ValueError("invalid dimensions or animation")
                source.verify()
            with Image.open(BytesIO(content), formats=("PNG", "JPEG", "WEBP")) as source:
                source.load()
                thumbnail = ImageOps.fit(
                    ImageOps.exif_transpose(source).convert("RGBA"), (self.size, self.size)
                )
                clean = Image.new("RGBA", thumbnail.size)
                clean.paste(thumbnail)
                output = BytesIO()
                clean.save(output, format="PNG")
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            SyntaxError,
            Image.DecompressionBombError,
        ) as error:
            raise AppError(
                422, "INVALID_AVATAR", "请选择有效的静态 PNG、JPEG 或 WebP 图片"
            ) from error
        self.root.mkdir(parents=True, exist_ok=True)
        filename = uuid4().hex + ".png"
        path = self.root / filename
        with path.open("xb") as target:
            try:
                target.write(output.getvalue())
            except BaseException:
                target.close()
                path.unlink(missing_ok=True)
                raise
        return AVATAR_PREFIX + filename

    async def read(self, filename: str) -> bytes:
        """公开读取随机文件名头像，拒绝路径穿越和符号链接。"""
        if not AVATAR_FILENAME.fullmatch(filename):
            raise AppError(404, "AVATAR_NOT_FOUND", "头像不存在")
        path = self.root / filename
        try:
            if path.is_symlink():
                raise FileNotFoundError
            return await run_in_threadpool(path.read_bytes)
        except (FileNotFoundError, IsADirectoryError) as error:
            raise AppError(404, "AVATAR_NOT_FOUND", "头像不存在") from error

    async def remove(self, url: str | None) -> None:
        """仅清理本模块生成的文件，不处理旧外链或客户端路径。"""
        if not url or not url.startswith(AVATAR_PREFIX):
            return
        filename = url.removeprefix(AVATAR_PREFIX)
        if AVATAR_FILENAME.fullmatch(filename):
            await run_in_threadpool((self.root / filename).unlink, missing_ok=True)
