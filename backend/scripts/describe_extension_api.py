"""확장 계약서를 **레지스트리에서 생성한다** — `docs/확장-계약.md`.

    python scripts/describe_extension_api.py            # docs/확장-계약.md 를 다시 쓴다
    python scripts/describe_extension_api.py --check    # 저장본과 같은지만 본다 (CI)

## 왜 생성하나

확장을 붙이려는 사람이 알아야 하는 것 — 처리 단계가 받는 열 이름, 앞 단계가 내는
스칼라, 적합식이 맞추는 축, 카드 블록이 담는 값, 렌더러가 먹는 블록 — 은 전부 코드가
이미 안다(`makes_columns` · `makes_values` · `Family.x_column` · `BlockSpec.produces` ·
`Renderer.needs`). 사람에게 안 보였을 뿐이다(2026-09-13, [계획] 계산 확장 §3).

손으로 쓰면 뒤처진다(`dependents.py` 의 교훈). 그래서 여기서 만들고, 아키텍처 시험이
저장본과 대조한다 — `openapi.json` 과 같은 방식.

DB 를 안 만진다. 레지스트리와 내장 정의만 읽는다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from _console import survive_cp949  # noqa: E402
from app.modules.tests.definitions import BUILTIN_TEST_TYPES  # noqa: E402
from matcore import cards, export, extensions, fitting, processing, registry  # noqa: E402
from matcore.export import systems  # noqa: E402

survive_cp949()

OUT = BACKEND_DIR.parent / "docs" / "확장-계약.md"
EXTENSIONS = BACKEND_DIR / "extensions"


def _load() -> None:
    processing.load_builtin()
    cards.load_builtin()
    fitting.load_builtin()
    # 묶음은 `load_builtin` 이 없다 — app 의 grouping 서비스가 import 로 등록시킨다.
    # 여기는 app 을 안 띄우므로 같은 둘을 직접 읽는다.
    # LS-DYNA 렌더러도 import 로 등록된다(`app/main.py` 와 같은 줄).
    from matcore.export import dyna as _dyna  # noqa: F401
    from matcore.groups import prony as _prony  # noqa: F401
    from matcore.groups import rate as _rate  # noqa: F401

    extensions.load(EXTENSIONS)


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    out += ["| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in rows]
    return out


def _produced(items: tuple[registry.Produced, ...]) -> str:
    return ", ".join(f"`{one.key}` ({one.si_unit or '?'})" for one in items) or "—"


def build() -> str:
    _load()
    lines: list[str] = [
        "# 확장 계약 — 새 계산이 받는 것과 내는 것",
        "",
        "**생성된 문서다.** `python scripts/describe_extension_api.py` 가 레지스트리에서 만든다 —",
        "손으로 고치지 않는다(아키텍처 시험이 대조한다). 붙이는 방법은",
        "[backend/extensions/README.md](../backend/extensions/README.md), 왜 이렇게 나뉘는지는",
        "[[계획] 계산 확장](%5B계획%5D%20계산%20확장.md).",
        "",
        "## 창구 — 전부 `backend/extensions/<이름>/__init__.py` 에서 부른다",
        "",
    ]
    lines += _table(
        ["무엇을", "등록 함수", "받는 것 → 내는 것"],
        [
            [
                "처리 단계 (시험 하나)",
                '`registry.register(kind="processing")`',
                "`(Frame, options) → StepResult`",
            ],
            [
                "묶음 (여러 시험 → 하나)",
                '`registry.register(kind="grouping")`',
                "`(list[Member], **options) → GroupOutcome`",
            ],
            ["적합식", "`fitting.register_family(Family)`", "`evaluate(파라미터, x) → y`"],
            [
                "카드 블록",
                "`cards.register_block(BlockSpec)`",
                "선언만 — 값·표의 이름과 SI 단위",
            ],
            ["솔버 렌더러", "`export.register_renderer(...)`", "`(Deck) → Rendered`"],
        ],
    )

    # ── 채널 ─────────────────────────────────────────────────────────────
    lines += ["", "## 채널 — 장비 파일이 주는 열 (내장 시험 종류)", ""]
    lines += [
        "처리 단계의 `Frame.columns` 첫 상태다. 부서가 만든 시험 종류는 이와 다를 수 있다 —",
        "그래서 단계는 키가 아니라 `requires_channels` 로 「이 열이 있으면 된다」 를 선언한다.",
        "",
    ]
    rows = []
    for spec in BUILTIN_TEST_TYPES:
        channels = ", ".join(
            f"`{key}` ({si})" for key, _label, _dim, si, _req in spec["channels"]
        )
        rows.append([f"`{spec['key']}`", spec["label"], channels])
    lines += _table(["시험 종류", "이름", "채널 (SI)"], rows)

    # ── 처리 단계 ────────────────────────────────────────────────────────
    lines += [
        "",
        "## 처리 단계 — `Frame` 을 받아 `StepResult` 를 낸다",
        "",
        "- `Frame`: `columns: dict[str, ndarray]` + `units: dict[str, str]`. **전부 SI.** 열 이름은 채널 키이거나 앞 단계가 만든 열이다(아래 표).",
        "- `StepResult(frame, scalars, notes)`: 곡선을 바꾸지 않아도 된다. **값을 못 내면 실패하지 않고 `notes` 에 이유를 남긴다** — 뒤 단계가 그 값을 가리키면 그 이유가 오류 문구에 실린다.",
        '- 앞 단계가 낸 스칼라는 옵션에 `"@키"` 로 받는다(`{"proof_stress": "@proof_stress"}`). 레시피는 JSON 으로 저장되므로 참조가 보인다.',
        "- `Scalar(key, label, value, si_unit, dimension=None)`. `Produced.property_key` 를 적으면 문헌 물성 키에 이어진다(값으로 찾기가 잰 값을 찾는다).",
        "",
        "### 내장·확장 단계가 만드는 것 (이 이름으로 뒤 단계가 받는다)",
        "",
    ]
    rows = []
    for plugin in sorted(
        registry.list_plugins(kind="processing"), key=lambda p: (p.order, p.id)
    ):
        rows.append(
            [
                f"`{plugin.id}`",
                plugin.label,
                _produced(plugin.makes_columns),
                _produced(plugin.makes_values),
            ]
        )
    lines += _table(["단계", "이름", "만드는 열", "내는 스칼라"], rows)

    # ── 묶음 ─────────────────────────────────────────────────────────────
    lines += [
        "",
        "## 묶음 — `Member` 들을 받아 `GroupOutcome` 을 낸다",
        "",
        "- `Member(label, columns, values)`: 시험 하나에서 꺼낸 곡선과 스칼라. 둘 이상이어야 묶인다.",
        "- `GroupOutcome(values, columns, detail, warnings, used)`: 처리 결과와 같은 모양(곡선 하나 + 스칼라). `used` 는 실제로 쓴 구성원.",
        '- **구성원을 모으는 법은 선언한다** — `register(..., members={"from": "adopted_result", "columns": [...], "conditions": [...], "values": [...]})`. 채택된 처리 결과의 곡선 열·시험 조건·스칼라를 그 이름으로 꺼내 준다. 계산이 필요한 것(변형률 속도)은 중심 코드의 `@collector` 다.',
        "",
    ]
    rows = []
    for plugin in sorted(
        registry.list_plugins(kind="grouping"), key=lambda p: (p.order, p.id)
    ):
        rule = plugin.meta.get("members")
        how = (
            f"선언: 열 {', '.join(f'`{c}`' for c in rule.get('columns', []))} · 조건 {', '.join(f'`{c}`' for c in rule.get('conditions', []))}"
            if isinstance(rule, dict)
            else "중심 코드의 수집기"
        )
        rows.append([f"`{plugin.id}`", plugin.label, how, _produced(plugin.makes_values)])
    lines += _table(["묶음", "이름", "구성원", "내는 스칼라"], rows)

    # ── 적합식 ───────────────────────────────────────────────────────────
    lines += [
        "",
        "## 적합식 — `Family`",
        "",
        "- `evaluate(parameters, x) → y` · `guess(x, y) → 초기값` · `bounds(x, y) → (하한, 상한)`. 축은 `x_column`·`y_column` 으로 선언한다(위 「만드는 열」 의 이름).",
        "- 결과는 `block` 이 가리키는 카드 블록에 담긴다. `applies_to` 로 재료군을 가른다 — 금속 경화식과 고무 초탄성을 한 줄로 세우지 않는다.",
        "",
    ]
    rows = []
    for family in sorted(fitting.families_for(), key=lambda f: f.key):
        rows.append(
            [
                f"`{family.key}`",
                family.label,
                f"`{family.x_column}` → `{family.y_column}`",
                ", ".join(
                    f"`{n}` ({u})"
                    for n, u in zip(
                        family.parameter_names, family.parameter_units, strict=True
                    )
                ),
                f"`{family.block}`",
                ", ".join(family.applies_to) or "전부",
            ]
        )
    lines += _table(["식", "이름", "축 (x → y)", "파라미터 (SI)", "블록", "재료군"], rows)

    # ── 카드 블록 ────────────────────────────────────────────────────────
    lines += [
        "",
        "## 카드 블록 — `BlockSpec`",
        "",
        "값(`produces`)과 표 열(`rows`)의 이름·SI 단위를 선언한다. 화면·저장·덱이 이 선언만 읽는다.",
        "블록이 드는 단위는 `matcore/export/systems.py` 의 단위계가 알아야 한다 — 새 단위를 들면 `DECLARED` 와 두 계의 기호에 함께 적는다(시험이 대조한다).",
        "",
    ]
    rows = []
    for block in cards.list_blocks():
        rows.append(
            [
                f"`{block.key}`",
                block.label,
                _produced(block.produces),
                _produced(block.rows),
                "—" if block.kind_priority is None else str(block.kind_priority),
            ]
        )
    lines += _table(["블록", "이름", "값", "표 열", "종류 우선순위"], rows)
    lines += ["", "선언 단위(`DECLARED`): " + ", ".join(f"`{u}`" for u in systems.DECLARED)]

    # ── 렌더러 ───────────────────────────────────────────────────────────
    lines += [
        "",
        "## 솔버 렌더러 — `Renderer`",
        "",
        "`needs` 가 먹는 블록과 값을 말한다. 없으면 그 솔버로는 못 내고, 화면이 그 이유를 말한다.",
        "",
    ]
    rows = []
    for renderer in sorted(export.list_renderers(), key=lambda r: r.key):
        needs = ", ".join(
            f"`{need.block}`"
            + (f"[{', '.join(need.values)}]" if need.values else "")
            + (" (선택)" if need.optional else "")
            for need in renderer.needs
        )
        rows.append(
            [f"`{renderer.key}`", renderer.label, f".{renderer.extension}", needs or "—"]
        )
    lines += _table(["렌더러", "이름", "확장자", "먹는 블록"], rows)

    # ── 확장 폴더 ────────────────────────────────────────────────────────
    lines += ["", "## 지금 붙어 있는 확장 (`backend/extensions/`)", ""]
    rows = []
    for loaded in extensions.load(EXTENSIONS):
        rows.append([f"`{loaded.name}`", "읽힘" if loaded.ok else f"실패: {loaded.error}"])
    lines += _table(["폴더", "상태"], rows)
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="저장본과 같은지만 본다")
    args = parser.parse_args()
    text = build()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current.replace("\r\n", "\n") != text:
            print(
                f"{OUT.name} 이 코드와 다릅니다. `python scripts/describe_extension_api.py` 로 다시 만드세요."
            )
            return 1
        print(f"{OUT.name} 이 코드와 같습니다.")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"썼습니다: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
