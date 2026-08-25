"""플러그인 레지스트리 — D7("정의는 데이터, 계산은 플러그인")의 계산 쪽.

65는 물성 6종을 4계층에 걸친 슬라이스로 복제해 131파일 44k줄이 됐다. 여기서는
계산 하나가 함수 하나이고, 등록하면 API·화면·익스포트가 따라온다.

이 패키지 전체가 DB도 HTTP도 모른다. tests/architecture가 이를 검사한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

Kind = Literal["parser", "processing", "statistics", "fitting", "export"]


@dataclass(frozen=True)
class ParamSpec:
    """사용자가 조절하는 값 하나. 화면의 폼 필드가 여기서 생성된다."""

    name: str
    label: str
    type: Literal["float", "int", "bool", "str", "choice"]
    default: Any = None
    choices: tuple[str, ...] = ()
    choice_labels: dict[str, str] = field(default_factory=dict)
    """고를 값 → 사람이 읽는 이름. **값 자체는 안 바꾼다.**

    `linear_regression` 은 레시피 JSON 에 저장되고 결과 스냅샷에도 남는 계약이다.
    그것을 한국어로 바꾸면 저장된 레시피가 전부 깨진다. 그래서 값은 그대로 두고
    화면에 보여 줄 이름만 따로 둔다 — `TestType.key`/`label` 을 나눈 것과 같다."""
    unit: str | None = None
    """**저장 단위(SI)** 다. 화면은 실무 단위로 보여 주고 받는다 — CAE 는 길이를
    mm 로 쓰고, `0.05` 를 치라고 하면 사람이 `50` 을 친다. 환산은 화면이 한다."""
    dimension: str | None = None
    """물리 차원. **단위만으로는 못 가르는 것이 있다.**

    변형률과 tan δ 는 저장 단위가 둘 다 `1` 이다(둘 다 무차원이라 맞다). 그런데
    사람은 변형률을 `0.2%` 로 읽지 `0.002` 로 읽지 않고, tan δ 는 그 반대다.
    0.2% 오프셋은 규격에도 그렇게 적혀 있다. 화면이 어느 쪽인지 알려면 차원이
    필요하다(`matcore/units.DIMENSION_ALIASES` 와 같은 이유)."""
    help: str | None = None
    required: bool = False
    """**비면 계산이 실패하는 칸.**

    `option_float(options, "gauge_length")` 처럼 기본값 없이 읽는 칸이다. 화면이
    이걸 모르면 "무엇을 더 채워야 하는가" 를 추측해야 하고, 추측은 틀린다 —
    빈 칸이 정상인 칸도 많다(`curve.resample` 의 시작·끝은 비우면 관측 범위).

    `when` 이 걸린 칸은 **그 조건일 때만** 필수다. 방법이 '직접 입력' 이 아니면
    `manual_modulus` 는 아무 데도 안 쓰인다."""
    links_to: str | None = None
    """이 칸에 이어 붙일 수 있는 **앞 단계의 값 이름.**

    비면 **칸 이름과 같은 이름**을 찾는다 — `youngs_modulus` 칸이 앞 단계의
    `youngs_modulus` 를 집는 것이 그 경우다. 이름이 다를 때만 적는다.

    실제로 그 자리가 있었다: 네킹 경계를 자르는 `manual_index` 칸은 앞 단계가
    낸 `necking_candidate_index` 를 받아야 하는데 이름이 달라서 **화면에 이어
    붙이기 단추가 안 떴다.** 사람이 후보 index 를 눈으로 보고 손으로 옮겨
    적어야 했고, 그러면 곡선을 다시 처리했을 때 **옛 index 가 남는다** — 그
    결과는 그럴듯해 보인다. `@youngs_modulus` 를 만든 이유와 같다."""

    role: Literal["column"] | None = None
    """이 칸이 **프레임의 열 이름**을 받는가.

    화면이 자유 입력 대신 목록을 내야 하는 칸이 어느 것인지 여기서 안다. 전에는
    프론트에 `['x','column','strain','stress',...]` 를 적어 뒀는데, 열을 받는 칸을
    가진 계산을 새로 만들면 그 목록에도 이름을 더해야 했다 — 안 더하면 자유
    입력이 되고, 오타 하나가 '열이 없습니다' 로 끝난다.

    `ParamSpec` 이 곧 화면의 칸이라는 D7 의 약속이 깨지는 자리가 정확히 거기였다."""
    when: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """이 칸이 **쓰이는 조건**. `{"method": ("manual",)}` 이면 방법이 `manual`
    일 때만 쓰인다.

    없으면 화면이 안 쓰는 칸까지 늘 보여 준다 — 탄성계수를 구간으로 재는데
    '직접 입력' 칸이 옆에 살아 있으면, 거기 넣은 숫자가 무시된다는 것을 알
    방법이 없다. 값을 넣었는데 아무 일도 안 일어나는 것이 가장 나쁘다.

    기존 앱(MaterialAppVer2)도 같은 것을 갖고 있었다 — `option.json` 의
    `enabled`/`disabled` 목록이 그것이다. 방법마다 쓰는 칸이 다른 것은 이
    도메인의 성질이지 화면의 사정이 아니다."""


@dataclass(frozen=True)
class Produced:
    """이 계산이 만들어 내는 것 하나 — 열이거나 값이다.

    **이름만 적으면 화면이 `strain_true_plastic` 을 그대로 보여 준다.** 그것이
    무엇인지는 코드를 읽어야 알 수 있고, 그러면 아무도 안 읽는다. 이름을 정하는
    자리에서 뜻도 같이 적는다.

    `key` 에 `{param}` 이 있으면 그 단계 옵션의 값으로 치환한다 — 평활은
    무엇을 평활했느냐에 따라 열 이름이 달라진다.
    """

    key: str
    label: str
    si_unit: str = "1"
    """**저장 단위(SI)** 다. 화면은 실무 단위로 바꿔 보여 준다."""
    help: str | None = None
    """무엇인지·어떻게 만들어졌는지 한 줄. 화면의 변수 목록에 그대로 뜬다."""


@dataclass(frozen=True)
class Plugin:
    id: str
    kind: Kind
    label: str
    fn: Callable[..., Any]
    produces: str | None = None
    """이 계산이 내는 것의 종류. 지금은 파서만 쓴다(`"curve"`).

    처리 단계는 이것 대신 `makes_columns`·`makes_values` 로 **무엇을 만드는지
    낱낱이** 선언한다 — 종류 하나로는 화면이 "지금 고를 수 있는 열" 을 못 만든다.

    한때 짝으로 `inputs` 가 있었는데 **아무도 채우지 않고 아무도 읽지 않았다.**
    v1.18.0 이 그 상태를 두고 *"있는 줄 알았던 것이 없었다"* 라고 적었고, 그때
    대체품(`makes_columns`·`order`·`ParamSpec.role`)을 만들면서도 원본은 안 지웠다.
    지금 지운다 — 남겨 두면 다음 사람이 또 "의존성 검사가 있구나" 하고 믿는다."""
    params: tuple[ParamSpec, ...] = ()
    applies_to: tuple[str, ...] = ()
    """적용 가능한 재료군·시험종류. 비어 있으면 제한 없음."""
    makes_columns: tuple[Produced, ...] = ()
    """이 단계가 프레임에 **새로 더하는 열**.

    없으면 화면이 "지금 고를 수 있는 열" 을 알 방법이 없다. 실제로 그랬다 —
    장비가 준 것은 변위·하중·폭뿐이라, 인장강도 단계의 '변형률 열' 목록에
    `strain_engineering` 이 없었다. 그 열은 **앞 단계가 만드는 것**이라 한 번
    돌려 보기 전에는 존재하지 않는다. 돌려 보려면 골라야 하고 고르려면 돌려
    봐야 하는 자리였다.

    `{param}` 은 그 단계 옵션의 값으로 치환한다 — 평활은 `{column}_smoothed`
    를 만들므로 무엇을 평활했느냐에 따라 열 이름이 달라진다."""
    makes_values: tuple[Produced, ...] = ()
    """이 단계가 내는 스칼라 키(`youngs_modulus` 등). 뒤 단계가 `@` 로 가리킨다.

    화면이 "탄성계수를 먼저 골라야 오프셋 항복강도를 쓸 수 있다" 를 말하려면
    누가 그 값을 만드는지 알아야 한다."""
    order: int = 100
    """권장 순서. **작을수록 앞.** 화면이 순서도를 이 값으로 세운다.

    순서는 화면의 사정이 아니라 **계산의 성질**이다 — 공칭 변환 없이는 변형률
    열이 없고, 재샘플을 앞에 두면 그 뒤 계산이 전부 보간된 점으로 돈다."""
    version: str = "1"
    """계산이 바뀌면 올린다. 결과 아티팩트에 기록해 재현 가능성을 남긴다."""
    meta: dict[str, Any] = field(default_factory=dict)


_REGISTRY: dict[str, Plugin] = {}


def register(
    *,
    id: str,
    kind: Kind,
    label: str,
    produces: str | None = None,
    params: tuple[ParamSpec, ...] = (),
    applies_to: tuple[str, ...] = (),
    makes_columns: tuple[Produced, ...] = (),
    makes_values: tuple[Produced, ...] = (),
    order: int = 100,
    version: str = "1",
    **meta: Any,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """계산 함수를 레지스트리에 등록한다.

    >>> @register(id="metal.voce", kind="fitting", label="Voce 경화식")
    ... def fit_voce(curve, opts): ...
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if id in _REGISTRY:
            raise ValueError(f"플러그인 id 중복: {id}")
        _REGISTRY[id] = Plugin(
            id=id,
            kind=kind,
            label=label,
            fn=fn,
            produces=produces,
            params=params,
            applies_to=applies_to,
            makes_columns=makes_columns,
            makes_values=makes_values,
            order=order,
            version=version,
            meta=meta,
        )
        return fn

    return decorator


def get(plugin_id: str) -> Plugin:
    try:
        return _REGISTRY[plugin_id]
    except KeyError:
        raise KeyError(f"등록되지 않은 플러그인: {plugin_id}") from None


def list_plugins(kind: Kind | None = None, applies_to: str | None = None) -> list[Plugin]:
    items = [p for p in _REGISTRY.values() if kind is None or p.kind == kind]
    if applies_to is not None:
        items = [p for p in items if not p.applies_to or applies_to in p.applies_to]
    # **권장 순서로 낸다.** 화면이 순서도를 이 순서로 세우고, 사람이 단계를
    # 고르는 순서도 이것이다 — 목록이 알파벳순이면 `curve.crop` 이 맨 앞에 오고
    # 공칭 변환이 가운데 묻힌다.
    return sorted(items, key=lambda p: (p.order, p.id))


def clear() -> None:
    """테스트 전용."""
    _REGISTRY.clear()
