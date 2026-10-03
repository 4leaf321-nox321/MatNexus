"""배포 뒤 도는 점검 스크립트(`scripts/check_fixes_20261004.py`)가 **흔적을 실제로 잡는가.**

운영에서 「0건」 이 나오면 사람은 손볼 것이 없다고 읽는다. 스크립트가 빈 손으로 0 을 내면
그 말이 거짓이 된다 — 그래서 흔적을 일부러 심고 잡는지 본다. 원본 덮어쓰기(③)와 마스터커브(①)는
그 기능의 시험(`test_run_edit` · `test_viscoelastic_api`)에서 같은 식으로 본다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.catalog.models import CatalogDefinition, CatalogMaterial, CatalogValue
from app.modules.materials.models import Material
from app.modules.processing.models import ProcessingRecipe
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestType

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def check_script() -> Any:
    """스크립트를 모듈로 읽는다 — `scripts` 는 꾸러미가 아니다."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "check_fixes_20261004", SCRIPTS / "check_fixes_20261004.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_환산이_빠진_불확도를_잡고_제대로_된_것은_안_잡는다(db: Session) -> None:
    for key in ("mechanical.check_e", "mechanical.check_g"):
        db.add(
            CatalogDefinition(
                key=key, domain="mechanical", name=key, si_unit="Pa", value_type="numeric"
            )
        )
    owner = CatalogMaterial(name="점검용 문헌 재료", category="metal")
    db.add(owner)
    db.flush()
    db.add_all(
        [
            # 9.4 ± 0.2 GPa 가 환산 없이 담긴 모양.
            CatalogValue(
                material_id=owner.id,
                property_key="mechanical.check_e",
                value_num=9.4e9,
                unit="Pa",
                uncertainty=0.2,
                quality_tier=2,
            ),
            CatalogValue(
                material_id=owner.id,
                property_key="mechanical.check_g",
                value_num=3.6e9,
                unit="Pa",
                uncertainty=0.1e9,
                quality_tier=2,
            ),
        ]
    )
    db.commit()
    found = check_script().catalog_uncertainty(db)
    assert len(found) == 1 and "check_e" in found[0], found


def test_빈_칸이_0_이_된_점과_통째로_같은_재료를_잡는다(db: Session) -> None:
    row = {
        "item": "탄성계수",
        "points": [{"value_si": 2.0e11, "value": 2.0e11, "temperature_k": None}],
        "source": "datasheet",
        "reference": "시트 A",
    }
    zero = {**row, "item": "푸아송비", "points": [{"value_si": 0, "value": 0}]}
    db.add_all(
        [
            Material(
                record_name="점검 A",
                family="Metal",
                category="Steel",
                grade="CHK-A",
                declared_properties=[row, zero],
            ),
            # B 와 C 는 줄이 통째로 같다 — 다른 재료의 줄이 들어간 모양.
            Material(
                record_name="점검 B",
                family="Metal",
                category="Steel",
                grade="CHK-B",
                declared_properties=[row],
            ),
            Material(
                record_name="점검 C",
                family="Metal",
                category="Steel",
                grade="CHK-C",
                declared_properties=[{**row, "approval": {"by": "누군가"}}],
            ),
        ]
    )
    db.commit()
    script = check_script()
    zeros = script.declared_zeros(db)
    assert len(zeros) == 1 and "푸아송비" in zeros[0], zeros
    copies, count = script.declared_copies(db)
    assert count == 2, copies
    assert "점검 B" in copies[0] and "점검 C" in copies[0]


def test_단위_있는_열로_적은_구간을_잡는다(db: Session) -> None:
    """변위(m) 열로 25 를 적은 구간 자르기 — 25 mm 를 뜻했다면 25 m 로 잘렸다."""
    ensure_builtin_test_types(db)
    tensile = db.scalar(select(TestType).where(TestType.key == "tensile"))
    assert tensile is not None
    db.add_all(
        [
            ProcessingRecipe(
                key="check_crop_m",
                label="변위로 자른 레시피",
                test_type_id=tensile.id,
                steps=[
                    {"plugin": "curve.crop", "options": {"x": "displacement", "start": 25}},
                ],
            ),
            # 무차원 열(변형률)은 단위 문제가 없다 — 안 잡는다.
            ProcessingRecipe(
                key="check_crop_strain",
                label="변형률로 자른 레시피",
                test_type_id=tensile.id,
                steps=[
                    {
                        "plugin": "curve.crop",
                        "options": {"x": "strain_engineering", "start": 0.01, "end": 0.2},
                    },
                ],
            ),
        ]
    )
    db.commit()
    rows, count = check_script().unit_column_ranges(db)
    assert count == 1, rows
    assert "변위로 자른 레시피" in rows[0] and "25000 mm" in rows[0], rows


def test_스크립트는_아무것도_안_쓴다(db: Session) -> None:
    """`main` 이 읽기 전용 트랜잭션으로 연다 — 쓰기가 끼면 DB 가 거절한다."""
    text = (SCRIPTS / "check_fixes_20261004.py").read_text(encoding="utf-8")
    assert "SET TRANSACTION READ ONLY" in text
    assert ".commit()" not in text
