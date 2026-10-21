"""적용 부품 — 파트명 · 제품 · 부품코드 · 사업부 · 출처의 줄(ADR 0064, 2026-10-21).

사용자 보고: 재료의 「적용 제품 · 파트」 가 칩 스무 개까지라 부품 50개를 담을 수 없었고, 어느
제품의
어느 파트인지 · 부품코드 · 사업부를 적을 자리가 없었다. BOM 에서 오는 것은 이 넷이 한 줄이다.

**조용히 틀리는 자리를 먼저 본다** — 예전 칸(`applied_parts`)으로 저장할 때 BOM 에서 온 줄이
지워지면
아무 오류 없이 부품코드가 사라진다. BOM 의 재질이 엉뚱한 재료에 붙으면 그 부품은 다른 재료의
것이 된다.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.models import MaterialPart
from app.modules.vocabulary import services as vocabulary_services
from app.modules.vocabulary.models import Vocabulary, VocabularyTerm
from app.modules.workbench.models import BomAlias
from app.shared.text import compare_key


def _material(client: TestClient, headers: dict[str, str], **over: Any) -> dict[str, Any]:
    made = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"G{uuid.uuid4().hex[:6]}",
            "spec_thickness": 1.0,
            **over,
        },
        headers=headers,
    )
    assert made.status_code == 201, made.text
    return dict(made.json())


def _add(
    client: TestClient,
    headers: dict[str, str],
    material_id: str,
    lines: list[dict[str, Any]],
    **kw: Any,
) -> Any:
    return client.post(
        f"/api/materials/{material_id}/parts", json={"lines": lines, **kw}, headers=headers
    )


def _member(client: TestClient, admin_headers: dict[str, str]) -> dict[str, str]:
    """다른 부서 사람 — 자료 관리자가 아니다."""
    made = client.post(
        "/api/workspaces",
        json={"name": "부품 시험 부서", "slug": "parts-b"},
        headers=admin_headers,
    )
    assert made.status_code == 201, made.text
    account = client.post(
        "/api/accounts",
        json={
            "email": "parts@b.com",
            "display_name": "보라",
            "workspace_slug": "parts-b",
            "role": "member",
        },
        headers=admin_headers,
    )
    assert account.status_code in (200, 201), account.text
    token = client.post(
        "/api/auth/login",
        json={"email": "parts@b.com", "password": account.json()["temporary_password"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _term(db: Session, slug: str, value: str) -> VocabularyTerm:
    axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == slug))
    assert axis is not None
    term = db.scalar(
        select(VocabularyTerm).where(
            VocabularyTerm.vocabulary_id == axis.id,
            VocabularyTerm.normalized == compare_key(value),
        )
    )
    assert term is not None, f"{slug}:{value}"
    db.refresh(term)
    return term


class Test줄_넣기:
    def test_미리보기가_기본이고_같은_줄_빈_줄을_가린다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material = _material(client, admin_headers)
        lines = [
            {
                "part": "도어 이너",
                "product": "냉장고 A",
                "part_code": "P-100",
                "division": "가전",
            },
            {
                "part": "도어 아우터",
                "product": "냉장고 A",
                "part_code": "P-101",
                "division": "가전",
            },
            {
                "part": "도어 이너",
                "product": "냉장고 A",
                "part_code": "P-100",
                "division": "가전",
            },
            {"note": "빈 줄"},
        ]
        preview = _add(client, admin_headers, material["id"], lines)
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert (body["applied"], body["new"], body["exists"], body["errors"]) == (
            False,
            2,
            1,
            1,
        )
        assert (
            db.scalar(
                select(MaterialPart).where(
                    MaterialPart.material_id == uuid.UUID(material["id"])
                )
            )
            is None
        )

        made = _add(
            client,
            admin_headers,
            material["id"],
            lines,
            dry_run=False,
            source_ref="냉장고 A BOM",
        )
        assert made.status_code == 200, made.text
        assert made.json()["new"] == 2
        page = client.get(
            f"/api/materials/{material['id']}/parts", headers=admin_headers
        ).json()
        assert [
            (one["part"], one["part_code"], one["division"], one["source"])
            for one in page["items"]
        ] == [
            ("도어 이너", "P-100", "가전", "manual"),
            ("도어 아우터", "P-101", "가전", "manual"),
        ]
        assert page["items"][0]["source_ref"] == "냉장고 A BOM"
        # 재료 응답의 이름 목록은 줄에서 뽑는다 — 같은 제품은 한 번.
        detail = client.get(f"/api/materials/{material['id']}", headers=admin_headers).json()
        assert detail["applied_parts"] == ["도어 이너", "도어 아우터"]
        assert detail["applied_products"] == ["냉장고 A"]
        assert detail["part_count"] == 2
        # 기준정보를 거친다 — 쓰는 수가 오른다.
        assert _term(db, "part", "도어 이너").usage_count == 1
        assert _term(db, "division", "가전").usage_count == 2

        # 같은 줄을 다시 넣으면(같은 BOM 을 두 번) 이미 있다고 말하고 안 넣는다.
        again = _add(client, admin_headers, material["id"], lines[:1], dry_run=False)
        assert again.json()["exists"] == 1 and again.json()["new"] == 0

    def test_부품_50개를_담고_쪽으로_찾고_거른다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """사용자 보고의 자리 — 예전 칩은 스물에서 막혔다."""
        material = _material(client, admin_headers)
        lines = [
            {
                "part": f"파트 {index:02d}",
                "product": "세탁기" if index % 2 else "건조기",
                "part_code": f"WM-{index:04d}",
                "division": "가전" if index < 40 else "전장",
            }
            for index in range(50)
        ]
        made = _add(client, admin_headers, material["id"], lines, dry_run=False)
        assert made.json()["new"] == 50
        url = f"/api/materials/{material['id']}/parts"
        last = client.get(
            url, params={"limit": 20, "offset": 40}, headers=admin_headers
        ).json()
        assert last["total"] == 50 and len(last["items"]) == 10
        assert last["items"][0]["part"] == "파트 40"
        assert {(one["value"], one["count"]) for one in last["divisions"]} == {
            ("가전", 40),
            ("전장", 10),
        }
        car = client.get(url, params={"division": "전장"}, headers=admin_headers).json()
        assert car["total"] == 10
        coded = client.get(url, params={"q": "WM-0007"}, headers=admin_headers).json()
        assert [one["part"] for one in coded["items"]] == ["파트 07"]
        # 부품코드로 재료를 찾는다 — BOM 을 들고 「이 품번 무슨 재료지」.
        found = client.get(
            "/api/materials", params={"q": "WM-0031"}, headers=admin_headers
        ).json()
        assert material["id"] in {one["id"] for one in found["items"]}
        # 상세 조건의 「용도」 칸도 같은 규칙이다 — 칸마다 찾는 범위가 다르면 어느 쪽을
        # 믿을지 모른다.
        for word in ("WM-0031", "세탁기"):
            used = client.get("/api/materials", params={"use": word}, headers=admin_headers)
            assert [one["id"] for one in used.json()["items"]] == [material["id"]], word

    def test_고치기는_보낸_칸만_같은_줄이_되면_막는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material = _material(client, admin_headers)
        _add(
            client,
            admin_headers,
            material["id"],
            [
                {"part": "범퍼", "part_code": "B-1", "division": "자동차"},
                {"part": "범퍼", "part_code": "B-2", "division": "자동차"},
            ],
            dry_run=False,
        )
        rows = client.get(
            f"/api/materials/{material['id']}/parts", headers=admin_headers
        ).json()["items"]
        first = rows[0]["id"]
        changed = client.patch(
            f"/api/materials/{material['id']}/parts/{first}",
            json={"division": None, "note": "사업부 미정"},
            headers=admin_headers,
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["division"] is None and changed.json()["part_code"] == "B-1"
        assert _term(db, "division", "자동차").usage_count == 1
        clash = client.patch(
            f"/api/materials/{material['id']}/parts/{rows[1]['id']}",
            json={"part_code": "B-1", "division": None},
            headers=admin_headers,
        )
        assert clash.status_code == 409, clash.text

        removed = client.post(
            f"/api/materials/{material['id']}/parts/remove",
            json={"ids": [first]},
            headers=admin_headers,
        )
        assert removed.json()["removed"] == 1
        assert _term(db, "part", "범퍼").usage_count == 1


class Test예전_칸:
    def test_예전_칸으로_저장하면_이름만_있는_줄만_갈아_끼운다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """BOM 에서 온 줄(부품코드 · 제품)은 칩 편집 한 번에 사라지면 안 된다."""
        material = _material(client, admin_headers, applied_parts=["이너", "아우터"])
        assert material["applied_parts"] == ["이너", "아우터"]
        _add(
            client,
            admin_headers,
            material["id"],
            [{"part": "이너", "product": "도어", "part_code": "D-1"}],
            dry_run=False,
        )
        edited = client.patch(
            f"/api/materials/{material['id']}",
            json={"applied_parts": ["아우터", "힌지"]},
            headers=admin_headers,
        )
        assert edited.status_code == 200, edited.text
        rows = client.get(
            f"/api/materials/{material['id']}/parts", headers=admin_headers
        ).json()
        kept = {(one["part"], one["part_code"]) for one in rows["items"]}
        assert ("이너", "D-1") in kept, "BOM 줄이 칩 편집으로 지워졌다"
        assert ("이너", None) not in kept
        assert {("아우터", None), ("힌지", None)} <= kept
        assert set(edited.json()["applied_parts"]) == {"이너", "아우터", "힌지"}

    def test_남은_이름의_줄은_출처를_지키고_비고가_있는_줄은_안_지운다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """지우고 다시 만들면 BOM 에서 온 줄이 「직접 입력」 이 되고, 비고가 사라진다."""
        material = _material(client, admin_headers)
        _add(
            client,
            admin_headers,
            material["id"],
            [{"part": "힌지"}, {"part": "가스켓", "note": "2열만"}],
            dry_run=False,
            source="bom",
            source_ref="모델 Y BOM",
        )
        edited = client.patch(
            f"/api/materials/{material['id']}",
            json={"applied_parts": ["힌지"]},
            headers=admin_headers,
        )
        assert edited.status_code == 200, edited.text
        rows = client.get(
            f"/api/materials/{material['id']}/parts", headers=admin_headers
        ).json()["items"]
        assert {
            (one["part"], one["source"], one["source_ref"], one["note"]) for one in rows
        } == {
            ("힌지", "bom", "모델 Y BOM", None),
            ("가스켓", "bom", "모델 Y BOM", "2열만"),
        }


class Test권한:
    def test_남의_재료에는_못_넣고_보기는_한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        material = _material(client, admin_headers)
        plain = _member(client, admin_headers)
        refused = _add(client, plain, material["id"], [{"part": "x"}], dry_run=False)
        assert refused.status_code == 403, refused.text
        assert (
            client.get(f"/api/materials/{material['id']}/parts", headers=plain).status_code
            == 200
        )


class TestBOM:
    def test_재질로_재료를_찾아_재료마다_넣고_못_찾은_것은_남긴다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        exact = _material(client, admin_headers, grade="SECC")
        twin_a = _material(client, admin_headers, grade="SGCC", details="A")
        twin_b = _material(client, admin_headers, grade="SGCC", details="B")
        remembered = _material(client, admin_headers)
        db.add(
            BomAlias(
                normalized=compare_key("냉연 0.8T"),
                query="냉연 0.8T",
                material_id=uuid.UUID(remembered["id"]),
            )
        )
        db.commit()
        rows = [
            {"material": exact["record_name"], "part": "베이스", "part_code": "C-1"},
            {"material": "냉연 0.8T", "part": "커버", "part_code": "C-2"},
            {"material": "SGCC", "part": "브래킷", "part_code": "C-3"},
            {"material": "없는 재질", "part": "나사", "part_code": "C-4"},
            {"material": exact["record_name"], "part": "", "part_code": ""},
        ]
        preview = client.post(
            "/api/materials/parts/bom",
            json={"rows": rows, "division": "가전", "source_ref": "모델 X BOM"},
            headers=admin_headers,
        )
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["counts"] == {"new": 2, "ambiguous": 1, "unmatched": 1, "error": 1}
        ambiguous = next(one for one in body["rows"] if one["status"] == "ambiguous")
        assert {one["id"] for one in ambiguous["candidates"]} == {twin_a["id"], twin_b["id"]}
        assert db.scalar(select(MaterialPart)) is None, "미리보기는 안 쓴다"

        done = client.post(
            "/api/materials/parts/bom",
            json={
                "rows": rows,
                "division": "가전",
                "source_ref": "모델 X BOM",
                "choices": {"SGCC": twin_b["id"]},
                "dry_run": False,
            },
            headers=admin_headers,
        )
        assert done.status_code == 200, done.text
        assert done.json()["counts"]["new"] == 3
        assert {one["id"] for one in done.json()["materials"]} == {
            exact["id"],
            remembered["id"],
            twin_b["id"],
        }
        got = client.get(f"/api/materials/{twin_b['id']}/parts", headers=admin_headers).json()
        assert [
            (one["part"], one["division"], one["source"], one["source_ref"])
            for one in got["items"]
        ] == [("브래킷", "가전", "bom", "모델 X BOM")]
        assert (
            client.get(f"/api/materials/{twin_a['id']}/parts", headers=admin_headers).json()[
                "total"
            ]
            == 0
        )

    def test_고칠_수_없는_재료의_줄은_남기고_나머지는_넣는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        others = _material(client, admin_headers, grade="SPCC")
        plain = _member(client, admin_headers)
        # 새 Grade 값은 자료 관리자만 세운다 — 있는 값을 고르게 둔다.
        vocabulary_services.resolve_or_create(
            db, vocabulary_services.get_vocabulary(db, "grade"), "SPHC", created_by_id=None
        )
        db.commit()
        mine = client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "SPHC",
                "spec_thickness": 2.0,
            },
            headers=plain,
        )
        assert mine.status_code == 201, mine.text
        done = client.post(
            "/api/materials/parts/bom",
            json={
                "rows": [
                    {"material": others["record_name"], "part": "프레임"},
                    {"material": mine.json()["record_name"], "part": "프레임"},
                ],
                "dry_run": False,
            },
            headers=plain,
        )
        assert done.status_code == 200, done.text
        assert done.json()["counts"] == {"blocked": 1, "new": 1}


class Test기준정보:
    def test_이름을_고치거나_합치면_줄도_따라온다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material = _material(client, admin_headers)
        _add(
            client,
            admin_headers,
            material["id"],
            [
                {"part": "도어 힌지", "division": "가전사업부"},
                {"part": "도어힌지 ", "part_code": "H-2"},
            ],
            dry_run=False,
        )
        term = _term(db, "part", "도어 힌지")
        vocabulary_services.rename(db, term, "도어 힌지(상)")
        db.commit()
        rows = client.get(
            f"/api/materials/{material['id']}/parts", headers=admin_headers
        ).json()
        assert "도어 힌지(상)" in {one["part"] for one in rows["items"]}
        division = _term(db, "division", "가전사업부")
        target = vocabulary_services.resolve_or_create(
            db, vocabulary_services.get_vocabulary(db, "division"), "가전", created_by_id=None
        )
        assert target is not None
        vocabulary_services.merge(db, division, target)
        db.commit()
        rows = client.get(
            f"/api/materials/{material['id']}/parts", headers=admin_headers
        ).json()
        assert {one["division"] for one in rows["items"]} == {"가전", None}
