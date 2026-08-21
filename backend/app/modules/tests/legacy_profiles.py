"""옛 앱(`MaterialAppVer2`) 파일을 읽는 기본 프로파일.

**코드가 아니라 데이터의 초기값이다** — `definitions.py` 의 시험 종류와 같은
자리에 있다. 관리 화면에서 고칠 수 있고, 고친 것을 시드가 되돌리지 않는다.

## 왜 기본으로 넣나

이 회사가 MatNexus 를 쓰기 시작한다는 것은 **옛 앱에 쌓인 것을 옮긴다는 뜻**이다.
그 파일은 한 종류(`.mtet`·`.mdss`·`.mdft`)이고 모양이 정해져 있다. 설치할 때마다
사람이 40줄짜리 정의를 손으로 다시 적게 두면, 그 손이 틀리는 날이 온다.

DMA 쪽(`.mdss`·`.mdft`)은 **아직 안 넣는다.** `definitions.py` 가 적어 둔 규율이
"파서가 있는 것만 넣는다" 인데, 그것을 넓히면 **읽을 수 있는 것만 넣는다** 이다.
DMA 는 읽히기는 하지만 담을 시험 종류가 없다 — 정의만 있고 못 쓰는 것이 목록에
보이면 사용자가 올렸다가 실패한다. 시험 종류와 함께 들어와야 한다.

## 단위를 프로파일이 선언한다

`.tra` 는 단위를 별도 줄로 주지만 이 파일은 **열 이름 안에** 갖고 있다
(`Standard extensometer (mm)`). 그걸 리더가 떼지 않는 이유는
`readers/json_tables.py` 에 적었다 — `Tan(delta)` 가 596번 나온다.

같은 열이 파일에 따라 단위를 달고도(55회) 안 달고도(33회) 온다. **둘 다 적는다.**
하나만 적으면 나머지 33개가 "단위를 알 수 없는 열" 로 등록을 거부당한다.

## 검증

실파일 107개에 돌렸다 — 데이터가 든 88개 전부 경고 없이 채널 3개로 읽혔고,
나머지 19개는 Raw Data 가 없는 껍데기라 옳게 거절됐다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.tests.models import FormatProfile, TestType

#: 옛 앱의 인장 결과 파일. 시험 종류는 `tensile`.
LEGACY_TENSILE_KEY = "legacy_mtet"

LEGACY_TENSILE_DEFINITION: dict[str, Any] = {
    "match": {
        # 확장자만으로는 못 가르지만(`.csv` 는 어느 장비나 쓴다) 이건 전용
        # 확장자라 확실하다. 그래도 열 이름을 함께 본다 — 확장자만 같고 속이
        # 다른 파일이 오는 날이 있다.
        "extensions": [".mtet"],
        "header_any": ["Standard extensometer (mm)", "Standard extensometer"],
    },
    # 이 파일에는 표가 하나다(`Tensile Test Raw Data`).
    "tables": {"mode": "first"},
    "columns": {
        # 행 번호. 안 버리면 단위 모르는 채널로 저장되어 곡선 고르는 자리에
        # 뜻 없는 계열이 하나 낀다. 실측 파일 전부에 이 열이 있다.
        "#": {"skip": True},
        "Standard extensometer (mm)": {"channel": "displacement", "unit": "mm"},
        "Standard extensometer": {"channel": "displacement", "unit": "mm"},
        "Standard load cell (N)": {"channel": "force", "unit": "N"},
        "Standard load cell": {"channel": "force", "unit": "N"},
        "Specimen width (mm)": {"channel": "specimen_width", "unit": "mm"},
        "Specimen width": {"channel": "specimen_width", "unit": "mm"},
    },
    # **옛 앱이 계산한 답을 버리지 않는다.** 같은 곡선을 MatNexus 가 처리한
    # 결과와 나란히 놓고 볼 수 있다 — 합성 데이터로는 못 사는 확신이다.
    # `legacy_` 를 붙여 우리가 계산한 값과 섞이지 않게 한다.
    "summary": {
        "Force at proof stress 0.2% (MPa)": {"key": "legacy_proof_stress", "unit": "MPa"},
        "Force maximum (MPa)": {"key": "legacy_tensile_strength", "unit": "MPa"},
        "Strain (plastic) at Fmax (%)": {"key": "legacy_strain_at_fmax", "unit": "%"},
        "Strain (plastic) at break (%)": {"key": "legacy_strain_at_break", "unit": "%"},
        "Work hardening coefficient k{lo  10 - 15} (MPa)": {
            "key": "legacy_hardening_k",
            "unit": "MPa",
        },
        "Work hardening exponent n{lo  10 - 15}": {"key": "legacy_hardening_n", "unit": "1"},
        "Vertical anisotropy r{lo  10 - 15}": {"key": "legacy_r_value", "unit": "1"},
        # 옛 앱은 못 구한 값을 `Unknown` 으로 적는다. 숫자가 아니면 글자 그대로
        # 남는다 — 0 으로 만들지 않는다.
        "Yield strain": {"key": "legacy_yield_strain"},
        "Upper yield point": {"key": "legacy_upper_yield"},
        "Lower yield point": {"key": "legacy_lower_yield"},
    },
    # 시편 치수는 **시험이 아니라 시편의 것**이다(ADR 0004). `a0`·`b0` 를 쓴다 —
    # 시험 조건에 적힌 값이 아니라 그 시험이 실제로 쓴 값이다.
    "specimen": {
        "Specimen thickness a0 (mm)": "specimen_thickness",
        "Specimen width b0 (mm)": "specimen_width",
    },
    "metadata": [
        "rundate",
        "Instrument name",
        "Operator",
        "Specimen Number",
        "Specimen Standard",
        "Sensor Type",
        "Testing Group",
        "Technical Data Record Name",
        "Tensile Data ID",
    ],
}

#: TA DMA850 이 TRIOS 로 내보낸 CSV. 시험 종류는 `dma_sweep`.
TA_DMA850_KEY = "ta_dma850"

TA_DMA850_DEFINITION: dict[str, Any] = {
    "match": {
        # `.csv` 는 어느 장비나 쓴다 — **열 이름이 지문이다.**
        "extensions": [".csv"],
        "header_any": ["Angular frequency", "Storage modulus"],
    },
    # **버리지도 섞지도 않는다.** 실파일에는 온도 스윕 6벌과 TTS 결과가 함께 온다.
    # TTS 는 장비가 계산한 것이므로 `derived` 로 적어 둔다 — 처리가 그것을 원본으로
    # 착각하면 마스터커브에 또 마스터커브를 씌운다.
    #
    # 실측: 기준 온도를 바꿔 두 벌(20 °C·30 °C)을 만든 파일이 있었다. 그래서
    # `^TTS` 로 넓게 잡는다 — `TTS 30 - master curve (30.0 °C)` 까지 걸려야 한다.
    "tables": {
        "mode": "all",
        "include": "^Temperature Sweep|^Strain Sweep|^Frequency Sweep",
        "derived": "^TTS",
    },
    "columns": {
        "Angular frequency": {"channel": "angular_frequency"},
        "Frequency": {"channel": "frequency"},
        "Temperature": {"channel": "temperature"},
        "Storage modulus": {"channel": "storage_modulus"},
        "Loss modulus": {"channel": "loss_modulus"},
        "Tan(delta)": {"channel": "tan_delta", "unit": "1"},
        "Oscillation strain": {"channel": "oscillation_strain"},
        "Oscillation stress": {"channel": "oscillation_stress"},
        "Step time": {"channel": "step_time"},
        "Phase angle": {"channel": "phase_angle"},
        "Complex modulus": {"channel": "complex_modulus"},
    },
    # 시편 치수는 시험이 아니라 시편의 것이다(ADR 0004). 값과 단위가 한 칸에
    # 붙어 온다(`50.0 mm`) — `_split_value_unit` 이 가른다.
    "specimen": {
        "Length": "specimen_length",
        "Width": "specimen_width",
        "Thickness": "specimen_thickness",
    },
    "metadata": [
        "rundate",
        "Instrument name",
        "Instrument location",
        "Operator",
        "Sample name",
        "Geometry name",
        "Procedure name",
        "proceduresegments",
    ],
}

#: (key, label, 시험 종류 key, description, definition)
BUILTIN_FORMAT_PROFILES: list[tuple[str, str, str, str, dict[str, Any]]] = [
    (
        LEGACY_TENSILE_KEY,
        "옛 앱 인장 결과 (.mtet)",
        "tensile",
        "MaterialAppVer2 가 남긴 JSON. 곡선과 함께 그 앱이 계산한 값도 요약으로 들어온다.",
        LEGACY_TENSILE_DEFINITION,
    ),
    (
        TA_DMA850_KEY,
        "TA DMA850 (TRIOS CSV)",
        "dma_sweep",
        "온도·주파수 스윕과 장비가 계산한 TTS 결과가 함께 들어온다.",
        TA_DMA850_DEFINITION,
    ),
]


def ensure_builtin_format_profiles(db: Session) -> list[str]:
    """기본 프로파일을 보장한다. 새로 만든 것의 key 를 돌려준다.

    **이미 있으면 손대지 않는다.** 운영 중에 관리자가 열 이름을 고쳤을 수 있고
    (같은 장비라도 부서마다 소프트웨어 설정이 다르다), 시드가 그것을 되돌리면
    안 된다 — 시험 종류와 같은 판단이다.

    담을 시험 종류가 없으면 **조용히 건너뛴다.** 그 종류를 여기서 만들지 않는
    이유는, 프로파일이 시험 종류를 만들기 시작하면 어느 쪽이 정본인지 갈리기
    때문이다. 시험 종류는 `definitions.py` 하나가 만든다.
    """
    created: list[str] = []

    for key, label, type_key, description, definition in BUILTIN_FORMAT_PROFILES:
        existing = db.scalar(
            select(FormatProfile).where(
                FormatProfile.key == key, FormatProfile.owner_workspace_id.is_(None)
            )
        )
        if existing is not None:
            continue

        test_type = db.scalar(select(TestType).where(TestType.key == type_key))
        if test_type is None:
            continue

        db.add(
            FormatProfile(
                key=key,
                label=label,
                description=description,
                test_type_id=test_type.id,
                definition=definition,
                # 전역이다. 옛 앱은 한 회사가 쓰던 것이라 부서를 안 가린다.
                owner_workspace_id=None,
            )
        )
        created.append(key)

    if created:
        db.flush()
    return created
