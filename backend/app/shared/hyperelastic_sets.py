"""파라미터 벌 → **초탄성 블록** — 문헌 덱과 사내 카드가 같은 길로(2026-10-08).

문헌 카탈로그에는 초탄성 벌이 450값 · 52재료 있다(Ecoflex · NBR · EPDM 실 · 폼). 덱 렌더러는
초탄성 블록(`hyperelastic`)을 읽는데, 그 벌은 모델 파라미터(ADR 0029)로만 들어와서 덱까지 가는
길이 없었다. 옮기는 규칙은 `matcore.cards.hyperelastic.from_parameter_set` 하나다 — 항 이름이
출처마다 달라(`C10` · `C1` · `mu`) 그 판단을 두 곳에 두면 갈린다.

## 벌이 여럿이면

문헌 재료 하나에 식 · 시험 모드 · 맞춘 변형 범위 · 노화 조건이 다른 벌이 여럿인 것이 흔하다.
문헌 덱은 고를 화면이 없어서 **정한 차례로 하나를 고르고 나머지를 각주로 말한다**:

    ① 큰 변형에서 안정한 것   기본값 범위(인장 100 % · 압축 50 % · 등이축 · 평면 전단 50 %)
    ② 등급이 좋은 것
    ③ 시험 모드             여러 모드 > 인장 = 모름 > 기타 > 이축 · 전단 > 압축
    ④ 모드 밖의 조건이 없는 것(노화 · 온도 …)
    ⑤ 항이 많은 식          Yeoh > 2차 다항식 > Mooney-Rivlin > Neo-Hookean

**①③ 은 2026-10-23 에 더했다.** 전에는 ②④⑤ 가 같으면 이름표(`yeoh_3/series-<uuid>`)가 정했다 —
Ecoflex 00-20 의 인장 Yeoh 와 압축 Yeoh 가 그렇게 갈려 **uuid 글자 순서로 압축이 뽑혔고**,
그 벌은 인장 33 % 에서 불안정했다(Mold Max 14NV · FsCO-BMI689 도 같았다). 덱은 어떤 하중이
걸릴지 모르고 만드는 기본값이라, 한 모드로만 맞춘 벌 가운데서는 인장 쪽이 덜 빗나간다. 압축
벌은 버리지 않는다 — 압축 부품(가스켓 · 패드)에는 그쪽이 맞으니 사내 재료로 받아 카드에서
고른다(사내 카드는 사람이 고른 벌만 쓰고, 불안정하면 근거에 적는다).

**단위**: 벌의 항 단위 칸이 비어 있으면 정의의 단위를 쓴다(`catalog.parameters.unit_of`) —
초탄성 계수는 정의가 Pa 다.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.modules.catalog import parameters
from app.modules.catalog.models import QUALITY_TIERS
from matcore.cards.hyperelastic import FromSet, Stability, from_parameter_set, stability
from matcore.export import initial_shear
from matcore.fitting.hyperelastic import COMPRESSION, TENSION

#: 초탄성 계수가 사는 문헌 키. 지수(`hyperelastic_exponent`)는 Ogden · Arruda-Boyce 의 것이라
#: 덱이 받는 식(Neo-Hookean · Mooney-Rivlin · Yeoh)에는 안 쓰인다.
COEFFICIENT_KEY = "mechanical.hyperelastic_coefficient"
BLOCK = "hyperelastic"

#: 사람이 읽는 식 이름.
FAMILY_LABELS = {
    "neo_hookean": "Neo-Hookean",
    "mooney_rivlin": "Mooney-Rivlin",
    "yeoh": "Yeoh",
    "ogden_1": "Ogden (N=1)",
    "polynomial_2": "다항식 (N=2)",
}
#: 여럿일 때 앞서는 식 — 항이 많은 쪽이 큰 변형을 더 잘 따른다. 2차 다항식은 Yeoh 뒤다 —
#: 항은 더 많아도 I₂ 항이 섞이면 큰 변형에서 불안정해지기 쉽다(Yeoh 는 계수가 양이면 안정).
RICHNESS = {"yeoh": 0, "polynomial_2": 1, "mooney_rivlin": 2, "neo_hookean": 3}

#: 시험 모드를 적는 조건 칸 — 출처마다 이름이 다르다(개발 DB: `mode` 289 · `deformation_mode`
#: 44 · `test_method` 46, 글은 `tension` · `uniaxial_tension` · `uniaxial tension` …). 앞의
#: 칸이 이긴다. `test_method` 는 자유 글이라 낱말로만 읽는다.
MODE_KEYS = ("mode", "deformation_mode", "test_mode", "loading_mode", "test_method")
#: 모드 → (화면 이름, 차례). 모름은 인장과 같은 자리다 — 제품 문서의 벌은 대개 모드를 안 적고,
#: 인장으로 맞춘 것이 흔하다.
MODES = {
    "multi": ("여러 모드", 0),
    "tension": (TENSION, 1),
    "": ("모드 모름", 1),
    "other": ("기타 모드", 2),
    "biaxial": ("이축", 3),
    "shear": ("전단", 3),
    "compression": (COMPRESSION, 4),
}


def mode_of(conditions: Mapping[str, Any]) -> str:
    """조건에서 시험 모드 하나 — `MODES` 의 키."""
    for key in MODE_KEYS:
        raw = conditions.get(key)
        if raw is None or str(raw).strip().lower() in ("", "none", "null"):
            continue
        text = str(raw).lower()
        if "combin" in text or "multi" in text:
            return "multi"
        if "biax" in text:
            return "biaxial"
        if "compress" in text:
            return "compression"
        if "shear" in text or "planar" in text:
            return "shear"
        if "tens" in text or "extens" in text or "stretch" in text:
            return "tension"
        return "other"
    return ""


@dataclass(frozen=True)
class Candidate:
    label: str
    tier: int | None
    variant: str
    """모드 밖의 갈림 조건(노화 · 온도 …) — 있으면 일반 벌 뒤로."""
    source: str | None
    made: FromSet
    mode: str
    stable: Stability | None

    @property
    def tag(self) -> str:
        """각주의 짧은 꼬리 — 「압축 · 인장 33 % 에서 불안정」."""
        parts = [MODES[self.mode][0]] if self.mode else []
        if self.stable is not None and not self.stable.ok:
            parts.append(self.stable.describe())
        return " · ".join(parts)


def block_of(made: FromSet, *, origin: str, mode: str = "") -> dict[str, Any]:
    """옮긴 벌 → 카드 블록. 계수는 SI(Pa), 단위계 환산은 덱이 한다."""
    values: dict[str, Any] = {
        "family": made.family,
        "label": f"{FAMILY_LABELS.get(made.family, made.family)} ({origin})",
        "shear_modulus": initial_shear(made.family, made.values),
    }
    if mode:
        values["mode"] = MODES[mode][0]
    return {
        "values": values,
        "rows": [
            {"name": name, "value": value, "si_unit": "Pa"}
            for name, value in made.values.items()
        ],
    }


def unstable_note(made: FromSet) -> str | None:
    """덱 기본값 범위 안에서 불안정하면 그 사실 한 줄 — 사람이 고른 벌(사내 카드)에도 단다."""
    found = stability(made.values)
    if found is None or found.ok:
        return None
    return (
        f"주의: 이 초탄성 계수는 {found.describe()}합니다 — 응력이 변형을 따라 늘지 않는 "
        "구간이라 솔버가 그 변형을 넘으면 멈추거나 국소화합니다. 그 범위를 넘는 해석에는 그 "
        "변형까지 맞춘 벌을 쓰세요."
    )


def terms_of(
    db: Session, key: str, terms: Iterable[dict[str, Any]]
) -> dict[str, tuple[float, str]]:
    """벌의 항 → (값, 단위). 단위 칸이 비면 정의의 단위."""
    out: dict[str, tuple[float, str]] = {}
    for term in terms:
        value = term.get("value")
        if not isinstance(value, int | float) or isinstance(value, bool):
            continue
        name = str(term.get("term") or "")
        out[name] = (
            float(value),
            str(term.get("unit") or "") or parameters.unit_of(db, key, name),
        )
    return out


def _rank(one: Candidate) -> tuple[Any, ...]:
    return (
        0 if one.stable is None or one.stable.ok else 1,
        one.tier if one.tier is not None else 9,
        MODES[one.mode][1],
        bool(one.variant),
        RICHNESS.get(one.made.family, 9),
        one.label,
    )


def from_catalog(
    db: Session, material_id: uuid.UUID
) -> tuple[dict[str, Any] | None, list[str]]:
    """문헌 재료의 초탄성 벌 가운데 하나를 블록으로 — `(블록 또는 None, 각주)`."""
    candidates: list[Candidate] = []
    skipped: list[str] = []
    for found in parameters.sets(db, key=COEFFICIENT_KEY, material_id=material_id):
        # 모드는 꼬리(`tag`)가 사람 말로 말한다 — 이름표에는 모드 밖의 갈림만.
        others = {k: v for k, v in found.distinguishing.items() if k not in MODE_KEYS}
        variant = " · ".join(f"{k}={v}" for k, v in sorted(others.items()))
        label = f"{found.model or '?'}/{found.set_id or '-'}" + (
            f" ({variant})" if variant else ""
        )
        if found.duplicated:
            skipped.append(f"{label}: 같은 항이 두 번")
            continue
        made = from_parameter_set(found.model, terms_of(db, COEFFICIENT_KEY, found.terms))
        if isinstance(made, str):
            skipped.append(f"{label}: {made}")
            continue
        candidates.append(
            Candidate(
                label,
                found.quality_tier,
                variant,
                found.source,
                made,
                mode_of({**found.conditions, **found.distinguishing}),
                stability(made.values),
            )
        )
    said: list[str] = []
    if not candidates:
        if skipped:
            said.append("문헌 초탄성 벌을 덱으로 옮기지 못했습니다 — " + " · ".join(skipped))
        return None, said
    candidates.sort(key=_rank)
    chosen = candidates[0]
    tier = QUALITY_TIERS.get(chosen.tier or 0, str(chosen.tier))
    said.append(
        f"초탄성 = {FAMILY_LABELS.get(chosen.made.family, chosen.made.family)} — 문헌 벌 "
        f"{chosen.label} · {chosen.source or '출처 미상'} [tier {chosen.tier}: {tier}]"
        + (f" · {MODES[chosen.mode][0]} 데이터" if chosen.mode else "")
        + (f". {chosen.made.note}" if chosen.made.note else "")
    )
    if chosen.mode in ("tension", "compression", "biaxial", "shear"):
        said.append(
            f"한 모드({MODES[chosen.mode][0]})로 맞춘 계수입니다 — 다른 변형 모드에서는 "
            "빗나갈 수 "
            "있습니다."
        )
    warned = unstable_note(chosen.made)
    if warned:
        said.append(warned)
    rest = [one.label + (f" · {one.tag}" if one.tag else "") for one in candidates[1:]]
    if rest:
        said.append(
            f"다른 초탄성 벌 {len(rest)}개({', '.join(rest[:4])}"
            + (" …" if len(rest) > 4 else "")
            + ")는 안 썼습니다 — 다른 벌을 쓰려면 사내 재료로 받아 카드에서 고르세요."
        )
    if skipped:
        said.append(
            "덱으로 못 옮긴 초탄성 벌: "
            + " · ".join(skipped[:4])
            + (" …" if len(skipped) > 4 else "")
        )
    return block_of(chosen.made, origin="문헌 벌", mode=chosen.mode), said
