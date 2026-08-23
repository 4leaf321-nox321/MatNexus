"""확장 폴더 — **폴더에 넣으면 읽는다.**

## 왜

새 물성을 더할 때 계산 파일을 만드는 것까지는 값이 낮았다(초탄성 실측: 식 300줄).
그런데 그 파일을 **읽게 하려면 중심 코드에 이름을 적어야** 했다.

    matcore/cards/__init__.py     from matcore.cards import hyperelastic, ...
    matcore/fitting/__init__.py   from matcore.fitting import hyperelastic

두 줄이지만 성격이 나쁘다. 여러 사람이 각자 물성을 붙이면 **같은 줄을 서로 고치게**
되고, 확장을 따로 배포할 길이 없다.

여기서는 폴더를 훑는다. `extensions/<이름>/__init__.py` 가 등록 함수를 부르면 끝이다.

## 하나가 잘못돼도 나머지는 산다

확장 하나가 import 에서 터진다고 서버가 안 뜨면 안 된다 — 그러면 **남의 확장 때문에
내 물성을 못 쓰는** 일이 생기고, 그 사실이 로그 없이 "서버가 안 켜진다" 로만 보인다.
실패한 것을 기록해 돌려주고, 부른 쪽이 로그에 남긴다.

## 이름이 겹치면 거절한다

같은 key 의 블록·솔버가 둘이면 **어느 쪽이 도는지 알 수 없다.** 레지스트리가
이미 `ValueError` 로 막는다 — 여기서는 그것을 실패로 기록만 한다.

## 폐쇄망을 고려한다

`pip install` 로 배포되는 패키지(entry_points)가 아니라 **폴더**인 이유다. 배포는
`deploy_package.zip` 하나로 들어가고, 패키징이 `backend` 를 통째로 복사하므로
확장이 저절로 따라간다.

DB 도 HTTP 도 모른다. `tests/architecture` 가 검사한다.
"""

from __future__ import annotations

import importlib.util
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

#: 확장이 들어가 사는 가짜 패키지 이름. 확장 안의 `from . import ...` 가 이
#: 이름 아래에서 풀린다.
PACKAGE = "matnexus_ext"


@dataclass(frozen=True)
class Loaded:
    """확장 하나를 읽은 결과."""

    name: str
    ok: bool
    error: str | None = None
    """실패한 이유. **삼키지 않는다** — 부른 쪽이 로그에 남긴다."""


def _parent() -> ModuleType:
    """확장들의 부모 패키지를 만들어 둔다(없으면)."""
    existing = sys.modules.get(PACKAGE)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_loader(PACKAGE, loader=None, is_package=True)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    module.__path__ = []
    sys.modules[PACKAGE] = module
    return module


def _load_one(folder: Path) -> Loaded:
    name = folder.name
    full = f"{PACKAGE}.{name}"
    if full in sys.modules:
        # 이미 읽었다. 두 번 읽으면 등록이 중복돼 거절된다.
        return Loaded(name=name, ok=True)

    init = folder / "__init__.py"
    if not init.is_file():
        return Loaded(name=name, ok=False, error="__init__.py 가 없습니다.")

    try:
        spec = importlib.util.spec_from_file_location(
            full, init, submodule_search_locations=[str(folder)]
        )
        if spec is None or spec.loader is None:
            return Loaded(name=name, ok=False, error="읽을 수 없는 폴더입니다.")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        spec.loader.exec_module(module)
    except Exception:  # 확장 하나가 서버를 못 켜게 두지 않는다.
        sys.modules.pop(full, None)
        return Loaded(name=name, ok=False, error=traceback.format_exc(limit=3).strip())
    return Loaded(name=name, ok=True)


def load(root: str | Path) -> tuple[Loaded, ...]:
    """폴더 안의 확장을 전부 읽는다. 이름 순서로 — **같은 순서로 등록되어야 한다.**

    폴더가 없으면 빈 결과다. 확장이 없는 설치가 정상이다.
    """
    base = Path(root)
    if not base.is_dir():
        return ()
    _parent()
    return tuple(
        _load_one(folder)
        for folder in sorted(base.iterdir())
        if folder.is_dir() and not folder.name.startswith((".", "_"))
    )


def failures(report: tuple[Loaded, ...]) -> tuple[Loaded, ...]:
    return tuple(item for item in report if not item.ok)
