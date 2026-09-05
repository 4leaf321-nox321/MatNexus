"""재료 고유 번호 — `materials.code` (M-000123).

`record_name` 은 기준정보 개명이 연쇄로 바꾸지만 code 는 안 바뀌는 손잡이다.
채번은 DB(시퀀스 server default)가 한다 — 만드는 코드가 몰라도 붙고, 그래서
서비스 코드를 안 고치고도 모든 생성 경로(화면·이관·스크립트)가 번호를 받는다.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.materials.models import Material

CODE_SHAPE = re.compile(r"^M-\d{6}$")


def make_material(db: Session, record_name: str) -> Material:
    material = Material(record_name=record_name, family="Steel", category="냉연", grade="SECC")
    db.add(material)
    db.flush()
    db.refresh(material)
    return material


class Test채번:
    def test_만들면_번호가_붙고_서로_다르며_형식이_맞다(self, db: Session) -> None:
        first = make_material(db, "SECC_A_1.0")
        second = make_material(db, "SECC_B_1.0")
        assert CODE_SHAPE.fullmatch(first.code), first.code
        assert CODE_SHAPE.fullmatch(second.code), second.code
        assert first.code != second.code
        # 나중 재료가 큰 번호 — 채번은 앞으로만 간다(재사용 없음).
        assert int(second.code[2:]) > int(first.code[2:])

    def test_같은_번호는_두_번_못_쓴다(self, db: Session) -> None:
        first = make_material(db, "SECC_C_1.0")
        clash = Material(
            record_name="SECC_D_1.0",
            family="Steel",
            category="냉연",
            grade="SECC",
            code=first.code,
        )
        db.add(clash)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_지워도_번호는_돌아오지_않는다(self, db: Session) -> None:
        """소프트 삭제된 재료의 번호가 다음 재료에게 가면, 옛 문서의 지칭이
        엉뚱한 재료를 가리키게 된다."""
        from datetime import UTC, datetime

        gone = make_material(db, "SECC_E_1.0")
        gone_code = gone.code
        gone.deleted_at = datetime.now(UTC)
        db.flush()
        after = make_material(db, "SECC_F_1.0")
        assert after.code != gone_code
        assert int(after.code[2:]) > int(gone_code[2:])
