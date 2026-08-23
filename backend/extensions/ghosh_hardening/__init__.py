"""Ghosh 경화식을 등록한다 — **확장 폴더 하나로 식이 붙는지 재는 자리.**

ADR 0013 이 *"물성은 폴더로 붙는다"* 고 적었는데 `extensions/` 에는 README 뿐이었다.
**만들어 두고 안 쓴 것**은 이 저장소가 반복해서 데인 패턴이다(`Plugin.inputs` 가
선언만 있고 읽는 코드가 없던 일, `abaqus_viscoelastic` 형식이 있는데 부를 카드가
없던 일). 그래서 첫 확장을 실제로 붙인다.

이 파일이 하는 일은 등록 하나다. 계산은 `equation.py` 에 있고, 중심 코드는 한 줄도
안 고쳤다.
"""

from __future__ import annotations

from matcore import fitting

from . import equation

fitting.register_family(
    fitting.Family(
        key="ghosh",
        label="Ghosh",
        parameter_names=("k", "epsilon_0", "n", "p"),
        parameter_units=("Pa", "1", "1", "Pa"),
        evaluate=equation.evaluate,
        guess=equation.guess,
        bounds=equation.bounds,
        tangent=equation.tangent,
        describe=(
            "sigma = K(e0 + eps)^n - p — Swift 를 상수만큼 내린 것. "
            "큰 변형에서 Swift 와 같은 기울기로 오르되 낮은 값에서 오른다."
        ),
        applies_to=fitting.METALLIC,
    )
)
