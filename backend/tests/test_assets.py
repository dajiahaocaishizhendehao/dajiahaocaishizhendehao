"""知识产权主档测试：类型隔离、名称录入、权限与逻辑删除。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _patent_payload() -> dict:
    return {
        "name": "一种基于边缘计算的设备状态分析方法",
        "ip_type": "patent",
        "status_group": "in_progress",
        "patent": {
            "patent_type": "invention",
            "application_no": "CN-DEMO-10001",
            "application_date": "2025-03-18",
        },
    }


def test_create_patent(client: TestClient, admin_headers) -> None:
    payload = _patent_payload()
    response = client.post("/api/assets", json=payload, headers=admin_headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["ip_type"] == "patent"
    assert body["patent"]["application_no"] == "CN-DEMO-10001"


def test_create_without_internal_number(client: TestClient, admin_headers) -> None:
    first = client.post(
        "/api/assets",
        json={"name": "未填内部编号案件一", "ip_type": "patent"},
        headers=admin_headers,
    )
    second = client.post(
        "/api/assets",
        json={"name": "未填内部编号案件二", "ip_type": "copyright", "copyright": {}},
        headers=admin_headers,
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    # 内部编号字段已彻底删除：响应不再返回，也不再要求唯一。
    assert "asset_no" not in first.json()
    assert "asset_no" not in second.json()


def test_legacy_asset_no_in_payload_is_ignored(client: TestClient, admin_headers) -> None:
    payload = {"asset_no": "OLD-001", "name": "旧调用方案件", "ip_type": "patent"}
    created = client.post("/api/assets", json=payload, headers=admin_headers)
    assert created.status_code == 201, created.text
    assert "asset_no" not in created.json()


def test_reject_cross_type_fields(client: TestClient, admin_headers) -> None:
    payload = _patent_payload()
    payload["trademark"] = {"word_mark": "示例"}
    response = client.post("/api/assets", json=payload, headers=admin_headers)
    assert response.status_code == 422


def test_grant_before_application_rejected(client: TestClient, admin_headers) -> None:
    payload = _patent_payload()
    payload["patent"]["grant_date"] = "2024-01-01"
    response = client.post("/api/assets", json=payload, headers=admin_headers)
    assert response.status_code == 422


def test_viewer_cannot_write(client: TestClient, viewer_headers) -> None:
    response = client.post("/api/assets", json=_patent_payload(), headers=viewer_headers)
    assert response.status_code == 403


def test_logical_delete_hides_asset(client: TestClient, admin_headers) -> None:
    created = client.post("/api/assets", json=_patent_payload(), headers=admin_headers).json()
    assert client.delete(f"/api/assets/{created['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/assets/{created['id']}", headers=admin_headers).status_code == 404
    listing = client.get("/api/assets", headers=admin_headers).json()
    assert listing["total"] == 0


def test_search_and_filter(client: TestClient, admin_headers) -> None:
    client.post("/api/assets", json=_patent_payload(), headers=admin_headers)
    client.post(
        "/api/assets",
        json={
            "name": "NOVA GRID 图形商标",
            "ip_type": "trademark",
            "trademark": {"word_mark": "NOVA GRID", "mark_type": "combined"},
        },
        headers=admin_headers,
    )
    assert client.get("/api/assets?ip_type=trademark", headers=admin_headers).json()["total"] == 1
    assert client.get("/api/assets?q=NOVA", headers=admin_headers).json()["total"] == 1


def test_list_grant_date_uses_patent_grant_date_and_copyright_certificate_date(
    client: TestClient, admin_headers
) -> None:
    patent = _patent_payload()
    patent["status_group"] = "granted"
    patent["patent"]["grant_date"] = "2025-06-01"
    assert client.post("/api/assets", json=patent, headers=admin_headers).status_code == 201
    assert (
        client.post(
            "/api/assets",
            json={
                "name": "有授权公告日的软著",
                "ip_type": "copyright",
                "status_group": "granted",
                "copyright": {"certificate_date": "2025-08-15"},
            },
            headers=admin_headers,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/assets",
            json={"name": "无授权公告日软著", "ip_type": "copyright", "copyright": {}},
            headers=admin_headers,
        ).status_code
        == 201
    )

    items = client.get("/api/assets", headers=admin_headers).json()["items"]
    by_name = {item["name"]: item for item in items}
    assert by_name[patent["name"]]["grant_date"] == "2025-06-01"
    assert by_name["有授权公告日的软著"]["grant_date"] == "2025-08-15"
    assert by_name["无授权公告日软著"]["grant_date"] is None


def test_default_order_ungranted_first_then_grant_date_desc(client: TestClient, admin_headers) -> None:
    def create(name: str, ip_type: str, status_group: str, grant_date: str | None = None) -> None:
        payload: dict = {"name": name, "ip_type": ip_type, "status_group": status_group}
        if ip_type == "patent":
            payload["patent"] = {"patent_type": "invention"}
            if grant_date:
                payload["patent"]["grant_date"] = grant_date
        else:
            payload["copyright"] = {}
            if grant_date:
                payload["copyright"]["certificate_date"] = grant_date
        response = client.post("/api/assets", json=payload, headers=admin_headers)
        assert response.status_code == 201, response.text

    create("办理中案件", "patent", "in_progress")
    create("较早取得专利", "patent", "granted", "2024-05-01")
    create("取得但无授权公告日软著", "copyright", "granted")
    create("较新取得专利", "patent", "granted", "2025-09-01")
    create("居中取得软著", "copyright", "granted", "2025-03-01")

    names = [item["name"] for item in client.get("/api/assets", headers=admin_headers).json()["items"]]
    assert names == [
        "办理中案件",
        "较新取得专利",
        "居中取得软著",
        "较早取得专利",
        "取得但无授权公告日软著",
    ]


def test_grant_date_editable_through_asset_update(client: TestClient, admin_headers) -> None:
    created = client.post("/api/assets", json=_patent_payload(), headers=admin_headers).json()
    response = client.patch(
        f"/api/assets/{created['id']}",
        json={"patent": {"grant_date": "2025-08-20"}},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["patent"]["grant_date"] == "2025-08-20"


def test_publication_and_legal_status_editable_through_asset_update(
    client: TestClient, admin_headers
) -> None:
    created = client.post("/api/assets", json=_patent_payload(), headers=admin_headers).json()
    response = client.patch(
        f"/api/assets/{created['id']}",
        json={
            "patent": {
                "publication_no": "CN-123456-A",
                "publication_date": "2025-07-01",
                "grant_date": "2025-08-20",
                "legal_status": "实质审查中",
            }
        },
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    patent = response.json()["patent"]
    assert patent["publication_no"] == "CN-123456-A"
    assert patent["publication_date"] == "2025-07-01"
    assert patent["grant_date"] == "2025-08-20"
    assert patent["legal_status"] == "实质审查中"


def test_create_copyright_with_certificate_date_and_owner(client: TestClient, admin_headers) -> None:
    party = client.post(
        "/api/parties",
        json={"name": "演示软件权利人", "party_type": "company"},
        headers=admin_headers,
    )
    assert party.status_code == 201, party.text
    party_id = party.json()["id"]

    created = client.post(
        "/api/assets",
        json={
            "name": "演示软件著作权",
            "ip_type": "copyright",
            "status_group": "granted",
            "copyright": {"rights_mode": "原始取得", "certificate_date": "2025-10-01"},
            "parties": [{"party_id": party_id, "role": "copyright_owner", "seq": 0}],
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["docket_no"] is None
    assert body["copyright"]["rights_mode"] == "原始取得"
    assert body["copyright"]["certificate_date"] == "2025-10-01"
    assert [item["name"] for item in body["parties"]] == ["演示软件权利人"]


def test_create_copyright_owner_atomically(client: TestClient, admin_headers) -> None:
    """软著创建用 copyright_owner 内联字段，单次请求内原子创建权利人并关联。"""

    created = client.post(
        "/api/assets",
        json={
            "name": "原子创建软著",
            "ip_type": "copyright",
            "copyright": {"rights_mode": "原始取得"},
            "copyright_owner": {"name": "原子权利人", "party_type": "company"},
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert [item["name"] for item in body["parties"]] == ["原子权利人"]
    assert body["parties"][0]["party_type"] == "company"


def test_update_and_clear_asset_persons(client: TestClient, admin_headers) -> None:
    created = client.post("/api/assets", json=_patent_payload(), headers=admin_headers).json()
    person = client.post(
        "/api/persons",
        json={"name": "演示发明人甲", "person_type": "inventor"},
        headers=admin_headers,
    )
    assert person.status_code == 201, person.text
    person_id = person.json()["id"]

    linked = client.patch(
        f"/api/assets/{created['id']}",
        json={"persons": [{"person_id": person_id, "role": "inventor", "seq": 0}]},
        headers=admin_headers,
    )
    assert linked.status_code == 200, linked.text
    assert [item["name"] for item in linked.json()["persons"]] == ["演示发明人甲"]
    assert linked.json()["persons"][0]["person_type"] == "inventor"

    cleared = client.patch(
        f"/api/assets/{created['id']}",
        json={"persons": []},
        headers=admin_headers,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["persons"] == []
