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
            # **시편 규격은 여기 없다.** 시편으로 옮겼다(`Specimen.standard`) —
            # 규격은 자를 때 정해지고 게이지 길이·폭을 정하는 쪽이다. 여기 남은
            # 것들은 전부 **시험할 때 정해지는 것**이다.
            ("sensor_type", "센서 종류", "text", None, None, None, False),
            ("testing_group", "시험 그룹", "text", None, None, None, False),
        ],
    },
    {
        # **읽을 수 있는 것만 넣는다.** 인장은 `.tra` 파서가, DMA 는 형식
        # 프로파일이 읽는다(`legacy_profiles.py`) — 둘 다 올리면 곡선이 나온다.
        "key": "dma_sweep",
        "label": "DMA 스윕",
        "abbr": "DMA",
        # 전용 파서가 없다. 프로파일이 읽는다 — 그게 ADR 0005 의 요점이다.
        "parser_key": None,
        "description": "동적 기계 분석. 온도·주파수 스윕에서 저장·손실 탄성률을 얻는다.",
        "sort_order": 20,
        # 채널은 실파일(`Example FreqTemp2.csv`, TA DMA850)을 열어 맞췄다.
        # 온도 6단(-40~10 °C)에 주파수 8점(0.1~20 Hz)씩.
        "channels": [
            # **필수는 넷이다.** 점탄성 계산이 이것 없이는 성립하지 않는다.
            # 다만 "모든 곡선" 이 아니라 "파일 전체" 기준이다 — 장비가 표마다
            # 다른 열을 준다. 실제로 첫 스윕 표에만 `Frequency` 가 있고
            # 나머지 여섯에는 없다.
            ("storage_modulus", "저장 탄성률", "stress", "Pa", True),
            ("loss_modulus", "손실 탄성률", "stress", "Pa", True),
            ("temperature", "온도", "temperature", "K", True),
            ("angular_frequency", "각주파수", "angular_frequency", "rad/s", True),
            ("frequency", "주파수", "frequency", "Hz", False),
            ("tan_delta", "손실계수", "dimensionless", "1", False),
            ("oscillation_strain", "진동 변형률", "strain", "1", False),
            ("oscillation_stress", "진동 응력", "stress", "Pa", False),
            ("step_time", "구간 시간", "time", "s", False),
            # 마스터커브 표가 함께 주는 것들. 장비가 계산한 값이라 버리지 않는다.
            ("phase_angle", "위상각", "angle", "rad", False),
            ("complex_modulus", "복소 탄성률", "stress", "Pa", False),
        ],
        "conditions": [
            # **기준 온도가 조건이다.** 마스터커브는 어느 온도로 겹쳤느냐에
            # 따라 다른 곡선이고, 그것을 안 적으면 나중에 알 방법이 없다.
            # 실파일에는 20 °C 와 30 °C 두 벌이 함께 들어 있었다.
            ("reference_temperature", "기준 온도", "number", "temperature", "K", None, False),
            ("preload", "예하중", "number", "force", "N", None, False),
            ("clamp", "지그", "text", None, None, None, False),
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
