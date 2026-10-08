"""기본 형식 정의판의 씨앗 — **배포가 넣되, 사람이 손댄 것은 안 덮는다**(ADR 0047).

정의판은 코드판이 틀렸을 때 대신 켜는 비상용이다. 운영에 넣는 길이 없어서, 사용 중단을
걸면 형식이 메뉴에서 빠지기만 하고 대신 쓸 것이 없었다(2026-09-30). 무는 자리의 순서는
가이드 씨앗과 같다 — 「씨앗이 들어간다」 보다 **「사람이 고치거나 켠 판이 말없이 덮이지
않는다」** 가 먼저다. 켜 둔 판은 지금 누군가 그것으로 덱을 내고 있다.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.fitting.models import ExportProfile
from app.shared.deckmap import all_renderers

BACKEND = Path(__file__).resolve().parent.parent.parent
REAL = json.loads(
    (BACKEND / "seeds" / "export-profiles" / "기본-형식-정의.json").read_text(encoding="utf-8")
)
#: 씨앗의 정의판 수 — 코드판마다 하나(중립 JSON · Zemax AGF 빼고). 2026-10-02 ECAE · 광학
#: 여섯을 더해 50 → 56, 2026-10-08 OptiStruct 속도 의존 · LS-DYNA ICFD 점도 · OptiStruct ·
#: Nastran 피로 · OptiStruct Hill48 로 61. 코드판을 더하면 정의판도 더하고 여기를 고친다.
SEEDED = 61


@pytest.fixture
def importer() -> Any:
    """`scripts/` 는 패키지가 아니라 경로로 읽는다."""
    path = BACKEND / "scripts" / "import_export_profiles.py"
    spec = importlib.util.spec_from_file_location("_script_import_export_profiles", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def one(key: str = "abaqus_def", **over: Any) -> dict[str, Any]:
    """진짜 씨앗의 한 벌 — 정의로 읽히는 것이어야 한다."""
    item = copy.deepcopy(next(p for p in REAL["profiles"] if p["key"] == key))
    item.update(over)
    return {"profiles": [item]}


def renewed(seed: dict[str, Any]) -> dict[str, Any]:
    """저장소에서 코드판을 고쳐 씨앗도 바뀐 것 — 정의의 첫 글자 줄을 바꾼다."""
    changed = copy.deepcopy(seed)
    changed["profiles"][0]["description"] = "코드판을 고쳐 씨앗도 바꿨다"
    return changed


def row(db: Session, key: str = "abaqus_def") -> ExportProfile:
    found = db.scalar(
        select(ExportProfile).where(
            ExportProfile.key == key, ExportProfile.deleted_at.is_(None)
        )
    )
    assert found is not None
    db.refresh(found)
    return found


def _put(
    client: TestClient, headers: dict[str, str], found: ExportProfile, **over: Any
) -> None:
    body = {
        "label": found.label,
        "description": found.description,
        "definition": found.definition,
        "is_active": found.is_active,
        **over,
    }
    response = client.put(
        f"/api/fitting/export-profiles/{found.key}", json=body, headers=headers
    )
    assert response.status_code == 200, response.text


class Test없는_것은_꺼진_채_넣는다:
    def test_전부_꺼진_채_들어가고_메뉴는_그대로다(self, db: Session, importer: Any) -> None:
        said = importer.load(db, REAL)

        assert len(said["new"]) == len(REAL["profiles"]) == SEEDED
        rows = list(db.scalars(select(ExportProfile)))
        assert all(not one.is_active for one in rows), (
            "켜진 채 들어갔다 — 메뉴에 같은 형식이 둘 선다"
        )
        assert all(one.created_by_id is None and one.seed_digest for one in rows)
        # **카드의 내보내기 메뉴는 그대로다** — 꺼진 정의는 형식 목록에 안 선다.
        assert not [one.key for one in all_renderers(db) if one.key.endswith("_def")]

    def test_두_번_돌려도_아무것도_안_바꾼다(self, db: Session, importer: Any) -> None:
        importer.load(db, REAL)
        before = {one.key: one.updated_at for one in db.scalars(select(ExportProfile))}

        said = importer.load(db, REAL)

        assert not said["new"] and not said["renew"] and len(said["same"]) == SEEDED
        after = {one.key: one.updated_at for one in db.scalars(select(ExportProfile))}
        assert after == before

    def test_씨앗이_깨졌으면_안_넣는다(self, db: Session, importer: Any) -> None:
        broken = one(definition={"lines": [{"value": "없는.값"}], "needs": "틀린 모양"})

        said = importer.load(db, broken)

        assert said["broken"] == ["abaqus_def"]
        assert db.scalar(select(ExportProfile.id)) is None


class Test손_안_댄_것만_씨앗을_따른다:
    """코드판을 고치면(예: Abaqus 점탄성의 MODULI) 정의판도 함께 고쳐진 씨앗이 온다."""

    def test_아무도_안_만진_정의판은_새_씨앗대로(self, db: Session, importer: Any) -> None:
        importer.load(db, one())

        said = importer.load(db, renewed(one()))

        assert said["renew"] == ["abaqus_def"]
        assert row(db).description == "코드판을 고쳐 씨앗도 바꿨다"
        assert not row(db).is_active

    def test_화면에서_고친_정의판은_안_덮는다(
        self, db: Session, importer: Any, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        importer.load(db, one())
        _put(client, admin_headers, row(db), description="운영에서 고친 판")

        said = importer.load(db, renewed(one()))

        assert said["guarded"] == ["abaqus_def"]
        assert row(db).description == "운영에서 고친 판", "사람이 고친 판이 덮였다"

    def test_켠_정의판은_안_덮는다(
        self, db: Session, importer: Any, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """켜 둔 판으로 누군가 덱을 내고 있다 — 배포 한 번에 바뀌면 이유를 모른다."""
        importer.load(db, one())
        _put(client, admin_headers, row(db), is_active=True)

        said = importer.load(db, renewed(one()))

        assert said["guarded"] == ["abaqus_def"]
        assert row(db).description != "코드판을 고쳐 씨앗도 바꿨다"
        assert row(db).is_active

    def test_지운_정의판은_되살리지_않는다(
        self, db: Session, importer: Any, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        importer.load(db, one())
        gone = client.delete("/api/fitting/export-profiles/abaqus_def", headers=admin_headers)
        assert gone.status_code == 204, gone.text

        said = importer.load(db, one())

        assert said["deleted"] == ["abaqus_def"]
        assert (
            db.scalar(
                select(ExportProfile).where(
                    ExportProfile.key == "abaqus_def", ExportProfile.deleted_at.is_(None)
                )
            )
            is None
        )


class Test손으로_들여온_판:
    """ADR 0047 전에는 「불러오기」 로 손으로 넣었다 — 지문이 없다."""

    def _imported(
        self, client: TestClient, headers: dict[str, str], item: dict[str, Any]
    ) -> None:
        response = client.post(
            "/api/fitting/export-profiles",
            json={
                "key": item["key"],
                "label": item["label"],
                "description": item.get("description"),
                "definition": item["definition"],
                "is_active": False,
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text

    def test_씨앗과_같으면_받아들여_다음부터_따라간다(
        self, db: Session, importer: Any, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        self._imported(client, admin_headers, one()["profiles"][0])

        said = importer.load(db, one())

        assert said["adopt"] == ["abaqus_def"]
        assert importer.load(db, renewed(one()))["renew"] == ["abaqus_def"]

    def test_옛_판이면_안_덮고_짚는다(
        self, db: Session, importer: Any, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """사람이 들여와 고쳤는지 씨앗의 옛 판인지 가를 수 없다 — 사람이 정한다."""
        old = one(description="손으로 들여온 옛 판")["profiles"][0]
        self._imported(client, admin_headers, old)

        said = importer.load(db, one())

        assert said["guarded"] == ["abaqus_def"]
        assert row(db).description == "손으로 들여온 옛 판"
        assert "안 덮음 1" in importer.summary(said, dry=False)


class Test보기는_쓰지_않는다:
    def test_check_는_판정만_한다(self, db: Session, importer: Any) -> None:
        said = importer.plan(db, REAL["profiles"])

        assert len(said["new"]) == SEEDED
        assert db.scalar(select(ExportProfile.id)) is None, "check 가 넣었다"
