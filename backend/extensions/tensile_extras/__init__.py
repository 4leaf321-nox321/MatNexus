"""인장 덧붙이기 — **처리 단계와 묶음을 확장 폴더에서 등록하는지 재는 자리.**

`ghosh_hardening` 이 적합식(①)을, `johnson_cook_static` 이 카드 블록을 확장 폴더에서
붙였다. 남은 창구가 둘이었다 — **처리 단계**(시험 하나: 곡선 → 스칼라)와 **묶음**(여러
시험 → 하나). 창구는 같은 `registry.register` 인데 확장에서 써 본 적이 없었다
(2026-09-13, [계획] 계산 확장 1단계). 이 폴더가 둘을 실제로 붙인다.

- `yield_ratio` — 항복비(항복강도 ÷ 인장강도). 앞 단계가 낸 값을 `@` 로 받는 단계.
- `temperature_family` — 온도별 인장 곡선을 묶어 **온도별 소성 표**와 온도 연화
  요약(기울기·Johnson-Cook m)을 낸다. 속도 가족과 같은 모양. 구성원은 파이썬
  수집기 없이 **선언**(`meta["members"]`)으로 모으고, 카드는 `card=` 로 선언한
  함수가 블록을 만든다(`/fitting/cards/from-group`). 블록과 Abaqus 덱은 `card.py`.

중심 코드는 한 줄도 안 고쳤다. 계산은 옆 파일에 있다.
"""

from __future__ import annotations

from matcore.registry import ParamSpec, Produced, register

from . import (  # noqa: F401  (card 는 import 만으로 블록·렌더러를 등록한다)
    band_model,
    card,
    effective_card_domain,
    model_anchor,
    model_curve,
    model_support,
    plastic_domain,
    ratio,
    source_elastic,
    source_proof,
    temperature,
    terminal_domain,
)

_MODEL_CARD_EFFECT_VALUES = (
    Produced("model_card_input_points", "모델 단계 입력 관측점 수", "1"),
    Produced("model_card_changed_points", "모델 단계 변경 관측점 수", "1"),
    Produced("model_card_last_changed_index", "마지막 변경 모델 행", "1"),
    Produced(
        "model_card_effect_end_index",
        "카드용 모델 영향 끝 관측행",
        "1",
        help="선언 지지가 없으면 마지막 변경행 뒤 첫 미변경 관측행을 씁니다.",
    ),
    Produced(
        "model_card_effect_end_strain",
        "카드용 모델 영향 끝 공칭 변형률",
        "1",
        help="영향이 없으면 0이며, 끝 행은 현재 모델 입력 프레임 기준입니다.",
    ),
    Produced(
        "model_card_support_kind",
        "모델 영향 지지 종류",
        "1",
        help="0 없음, 1 변경 곡선 접합, 2 선언 지지를 포함한 끝입니다.",
    ),
)

register(
    id="tensile.source_elastic_modulus",
    kind="processing",
    label="원행 탄성계수",
    params=(
        ParamSpec(
            name="policy",
            label="원행 탄성 구간",
            type="choice",
            choices=source_elastic.POLICIES,
            default=source_elastic.AUTO_POLICY,
            choice_labels={
                source_elastic.AUTO_POLICY: "최대응력 띠의 원행 구간",
                source_elastic.MANUAL_POLICY: "현재 입력 원행 직접 지정",
            },
            help=(
                "자동은 첫 최대응력의 10~40% 띠를 포함하는 원행 구간을 씁니다. "
                "현재 입력 전체를 정렬·평활·이동하지 않습니다."
            ),
        ),
        ParamSpec(
            name="start_index",
            label="시작 원행 인덱스 (현재 입력, 0부터)",
            type="int",
            required=True,
            when={"policy": (source_elastic.MANUAL_POLICY,)},
            help="포함할 현재 입력 프레임의 시작 행입니다.",
        ),
        ParamSpec(
            name="end_index",
            label="끝 원행 인덱스 (현재 입력, 0부터)",
            type="int",
            required=True,
            when={"policy": (source_elastic.MANUAL_POLICY,)},
            help="포함할 현재 입력 프레임의 끝 행입니다.",
        ),
        ParamSpec(
            name="strain",
            label="변형률 열",
            type="str",
            role="column",
            default="strain_engineering",
            unit="1",
            dimension="strain",
        ),
        ParamSpec(
            name="stress",
            label="응력 열",
            type="str",
            role="column",
            default="stress_engineering",
            unit="Pa",
        ),
    ),
    applies_to=("tensile",),
    requires_channels=(("displacement",), ("force",)),
    makes_values=(
        Produced(
            key="youngs_modulus",
            label="탄성계수",
            si_unit="Pa",
            help="수치·품질 검사를 통과한 원행 변형률-응력 구간의 기울기.",
            property_key="mechanical.youngs_modulus",
        ),
        Produced(key="elastic_intercept", label="탄성 절편", si_unit="Pa"),
        Produced(key="elastic_r_squared", label="탄성 구간 R²", si_unit="1"),
        Produced(key="elastic_point_count", label="탄성 구간 점 수", si_unit="1"),
        Produced(key="elastic_window_start", label="실제 적합 변형률 시작", si_unit="1"),
        Produced(key="elastic_window_end", label="실제 적합 변형률 끝", si_unit="1"),
        Produced(
            key="elastic_slope_reference",
            label="참고 기울기(믿을 수 없음)",
            si_unit="Pa",
        ),
        Produced(
            key="source_elastic_start_index",
            label="원행 E 시작 인덱스 (현재 입력, 0부터)",
            si_unit="1",
            help="실제 적합 구간의 첫 입력 행. 원본 CSV 행 번호와는 다릅니다.",
        ),
        Produced(
            key="source_elastic_end_index",
            label="원행 E 끝 인덱스 (현재 입력, 0부터)",
            si_unit="1",
            help="실제 적합 구간의 마지막 입력 행. 원본 CSV 행 번호와는 다릅니다.",
        ),
        Produced(
            key="source_elastic_nonincreasing_step_count",
            label="원행 E 구간 비증가 단계 수",
            si_unit="1",
            help="실제 적합 구간의 인접 원행에서 변형률이 감소하거나 같은 횟수.",
        ),
    ),
    order=71,
    version="1",
)(source_elastic.source_elastic_modulus)

register(
    id="tensile.source_proof_stress",
    kind="processing",
    label="원행 내력 교점",
    applies_to=("tensile",),
    requires_channels=(("displacement",), ("force",)),
    params=(
        ParamSpec(
            name="policy",
            label="원행 내력 정책",
            type="choice",
            choices=(source_proof.POLICY,),
            default=source_proof.POLICY,
            help="인접한 원행에서 변형률이 증가하는 첫 양수 오프셋 교점을 선택합니다.",
        ),
        ParamSpec(
            name="youngs_modulus",
            label="탄성계수",
            type="float",
            unit="Pa",
            default="@youngs_modulus",
            required=True,
            help="비우면 앞 단계 원행 E 값을 씁니다. 직접 입력값도 사용할 수 있습니다.",
        ),
        ParamSpec(
            name="offset_strain",
            dimension="strain",
            label="오프셋 변형률",
            type="float",
            unit="1",
            default=source_proof.DEFAULT_OFFSET,
            help="0 이상이어야 합니다. E 절편이나 별도 영점 이동은 더하지 않습니다.",
        ),
        ParamSpec(
            name="start_index",
            label="검색 시작 원행 (현재 입력, 0부터)",
            type="int",
            default="@source_elastic_end_index",
            required=True,
            links_to="source_elastic_end_index",
            help="비우면 원행 E 구간의 끝 행부터 검색합니다.",
        ),
        ParamSpec(
            name="end_index",
            label="검색 끝 원행 (현재 입력, 0부터)",
            type="int",
            help="비우면 현재 입력 프레임의 마지막 행까지 검색합니다.",
        ),
        ParamSpec(
            name="search_start",
            dimension="strain",
            label="검색 시작 변형률",
            type="float",
            unit="1",
            default="@elastic_window_end",
            required=True,
            links_to="elastic_window_end",
            help="비우면 원행 E 적합 창의 끝 변형률부터 검색합니다.",
        ),
        ParamSpec(
            name="search_end",
            dimension="strain",
            label="검색 끝 변형률",
            type="float",
            unit="1",
            help="비우면 선택한 입력 구간의 관측 최대 변형률까지 검색합니다.",
        ),
        ParamSpec(
            name="strain",
            label="변형률 열",
            type="str",
            role="column",
            default=source_proof.DEFAULT_STRAIN,
            unit="1",
            dimension="strain",
        ),
        ParamSpec(
            name="stress",
            label="응력 열",
            type="str",
            role="column",
            default=source_proof.DEFAULT_STRESS,
            unit="Pa",
        ),
    ),
    makes_values=(
        Produced(
            key="proof_stress",
            label="원행 내력",
            si_unit="Pa",
            property_key="mechanical.yield_strength",
            help=(
                "관측된 인접 전진 원행 교점의 응력. 적격 양수 교점이 없으면 값을 "
                "내지 않습니다."
            ),
        ),
        Produced(key="proof_strain", label="원행 내력 변형률", si_unit="1"),
        Produced(key="proof_offset", label="원행 내력 오프셋", si_unit="1"),
        Produced(
            key="source_proof_left_index",
            label="원행 내력 교점 왼쪽 행 (현재 입력, 0부터)",
            si_unit="1",
            help="보간에 사용한 첫 원행이며 원본 파일 행 번호가 아닙니다.",
        ),
        Produced(
            key="source_proof_right_index",
            label="원행 내력 교점 오른쪽 행 (현재 입력, 0부터)",
            si_unit="1",
            help="보간에 사용한 바로 다음 원행이며 원본 파일 행 번호가 아닙니다.",
        ),
        Produced(
            key="source_proof_search_start_index", label="내력 검색 시작 원행", si_unit="1"
        ),
        Produced(key="source_proof_search_end_index", label="내력 검색 끝 원행", si_unit="1"),
        Produced(
            key="source_proof_search_start_strain", label="내력 검색 시작 변형률", si_unit="1"
        ),
        Produced(
            key="source_proof_search_end_strain", label="내력 검색 끝 변형률", si_unit="1"
        ),
        Produced(
            key="source_proof_forward_eligible_pair_count",
            label="전진 적격 인접 원행 쌍 수",
            si_unit="1",
        ),
        Produced(
            key="source_proof_backward_crossing_candidate_count",
            label="역행 잔차 교점 후보 수",
            si_unit="1",
        ),
        Produced(
            key="source_proof_equal_strain_crossing_candidate_count",
            label="같은 변형률 잔차 교점 후보 수",
            si_unit="1",
        ),
        Produced(
            key="source_proof_positive_crossing_candidate_count",
            label="양수 전진 교점 후보 수",
            si_unit="1",
        ),
        Produced(
            key="source_proof_nonpositive_crossing_candidate_count",
            label="비양수 전진 교점 후보 수",
            si_unit="1",
        ),
        Produced(
            key="source_proof_coincident_forward_residual_segment_count",
            label="전진 일치 잔차 선분 수",
            si_unit="1",
        ),
    ),
    order=72,
    version="1",
    prepare_options=source_proof.prepare_options,
)(source_proof.source_proof_stress)

register(
    id="tensile.model_support",
    kind="processing",
    label="원행 기반 모델 입력",
    applies_to=("tensile",),
    requires_channels=(("displacement",), ("force",)),
    params=(
        ParamSpec(
            name="policy",
            label="모델 입력 정책",
            type="choice",
            choices=(model_support.POLICY,),
            default=model_support.POLICY,
            help=(
                "원래 입력 행에서 변형률 기록 최고점을 보수적으로 골라 모델 입력을 "
                "만듭니다. 계측 이상이나 물리적 유효성을 판정하지 않습니다."
            ),
        ),
        ParamSpec(
            name="start_index",
            label="모델 범위 시작 현재행 (0부터, 선택)",
            type="int",
            default=0,
            help="비우면 현재 입력의 첫 행부터 모델 범위를 봅니다.",
        ),
        ParamSpec(
            name="end_index",
            label="모델 범위 끝 현재행 (0부터, 선택)",
            type="int",
            help="비우면 현재 입력의 마지막 행까지 모델 범위를 봅니다.",
        ),
        ParamSpec(
            name="youngs_modulus",
            label="원행 탄성계수",
            type="float",
            unit="Pa",
            default="@youngs_modulus",
            required=True,
            help="앞 단계에서 원자료로 계산한 E. 이 단계가 다시 계산하지 않습니다.",
        ),
        ParamSpec(
            name="elastic_intercept",
            label="원행 E 적합 절편",
            type="float",
            unit="Pa",
            default="@elastic_intercept",
            required=True,
            help="원행 E 적합의 절편이며 paired-row guard 잔차 폭에만 사용합니다.",
        ),
        ParamSpec(
            name="source_elastic_start_index",
            label="원행 E 적합 시작 현재행",
            type="int",
            default="@source_elastic_start_index",
            required=True,
            links_to="source_elastic_start_index",
        ),
        ParamSpec(
            name="source_elastic_end_index",
            label="원행 E 적합 끝 현재행",
            type="int",
            default="@source_elastic_end_index",
            required=True,
            links_to="source_elastic_end_index",
        ),
        ParamSpec(
            name="source_proof_left_index",
            label="원행 내력 교점 왼쪽 현재행",
            type="int",
            default="@source_proof_left_index",
            required=True,
            links_to="source_proof_left_index",
        ),
        ParamSpec(
            name="source_proof_right_index",
            label="원행 내력 교점 오른쪽 현재행",
            type="int",
            default="@source_proof_right_index",
            required=True,
            links_to="source_proof_right_index",
        ),
        ParamSpec(
            name="strain",
            label="공학 변형률 열",
            type="str",
            role="column",
            default=model_support.DEFAULT_STRAIN,
            unit="1",
            dimension="strain",
        ),
        ParamSpec(
            name="stress",
            label="공학 응력 열",
            type="str",
            role="column",
            default=model_support.DEFAULT_STRESS,
            unit="Pa",
        ),
    ),
    makes_columns=(Produced("model_input_index", "모델 입력 원행 대응 열", "1"),),
    makes_values=(
        Produced("model_support_start_index", "모델 범위 시작 현재행", "1"),
        Produced("model_support_end_index", "모델 범위 끝 현재행", "1"),
        Produced("model_support_selected_row_count", "모델 입력 유지 행 수", "1"),
        Produced("model_support_omitted_row_count", "모델 입력 제외 행 수", "1"),
        Produced("model_support_record_high_gap_row_count", "기록 최고 gap 행 수", "1"),
        Produced("model_support_backward_gap_row_count", "변형률 후퇴 gap 행 수", "1"),
        Produced("model_support_guard_flagged_row_count", "선택 범위 guard 표시 행 수", "1"),
        Produced(
            "model_support_full_guard_flagged_row_count", "전체 입력 guard 표시 행 수", "1"
        ),
        Produced(
            "model_support_excluded_flagged_boundary_count",
            "수동 범위가 끊은 표시 경계 수",
            "1",
        ),
        Produced("model_support_guard_allowance", "paired-row guard 허용 후퇴 상한", "1"),
        Produced("model_support_max_backward_step", "최대 변형률 후퇴 폭", "1"),
        Produced(
            "model_support_elastic_rows_inside_count", "모델 범위 안 원행 E 적합 수", "1"
        ),
        Produced(
            "model_support_elastic_rows_outside_count", "모델 범위 밖 원행 E 적합 수", "1"
        ),
        Produced(
            "model_support_elastic_rows_retained_count", "모델 입력에 남은 원행 E 적합 수", "1"
        ),
        Produced("model_support_proof_pair_inside", "원행 내력 쌍 범위 포함", "1"),
        Produced("model_support_proof_pair_retained", "원행 내력 쌍 두 행 선택 유지", "1"),
        Produced(
            "model_support_proof_rows_retained_count", "모델 입력에 남은 원행 내력 점 수", "1"
        ),
        Produced("model_support_full_peak_inside", "전체 입력 첫 최대응력 범위 포함", "1"),
        Produced(
            "model_support_full_peak_retained", "전체 입력 첫 최대응력 행 선택 유지", "1"
        ),
        Produced("model_support_range_peak_index", "모델 범위 첫 최대응력 현재행", "1"),
    ),
    order=81,
    version="1",
    prepare_options=model_support.prepare_options,
)(model_support.model_support)

register(
    id="tensile.yield_ratio",
    kind="processing",
    label="항복비",
    applies_to=("tensile",),
    # 키만으로 거르지 않는다 — 변위·하중을 재는 시험이면 강도가 나오고 항복비가 선다.
    requires_channels=(("displacement",), ("force",)),
    params=(
        ParamSpec(
            name="proof_stress",
            label="항복강도",
            type="float",
            unit="Pa",
            default="@proof_stress",
            required=True,
            help="항복강도 단계가 낸 값. 손으로 적으면 항복 정의를 바꿔도 여기는 옛 값이 "
            "남는다.",
        ),
        ParamSpec(
            name="tensile_strength",
            label="인장강도",
            type="float",
            unit="Pa",
            default="@tensile_strength",
            required=True,
            help="인장강도 단계가 낸 값.",
        ),
    ),
    makes_values=(
        Produced(
            key="yield_ratio",
            label="항복비",
            si_unit="1",
            help="항복강도 ÷ 인장강도. 강구조 규격이 상한(예: 0.85)을 둔다.",
        ),
    ),
    # 강도(70)·항복강도(60) 뒤, 소성 곡선(90) 앞 — 재샘플(95)이 맨 끝인 것은 규칙이다.
    order=85,
    version="1",
)(ratio.yield_ratio)

register(
    id="tensile.terminal_domain",
    kind="processing",
    label="인장 시험 종료 구간",
    applies_to=("tensile",),
    requires_channels=(("displacement",), ("force",)),
    params=(
        ParamSpec(
            name="policy",
            label="말단 구간 정책",
            type="choice",
            choices=terminal_domain.POLICIES,
            default=terminal_domain.AUTO_POLICY,
            choice_labels={
                terminal_domain.AUTO_POLICY: "말단 하중 소실 자동 검토",
                terminal_domain.PROGRESSIVE_POLICY: "연속 말단 하중 가속 시작 검토",
                terminal_domain.MANUAL_POLICY: "검토한 끝 행 직접 지정",
            },
            choice_help={
                terminal_domain.AUTO_POLICY: (
                    "진행축 마지막 10%에서 급격하고 회복되지 않는 하중 소실만 제외합니다. "
                    "응력값은 바꾸지 않으므로 뒤에 둔 강도·E·Rp 단계는 보존한 원응력에서 "
                    "계산됩니다."
                ),
                terminal_domain.PROGRESSIVE_POLICY: (
                    "먼저 v1 급락 끝을 찾은 뒤, 시간 또는 엄격 증가 변형률 진행축에서 "
                    "연속 힌지로 구별되는 말단 응력 가속 시작을 근사해 앞당깁니다. "
                    "양의 응력 최댓값의 3% 손실은 이 보수적 자동 프로필의 고정 선별값이며 "
                    "보편적인 물성 임계값이나 파단 판정이 아닙니다. 모호한 간격·회복·안정 "
                    "하중 꼬리에서는 v1 끝을 유지합니다."
                ),
                terminal_domain.MANUAL_POLICY: (
                    "현재 입력 프레임의 0부터 세는 마지막 포함 행을 직접 지정합니다. "
                    "전체 공학 변환 직후라면 원래 취득행 인덱스와 같습니다."
                ),
            },
        ),
        ParamSpec(
            name="end_index",
            label="마지막 포함 행 위치 (현재 프레임, 0부터)",
            type="int",
            required=True,
            when={"policy": (terminal_domain.MANUAL_POLICY,)},
            help=(
                "현재 입력 프레임의 0-based 행 위치입니다. 전체 공학 변환 직후라면 원래 "
                "취득행 위치와 같고, upstream crop 뒤라면 그 입력 프레임 기준입니다. "
                "해당 행까지 포함하고 뒤 행은 제외합니다."
            ),
        ),
        ParamSpec(
            name="strain",
            label="변형률 열",
            type="str",
            role="column",
            default=terminal_domain.DEFAULT_STRAIN,
            unit="1",
            dimension="strain",
        ),
        ParamSpec(
            name="stress",
            label="응력 열",
            type="str",
            role="column",
            default=terminal_domain.DEFAULT_STRESS,
            unit="Pa",
        ),
        ParamSpec(
            name="time",
            label="시간 열 (선택)",
            type="str",
            role="column",
            unit="s",
            help=(
                "비우면 'time' 열이 있을 때 초 단위로 확인해 씁니다. 선택한 열이 없거나 "
                "유효하지 않으면 변형률 또는 행 순서로 대체합니다."
            ),
        ),
    ),
    makes_values=(
        Produced(
            key="terminal_domain_end_index",
            label="모델 구간 끝 행 위치 (0부터)",
            si_unit="1",
            help="유지한 현재 입력 프레임에서 0부터 세는 마지막 행 위치(포함).",
        ),
        Produced(
            key="terminal_domain_end_strain",
            label="모델 구간 끝 변형률",
            si_unit="1",
            help="모델 구간에 포함한 마지막 행의 공칭 변형률.",
        ),
        Produced(
            key="terminal_domain_removed_points",
            label="제외한 말단 점 수",
            si_unit="1",
            help="현재 입력 프레임에서 모델 구간 밖으로 제외한 행 수.",
        ),
        Produced(key="terminal_domain_input_points", label="입력 점 수", si_unit="1"),
        Produced(
            key="terminal_domain_input_end_load",
            label="입력 끝 응력",
            si_unit="Pa",
        ),
        Produced(
            key="terminal_domain_decision_code",
            label="말단 결정 코드",
            si_unit="1",
            help=(
                "0은 자동 무절단, 1은 v1 자동 제외, 2는 수동 끝 행 적용, "
                "3은 v2 연속 말단 가속 시작 제외입니다."
            ),
        ),
        Produced(
            key="terminal_domain_strain_strict",
            label="입력 변형률 엄격 증가 여부",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_progress_basis_code",
            label="진행축 코드",
            si_unit="1",
            help=(
                "0은 행 순서, 1은 변형률, 2는 시간입니다. 자세한 대체 사유는 "
                "단계 설명에 있습니다."
            ),
        ),
        Produced(
            key="terminal_domain_v2_old_end_index",
            label="v2 기준 끝 행 위치",
            si_unit="1",
            help="v2가 비교에 사용한 변경 전 v1 말단 끝 행입니다.",
        ),
        Produced(
            key="terminal_domain_v2_onset_status_code",
            label="v2 가속 시작 적용 코드",
            si_unit="1",
            help=(
                "0은 v1 끝 유지, 1은 근사 가속 시작 적용입니다. "
                "자세한 보류 사유는 단계 설명에 있습니다."
            ),
        ),
        Produced(
            key="terminal_domain_v2_candidate_index",
            label="v2 가속 시작 후보 행 위치",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_knot_progress",
            label="v2 힌지 무릎 진행도",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_raw_fit_pre_progress_span",
            label="v2 적합창 무릎 전 진행폭",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_raw_fit_post_progress_span",
            label="v2 적합창 무릎 후 진행폭",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_pre_slope_per_progress",
            label="v2 무릎 전 기울기",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_post_slope_per_progress",
            label="v2 무릎 후 기울기",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_slope_magnitude_ratio",
            label="v2 기울기 크기비",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_hinge_sse_gain",
            label="v2 힌지 SSE 개선",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_remaining_loss_over_peak",
            label="v2 후보~끝 응력 손실/양의 최댓값",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_local_pre_knee_stress",
            label="v2 국소 무릎 전 기준응력",
            si_unit="Pa",
        ),
        Produced(
            key="terminal_domain_v2_candidate_stress",
            label="v2 가속 시작 후보 응력",
            si_unit="Pa",
        ),
        Produced(
            key="terminal_domain_v2_loss_over_local_pre_knee",
            label="v2 응력 손실/국소 기준응력",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_late_residual_mad_over_peak",
            label="v2 후반 힌지 잔차 MAD/양의 최댓값",
            si_unit="1",
            help="힌지 적합 잔차의 산포 진단이며 센서 잡음 추정값이 아닙니다.",
        ),
        Produced(
            key="terminal_domain_v2_loss_to_residual_mad",
            label="v2 손실/후반 힌지 잔차 MAD",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_source_rows_before_knot",
            label="v2 무릎 전 원래 행 수",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_source_rows_after_candidate",
            label="v2 후보 뒤 원래 행 수",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_source_pre_progress_span",
            label="v2 무릎 전 원래 진행폭",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_source_post_progress_span",
            label="v2 후보 뒤 원래 진행폭",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_near_optimal_knot_low",
            label="v2 근최적 무릎 하한",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_near_optimal_knot_high",
            label="v2 근최적 무릎 상한",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_near_optimal_knot_span",
            label="v2 근최적 무릎 폭",
            si_unit="1",
            help="SSE가 최솟값의 1.05배 이내인 탐색 격자 무릎 폭이며 신뢰구간이 아닙니다.",
        ),
        Produced(
            key="terminal_domain_v2_sensitivity_knot_spread",
            label="v2 점수 시작 민감도 무릎 폭",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_intersecting_gap_count",
            label="v2 점수 구간 교차 큰 간격 수",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_max_scored_gap",
            label="v2 점수 구간 최대 원래 간격",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_post_half_loss_recovery",
            label="v2 절반 응력 손실 뒤 회복 여부",
            si_unit="1",
        ),
        Produced(
            key="terminal_domain_v2_stable_loaded_suffix",
            label="v2 안정 응력 끝 구간 여부",
            si_unit="1",
        ),
    ),
    order=20,
    version="2",
)(terminal_domain.terminal_domain)

register(
    id="tensile.band_model",
    kind="processing",
    label="안정 밴드 소성 모델",
    applies_to=("tensile",),
    requires_channels=(("displacement",), ("force",)),
    params=(
        ParamSpec(
            name="policy",
            label="원행 영역 정책",
            type="choice",
            choices=band_model.POLICIES,
            default=band_model.AUTO_POLICY,
            choice_labels={
                band_model.AUTO_POLICY_V1: "안정 밴드 및 사건 자동 선택 (v1)",
                band_model.AUTO_POLICY_V2: "안정 밴드 및 연결 사건 자동 선택 (v2)",
                band_model.SOURCE_EVENT_POLICY: "원행 E 경계 뒤 사건 보정 (v1)",
                band_model.MANUAL_POLICY: "검토한 밴드 행 직접 지정",
            },
            choice_help={
                band_model.AUTO_POLICY_V1: (
                    "현재 입력 원행에서 가장 긴 지지 가능한 post-peak 안정 밴드를 찾습니다. "
                    "밴드가 없으면 같은 방법의 legacy 자동 프로필에 "
                    "원입력을 그대로 위임합니다. "
                    "지원하지 않는 후보나 선택 밴드 적합 실패는 명시적으로 보류합니다."
                ),
                band_model.AUTO_POLICY_V2: (
                    "v1의 원행 밴드 선택에 더해 밴드 안에서 시작해 밴드 끝 뒤에 "
                    "완료되는 full-recovery 사건의 관측 끝행까지 적합합니다. "
                    "lower_envelope에서 닫힌 회복 사건이 앵커만 실패하면 원행 사건으로 "
                    "연결된 직전 모델 성분을 원응력 하측 포락선으로 함께 재계산합니다. "
                    "열린·말단 사건은 연결에 쓰지 않으며 밴드 통계는 원래 선택 행에서 "
                    "계산합니다."
                ),
                band_model.SOURCE_EVENT_POLICY: (
                    "선택 밴드가 있으면 v2와 같은 계산을 합니다. "
                    "밴드가 없을 때 네 앵커 방법은 "
                    "model_input_index로 원행 E 끝을 대응시켜 E prefix 안의 닫힌 회복 사건을 "
                    "대상에서 제외하고, 뒤의 닫힌 사건만 원행 core 전체로 적합합니다. "
                    "경계 사건을 prefix 안쪽으로 자르지 않으며 terminal 행은 보존합니다. "
                    "lower_envelope와 isotonic의 no-band 경로는 기존 동작을 유지합니다."
                ),
                band_model.MANUAL_POLICY: (
                    "현재 입력 프레임의 0-based 포함 행으로 밴드 끝 앵커를 지정합니다. "
                    "왼쪽 관측 앵커와 봉우리도 선택적으로 지정할 수 있습니다."
                ),
            },
        ),
        ParamSpec(
            name="method",
            label="밴드 모델 방법",
            type="choice",
            choices=band_model.METHODS,
            required=True,
            choice_labels={
                "lower_envelope": "하측 원행 포락선",
                "isotonic": "전체 영향 구간 단조 회귀",
                "median_plateau": "밴드 중앙값 평탄부",
                "linear": "관측 앵커 끝점 직선",
                "least_squares": "밴드 원행 최소제곱 직선",
                "robust_linear": "밴드 원행 Huber 직선",
            },
            choice_help={
                "lower_envelope": (
                    "각 원행에서 오른쪽 앵커까지의 원응력 최솟값을 적용합니다. "
                    "하측 근사라 내부 trough를 낮게 남길 수 있습니다."
                ),
                "isotonic": (
                    "왼쪽 관측 앵커부터 오른쪽 관측 앵커까지 PAVA 최소제곱 단조 적합을 합니다."
                ),
                "median_plateau": (
                    "오른쪽 앵커를 제외한 밴드 core의 중앙값으로 평탄부를 만들고 "
                    "왼쪽 관측 앵커에서 원행 변형률로 연결합니다."
                ),
                "linear": "선택 밴드의 끝과 왼쪽 관측 앵커 두 점만 잇는 직선입니다.",
                "least_squares": (
                    "밴드 core 원행을 같은 가중치로 맞추고 두 관측 앵커 응력 사이에서 "
                    "비감소 직선을 제약합니다."
                ),
                "robust_linear": (
                    "기존 고정-scale Huber IRLS로 밴드 core를 맞추고 관측 앵커 사이에서 "
                    "비감소 직선을 제약합니다."
                ),
            },
        ),
        ParamSpec(
            name="band_start",
            label="밴드 시작 행 위치 (현재 프레임, 0부터)",
            type="int",
            required=True,
            when={"policy": (band_model.MANUAL_POLICY,)},
        ),
        ParamSpec(
            name="band_end",
            label="밴드 끝 앵커 행 위치 (현재 프레임, 0부터)",
            type="int",
            required=True,
            when={"policy": (band_model.MANUAL_POLICY,)},
        ),
        ParamSpec(
            name="peak_row",
            label="선행 봉우리 행 위치 (선택, 0부터)",
            type="int",
            when={"policy": (band_model.MANUAL_POLICY,)},
            help="비우면 band_start 앞 원응력 최댓값의 첫 원행을 사용합니다.",
        ),
        ParamSpec(
            name="left_anchor",
            label="왼쪽 관측 앵커 행 위치 (선택, 0부터)",
            type="int",
            when={"policy": (band_model.MANUAL_POLICY,)},
            help=("비우면 보호 하중구간 뒤, 봉우리 전 마지막 유효 상향 교차를 씁니다."),
        ),
        ParamSpec(
            name="source_elastic_end_index",
            label="원자료 E 끝 원행 위치",
            type="int",
            default="@source_elastic_end_index",
            required=True,
            when={"policy": (band_model.SOURCE_EVENT_POLICY,)},
            links_to="source_elastic_end_index",
            help="source_index_column의 원행 번호와 비교할 원자료의 E 끝 원행 위치입니다.",
        ),
        ParamSpec(
            name="source_index_column",
            label="현재 모델 행의 원행 대응 열",
            type="str",
            role="column",
            default=band_model.DEFAULT_SOURCE_INDEX_COLUMN,
            when={"policy": (band_model.SOURCE_EVENT_POLICY,)},
            unit="1",
            help="model_support가 만든 엄격 증가 정수 원행 대응 열입니다.",
        ),
        ParamSpec(
            name="minimum_band_rows",
            label="자동 밴드 최소 원행 수",
            type="int",
            default=band_model.DEFAULT_MINIMUM_BAND_ROWS,
            when={"policy": band_model.AUTO_POLICIES},
        ),
        ParamSpec(
            name="minimum_progress_span",
            label="자동 밴드 최소 정규화 진행폭",
            type="float",
            default=band_model.DEFAULT_MINIMUM_PROGRESS_SPAN,
            unit="1",
            when={"policy": band_model.AUTO_POLICIES},
        ),
        ParamSpec(
            name="maximum_stress_over_peak",
            label="자동 밴드 최대 응력/봉우리 비율",
            type="float",
            default=band_model.DEFAULT_MAXIMUM_STRESS_OVER_PEAK,
            unit="1",
            when={"policy": band_model.AUTO_POLICIES},
        ),
        ParamSpec(
            name="maximum_range_over_peak",
            label="자동 밴드 응력 범위/봉우리 상한",
            type="float",
            default=band_model.DEFAULT_MAXIMUM_RANGE_OVER_PEAK,
            unit="1",
            when={"policy": band_model.AUTO_POLICIES},
        ),
        ParamSpec(
            name="maximum_gap_over_band_span",
            label="밴드 최대 원행 간격 비율",
            type="float",
            default=band_model.DEFAULT_MAXIMUM_GAP_OVER_BAND_SPAN,
            unit="1",
        ),
        ParamSpec(
            name="loading_floor_fraction",
            label="봉우리 대비 보호 하중 비율",
            type="float",
            default=band_model.DEFAULT_LOADING_FLOOR_FRACTION,
            unit="1",
        ),
        ParamSpec(
            name="strain",
            label="공학 변형률 열",
            type="str",
            role="column",
            default=band_model.DEFAULT_STRAIN,
            unit="1",
            dimension="strain",
        ),
        ParamSpec(
            name="stress",
            label="공학 응력 열",
            type="str",
            role="column",
            default=band_model.DEFAULT_STRESS,
            unit="Pa",
        ),
        ParamSpec(
            name="time",
            label="시간 진행 열 (선택)",
            type="str",
            role="column",
            unit="s",
            help=(
                "초 단위로 엄격 증가할 때만 진행축으로 씁니다. 그 밖에는 변형률로 대체합니다."
            ),
        ),
    ),
    makes_values=(
        Produced("band_model_peak_index", "원응력 최댓값 행 위치", "1"),
        Produced("band_model_band_start_index", "모델 밴드 시작 행 위치", "1"),
        Produced("band_model_band_end_index", "선택 밴드 오른쪽 끝 원행", "1"),
        Produced(
            "band_model_model_end_index",
            "밴드 연결 모델 영향 오른쪽 관측 앵커 행 위치",
            "1",
        ),
        Produced("band_model_released_internal_anchor_count", "해제한 내부 모델 앵커 수", "1"),
        Produced("band_model_lower_composition_count", "하측 연결 조합 수", "1"),
        Produced(
            "band_model_lower_composition_changed_points",
            "하측 연결 조합 신규 구간의 최종 변경 점 수",
            "1",
        ),
        Produced(
            "band_model_lower_composition_max_additional_change",
            "하측 연결 조합 신규 구간 최종 최대 응력 변화",
            "Pa",
        ),
        Produced("band_model_left_anchor_index", "모델 영향 왼쪽 관측 앵커 행 위치", "1"),
        Produced("band_model_support_rows", "밴드 원행 지지 수", "1"),
        Produced("band_model_progress_span", "밴드 정규화 진행폭", "1"),
        Produced("band_model_max_gap_ratio", "밴드 최대 원행 간격 비율", "1"),
        Produced("band_model_changed_points", "모델 단계 변경 점 수", "1"),
        Produced(
            "band_model_peak_depression",
            "원봉우리 행 모델 응력 감소",
            "Pa",
            help=(
                "선택한 모델이 원봉우리 행의 응력을 얼마나 낮췄는지; "
                "물리적 하항복 값이 아닙니다."
            ),
        ),
        Produced("band_model_max_stress_change", "최대 원응력 변경 폭", "Pa"),
        Produced(
            "band_model_source_elastic_end_index",
            "원자료 E 끝 원행 위치",
            "1",
        ),
        Produced(
            "band_model_source_elastic_prefix_end_index",
            "현재 모델 입력에서 E prefix 끝 행 위치",
            "1",
        ),
        Produced(
            "band_model_source_event_recovered_count",
            "검출된 닫힌 회복 사건 수",
            "1",
        ),
        Produced(
            "band_model_source_event_excluded_in_elastic_count",
            "E prefix 안에서 제외한 닫힌 사건 수",
            "1",
        ),
        Produced(
            "band_model_source_event_target_count",
            "E prefix 뒤 적합 대상 닫힌 사건 수",
            "1",
        ),
        Produced(
            "band_model_source_event_fit_region_count",
            "자동 사건 적합 영향 구간 수",
            "1",
        ),
        Produced(
            "band_model_source_event_crossing_noop_count",
            "경계에 편집 행이 없어 그대로 둔 사건 수",
            "1",
        ),
        Produced(
            "band_model_source_event_one_free_row_region_count",
            "관측 자유행이 하나뿐인 퇴화 적합 구간 수",
            "1",
        ),
        Produced(
            "band_model_source_event_bounded_anchor_count",
            "bounded observed anchor 규칙을 쓴 적합 구간 수",
            "1",
        ),
        Produced(
            "band_model_source_event_isotonic_trigger_count",
            "고정 관측 말단 접합 게이트 통과 수",
            "1",
        ),
        Produced(
            "band_model_source_event_isotonic_fit_region_count",
            "등위회귀 적합 연결 성분 수",
            "1",
        ),
        Produced(
            "band_model_source_event_isotonic_released_anchor_count",
            "연결 성분에서 해제한 내부 앵커 수",
            "1",
        ),
        Produced(
            "band_model_source_event_isotonic_changed_points",
            "등위회귀 열린 구간 변경 원행 수",
            "1",
        ),
        Produced(
            "band_model_source_event_isotonic_max_abs_distortion",
            "등위회귀 최대 절대 왜곡",
            "Pa",
        ),
        Produced(
            "band_model_source_event_isotonic_rmse",
            "등위회귀 열린 구간 RMSE",
            "Pa",
        ),
        Produced(
            "band_model_source_event_isotonic_remaining_unedited_declines",
            "적합하지 않은 인접 원행에 남은 하강 수",
            "1",
        ),
        *_MODEL_CARD_EFFECT_VALUES,
    ),
    order=82,
    version="3",
    prepare_options=band_model.prepare_options,
)(band_model.band_model)

register(
    id="tensile.model_curve",
    kind="processing",
    label="소성 모델 공칭곡선",
    applies_to=("tensile",),
    requires_channels=(("displacement",), ("force",)),
    params=(
        ParamSpec(
            name="method",
            label="방법",
            type="choice",
            choices=(model_curve.METHOD,),
            default=model_curve.METHOD,
            choice_labels={model_curve.METHOD: "상측 포락선(자동)"},
            help="모든 입력 행에 원응력의 누적 최댓값을 적용합니다.",
        ),
        ParamSpec(
            name="strain",
            label="변형률 열",
            type="str",
            role="column",
            default=model_curve.DEFAULT_STRAIN,
            unit="1",
            dimension="strain",
        ),
        ParamSpec(
            name="stress",
            label="응력 열",
            type="str",
            role="column",
            default=model_curve.DEFAULT_STRESS,
            unit="Pa",
        ),
    ),
    makes_values=(
        Produced(key="model_curve_changed_points", label="변경 점 수", si_unit="1"),
        Produced(
            key="model_curve_peak_stress",
            label="입력 응력 최댓값",
            si_unit="Pa",
            help="현재 입력 프레임의 선택 응력 열에서 가장 높은 원래 관측값.",
        ),
        Produced(
            key="model_curve_peak_strain",
            label="입력 응력 최댓값 변형률",
            si_unit="1",
            help="현재 입력 프레임에서 응력 최댓값이 처음 나타난 변형률.",
        ),
        Produced(
            key="model_curve_peak_index",
            label="입력 행 위치 (0부터)",
            si_unit="1",
            help="현재 입력 프레임에서 0부터 세는 행 위치이며 Excel 행 번호가 아닙니다.",
        ),
        Produced(key="model_curve_max_raise", label="최대 응력 올림 폭", si_unit="Pa"),
        Produced(key="model_curve_end_raise", label="기록 끝 응력 올림 폭", si_unit="Pa"),
        *_MODEL_CARD_EFFECT_VALUES,
    ),
    order=82,
    version="2",
)(model_curve.model_curve)

register(
    id="tensile.model_anchor",
    kind="processing",
    label="모델 소성 시작점(오프셋)",
    applies_to=("tensile",),
    requires_channels=(("displacement",), ("force",)),
    params=(
        ParamSpec(
            name="offset_strain",
            dimension="strain",
            label="오프셋",
            type="float",
            default=0.002,
            unit="1",
            help="모델 소성 곡선의 시작점을 정할 오프셋. 금속은 보통 0.2%입니다.",
        ),
        ParamSpec(
            name="youngs_modulus",
            label="탄성계수",
            type="float",
            unit="Pa",
            default="@youngs_modulus",
            required=True,
            help=(
                "비우면 앞 단계가 잰 @youngs_modulus 를 씁니다. "
                "숫자나 다른 참조도 지정할 수 있습니다."
            ),
        ),
        ParamSpec(
            name="search_start",
            dimension="strain",
            label="탐색 시작",
            type="float",
            unit="1",
            help="오프셋 직선과 모델 곡선의 교점을 찾을 공칭 변형률 구간 시작.",
        ),
        ParamSpec(
            name="search_end",
            dimension="strain",
            label="탐색 끝",
            type="float",
            unit="1",
            help="비우면 관측 끝까지 탐색합니다.",
        ),
        ParamSpec(
            name="strain",
            label="변형률 열",
            type="str",
            role="column",
            default="strain_engineering",
        ),
        ParamSpec(
            name="stress",
            label="응력 열",
            type="str",
            role="column",
            default="stress_engineering",
        ),
    ),
    makes_values=(
        Produced(
            key="model_proof_stress",
            label="모델 소성 시작 응력",
            si_unit="Pa",
            help="오프셋 교점의 공칭응력. 재료의 Rp 가 아니라 소성 모델 곡선의 시작점입니다.",
        ),
        Produced(
            key="model_proof_strain",
            label="모델 소성 시작 변형률",
            si_unit="1",
            help="모델 소성 시작 응력과 짝지은 오프셋 교점 변형률.",
        ),
        Produced(
            key="model_proof_offset",
            label="모델 소성 시작 오프셋",
            si_unit="1",
            help="모델 소성 시작점을 계산할 때 사용한 오프셋.",
        ),
    ),
    order=85,
    version="1",
    prepare_options=model_anchor.prepare_options,
)(model_anchor.model_anchor)

register(
    id="tensile.plastic_domain",
    kind="processing",
    label="모델 소성 구간",
    applies_to=("tensile",),
    requires_channels=(("displacement",), ("force",)),
    params=(
        ParamSpec(
            name="proof_strain",
            dimension="strain",
            label="모델 소성 시작 변형률",
            type="float",
            unit="1",
            default="@model_proof_strain",
            help="모델 소성 시작점의 변형률 좌표입니다.",
        ),
        ParamSpec(
            name="proof_stress",
            label="모델 소성 시작 응력",
            type="float",
            unit="Pa",
            default="@model_proof_stress",
            help="같은 모델 소성 시작점의 응력이며 현재 곡선 보간값과 대조합니다.",
        ),
        ParamSpec(
            name="end_strain",
            dimension="strain",
            label="소성 구간 끝 변형률",
            type="float",
            unit="1",
            default="@necking_candidate_strain",
            help="기본값은 네킹 후보 변형률입니다. 이 값 이하는 허용됩니다.",
        ),
        ParamSpec(
            name="necking_limit",
            dimension="strain",
            label="네킹 상한 변형률",
            type="float",
            unit="1",
            default="@necking_candidate_strain",
            help=("네킹 후보 변형률을 상한으로 씁니다. end_strain 은 이를 넘을 수 없습니다."),
        ),
        ParamSpec(
            name="strain",
            label="변형률 열",
            type="str",
            role="column",
            default=plastic_domain.DEFAULT_STRAIN,
            unit="1",
            dimension="strain",
        ),
        ParamSpec(
            name="stress",
            label="응력 열",
            type="str",
            role="column",
            default=plastic_domain.DEFAULT_STRESS,
            unit="Pa",
        ),
    ),
    makes_values=(
        Produced(key="plastic_domain_input_points", label="입력 관측점 수", si_unit="1"),
        Produced(
            key="plastic_domain_support_points", label="입력 모델 관측점 수", si_unit="1"
        ),
        Produced(key="plastic_domain_output_points", label="출력 구간 점 수", si_unit="1"),
        Produced(key="plastic_domain_inserted_points", label="삽입 경계점 수", si_unit="1"),
        Produced(
            key="plastic_domain_proof_inserted", label="proof 경계 삽입 여부", si_unit="1"
        ),
        Produced(key="plastic_domain_end_inserted", label="끝 경계 삽입 여부", si_unit="1"),
        Produced(
            key="plastic_domain_proof_strain",
            label="모델 proof 변형률",
            si_unit="1",
        ),
        Produced(key="plastic_domain_proof_stress", label="모델 proof 응력", si_unit="Pa"),
        Produced(
            key="plastic_domain_end_strain",
            label="소성 구간 끝 변형률",
            si_unit="1",
        ),
        Produced(
            key="plastic_domain_necking_limit",
            label="네킹 상한 변형률",
            si_unit="1",
        ),
    ),
    order=87,
    version="1",
    prepare_options=plastic_domain.prepare_options,
)(plastic_domain.plastic_domain)

register(
    id="tensile.effective_card_domain",
    kind="processing",
    label="모델 영향 기반 카드 구간",
    applies_to=("tensile",),
    requires_channels=(("displacement",), ("force",)),
    params=(
        ParamSpec(
            name="policy",
            label="카드 끝 정책",
            type="choice",
            choices=effective_card_domain.POLICIES,
            default=effective_card_domain.DEFAULT_POLICY,
            choice_labels={
                effective_card_domain.UNIFORM_MEASURED_POLICY: "원자료 네킹 후보 끝",
                effective_card_domain.EFFECTIVE_MODEL_POLICY: "원행 모델 영향까지 포함",
                effective_card_domain.MANUAL_POLICY: "관측 끝 행 직접 지정",
            },
            choice_help={
                effective_card_domain.UNIFORM_MEASURED_POLICY: (
                    "기존 plastic_domain 과 같은 원자료 네킹 후보 경계입니다. "
                    "모델 영향 메타데이터가 없어도 사용할 수 있습니다."
                ),
                effective_card_domain.EFFECTIVE_MODEL_POLICY: (
                    "원자료 네킹 후보와 모델 영향의 오른쪽 지지 중 뒤의 경계를 씁니다. "
                    "proof-to-band 전체 구간은 별도 감사 대상이며 이 단계가 보증하지 않습니다."
                ),
                effective_card_domain.MANUAL_POLICY: (
                    "현재 모델 입력 프레임의 관측 끝 행을 포함합니다. 모델 영향 끝보다 "
                    "앞을 고르면 잘린 영향이 진단됩니다."
                ),
            },
            help="카드에 넘길 공학곡선의 끝을 고릅니다.",
        ),
        ParamSpec(
            name="coordinate_assumption",
            label="네킹 뒤 좌표 가정",
            type="choice",
            choices=(effective_card_domain.COORDINATE_ASSUMPTION,),
            default=effective_card_domain.COORDINATE_ASSUMPTION,
            choice_labels={
                effective_card_domain.COORDINATE_ASSUMPTION: (
                    "유효 공학 변형률에서 균일변형 true 좌표로 계산"
                )
            },
            help=(
                "원자료 네킹 후보 뒤까지 포함할 때 저장하는 시뮬레이션 근사 가정입니다. "
                "측정된 국부 응력이나 일정한 완전소성 진응력을 뜻하지 않습니다."
            ),
        ),
        ParamSpec(
            name="proof_strain",
            dimension="strain",
            label="모델 proof 변형률",
            type="float",
            unit="1",
            default="@model_proof_strain",
            required=True,
        ),
        ParamSpec(
            name="proof_stress",
            label="모델 proof 응력",
            type="float",
            unit="Pa",
            default="@model_proof_stress",
            required=True,
        ),
        ParamSpec(
            name="source_necking_strain",
            dimension="strain",
            label="원자료 네킹 후보 변형률",
            type="float",
            unit="1",
            default="@necking_candidate_strain",
            required=True,
            links_to="necking_candidate_strain",
            help="원자료에서 계산한 네킹 후보이며, 계산용 카드 상한과 별도 보존합니다.",
        ),
        ParamSpec(
            name="effect_end_index",
            label="모델 영향 끝 행",
            type="int",
            default="@model_card_effect_end_index",
            required=True,
            when={
                "policy": (
                    effective_card_domain.EFFECTIVE_MODEL_POLICY,
                    effective_card_domain.MANUAL_POLICY,
                )
            },
            links_to="model_card_effect_end_index",
        ),
        ParamSpec(
            name="effect_end_strain",
            dimension="strain",
            label="모델 영향 끝 변형률",
            type="float",
            unit="1",
            default="@model_card_effect_end_strain",
            required=True,
            when={
                "policy": (
                    effective_card_domain.EFFECTIVE_MODEL_POLICY,
                    effective_card_domain.MANUAL_POLICY,
                )
            },
            links_to="model_card_effect_end_strain",
        ),
        ParamSpec(
            name="model_input_points",
            label="모델 단계 입력 행 수",
            type="int",
            unit="1",
            default="@model_card_input_points",
            required=True,
            when={
                "policy": (
                    effective_card_domain.EFFECTIVE_MODEL_POLICY,
                    effective_card_domain.MANUAL_POLICY,
                )
            },
            links_to="model_card_input_points",
        ),
        ParamSpec(
            name="end_index",
            label="카드 끝 관측행 (현재 모델 프레임, 0부터)",
            type="int",
            required=True,
            when={"policy": (effective_card_domain.MANUAL_POLICY,)},
            help="선택한 관측행을 포함합니다. 원본 취득행 식별자로 보지 않습니다.",
        ),
        ParamSpec(
            name="strain",
            label="공학 변형률 열",
            type="str",
            role="column",
            default=effective_card_domain.DEFAULT_STRAIN,
            unit="1",
            dimension="strain",
        ),
        ParamSpec(
            name="stress",
            label="공학 응력 열",
            type="str",
            role="column",
            default=effective_card_domain.DEFAULT_STRESS,
            unit="Pa",
        ),
    ),
    makes_values=(
        Produced(
            "plastic_domain_input_points",
            "입력 관측점 수",
            "1",
            help="기존 plastic_domain 진단을 그대로 보존합니다.",
        ),
        Produced("plastic_domain_support_points", "입력 모델 관측점 수", "1"),
        Produced("plastic_domain_output_points", "출력 구간 점 수", "1"),
        Produced("plastic_domain_inserted_points", "삽입 경계점 수", "1"),
        Produced("plastic_domain_proof_inserted", "proof 경계 삽입 여부", "1"),
        Produced("plastic_domain_end_inserted", "끝 경계 삽입 여부", "1"),
        Produced("plastic_domain_proof_strain", "모델 proof 변형률", "1"),
        Produced("plastic_domain_proof_stress", "모델 proof 응력", "Pa"),
        Produced("plastic_domain_end_strain", "소성 구간 끝 변형률", "1"),
        Produced(
            "plastic_domain_necking_limit",
            "카드 계산 상한 변형률",
            "1",
            help=(
                "카드 구간을 자르는 계산용 상한입니다. 원자료 네킹 후보는 "
                "card_domain_source_necking_strain 에 별도로 기록됩니다."
            ),
        ),
        Produced("card_domain_source_necking_strain", "원자료 네킹 후보 변형률", "1"),
        Produced("card_domain_end_index", "카드 끝 관측 모델 행", "1"),
        Produced("card_domain_end_strain", "카드 끝 공학 변형률", "1"),
        Produced("card_domain_end_stress", "카드 끝 공학 응력", "Pa"),
        Produced("card_domain_effect_end_index", "모델 영향 끝 관측 모델 행", "1"),
        Produced("card_domain_effect_end_strain", "모델 영향 끝 공학 변형률", "1"),
        Produced("card_domain_effect_info_known", "모델 영향 메타데이터 제공 여부", "1"),
        Produced("card_domain_beyond_source_neck", "원자료 네킹 후보 뒤 카드 끝 여부", "1"),
        Produced("card_domain_effect_truncated", "모델 영향 지지 끝 전 카드 종료 여부", "1"),
        Produced(
            "card_domain_effect_truncation_deliberate",
            "수동 끝 지정으로 모델 영향이 실제 잘렸는지 여부",
            "1",
        ),
        Produced("card_domain_model_input_points", "모델 단계 입력 관측점 수", "1"),
        Produced("card_domain_last_input_strain", "마지막 모델 입력 변형률", "1"),
    ),
    order=87,
    version="1",
    prepare_options=effective_card_domain.prepare_options,
)(effective_card_domain.effective_card_domain)

register(
    id="tensile.temperature_family",
    kind="grouping",
    label="온도별 소성 곡선",
    applies_to=("tensile",),
    requires_channels=(("displacement",), ("force",)),
    params=(
        ParamSpec(
            name="bin_kelvin",
            label="같은 온도로 볼 폭",
            type="float",
            unit="K",
            default=5.0,
            help=(
                "온도가 이 폭 안에서 다르면 같은 온도로 묶음. 5 면 296 과 299 는 한 묶음. "
                "장비가 목표 온도를 정확히 재현하지 못하므로 0 이면 시편마다 따로 섬."
            ),
        ),
        ParamSpec(
            name="levels",
            label="응력비를 읽을 변형률",
            type="str",
            default=temperature.DEFAULT_LEVELS,
            dimension="strain",
            help=(
                "이 진소성변형률들에서 기준 온도 대비 응력비를 읽음. 쉼표로 구분. "
                "첫 값에서 연화 기울기(dσ/dT)도 냄."
            ),
        ),
        ParamSpec(
            name="model",
            label="온도 연화 식",
            type="choice",
            choices=temperature.MODELS,
            default="none",
            choice_labels={"none": "식 없이 표만", "johnson_cook": "Johnson-Cook (m 만)"},
            choice_help={
                "none": "온도별 표만 산출. 솔버가 표를 그대로 받으면 충분.",
                "johnson_cook": (
                    "σ/σ₀ = 1 - T*^m, T* = (T-T₀)/(T_melt-T₀). 기준 온도 T₀ 는 가장 낮은 "
                    "묶음, 녹는점은 아래 칸. 응력이 안 내린 온도는 못 넣음."
                ),
            },
            help="온도별 표에 더해 응력비를 식으로 요약할지 여부.",
        ),
        ParamSpec(
            name="melt_temperature",
            label="녹는점",
            type="float",
            unit="K",
            default=0.0,
            help=(
                "Johnson-Cook 을 고를 때만. 기준 온도보다 커야 함"
                "(강 ≈ 1,800 K, 알루미늄 ≈ 930 K)."
            ),
        ),
    ),
    makes_values=(
        Produced(key="temperature_count", label="온도 묶음 수", si_unit="1"),
        Produced(key="reference_temperature", label="기준 온도", si_unit="K"),
        Produced(key="temperature_min", label="가장 낮은 온도", si_unit="K"),
        Produced(key="temperature_max", label="가장 높은 온도", si_unit="K"),
        Produced(
            key="softening_slope",
            label="온도 연화 기울기",
            si_unit="Pa/K",
            help="첫 변형률에서 읽은 응력의 온도에 대한 기울기(최소제곱). 음수면 연화.",
        ),
        Produced(key="softening_r_squared", label="기울기의 R²", si_unit="1"),
        Produced(key="jc_m", label="Johnson-Cook m", si_unit="1"),
        Produced(key="model_r_squared", label="식의 R²", si_unit="1"),
    ),
    # **구성원을 모으는 법을 선언한다.** 채택된 결과의 두 열과 시험 조건의 온도.
    # 파이썬 수집기가 없어도 grouping 이 이 선언을 읽는다(`app/modules/grouping`).
    # `register` 의 남는 키워드는 `Plugin.meta` 로 간다.
    members={
        "from": "adopted_result",
        "columns": [temperature.PLASTIC_STRAIN, temperature.TRUE_STRESS],
        "conditions": [temperature.TEMPERATURE],
    },
    # **카드를 만드는 법도 선언한다.** 묶음 결과(값·상세·경고)를 블록으로 바꾸는
    # 함수 — 재료·탄성·계보는 중심의 공용 길(`/fitting/cards/from-group`)이 맡는다.
    card=temperature.card_blocks,
    order=25,
    version="2",
)(temperature.temperature_family)
