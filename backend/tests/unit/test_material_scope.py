"""재료의 소유 범위와 전역 승격 — 설계가 기대는 제약이 실제로 걸렸는지 본다.

여기서 검사하는 것은 성질 하나다: **승격은 컬럼 하나를 NULL 로 바꾸는 일이고,
그때 하위 데이터는 움직이지 않는다.** 이 성질이 성립하지 않으면 승격이 테이블
이사가 되고, FK·이력·참조가 전부 걸린다.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.materials.models import Material, Sample
from app.modules.workspaces.models import Workspace
from matcore import naming


def _workspace(db: Session, slug: str) -> Workspace:
    workspace = Workspace(slug=slug, name=slug, kind="org")
    db.add(workspace)
    db.flush()
    return workspace


def _material(db: Session, *, workspace_id: uuid.UUID | None, grade: str = "SECC") -> Material:
    material = Material(
        owner_workspace_id=workspace_id,
        record_name=naming.material_name(grade=grade, details="MDOI", thickness_mm=1.0),
        family="Metal",
        category="Steel",
        grade=grade,
        details="MDOI",
        spec_thickness_m=0.001,
        input_units={"spec_thickness": "mm"},
    )
    db.add(material)
    return material


class TestScope:
    def test_부서가_다르면_같은_이름을_쓸_수_있다(self, db: Session) -> None:
        a = _workspace(db, "a")
        b = _workspace(db, "b")
        _material(db, workspace_id=a.id)
        _material(db, workspace_id=b.id)
        db.commit()  # 부서 경계 안에서만 유일하면 된다

    def test_같은_부서에_같은_이름을_두_번_넣을_수_없다(self, db: Session) -> None:
        a = _workspace(db, "a")
        _material(db, workspace_id=a.id)
        _material(db, workspace_id=a.id)
        with pytest.raises(IntegrityError):
            db.commit()

    def test_전역_재료끼리도_같은_이름을_막는다(self, db: Session) -> None:
        """`NULLS NOT DISTINCT` 가 없으면 여기가 조용히 통과한다.

        Postgres 는 기본적으로 NULL != NULL 로 본다. 전역을 NULL 로 표현하면서
        그 옵션을 빠뜨리면, **유니크 제약을 둔 이유가 그대로 사라진다.**
        """
        _material(db, workspace_id=None)
        _material(db, workspace_id=None)
        with pytest.raises(IntegrityError):
            db.commit()


class TestPromotion:
    def test_승계는_UPDATE_한_줄이고_하위는_움직이지_않는다(self, db: Session) -> None:
        a = _workspace(db, "a")
        material = _material(db, workspace_id=a.id)
        db.flush()

        sample = Sample(
            workspace_id=a.id,
            material_id=material.id,
            seq_no=1,
            record_name=naming.sample_name(material=material.record_name, seq_no=1),
        )
        db.add(sample)
        db.commit()

        material.owner_workspace_id = None  # 승격
        db.commit()
        db.refresh(sample)

        assert material.owner_workspace_id is None
        assert sample.material_id == material.id
        assert sample.workspace_id == a.id, "하위는 자기 부서 소속으로 남는다"

    def test_전역_재료_밑에서_부서가_달라도_시료_이름이_겹치지_않는다(
        self, db: Session
    ) -> None:
        """채번을 재료 단위로 하기 때문이다.

        부서 단위로 채번하면 두 부서가 각자 01 을 받아, 전역 재료의 시료 목록에
        같은 이름이 두 개 보인다.
        """
        a = _workspace(db, "a")
        b = _workspace(db, "b")
        material = _material(db, workspace_id=None)
        db.flush()

        names = []
        for index, workspace in enumerate((a, b), start=1):
            sample = Sample(
                workspace_id=workspace.id,
                material_id=material.id,
                seq_no=index,
                record_name=naming.sample_name(material=material.record_name, seq_no=index),
            )
            db.add(sample)
            names.append(sample.record_name)
        db.commit()

        assert names == ["SECC_MDOI_1.0__01", "SECC_MDOI_1.0__02"]
        assert len(set(names)) == 2

    def test_같은_재료에_같은_일련번호를_두_번_쓸_수_없다(self, db: Session) -> None:
        a = _workspace(db, "a")
        material = _material(db, workspace_id=None)
        db.flush()
        for _ in range(2):
            db.add(
                Sample(
                    workspace_id=a.id,
                    material_id=material.id,
                    seq_no=1,
                    record_name="x",
                )
            )
        with pytest.raises(IntegrityError):
            db.commit()
