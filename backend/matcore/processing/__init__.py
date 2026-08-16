"""처리 파이프라인 — 원본 곡선을 물성 계산이 쓸 수 있는 곡선으로 바꾼다.

**장비가 주는 것과 물성이 필요한 것 사이에는 늘 변환이 있다.** Zwick 인장기가
주는 것은 변위(m)·하중(N)·시편폭(m)이다. 응력-변형률이 아니다. 그것을 공칭으로
바꾸고, 정렬하고, 탄성계수를 재고, 0.2% 오프셋으로 항복을 잡고, 진응력으로
바꾸는 일이 전부 여기에 있다.

## 이 패키지가 지키는 것

**추정하지 않는다.** 65 의 처리 도메인에서 가장 잘 만들어진 부분이 이 태도였고
그대로 가져왔다. 0.2% 오프셋 선이 관측 구간과 만나지 않으면 외삽해서 값을
만들어 내지 않고 **실패한다.** 네킹은 후보만 제시하고 **아무것도 자르지 않는다.**
그럴듯한 숫자를 만들어 내는 것이 이 도메인에서 가장 비싼 결함이다 — 틀린 항복강도는
그럴듯해 보이고, 그 값으로 적합한 소성 모델이 해석에 들어간다.

**모든 단계가 근거를 남긴다.** `notes` 는 장식이 아니다. "무슨 방법으로 어느
구간에서 몇 점을 써서 구했는가" 가 결과와 함께 저장돼야, 반년 뒤에 "이 E 값이
왜 이렇지" 를 답할 수 있다.

**단계는 원본을 고치지 않는다.** 각 단계가 새 `Frame` 을 낸다. 파이프라인은
단계마다의 결과를 다 들고 있어서, 화면이 "정렬 전/후" 를 나란히 보여 줄 수 있다.

## 왜 플러그인인가

새 처리를 추가하는 것이 **함수 하나 + `@register`** 로 끝나야 한다(D7). 65 는
물성 6종을 4계층 슬라이스로 복제해 131파일 44k줄이 됐다. 여기서는 계산이
레지스트리에 등록되면 API 의 목록·화면의 폼·결과 저장이 전부 따라온다 —
`ParamSpec` 이 곧 화면의 입력 칸이다.

DB 도 HTTP 도 모른다. `tests/architecture` 가 검사한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from matcore import registry


class ProcessingError(Exception):
    """이 단계를 이 입력에 적용할 수 없다.

    메시지는 **사용자가 읽는다.** "무엇을 기대했는데 무엇이 왔는지" 를 적는다 —
    '처리 실패' 만 남기면 다음 사람이 숫자를 직접 들여다봐야 한다.
    """


@dataclass(frozen=True)
class Frame:
    """곡선 한 벌. 열 이름 → 값, 그리고 열 이름 → SI 단위.

    `columns` 의 키는 채널 키(`displacement`·`force`)이거나 이 패키지가 만들어
    낸 파생 열(`stress_engineering`)이다. **값은 언제나 SI 다** — 이 패키지는
    단위 변환을 하지 않는다. 그것은 파서와 `matcore.units` 의 일이고, 여기까지
    온 숫자는 이미 SI 라고 믿는다. 믿지 못하면 두 곳에서 변환하게 되고, 그때
    10⁶ 배 어긋나는 종류의 사고가 난다.
    """

    columns: dict[str, np.ndarray]
    units: dict[str, str]

    def require(self, key: str, *, what: str) -> np.ndarray:
        column = self.columns.get(key)
        if column is None:
            available = ", ".join(sorted(self.columns)) or "(없음)"
            raise ProcessingError(
                f"{what} 로 쓸 열이 없습니다: '{key}'. 이 곡선에 있는 열: {available}"
            )
        return column

    def with_columns(self, added: dict[str, np.ndarray], units: dict[str, str]) -> Frame:
        return Frame({**self.columns, **added}, {**self.units, **units})

    def select(self, mask_or_index: np.ndarray) -> Frame:
        """모든 열에 같은 선택을 적용한다.

        열마다 따로 자르면 **길이가 어긋난 채로 저장된다.** 그 곡선은 그려지긴
        하는데 x 와 y 가 다른 점을 가리킨다 — 조용히 틀린 그림이 된다.
        """
        return Frame(
            {key: value[mask_or_index] for key, value in self.columns.items()},
            dict(self.units),
        )

    def length(self) -> int:
        return len(next(iter(self.columns.values()))) if self.columns else 0


@dataclass(frozen=True)
class Scalar:
    """단계가 낸 값 하나 — 탄성계수·항복강도처럼 곡선이 아닌 결과.

    `si_unit` 을 값과 함께 들고 다니는 이유는 ADR 0004 와 같다. 라벨에 단위를
    적어 두면 라벨을 고치는 순간 뜻이 바뀐다.
    """

    key: str
    label: str
    value: float
    si_unit: str


@dataclass(frozen=True)
class StepResult:
    """한 단계의 결과. 곡선이 안 바뀌는 단계(측정만 하는 단계)도 있다."""

    frame: Frame
    notes: tuple[str, ...] = ()
    scalars: tuple[Scalar, ...] = ()


@dataclass(frozen=True)
class Step:
    """레시피의 한 줄. **데이터다** — DB 에 JSON 으로 저장된다."""

    plugin: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Stage:
    """단계 하나가 끝난 시점의 상태. 화면이 전/후를 나란히 보여 주는 근거다."""

    index: int
    plugin: str
    label: str
    version: str
    options: dict[str, Any]
    frame: Frame
    notes: tuple[str, ...]
    scalars: tuple[Scalar, ...]


@dataclass(frozen=True)
class PipelineResult:
    stages: tuple[Stage, ...]

    @property
    def frame(self) -> Frame:
        if not self.stages:
            raise ProcessingError("적용된 단계가 없습니다.")
        return self.stages[-1].frame

    @property
    def scalars(self) -> tuple[Scalar, ...]:
        """모든 단계의 스칼라를 순서대로. 뒤 단계가 같은 키를 내면 **뒤가 이긴다**
        — 사람이 방법을 바꿔 다시 재는 것이 정상이고, 그때 앞의 값이 남아 있으면
        어느 것이 최종인지 알 수 없다."""
        merged: dict[str, Scalar] = {}
        for stage in self.stages:
            for scalar in stage.scalars:
                merged[scalar.key] = scalar
        return tuple(merged.values())

    @property
    def notes(self) -> tuple[str, ...]:
        return tuple(note for stage in self.stages for note in stage.notes)


def apply(steps: list[Step], frame: Frame) -> PipelineResult:
    """레시피를 순서대로 적용한다.

    **실패하면 거기서 멈춘다.** 남은 단계를 건너뛰고 계속하지 않는다 — 뒤 단계는
    앞 단계의 결과를 전제로 하므로, 하나가 빠진 채로 나온 값은 틀린 값이면서
    틀린 티가 안 난다.

    어느 단계에서 왜 멈췄는지는 예외 메시지에 단계 번호와 함께 남는다.
    """
    stages: list[Stage] = []
    current = frame
    carried: dict[str, Scalar] = {}
    for index, step in enumerate(steps):
        plugin = _plugin(step.plugin)
        options = _resolve_references(step.options, carried, index)
        try:
            result = plugin.fn(current, options)
        except ProcessingError as exc:
            raise ProcessingError(f"{index + 1}단계 '{plugin.label}': {exc}") from exc
        stages.append(
            Stage(
                index=index,
                plugin=plugin.id,
                label=plugin.label,
                version=plugin.version,
                options=options,
                frame=result.frame,
                notes=result.notes,
                scalars=result.scalars,
            )
        )
        for scalar in result.scalars:
            carried[scalar.key] = scalar
        current = result.frame
    return PipelineResult(tuple(stages))


#: 앞 단계가 낸 값을 가리키는 표기. `{"youngs_modulus": "@youngs_modulus"}`
REFERENCE_PREFIX = "@"


def _resolve_references(
    options: dict[str, Any], carried: dict[str, Scalar], index: int
) -> dict[str, Any]:
    """`"@youngs_modulus"` 를 앞 단계가 낸 값으로 바꾼다.

    **왜 표기를 만들었나.** 항복강도는 탄성계수를 입력으로 받는데, 그 값은 바로
    앞 단계가 방금 잰 것이다. 사람이 손으로 옮겨 적게 하면 두 값이 어긋나는
    순간이 반드시 오고 — 방법을 바꿔 E 를 다시 쟀는데 항복강도는 옛 E 로 계산된
    채 남는다 — 그 결과는 그럴듯해 보인다.

    숨은 규약(뒤 단계가 알아서 앞 값을 쓴다)으로 하지 않은 이유: 레시피는 DB 에
    JSON 으로 저장되고 사람이 읽는다. `"@youngs_modulus"` 라고 적혀 있으면 무엇을
    참조하는지 보이지만, 규약은 코드를 읽어야 안다.
    """
    resolved: dict[str, Any] = {}
    for key, value in options.items():
        if not isinstance(value, str) or not value.startswith(REFERENCE_PREFIX):
            resolved[key] = value
            continue
        name = value[len(REFERENCE_PREFIX) :]
        scalar = carried.get(name)
        if scalar is None:
            available = ", ".join(sorted(carried)) or "(아직 없음)"
            raise ProcessingError(
                f"{index + 1}단계: '{value}' 가 가리키는 값을 앞 단계가 내지 않았습니다. "
                f"지금까지 나온 값: {available}. 그 값을 내는 단계를 앞에 두세요."
            )
        resolved[key] = scalar.value
    return resolved


def _plugin(plugin_id: str) -> registry.Plugin:
    try:
        plugin = registry.get(plugin_id)
    except KeyError:
        raise ProcessingError(
            f"등록되지 않은 처리 단계입니다: {plugin_id}. "
            f"처리는 **코드**입니다 — 정의만으로는 만들 수 없습니다."
        ) from None
    if plugin.kind != "processing":
        raise ProcessingError(f"처리 단계가 아닙니다: {plugin_id} ({plugin.kind})")
    return plugin


# --- 단계 구현이 함께 쓰는 것 -------------------------------------------------


def option_float(options: dict[str, Any], key: str, default: float | None = None) -> float:
    raw = options.get(key, default)
    if raw is None:
        raise ProcessingError(f"'{key}' 값이 필요합니다.")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ProcessingError(f"'{key}' 는 숫자여야 합니다: {raw!r}") from None
    if not np.isfinite(value):
        raise ProcessingError(f"'{key}' 가 유한하지 않습니다: {raw!r}")
    return value


def option_int(options: dict[str, Any], key: str, default: int | None = None) -> int:
    raw = options.get(key, default)
    if raw is None:
        raise ProcessingError(f"'{key}' 값이 필요합니다.")
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ProcessingError(f"'{key}' 는 정수여야 합니다: {raw!r}") from None


def option_text(options: dict[str, Any], key: str, allowed: tuple[str, ...]) -> str:
    raw = options.get(key, allowed[0] if allowed else None)
    if raw is None:
        raise ProcessingError(f"'{key}' 값이 필요합니다.")
    value = str(raw)
    if allowed and value not in allowed:
        raise ProcessingError(f"'{key}' 는 {', '.join(allowed)} 중 하나여야 합니다: {value}")
    return value


def require_increasing(x: np.ndarray, *, what: str) -> None:
    """단조 증가인가.

    보간·교점 계산이 전부 이것을 전제한다. 확인하지 않고 `np.interp` 를 부르면
    **오류 없이 엉뚱한 값**이 나온다 — numpy 는 정렬을 검사하지 않는다. 그래서
    거의 모든 단계 앞에 `curve.sort_unique` 를 두게 된다.
    """
    if len(x) < 2:
        raise ProcessingError(f"{what} 이 2점 미만입니다. 계산할 것이 없습니다.")
    if np.any(np.diff(x) <= 0):
        raise ProcessingError(
            f"{what} 이 단조 증가가 아닙니다. 'curve.sort_unique' 를 먼저 적용하세요 — "
            f"보간과 교점 계산이 정렬을 전제합니다."
        )


def load_builtin() -> None:
    """내장 처리 단계를 레지스트리에 등록한다.

    import 부작용에 기대지 않고 명시적으로 부른다 — `parsers.load_builtin` 과
    같은 이유다. 워커와 테스트가 같은 함수를 부르면 "테스트에서는 되는데 워커에서는
    단계가 없다" 는 어긋남이 생기지 않는다.
    """
    from matcore.processing import common, tensile  # noqa: F401


__all__ = [
    "Frame",
    "PipelineResult",
    "ProcessingError",
    "Scalar",
    "Stage",
    "Step",
    "StepResult",
    "apply",
    "load_builtin",
    "option_float",
    "option_int",
    "option_text",
    "replace",
    "require_increasing",
]
