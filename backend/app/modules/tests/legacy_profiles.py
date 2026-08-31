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

## 고친 것 — 시편 치수가 안 채워졌다 (2026-08-26)

처음에는 `"Specimen thickness a0 (mm)": "specimen_thickness"` 로 **키만** 적었다.
그러면 메타에 `specimen_thickness = "0.986"` 이 들어가는데, 읽는 쪽은 숫자만
있고 단위를 모르면 포기한다(`app/shared/curvedata.py` 의 `_as_metres` — mm 라고
가정하면 m 로 적은 파일에서 1000배 틀린 시편이 만들어진다). 그래서 **치수가
하나도 안 채워졌고 오류도 안 났다.** 처리 1단계의 `@specimen_area` 가 그제서야
"그 값이 없습니다" 로 멈춘다 — 원인에서 세 단계 떨어진 자리다.

`.tra` 는 단위를 별도 칸으로 주고 DMA CSV 는 값에 붙여 주므로(`50.0 mm`) 둘 다
멀쩡했다. **이 파일만 단위가 이름에 있었다.**

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
    # **단위를 프로파일이 적는다.** 이 파일은 단위를 열 이름 안에만 갖고 있고
    # (`(mm)`), 값 옆에는 `0.986` 뿐이다. 안 적으면 시편 치수가 조용히 안
    # 채워진다 — 실측으로 그랬다(아래 "고친 것" 참고).
    "specimen": {
        "Specimen thickness a0 (mm)": {"key": "specimen_thickness", "unit": "mm"},
        "Specimen width b0 (mm)": {"key": "specimen_width", "unit": "mm"},
    },
    # **시험이 낸 결과가 아닌 것은 결과 자리에 두지 않는다.**
    #
    # 처음에는 아래 다섯이 전부 `metadata`(원문 보관)에 있었다. 보관은 글자로만
    # 남아서 **비교도 통계도 안 되고**, 무엇보다 그 값들이 갈 **제자리가 이미
    # 있었다** — 시험 종류가 `sensor_type`·`testing_group` 을 조건으로 선언하고
    # 있고, 시험 기록에는 시험일·시험자·장비 칸이 있다.
    #
    # 자리가 맞으면 따라오는 것들: 조건은 정의가 검증하고(모르는 값은 거절),
    # 장비는 기준정보로 묶이며(`Zwick Z100` 과 `zwick z100` 이 안 갈린다),
    # 시험일로 거를 수 있다.
    "record": {
        "Operator": {"field": "operator"},
        "Instrument name": {"field": "instrument"},
        # 옛 앱은 `2024-03-11 09:20:00` 으로 적는다. **형식을 선언한다** —
        # 안 적으면 ISO 만 읽고 나머지는 비워 둔다(짐작하지 않는다).
        "rundate": {"field": "tested_at", "format": "%Y-%m-%d %H:%M:%S"},
    },
    "conditions": {
        # 둘 다 글자 조건이라 단위가 없다.
        "Sensor Type": {"field": "sensor_type"},
        "Testing Group": {"field": "testing_group"},
    },
    # **짚어만 둔다.** 시험은 만들 때 시편에 매달리므로 자동으로 안 붙인다.
    "identity": {"Specimen Number": {"field": "specimen_seq_no"}},
    # 남는 것은 **정말 기록일 뿐인 것들**이다. 시편 규격은 시편의 것이지만
    # 프로파일에 그 자리가 없어서(치수가 아니다) 보관으로 둔다.
    "metadata": [
        "Specimen Standard",
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
        # **읽자마자 마스터커브로 등록한다**(ADR 0023 의 B). 이 장비는 기준 온도를
        # 표 이름에만 적는다 — 파일 머리에는 없다. 첫 괄호가 그 온도이고, 단위는
        # 여기서 정한다(이름에 `°C` 가 보인다고 단정하지 않는다).
        #
        # 규칙이 없으면 자동 등록을 안 한다. 그때는 점탄성 화면에서 손으로 가져온다.
        "master_curve": {"pattern": r"\(([\d.]+)\s*°?\s*C\)", "unit": "degC"},
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
        # **지운 것도 센다 — 일부러 그렇다.** 관리자가 기본 프로파일을 지웠는데
        # 다음 부팅에 조용히 되살아나면, 지운 사람은 그것을 못 지운다. 되살리려면
        # 휴지통에서 명시적으로 한다.
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
