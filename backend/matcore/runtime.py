"""계산이 **무엇으로 나왔는지**. 결과에 함께 박아 둔다.

## 왜

이 저장소는 이미 재현을 위해 여러 가지를 남긴다 — 레시피를 통째로 스냅샷하고,
플러그인 버전을 단계마다 적고, 적합의 **경계와 초기값**까지 저장한다. 그 이유가
`fitting` 에 이렇게 적혀 있다.

    경계와 초기값을 함께 남긴다. 비선형 적합은 여기에 따라 다른 답에 수렴한다.
    남기지 않으면 같은 데이터로 다시 돌려도 재현이 안 된다.

**그 논리의 나머지 절반이 빠져 있었다.** 우리 적합은 `scipy.optimize.least_squares`
를 쓴다. scipy 가 바뀌면 신뢰영역 구현이 달라지고, **같은 데이터·같은 플러그인
버전에서 다른 파라미터가 나올 수 있다.** 곡선 저장은 pyarrow 를 쓰고, 수치는 전부
numpy 다.

## 소급이 안 된다

오늘 만든 카드가 어느 scipy 로 계산됐는지는 **오늘 적어야 안다.** 나중에 붙이면
그 전에 만든 것은 영영 모른다 — 그래서 값이 작아도 미루지 않는다.

## 무엇을 안 담나

경로·호스트 이름·사용자 이름은 안 담는다. 재현에 안 쓰이고 그 자체로 정보다.
`digest` 는 **같은 환경인지 한눈에 보려는 것**이지 무결성 증명이 아니다.

DB 도 HTTP 도 모른다. `tests/architecture` 가 검사한다.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from importlib.metadata import PackageNotFoundError, version

#: 계산 결과를 바꿀 수 있는 것들. **여기 없는 것은 바뀌어도 결과가 안 바뀐다**는
#: 뜻이므로, 새 계산 의존성을 들일 때 같이 적는다.
#:
#: `scipy` 가 가장 중요하다 — 적합의 최적화기가 거기 있다. `numpy` 는 수치 전부,
#: `pyarrow` 는 곡선 저장(Parquet)이다.
LIBRARIES = ("numpy", "scipy", "pyarrow")


def _installed(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        # 없는 것도 사실이다. 빈칸으로 두면 "안 적혔다" 와 구별이 안 된다.
        return "없음"


def manifest() -> dict[str, str]:
    """이 계산을 낸 환경. 결과에 그대로 담긴다.

    `digest` 는 나머지 값들의 해시다 — 두 결과가 같은 환경에서 나왔는지 문자열
    하나로 볼 수 있게 한다.
    """
    facts = {
        "python": platform.python_version(),
        "implementation": sys.implementation.name,
        **{name: _installed(name) for name in LIBRARIES},
    }
    facts["digest"] = hashlib.sha256(
        json.dumps(facts, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    return facts


def same(first: dict[str, str] | None, second: dict[str, str] | None) -> bool:
    """두 결과가 같은 환경에서 나왔는가.

    한쪽이라도 기록이 없으면 **같다고 하지 않는다.** 모르는 것과 같은 것은 다르다 —
    기록이 없는 결과는 v1.48.0 이전에 만들어진 것이고, 그때 무엇이었는지는 알 길이
    없다.
    """
    if not first or not second:
        return False
    return first.get("digest") == second.get("digest")
