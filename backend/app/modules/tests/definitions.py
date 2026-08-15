"""기본 시험 종류 정의 — 시드이자, 수준 2 설계의 증명.

여기 있는 것은 **데이터의 초기값이지 코드가 아니다.** 새 시험 종류(압축·굽힘·
DMA)를 추가하는 일은 관리 화면에서 행을 넣는 일이고, 등록·목록·조회·곡선 표시는
배포 없이 동작한다. 전용 계산이 필요할 때만 `matcore` 에 플러그인을 붙인다.

인장 하나만 넣는 이유: **파서가 있는 것만 넣는다.** 정의만 있고 읽지 못하는
종류가 목록에 보이면 사용자가 올렸다가 실패한다. DMA 는 파서와 함께 들어온다.

채널은 실제 장비 파일(`Example.tra`, Zwick)을 열어 확인한 것에 맞췄다. 장비가
주는 것은 응력-변형률이 아니라 **변위·하중·시편폭**이다 — 공칭→진응력 변환과
n·r 값 계산은 MatNexus 가 한다.

멱등하다. 이미 있으면 건드리지 않는다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.tests.models import TestChannel, TestConditionField, TestType

#: 시험 종류 → 채널 · 조건 항목.
#:
#: 조건에 넣지 않은 것들이 있다. 시험자·장비·시험일은 `TestRun` 의 컬럼이고,
#: 실측 두께·폭·게이지길이는 **시편**의 속성이다(같은 시편으로 두 번 시험해도
#: 치수는 같다). 기존 앱은 이 셋을 시험 조건에 두어 시험마다 다시 적게 했다.
BUILTIN_TEST_TYPES: list[dict[str, Any]] = [
    {
        "key": "tensile",
        "label": "인장시험",
        "abbr": "TEN",
        "parser_key": "zwick_tra",
        "description": "단축 인장. 변위-하중 원본에서 공칭·진응력 곡선을 만든다.",
        "sort_order": 10,
        "channels": [
            ("displacement", "변위", "length", "m", True),
            ("force", "하중", "force", "N", True),
            ("specimen_width", "시편 폭", "length", "m", False),
        ],
        "conditions": [
            ("temperature", "시험 온도", "number", "temperature", "K", None, False),
            ("speed_elastic", "탄성역 속도", "number", "velocity", "m/s", None, False),
            ("speed_plastic", "소성역 속도", "number", "velocity", "m/s", None, False),
            ("preload", "예하중", "number", "force", "N", None, False),
            ("sensor_type", "센서 종류", "text", None, None, None, False),
            ("specimen_standard", "시편 규격", "text", None, None, None, False),
            ("testing_group", "시험 그룹", "text", None, None, None, False),
        ],
    },
]


def ensure_builtin_test_types(db: Session) -> list[str]:
    """기본 시험 종류를 보장한다. 새로 만든 것의 key 를 돌려준다.

    이미 있는 종류는 손대지 않는다 — 운영 중에 관리자가 라벨이나 정렬을
    고쳤을 수 있고, 시드가 그것을 되돌리면 안 된다.
    """
    created: list[str] = []

    for spec in BUILTIN_TEST_TYPES:
        existing = db.scalar(select(TestType).where(TestType.key == spec["key"]))
        if existing is not None:
            continue

        test_type = TestType(
            key=spec["key"],
            label=spec["label"],
            abbr=spec["abbr"],
            parser_key=spec["parser_key"],
            description=spec["description"],
            sort_order=spec["sort_order"],
        )
        db.add(test_type)
        db.flush()  # id 가 있어야 자식을 매단다

        for order, (key, label, dimension, si_unit, required) in enumerate(spec["channels"]):
            db.add(
                TestChannel(
                    test_type_id=test_type.id,
                    key=key,
                    label=label,
                    dimension=dimension,
                    si_unit=si_unit,
                    is_required=required,
                    sort_order=order * 10,
                )
            )

        for order, condition in enumerate(spec["conditions"]):
            key, label, value_type, dimension, si_unit, choices, required = condition
            db.add(
                TestConditionField(
                    test_type_id=test_type.id,
                    key=key,
                    label=label,
                    value_type=value_type,
                    dimension=dimension,
                    si_unit=si_unit,
                    choices=choices,
                    is_required=required,
                    sort_order=order * 10,
                )
            )

        created.append(spec["key"])

    return created
