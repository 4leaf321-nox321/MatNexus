"""프로파일이 가리킬 수 있는 **칸 목록**이 프론트와 서버에서 갈리면 실패한다.

편집 화면의 ⑤ 에서 「시험 칸에 채움」·「어느 재료·시료·시편인지」 를 고를 때,
드롭다운의 항목은 프론트가 들고 있고 **거절 판정은 서버가 한다.**

  - 서버에 있는 칸이 프론트에 없으면 **화면에서 고를 수 없다.** 오류가 아니라
    '목록에 없음' 이라 원인을 찾기 어렵다 — `angular_frequency` 때 실제로
    겪은 종류의 고장이다(`test_frontend_units.py`).
  - 프론트에만 있는 칸을 고르면 저장이 422 로 거절된다. 이쪽은 시끄러워서
    낫지만, 사람이 화면에서 막히는 것은 마찬가지다.

이 표는 **값**이라 OpenAPI 생성 대상이 아니다. 그래서 검사로 묶는다.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.modules.tests.schemas import (
    IDENTITY_FIELDS,
    MATERIAL_FIELDS,
    RECORD_FIELDS,
    SAMPLE_FIELDS,
    SPECIMEN_FIELDS,
)

EDITOR = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "src"
    / "modules"
    / "tests"
    / "FormatProfileEditorPage.tsx"
)

_ENTRY = re.compile(r"^\s*([A-Za-z_]+):\s*'([^']*)'", re.MULTILINE)


def _table(name: str) -> dict[str, str]:
    text = EDITOR.read_text(encoding="utf-8")
    block = re.search(
        rf"const {name}: Record<string, string> = \{{(.*?)\n\}}", text, re.DOTALL
    )
    assert block, f"{EDITOR.name} 에서 {name} 을 찾지 못했습니다."
    return dict(_ENTRY.findall(block.group(1)))


def test_시험_칸_목록이_서버와_같다() -> None:
    assert _table("RECORD_FIELD_LABEL") == RECORD_FIELDS


def test_식별자_목록이_서버와_같다() -> None:
    assert _table("IDENTITY_FIELD_LABEL") == IDENTITY_FIELDS


def test_재료_속성_목록이_서버와_같다() -> None:
    assert _table("MATERIAL_FIELD_LABEL") == MATERIAL_FIELDS


def test_시료_속성_목록이_서버와_같다() -> None:
    assert _table("SAMPLE_FIELD_LABEL") == SAMPLE_FIELDS


def test_시편_속성_목록이_서버와_같다() -> None:
    assert _table("SPECIMEN_FIELD_LABEL") == SPECIMEN_FIELDS


def test_메모는_파일이_못_채운다() -> None:
    """메모는 사람이 쓰는 자리다. 파일이 거기에 무언가 적으면 사람이 쓴 것과
    구별이 안 되고, 그러면 그 칸의 뜻이 없어진다."""
    assert "note" not in RECORD_FIELDS


def test_열쇠는_한_군데에만_있다() -> None:
    """**실사용에서 걸렸다** — *"재료 속성을 선택하면 그 안에 grade 가 없어"*.

    없는 것이 맞다. `grade` 는 **채우는 값이 아니라 고르는 값**이다 — 이관은
    파일이 `SPCC` 라고 하면 그 grade 인 재료를 찾고, 없으면 그 이름으로 만든다.
    속성 쪽에 또 두면 같은 값을 두 군데서 정하게 되고, 둘이 어긋날 때(짚기는
    `SPCC`, 속성은 `SGCC`) 어느 쪽이 이겨야 하는지 답이 없다.

    게다가 `grade` 는 **재료 이름의 일부**다(ADR 0004). 이미 있는 재료의 grade 를
    파일이 덮으면 그건 값 채우기가 아니라 이름 바꾸기이고, 그러면 그 아래 시료·
    시편·시험 이름이 전부 다시 계산된다. 시험 파일 하나가 할 일이 아니다.

    화면은 이 사실을 **목적지 목록 안에서 짚어 준다**(`KEY_ELSEWHERE`). 여기서는
    두 목록이 실제로 안 겹치는지만 본다 — 겹치는 순간 위 설명이 거짓이 된다.
    """
    assert "grade" not in MATERIAL_FIELDS
    assert "lot_no" not in SAMPLE_FIELDS
    # 반대로 **열쇠 쪽에는 있어야 한다.** 양쪽에 다 없으면 파일이 그 값을 아예
    # 못 준다 — 그러면 이관이 재료를 못 찾는다.
    assert "material_grade" in IDENTITY_FIELDS
    assert "sample_lot_no" in IDENTITY_FIELDS


#: 폼이 안 그려도 되는 칸과 그 사유. **비면 그 칸은 화면에서 영영 못 채운다.**
_EQUIPMENT_NOT_IN_FORM = {
    # 유형이 선언한 칸의 값. 폼이 따로 그린다(`fields` 절) — Draft 에 안 든다.
    "attributes": "장비 유형이 정한 칸을 따로 그린다",
    # 문헌 장비 카탈로그의 모델을 잇는 자리. **아직 화면이 없다** — 측정법 쪽에서
    # 고르는 흐름이 필요하고, 그 화면이 생기면 여기서 지운다.
    "instrument_id": "문헌 모델 잇기 화면이 아직 없다",
}


def test_장비_폼이_서버_칸을_다_그린다() -> None:
    """**실측(2026-09-08): 시험실 칸이 화면에서 사라져 있었다.**

    조직 칸을 부서 피커로 바꾸면서 잘라낸 범위가 넓어 옆의 시험실까지 지웠는데,
    빌드도 시험도 통과했다 — 서버는 그 칸을 여전히 받고, 화면만 조용히 못 채우는
    상태였다. 폐기일도 같은 이유로 처음부터 빠져 있었다.

    **칸이 없어진 것은 오류로 안 보인다.** 그래서 기계가 센다.
    """
    from app.modules.equipment.schemas import EquipmentUnitCreate

    form = (
        Path(__file__).resolve().parents[3]
        / "frontend"
        / "src"
        / "modules"
        / "equipment"
        / "EquipmentForm.tsx"
    ).read_text(encoding="utf-8")
    draft = re.search(r"interface Draft \{(.*?)\n\}", form, re.S)
    assert draft is not None, "EquipmentForm 의 Draft 를 찾지 못했습니다."
    drawn = {one.group(1) for one in re.finditer(r"^\s+(\w+):", draft.group(1), re.M)}

    missing = set(EquipmentUnitCreate.model_fields) - drawn - set(_EQUIPMENT_NOT_IN_FORM)
    assert not missing, (
        f"서버는 받는데 폼이 안 그리는 칸: {sorted(missing)}. "
        "화면에서 채울 수 없는 칸이 생겼습니다 — 그릴 자리를 넣거나, "
        "안 그릴 이유를 `_EQUIPMENT_NOT_IN_FORM` 에 적으세요."
    )
