"""카드 각주 — 출처 설명과 경고를 가른다(`app/shared/card_notes.py`).

문장은 **개발 DB 의 카드 42장에서 실제로 나온 것**이다(2026-10-04). 각주를 쓰는 쪽이 문구를
바꾸면 여기서 먼저 걸린다 — 그러면 표지를 고칠지, 문장을 고칠지 정한다.
"""

from __future__ import annotations

import pytest

from app.shared.card_notes import cautions

#: 값을 그대로 믿으면 안 된다는 말.
CAUTIONS = [
    "밀도: 재료에도 시료에도 밀도가 없습니다.",
    "푸아송비: 재료에 푸아송비가 없습니다 — 인장시험은 이 값을 주지 않습니다.",
    "시험에서 나온 값이 하나도 없습니다 — 재료에 적어 둔 값으로만 만들었습니다.",
    "합성 소성 표 — 실측이 아니다. 모델: elastic + Hollomon hardening (n=0.052)",
    "합성 주의 — 항복·UTS·연신율 스칼라에서 합성한 근사 곡선 — 실측이 아니다.",
    "완화시간 2개가 관측 범위 경계에 붙어 있습니다 — 그만큼은 잰 범위 밖을 외삽한 값입니다.",
    "네킹을 안 자른 곡선이 3건 섞여 있습니다(FLOW0B5A4A_흐름점검_1.0__01__MD_01__TEN_01).",
    "시편 1개의 곡선으로 적합했습니다 — 재료의 대푯값이 아니라 그 시편의 값입니다.",
    "시편 1개('CRVC6F66_T')의 곡선입니다 — 평균이 아니라 그 시편의 값입니다.",
]

#: 값이 어디서 왔는지 적는 말 — 경고가 아니다.
PROVENANCE = [
    "푸아송비: 재료에 적힌 값입니다.",
    "푸아송비: 직접 입력한 값입니다.",
    "시편 2건의 선형 구간 E′ 평균입니다.",
    "밀도: 재료의 공칭값입니다 (7.85e-09 tonne/mm3).",
    "시편 3건을 'pooled' 방법으로 묶어 만들었습니다.",
    "시편 3개의 각 점에서 평균과 흩어짐을 냈습니다 (300점, x 0~0.24714).",
    "합성 입력 항복강도: declared:literature — 금속재료 핸드북 7판 표 3.1",
    "탄성계수: 사람이 적은 값입니다 — 금속재료 핸드북 7판 표 3.1.",
    "잔차가 가장 작은 EPDM-EX_예제-aee4_1.0__01__NA_03__DMA_01 을 대표로 골랐습니다.",
    "소성변형률이 0 인 점이 10개였습니다 — 탄성 구간을 0 으로 자른 자국입니다.",
]


@pytest.mark.parametrize("note", CAUTIONS)
def test_경고는_경고로_센다(note: str) -> None:
    assert cautions([note]) == [note]


@pytest.mark.parametrize("note", PROVENANCE)
def test_출처_설명은_경고가_아니다(note: str) -> None:
    """**전부 세면 카드 42장이 다 경고 카드가 된다** — 늘 켜진 경고는 안 읽힌다."""
    assert cautions([note]) == []


def test_섞여_있으면_경고만_차례대로() -> None:
    notes = [PROVENANCE[0], CAUTIONS[0], PROVENANCE[1], CAUTIONS[3]]
    assert cautions(notes) == [CAUTIONS[0], CAUTIONS[3]]


def test_비었거나_없으면_빈_목록() -> None:
    assert cautions(None) == []
    assert cautions([]) == []
