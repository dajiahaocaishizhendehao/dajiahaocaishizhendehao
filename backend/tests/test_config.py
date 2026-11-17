"""配置模块测试（需要 pydantic-settings，不需要数据库）。

    python -m unittest discover -s backend/tests -t backend -p "test_config.py"
"""

from __future__ import annotations

import os
import unittest

try:  # pragma: no cover - 环境相关
    from pydantic import ValidationError
    from pydantic_settings import BaseSettings  # noqa: F401
except ImportError:  # pragma: no cover
    raise unittest.SkipTest("未安装 pydantic-settings，跳过配置测试") from None

from app.config import Settings


class SettingsDefaultTest(unittest.TestCase):
    def test_defaults(self) -> None:
        settings = Settings(_env_file=None)
        self.assertEqual(settings.api_prefix, "/api")
        self.assertEqual(settings.due_soon_days, 30)
        self.assertEqual(settings.max_upload_bytes, 50 * 1024 * 1024)
        self.assertEqual(settings.session_ttl_minutes, 720)
        self.assertIn("application/pdf", settings.allowed_mime_types)
        self.assertFalse(settings.is_production)

    def test_storage_root_under_backend(self) -> None:
        settings = Settings(_env_file=None)
        self.assertTrue(str(settings.storage_root).endswith(os.path.join("var", "storage")))


class SettingsEnvOverrideTest(unittest.TestCase):
    def test_env_overrides_defaults(self) -> None:
        os.environ["DUE_SOON_DAYS"] = "45"
        os.environ["ENVIRONMENT"] = "production"
        try:
            settings = Settings(_env_file=None)
            self.assertEqual(settings.due_soon_days, 45)
            self.assertTrue(settings.is_production)
        finally:
            os.environ.pop("DUE_SOON_DAYS", None)
            os.environ.pop("ENVIRONMENT", None)

    def test_invalid_env_value_rejected(self) -> None:
        os.environ["DUE_SOON_DAYS"] = "not-a-number"
        try:
            with self.assertRaises(ValidationError):
                Settings(_env_file=None)
        finally:
            os.environ.pop("DUE_SOON_DAYS", None)

    def test_environment_variants(self) -> None:
        for value, expected in (("prod", True), ("production", True), ("local", False), ("test", False)):
            os.environ["ENVIRONMENT"] = value
            try:
                self.assertEqual(Settings(_env_file=None).is_production, expected, value)
            finally:
                os.environ.pop("ENVIRONMENT", None)


if __name__ == "__main__":
    unittest.main()
