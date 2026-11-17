"""查询条件与分页逻辑测试（零依赖）。

    python -m unittest discover -s backend/tests -t backend -p "test_query.py"
"""

from __future__ import annotations

import unittest

from app.query import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    normalize_asset_query,
    clamp_pagination,
)


class NormalizeQueryTest(unittest.TestCase):
    def test_trims_and_drops_blank_values(self) -> None:
        query = normalize_asset_query(q="  NOVA  ", ip_type="  ", status_group=None)
        self.assertEqual(query.q, "NOVA")
        self.assertIsNone(query.ip_type)
        self.assertIsNone(query.status_group)

    def test_all_empty(self) -> None:
        query = normalize_asset_query()
        self.assertEqual((query.q, query.ip_type, query.status_group), (None, None, None))

    def test_keeps_project_and_owner_filters(self) -> None:
        query = normalize_asset_query(q="NOVA", ip_type="trademark", project_id="p-1", owner_user_id="u-1")
        self.assertEqual(
            (query.q, query.ip_type, query.project_id, query.owner_user_id),
            ("NOVA", "trademark", "p-1", "u-1"),
        )


class PaginationTest(unittest.TestCase):
    def test_defaults(self) -> None:
        self.assertEqual(clamp_pagination(None, None), (1, DEFAULT_PAGE_SIZE))

    def test_rejects_invalid_values(self) -> None:
        self.assertEqual(clamp_pagination(0, 0), (1, DEFAULT_PAGE_SIZE))
        self.assertEqual(clamp_pagination(-5, -10), (1, DEFAULT_PAGE_SIZE))

    def test_caps_page_size(self) -> None:
        self.assertEqual(clamp_pagination(2, 10_000), (2, MAX_PAGE_SIZE))

    def test_keeps_valid_values(self) -> None:
        self.assertEqual(clamp_pagination(3, 50), (3, 50))


if __name__ == "__main__":
    unittest.main()
