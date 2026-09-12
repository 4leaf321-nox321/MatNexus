"""확장 계약서(`docs/확장-계약.md`)가 코드와 같은가.

레지스트리에서 생성하는 문서다 — 손으로 쓰면 뒤처진다(`dependents.py` 의 교훈). 단계·
식·블록·렌더러를 더하거나 바꿨는데 문서를 다시 안 만들었으면 여기서 걸린다.
`openapi.json` 과 같은 방식.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
DOC = BACKEND.parent / "docs" / "확장-계약.md"


def _script() -> Any:
    spec = importlib.util.spec_from_file_location(
        "describe_extension_api", BACKEND / "scripts" / "describe_extension_api.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["describe_extension_api"] = module
    spec.loader.exec_module(module)
    return module


def test_확장_계약서가_코드와_같다() -> None:
    assert DOC.exists(), (
        "docs/확장-계약.md 가 없습니다 — scripts/describe_extension_api.py 로 만드세요."
    )
    fresh = _script().build()
    saved = DOC.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert saved == fresh, (
        "확장 계약서가 코드와 다릅니다 — 단계·식·블록·렌더러를 바꿨으면 "
        "`python scripts/describe_extension_api.py` 로 다시 만들어 함께 커밋하세요."
    )


def test_확장_폴더의_등록이_계약서에_실린다() -> None:
    """확장이 붙였는데 계약서에 안 보이면 다음 사람이 그 창구를 모른다."""
    text = DOC.read_text(encoding="utf-8")
    for key in ("tensile.yield_ratio", "tensile.temperature_family", "ghosh", "johnson_cook"):
        assert key in text, key
