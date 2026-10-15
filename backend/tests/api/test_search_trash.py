"""전체 검색과 휴지통 — **지움 칸이 없는 것은 부모의 휴지통을 따른다, 시스템 관리자에게도**.

검색의 가시 판정(`graph.visible_ids`)은 시스템 관리자에게 거르기를 통째로 건너뛴다. 시료 ·
시편 · 시험은 제 지움 칸이 있어 검색이 따로 거르지만, 카드 · 받아 온 파라미터 벌 · 처리 결과는
지움 칸이 없어 **휴지통에 든 재료(지운 시험)의 것이 검색에 떴다** — 열면 「찾을 수 없습니다」.
2026-10-16 AI 평가가 카드 번호로 찾다가 처음 드러냈다(카드는 `test_codes.py`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.models import Material, MaterialParameterSet, Sample, Specimen
from app.modules.processing.models import ProcessingResult
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun, TestType
from app.modules.workspaces.models import Workspace


def _found(client: TestClient, headers: dict[str, str], kind: str, q: str) -> list[str]:
    body = client.get("/api/search", params={"q": q}, headers=headers).json()
    return [
        hit["id"] for group in body["groups"] if group["kind"] == kind for hit in group["hits"]
    ]


def _run(db: Session, workspace: Workspace) -> tuple[Material, TestRun]:
    """재료 → 시료 → 시편 → 시험 하나(파싱은 안 한다 — 검색이 보는 것은 줄뿐이다)."""
    ensure_builtin_test_types(db)
    tag = uuid.uuid4().hex[:6].upper()
    material = Material(
        record_name=f"TRASH{tag}_-_-", family="Metal", category="Steel", grade=f"TRASH{tag}"
    )
    db.add(material)
    db.flush()
    sample = Sample(
        workspace_id=workspace.id,
        material_id=material.id,
        seq_no=1,
        record_name=f"{material.record_name}__01",
    )
    db.add(sample)
    db.flush()
    specimen = Specimen(
        workspace_id=workspace.id,
        sample_id=sample.id,
        orientation="MD",
        seq_no=1,
        record_name=f"{sample.record_name}__MD_01",
    )
    db.add(specimen)
    db.flush()
    tensile = db.scalar(select(TestType).where(TestType.key == "tensile"))
    assert tensile is not None
    run = TestRun(
        workspace_id=workspace.id,
        specimen_id=specimen.id,
        test_type_id=tensile.id,
        seq_no=1,
        record_name=f"{specimen.record_name}__TEN_01",
        status="parsed",
    )
    db.add(run)
    db.commit()
    return material, run


def test_지운_시험의_처리_결과는_관리자_검색에도_안_뜬다(
    client: TestClient, admin_headers: dict[str, str], db: Session, workspace: Workspace
) -> None:
    _, run = _run(db, workspace)
    label = f"휴지통점검레시피 {uuid.uuid4().hex[:6]}"
    result = ProcessingResult(
        test_run_id=run.id,
        source_curve_key="raw",
        recipe_label=label,
        steps_snapshot=[],
        stages=[],
        scalars=[],
        storage_path="none",
        row_count=0,
        sha256="0" * 64,
        byte_size=0,
    )
    db.add(result)
    db.commit()
    assert _found(client, admin_headers, "processing_result", label) == [str(result.id)]

    run.deleted_at = datetime.now(UTC)
    db.commit()
    assert _found(client, admin_headers, "processing_result", label) == []


def test_휴지통에_든_재료의_파라미터_벌은_관리자_검색에도_안_뜬다(
    client: TestClient, admin_headers: dict[str, str], db: Session, workspace: Workspace
) -> None:
    material, _ = _run(db, workspace)
    label = f"휴지통점검벌 {uuid.uuid4().hex[:6]}"
    found = MaterialParameterSet(material_id=material.id, model="ogden", label=label)
    db.add(found)
    db.commit()
    assert _found(client, admin_headers, "parameter_set", label) == [str(found.id)]

    material.deleted_at = datetime.now(UTC)
    db.commit()
    assert _found(client, admin_headers, "parameter_set", label) == []
