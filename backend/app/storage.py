"""本地文件存储抽象。

当前实现写入本地目录；数据库只保存 storage_key 与元数据，绝不保存文件二进制。
将来切换对象存储时，只需替换本模块实现。
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# 注意：不要在模块导入时依赖 app.config，否则存储层会被迫绑定 pydantic-settings。
# 只有未显式传入 root 时才在运行时读取配置。


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    size_bytes: int
    sha256: str


class LocalStorage:
    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            from app.config import get_settings

            root = get_settings().storage_root
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, storage_key: str) -> Path:
        # storage_key 由服务端生成，不接受客户端提供的路径片段。
        candidate = (self.root / storage_key).resolve()
        root = self.root.resolve()
        if root not in candidate.parents and candidate != root:
            raise ValueError("非法的存储键")
        return candidate

    def save(self, content: bytes, *, suffix: str = "") -> StoredFile:
        digest = hashlib.sha256(content).hexdigest()
        key = f"{uuid.uuid4().hex}{suffix}"
        target = self._path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return StoredFile(storage_key=key, size_bytes=len(content), sha256=digest)

    def read(self, storage_key: str) -> bytes:
        return self._path_for(storage_key).read_bytes()

    def exists(self, storage_key: str) -> bool:
        return self._path_for(storage_key).is_file()

    def delete(self, storage_key: str) -> None:
        path = self._path_for(storage_key)
        if path.is_file():
            path.unlink()


@lru_cache(maxsize=1)
def get_storage() -> LocalStorage:
    return LocalStorage()
