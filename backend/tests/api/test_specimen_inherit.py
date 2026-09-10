"""시편이 규격에서 치수를 물려받는다 — **잰 값은 안 덮는다.**

시편 41개 중 치수가 있는 것이 3개뿐이라 처리가 첫 단계에서 막혔다. 규격서에는
`ASTM E8 subsize = 게이지 길이 25 mm` 라고 적혀 있는데 그 값이 시스템 어디에도
없어서 사람이 시편마다 옮겨 적어야 했다.

규칙은 하나다.

    시편에 값이 있다   그 값을 쓴다        ← 사람이 실제로 잰 것
    시편이 비었다      규격의 공칭을 쓴다

**규격이 잰 값을 조용히 덮으면 안 된다.** 덮어쓰면 "이 두께가 실측인가 규격값
인가" 를 나중에 답할 수 없다.

그리고 단면적은 **규격이 고른 식**으로 낸다. 12.5 mm 환봉은 122.7 mm² 인데
평판 식으로는 그 값이 안 나온다 — 그런데 그 수로 나눈 응력은 오류 없이
그럴듯하다.
"""

from __future__ import annotations

import math
import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.models import Material, Sample, Specimen
from app.modules.vocabulary.definitions import (
    ensure_builtin_axis_fields,
    ensure_builtin_specimen_categories,
    ensure_builtin_vocabularies,
)
from app.modules.vocabulary.models import Vocabulary, VocabularyTerm
from app.modules.workspaces.models import Workspace
from app.shared import specimen_size
from app.shared.text import clean, compare_key


@pytest.fixture
def seeded(db: Session) -> None:
    ensure_builtin_vocabularies(db)
    ensure_builtin_axis_fields(db)
    ensure_builtin_specimen_categories(db)
    db.commit()


def axis_of(db: Session, slug: str) -> Vocabulary:
    found = db.scalar(select(Vocabulary).where(Vocabulary.slug == slug))
    assert found is not None, f"{slug} 축이 없습니다"
    return found


def term(
    db: Session, slug: str, value: str, parent: VocabularyTerm | None = None
) -> VocabularyTerm:
    row = VocabularyTerm(
        vocabulary_id=axis_of(db, slug).id,
        value=clean(value),
        normalized=compare_key(value),
        parent_term_id=parent.id if parent else None,
    )
    db.add(row)
    db.flush()
    return row


def category(db: Session, value: str) -> VocabularyTerm:
    found = db.scalar(
        select(VocabularyTerm).where(
            VocabularyTerm.vocabulary_id == axis_of(db, "specimen_category").id,
            VocabularyTerm.normalized == compare_key(value),
        )
    )
    assert found is not None, f"기본 분류에 {value} 가 없습니다"
    return found


def standard(
    db: Session,
    value: str,
    *,
    parent: VocabularyTerm,
    attributes: dict[str, float],
    extra_fields: list[dict[str, Any]] | None = None,
    cross_section: str | None = None,
) -> VocabularyTerm:
    row = term(db, "specimen_standard", value, parent)
    row.attributes = attributes
    row.extra_fields = extra_fields or []
    row.cross_section = cross_section
    db.flush()
    return row


def specimen_on(
    db: Session, std: VocabularyTerm, *, spec_thickness: float | None = None, **fields: Any
) -> Specimen:
    """규격 하나를 가리키는 시편.

    `spec_thickness` 를 주면 **재료가 스펙 두께를 갖는다**(판재). 안 주면 예전처럼
    재료·시료는 만들기만 하고 쓰지 않는다.
    """
    tag = uuid.uuid4().hex[:6]
    workspace = Workspace(slug=f"w{tag}", name=f"부서 {tag}")
    db.add(workspace)
    db.flush()

    material = Material(
        owner_workspace_id=workspace.id,
        record_name=f"M-{tag}",
        family="Metal",
        category="Steel",
        grade=f"G{tag}",
        spec_thickness_m=spec_thickness,
    )
    db.add(material)
    db.flush()
    sample = Sample(
        workspace_id=workspace.id,
        material_id=material.id,
        seq_no=1,
        record_name=f"S-{tag}",
    )
    db.add(sample)
    db.flush()
    row = Specimen(
        workspace_id=workspace.id,
        sample_id=sample.id,
        seq_no=1,
        orientation="MD",
        record_name=f"SP-{tag}",
        standard_term_id=std.id,
        **fields,
    )
    db.add(row)
    db.flush()
    return row


class TestInherit:
    def test_빈_시편은_규격의_공칭을_쓴다(self, db: Session, seeded: None) -> None:
        """**이 파일의 이유.** 시편마다 규격서를 옮겨 적지 않아도 된다."""
        std = standard(
            db,
            "ASTM E8 subsize",
            parent=category(db, "인장"),
            attributes={"gauge_length": 0.025},
        )
        sizes = specimen_size.sizes_of(db, specimen_on(db, std))
        assert sizes.get("gauge_length") == pytest.approx(0.025)
        assert [item.source for item in sizes.items if item.key == "gauge_length"] == [
            "nominal"
        ]

    def test_잰_값이_이긴다(self, db: Session, seeded: None) -> None:
        """**규격이 실측을 덮으면 안 된다.** 덮으면 그 값이 무엇이었는지 모른다."""
        std = standard(
            db, "ASTM E8", parent=category(db, "인장"), attributes={"gauge_length": 0.05}
        )
        row = specimen_on(db, std, dimensions={"gauge_length": 0.0498})
        sizes = specimen_size.sizes_of(db, row)
        assert sizes.get("gauge_length") == pytest.approx(0.0498)
        assert [item.source for item in sizes.items if item.key == "gauge_length"] == [
            "measured"
        ]

    def test_옛_컬럼도_실측으로_읽는다(self, db: Session, seeded: None) -> None:
        """아직 그쪽으로만 채워진 시편이 있다(ADR 0010 Expand)."""
        std = standard(
            db, "JIS 5호", parent=category(db, "인장"), attributes={"gauge_length": 0.05}
        )
        row = specimen_on(db, std, gauge_length_m=0.0501)
        assert specimen_size.sizes_of(db, row).get("gauge_length") == pytest.approx(0.0501)

    def test_규격이_없으면_잰_것만_있다(self, db: Session, seeded: None) -> None:
        std = standard(db, "이름만", parent=category(db, "인장"), attributes={})
        row = specimen_on(db, std, dimensions={"width": 0.0125})
        sizes = specimen_size.sizes_of(db, row)
        assert sizes.get("width") == pytest.approx(0.0125)
        assert sizes.get("gauge_length") is None


class TestArea:
    def _round(self, db: Session) -> VocabularyTerm:
        return standard(
            db,
            "ASTM E8 R1",
            parent=category(db, "인장"),
            attributes={"gauge_length": 0.05, "diameter": 0.0125},
            extra_fields=[
                {
                    "key": "diameter",
                    "label": "직경",
                    "dimension": "length",
                    "si_unit": "m",
                    "is_required": True,
                    "help": None,
                }
            ],
            cross_section="circle",
        )

    def test_환봉은_원_식으로_낸다(self, db: Session, seeded: None) -> None:
        """12.5 mm 환봉 = 122.7 mm². 평판 식으로는 나올 수 없는 값이다."""
        area = specimen_size.area_of(db, specimen_on(db, self._round(db)))
        assert area == pytest.approx(math.pi * 0.00625**2, rel=1e-12)

    def test_잰_직경이_이긴다(self, db: Session, seeded: None) -> None:
        row = specimen_on(db, self._round(db), dimensions={"diameter": 0.01248})
        area = specimen_size.area_of(db, row)
        assert area == pytest.approx(math.pi * (0.01248 / 2) ** 2, rel=1e-12)

    def test_식을_안_고르면_옛_규칙으로_돈다(self, db: Session, seeded: None) -> None:
        """**지금까지 이렇게 돌던 시편이 갑자기 못 돌면 안 된다.**"""
        std = standard(
            db, "옛 규격", parent=category(db, "인장"), attributes={"gauge_length": 0.05}
        )
        row = specimen_on(db, std, width_m=0.0125, thickness_m=0.001)
        assert specimen_size.area_of(db, row) == pytest.approx(0.0125 * 0.001)

    def test_값이_모자라면_안_만든다(self, db: Session, seeded: None) -> None:
        """**어림값을 만들지 않는다.** 단면적이 틀리면 응력이 자릿수째로 어긋난다."""
        std = standard(
            db,
            "직경 없는 환봉",
            parent=category(db, "인장"),
            attributes={"gauge_length": 0.05},
            extra_fields=[
                {
                    "key": "diameter",
                    "label": "직경",
                    "dimension": "length",
                    "si_unit": "m",
                    "is_required": False,
                    "help": None,
                }
            ],
            cross_section="circle",
        )
        assert specimen_size.area_of(db, specimen_on(db, std)) is None


class Test재료_스펙_두께:
    """**판재는 이름이 곧 두께다** — 그런데 그 값이 시편 치수에 안 들어왔다.

    VOC(2026-09-11): *"실두께 미기입 시 에러인데, 스펙두께가 있음에도 발생한다."*
    화면에는 `SECC_-_0.8` 이라고 쓰여 있는데 「두께가 없습니다」 가 뜬다.

    규격은 판재 두께를 정하지 않는다 — 그건 소재 쪽 값이라 규격 공칭으로는
    영영 안 채워진다. 그래서 **재료의 스펙 두께를 마지막 자리에** 둔다.

    실측(개발 DB, 2026-09-10): 시편 244개 중 145개가 두께를 안 적었고, 그중
    131개의 재료는 스펙 두께를 갖고 있었다.
    """

    def _flat(self, db: Session) -> VocabularyTerm:
        """폭은 규격이 정하고 두께는 안 정하는 평판 — 판재 인장이 이 모양이다."""
        return standard(
            db,
            "평판 (두께는 소재가 정한다)",
            parent=category(db, "인장"),
            attributes={"gauge_length": 0.05, "width": 0.0125},
            cross_section="rectangle",
        )

    def test_재료_스펙_두께로_단면적을_낸다(self, db: Session, seeded: None) -> None:
        row = specimen_on(db, self._flat(db), spec_thickness=0.0008)
        assert specimen_size.area_of(db, row) == pytest.approx(0.0125 * 0.0008)

    def test_어디서_온_값인지_말한다(self, db: Session, seeded: None) -> None:
        """**조용히 쓰면 안 된다.** 압연 공차가 있어 0.8t 가 0.786 으로 나온다 —
        1~2% 면 응력이 그만큼 어긋나므로, 사람이 그것을 알고 잰 값을 넣을 수
        있어야 한다."""
        sizes = specimen_size.sizes_of(
            db, specimen_on(db, self._flat(db), spec_thickness=0.0008)
        )
        found = {one.key: one.source for one in sizes.items}
        assert found["thickness"] == "material"
        assert found["width"] == "nominal"

    def test_잰_값이_이긴다(self, db: Session, seeded: None) -> None:
        row = specimen_on(
            db, self._flat(db), spec_thickness=0.0008, dimensions={"thickness": 0.000786}
        )
        sizes = specimen_size.sizes_of(db, row)
        assert sizes.get("thickness") == pytest.approx(0.000786)
        assert {one.key: one.source for one in sizes.items}["thickness"] == "measured"

    def test_규격_공칭이_재료보다_앞선다(self, db: Session, seeded: None) -> None:
        """규격이 두께를 정해 뒀다면 그것이 이 시편의 두께다 — 소재 두께가 아니라."""
        std = standard(
            db,
            "두께를 정한 평판",
            parent=category(db, "인장"),
            attributes={"gauge_length": 0.05, "width": 0.0125, "thickness": 0.002},
            cross_section="rectangle",
        )
        sizes = specimen_size.sizes_of(db, specimen_on(db, std, spec_thickness=0.0008))
        assert sizes.get("thickness") == pytest.approx(0.002)
        assert {one.key: one.source for one in sizes.items}["thickness"] == "nominal"

    def test_두께_없는_재료는_그대로_못_낸다(self, db: Session, seeded: None) -> None:
        """**없는 것을 지어내지 않는다.** 스펙 두께가 없으면 전과 같이 못 낸다."""
        got = specimen_size.area_detail(db, specimen_on(db, self._flat(db)))
        assert got.value is None
        assert "두께" in (got.problem or "")

    def test_규격이_없어도_물려받는다(self, db: Session, seeded: None) -> None:
        """**규격이 없으면 칸도 없다** — 거기서 빼면 물려받을 길이 영영 없다.

        실측(개발 DB, 2026-09-11): 시편 244개 중 177개가 규격을 안 정했고 그중
        120개가 두께를 안 적었다. 규격이 선언한 칸만 채우면 이 쪽은 하나도 안
        풀린다.
        """
        tag = uuid.uuid4().hex[:6]
        workspace = Workspace(slug=f"w{tag}", name=f"부서 {tag}")
        db.add(workspace)
        db.flush()
        material = Material(
            owner_workspace_id=workspace.id,
            record_name=f"M-{tag}",
            family="Metal",
            category="Steel",
            grade=f"G{tag}",
            spec_thickness_m=0.0008,
        )
        db.add(material)
        db.flush()
        sample = Sample(
            workspace_id=workspace.id,
            material_id=material.id,
            seq_no=1,
            record_name=f"S-{tag}",
        )
        db.add(sample)
        db.flush()
        row = Specimen(
            workspace_id=workspace.id,
            sample_id=sample.id,
            seq_no=1,
            orientation="MD",
            record_name=f"SP-{tag}",
            width_m=0.0125,
        )
        db.add(row)
        db.flush()

        # 규격이 없으면 옛 규칙(폭 곱하기 두께)으로 돈다 — 그 두께가 재료에서 온다.
        assert specimen_size.area_of(db, row) == pytest.approx(0.0125 * 0.0008)

    def test_못_낼_때_어디서_온_값인지_말한다(self, db: Session, seeded: None) -> None:
        """**「이 시편에 있는 값」 이라고만 적으면 자기가 적은 줄 안다.**

        VOC 가 나온 자리가 여기다 — 재료에 0.8t 라고 적어 뒀는데 화면은 두께를
        모르는 듯 말하니, 무엇을 채워야 하는지가 안 보였다.
        """
        std = standard(
            db,
            "폭 없는 평판",
            parent=category(db, "인장"),
            attributes={"gauge_length": 0.05},
        )
        got = specimen_size.area_detail(db, specimen_on(db, std, spec_thickness=0.0008))
        assert got.value is None
        assert "(재료 스펙)" in (got.problem or "")

    def test_시험이_잰_값이_가장_세다(self, db: Session, seeded: None) -> None:
        """같은 시편을 여러 번 재면 **그 시험이 잰 값**이 맞다(`run_measured`)."""
        row = specimen_on(db, self._flat(db), spec_thickness=0.0008)
        sizes = specimen_size.sizes_of(db, row, {"thickness": 0.00079})
        assert sizes.get("thickness") == pytest.approx(0.00079)
