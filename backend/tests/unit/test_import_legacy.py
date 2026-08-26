"""옛 데이터 이관의 **미리 보기** — 넣기 전에 무엇을 알아채는가.

이관은 되돌릴 수 없다. 처리 결과는 불변이고, 지우는 스크립트는 언젠가 잘못된
것을 지운다. 그래서 이 스크립트에서 값진 부분은 넣는 쪽이 아니라 **안 넣고
문제를 말하는 쪽**이다 — 여기를 시험한다.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]

#: 스크립트는 패키지가 아니라 파일이다. 경로로 불러온다 — 그래야 시험이
#: 실제로 돌아가는 그 파일을 본다.
_spec = importlib.util.spec_from_file_location(
    "import_legacy", BACKEND_DIR / "scripts" / "import_legacy.py"
)
assert _spec is not None and _spec.loader is not None
import_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(import_legacy)

KEYS = {
    "material": "material_code",
    "lot": "lot_no",
    "seq": "specimen_no",
    "orientation": "orientation",
}

PROFILE: dict[str, Any] = {
    "match": {"extensions": [".json"], "header_any": ["force_N"]},
    "tables": {"mode": "all", "include": "^curve$"},
    "columns": {
        "displacement_mm": {"channel": "displacement", "unit": "mm"},
        "force_N": {"channel": "force", "unit": "N"},
    },
    "specimen": {
        "thickness_mm": {"key": "specimen_thickness", "unit": "mm"},
        "width_mm": {"key": "specimen_width", "unit": "mm"},
        "gauge_mm": {"key": "specimen_gauge_length", "unit": "mm"},
    },
    "metadata": ["material_code", "lot_no", "specimen_no", "orientation"],
}


def make(tmp_path: Path, name: str = "SECC_LOT-A_MD_01.json", **overrides: Any) -> Path:
    doc: dict[str, Any] = {
        "material_code": "SECC",
        "lot_no": "LOT-A",
        "specimen_no": 1,
        "orientation": "MD",
        "thickness_mm": 1.02,
        "width_mm": 12.5,
        "gauge_mm": 50.0,
        "curve": [
            {"displacement_mm": 0.0, "force_N": 0.0},
            {"displacement_mm": 0.1, "force_N": 400.0},
            {"displacement_mm": 0.2, "force_N": 800.0},
        ],
    }
    doc.update(overrides)
    for key, value in list(doc.items()):
        if value is None:
            del doc[key]
    path = tmp_path / name
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


def read(path: Path, pattern: str | None = None) -> Any:
    return import_legacy._read(path, PROFILE, KEYS, re.compile(pattern) if pattern else None)


class Test읽힌다:
    def test_식별자와_치수를_뽑는다(self, tmp_path: Path) -> None:
        row = read(make(tmp_path))
        assert row.ok, row.problem
        assert (row.grade, row.lot, row.orientation, row.seq) == ("SECC", "LOT-A", "MD", 1)
        # **F-D 만 올린다.** S-S 는 이 치수로 시스템이 계산한다.
        assert row.dimensions["gauge_length"] == pytest.approx(0.05)
        assert row.dimensions["thickness"] == pytest.approx(0.00102)


class Test안_읽히면_말한다:
    def test_지문이_안_맞으면_넣지_않는다(self, tmp_path: Path) -> None:
        """확장자가 맞아도 열 이름이 다르면 남의 파일이다."""
        path = tmp_path / "other.json"
        path.write_text(json.dumps({"curve": [{"a": 1, "b": 2}, {"a": 3, "b": 4}]}))
        row = read(path)
        assert not row.ok
        assert "지문" in row.problem

    def test_식별자가_없으면_있는_키를_알려_준다(self, tmp_path: Path) -> None:
        """**무엇으로 고쳐야 하는지**까지 말해야 쓸모가 있다. 「없습니다」 만
        하면 사람이 파일을 열어 키 이름을 손으로 찾는다."""
        row = read(make(tmp_path, lot_no=None, orientation=None))
        assert not row.ok
        assert "lot_no" in row.problem and "orientation" in row.problem
        assert "material_code" in row.problem  # 있는 키 목록

    def test_시편_번호를_지어내지_않는다(self, tmp_path: Path) -> None:
        """파일 순서로 번호를 매기면, 폴더에 파일이 하나 더 들어온 날 번호가
        통째로 밀린다 — 그러면 어제 만든 카드와 오늘 만든 카드가 다른 시편을
        가리킨다."""
        row = read(make(tmp_path, specimen_no="일번"))
        assert not row.ok
        assert row.seq is None

    def test_치수가_없으면_미리_말한다(self, tmp_path: Path) -> None:
        """오류는 아니다. 하지만 처리 1단계의 `@specimen_area` 가 거기서
        멈추므로, 200개를 넣고 나서 알면 늦다."""
        bare = {**PROFILE, "specimen": {}}
        row = import_legacy._read(make(tmp_path), bare, KEYS, None)
        assert not row.ok
        assert "단위" in row.problem


class Test이름에서_뽑기:
    """옛 앱의 `.mtet` 에는 재료 코드도 로트도 방향도 없다 — 파일 이름에 있다."""

    PATTERN = r"(?P<material>[^_]+)_(?P<lot>[^_]+)_(?P<orientation>MD|TD)_(?P<seq>[0-9]+)"

    def test_메타에_없는_것만_채운다(self, tmp_path: Path) -> None:
        row = read(make(tmp_path, lot_no=None, orientation=None), self.PATTERN)
        assert row.ok, row.problem
        assert (row.lot, row.orientation) == ("LOT-A", "MD")

    def test_메타가_이긴다(self, tmp_path: Path) -> None:
        """파일 안의 값이 이름보다 믿을 만하다 — 이름은 사람이 손으로 바꾼
        적이 있다."""
        path = make(tmp_path, name="SECC_LOT-Z_TD_09.json")
        row = read(path, self.PATTERN)
        assert (row.lot, row.orientation, row.seq) == ("LOT-A", "MD", 1)

    def test_이름_규칙에_안_맞으면_멈춘다(self, tmp_path: Path) -> None:
        """반쯤 맞는 이름에서 조각을 주워 오면, 어느 시편에 붙었는지 아무도
        모르는 시험이 생긴다."""
        row = read(make(tmp_path, name="아무이름.json", lot_no=None), self.PATTERN)
        assert not row.ok
        assert "이름 규칙" in row.problem
