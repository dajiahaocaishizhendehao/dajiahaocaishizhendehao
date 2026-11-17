"""本地文件存储测试（仅标准库，真实读写临时目录）。

    python -m unittest discover -s backend/tests -t backend -p "test_storage.py"
"""

from __future__ import annotations

import hashlib
import pathlib
import unittest

from app.storage import LocalStorage

# 临时文件放在仓库内已存在的可写目录下：系统临时目录与新建目录
# 在某些沙箱里会拒绝写入/删除，导致测试因环境原因失败。
_VAR_ROOT = pathlib.Path(__file__).resolve().parent.parent / "var" / "storage"


class LocalStorageTest(unittest.TestCase):
    def setUp(self) -> None:
        _VAR_ROOT.mkdir(parents=True, exist_ok=True)
        self.storage = LocalStorage(_VAR_ROOT)
        self.created: list[str] = []

    def tearDown(self) -> None:
        for key in self.created:
            self.storage.delete(key)

    def _save(self, content: bytes, suffix: str = ".bin"):
        stored = self.storage.save(content, suffix=suffix)
        self.created.append(stored.storage_key)
        return stored

    def test_save_and_read_roundtrip(self) -> None:
        content = "示例材料内容".encode("utf-8")
        stored = self._save(content, suffix=".pdf")
        self.assertEqual(stored.size_bytes, len(content))
        self.assertEqual(stored.sha256, hashlib.sha256(content).hexdigest())
        self.assertTrue(stored.storage_key.endswith(".pdf"))
        self.assertEqual(self.storage.read(stored.storage_key), content)
        self.assertTrue(self.storage.exists(stored.storage_key))

    def test_storage_key_is_unpredictable(self) -> None:
        first = self._save(b"a", suffix=".pdf").storage_key
        second = self._save(b"a", suffix=".pdf").storage_key
        self.assertNotEqual(first, second, "相同内容也应生成不同对象键")

    def test_delete_is_idempotent(self) -> None:
        key = self._save(b"x", suffix=".txt").storage_key
        self.storage.delete(key)
        self.assertFalse(self.storage.exists(key))
        self.storage.delete(key)  # 再次删除不应抛错

    def test_rejects_path_traversal(self) -> None:
        for evil in ("../escape.txt", "..\\escape.txt", "a/../../b.txt"):
            with self.assertRaises(ValueError):
                self.storage.read(evil)

    def test_empty_content_allowed_at_storage_layer(self) -> None:
        """存储层不负责业务校验，空文件由上传接口按规则拒绝。"""

        stored = self._save(b"", suffix=".pdf")
        self.assertEqual(stored.size_bytes, 0)
        self.assertEqual(self.storage.read(stored.storage_key), b"")


if __name__ == "__main__":
    unittest.main()
