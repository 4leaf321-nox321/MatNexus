"""핸드북 씨앗 왕복 — **저장소와 운영, 두 곳에서 바뀌는 것을 어떻게 다루나.**

가이드는 저장소에서 갱신되어 배포로 올라가는데, 운영에서도 사람이 고치고 검토자가
승인한다. 무는 자리를 고를 때 「씨앗이 들어간다」 보다 **「운영 편집이 말없이
덮이지 않는다」** 를 우선한다 — 앞엣것은 안 되면 화면이 비어 바로 보이지만,
뒤엣것은 사람이 쓴 글이 사라지고 아무도 그 사실을 모른다.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.guide.models import GuideDocument, GuideSection

BACKEND = Path(__file__).resolve().parent.parent.parent


def _script(name: str) -> Any:
    """`scripts/` 는 패키지가 아니라 경로로 읽는다."""
    path = BACKEND / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_script_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def guides() -> Any:
    return _script("import_guides")


def seed(**over: Any) -> dict[str, Any]:
    def body(text: str) -> dict[str, Any]:
        return {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
        }

    base = {
        "key": "sample-guide",
        "kind": "method",
        "topic": None,
        "title": "표본 가이드",
        "summary": "시험용",
        "source_filename": "sample-KR.html",
        "sections": [
            {"key": "00-처음", "title": "00 · 처음", "position": 1, "body": body("첫 절")},
            {"key": "01-다음", "title": "01 · 다음", "position": 2, "body": body("둘째 절")},
        ],
        "assets": [],
    }
    base.update(over)
    return base


def _bodies(db: Session, key: str = "sample-guide") -> dict[str, str]:
    document = db.scalar(select(GuideDocument).where(GuideDocument.key == key))
    assert document is not None
    return {
        row.key: row.body_text
        for row in db.scalars(
            select(GuideSection).where(GuideSection.document_id == document.id)
        )
    }


class Test기본은_안_덮는다:
    """**여기가 제일 위험한 자리다.** 배포마다 도는 모드이므로, 여기서 덮으면
    운영 편집이 릴리스마다 사라진다."""

    def test_없으면_만든다(self, db: Session, guides: Any) -> None:
        said = guides.load(db, seed(), replace=False)
        assert "만듦" in said
        assert set(_bodies(db)) == {"00-처음", "01-다음"}

    def test_고쳐진_절을_안_덮는다(self, db: Session, guides: Any) -> None:
        guides.load(db, seed(), replace=False)
        document = db.scalar(select(GuideDocument).where(GuideDocument.key == "sample-guide"))
        assert document is not None
        section = db.scalar(
            select(GuideSection).where(
                GuideSection.document_id == document.id, GuideSection.key == "00-처음"
            )
        )
        assert section is not None
        section.body = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "운영에서 고친 글"}],
                }
            ],
        }
        section.body_text = "운영에서 고친 글"
        db.commit()

        said = guides.load(db, seed(), replace=False)

        assert "채움" in said
        assert _bodies(db)["00-처음"] == "운영에서 고친 글", "운영 편집이 덮였다"

    def test_저장소에_더한_절은_들어간다(self, db: Session, guides: Any) -> None:
        """전에는 문서 key 가 있으면 **통째로** 건너뛰었다 — 저장소에 절을 새로
        써도 운영에 영영 안 갔다."""
        guides.load(db, seed(), replace=False)
        grown = seed()
        grown["sections"].append(
            {
                "key": "02-새로",
                "title": "02 · 새로",
                "position": 3,
                "body": {
                    "type": "doc",
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "새 절"}]}
                    ],
                },
            }
        )

        guides.load(db, grown, replace=False)

        assert set(_bodies(db)) == {"00-처음", "01-다음", "02-새로"}


class Test덮기는_의식적으로만:
    def test_replace_는_덮는다(self, db: Session, guides: Any) -> None:
        guides.load(db, seed(), replace=False)
        document = db.scalar(select(GuideDocument).where(GuideDocument.key == "sample-guide"))
        assert document is not None
        section = db.scalar(
            select(GuideSection).where(
                GuideSection.document_id == document.id, GuideSection.key == "00-처음"
            )
        )
        assert section is not None
        section.body_text = "운영에서 고친 글"
        db.commit()

        guides.load(db, seed(), replace=True)

        assert _bodies(db)["00-처음"] == "첫 절"

    def test_운영에서_만든_절은_안_지운다(self, db: Session, guides: Any) -> None:
        """씨앗에 없는 절까지 지우면 **현장에서 쓴 글이 통째로** 사라진다."""
        guides.load(db, seed(), replace=False)
        document = db.scalar(select(GuideDocument).where(GuideDocument.key == "sample-guide"))
        assert document is not None
        db.add(
            GuideSection(
                document_id=document.id,
                key="99-현장",
                title="현장 메모",
                position=99,
                body={"type": "doc", "content": []},
                body_text="현장에서 쓴 글",
            )
        )
        db.commit()

        guides.load(db, seed(), replace=True)

        assert "99-현장" in _bodies(db)


class Test차이를_먼저_보여_준다:
    """덮기 전에 무엇이 부딪히는지 아는 것이 이 문제의 핵심이다."""

    def test_없으면_없다고_한다(self, db: Session, guides: Any) -> None:
        assert "운영에 없음" in guides.check(db, seed())

    def test_같으면_같다고_한다(self, db: Session, guides: Any) -> None:
        guides.load(db, seed(), replace=False)
        assert guides.check(db, seed()) == "같음"

    def test_다른_절을_짚는다(self, db: Session, guides: Any) -> None:
        guides.load(db, seed(), replace=False)
        document = db.scalar(select(GuideDocument).where(GuideDocument.key == "sample-guide"))
        assert document is not None
        section = db.scalar(
            select(GuideSection).where(
                GuideSection.document_id == document.id, GuideSection.key == "01-다음"
            )
        )
        assert section is not None
        section.body = {"type": "doc", "content": []}
        section.body_text = "운영에서 비운 절"
        db.commit()
        before = _bodies(db)

        said = guides.check(db, seed())

        assert "다름" in said and "01-다음" in said
        # **넣지는 않는다.** 보기만 하는 모드가 쓰면 그것은 보기가 아니다.
        assert _bodies(db) == before, "check 가 본문을 건드렸다"

    def test_저장소에만_있는_절도_짚는다(self, db: Session, guides: Any) -> None:
        guides.load(db, seed(), replace=False)
        grown = seed()
        grown["sections"].append(
            {
                "key": "02-새로",
                "title": "02",
                "position": 3,
                "body": {"type": "doc", "content": []},
            }
        )
        assert "새 절 1" in guides.check(db, grown)


class Test내보내기는_들여오기를_되돌린다:
    """되돌리는 길이 없으면 운영 편집은 언젠가 반드시 사라진다."""

    def test_왕복하면_본문이_같다(self, db: Session, guides: Any, tmp_path: Path) -> None:
        guides.load(db, seed(), replace=False)
        document = db.scalar(select(GuideDocument).where(GuideDocument.key == "sample-guide"))
        assert document is not None

        out = _script("export_guides").dump(db, document, tmp_path)

        assert "절 2" in out
        written = json.loads((tmp_path / "sample-guide.json").read_text(encoding="utf-8"))
        assert {one["key"] for one in written["sections"]} == {"00-처음", "01-다음"}
        assert written["kind"] == "method"
        assert written["source_filename"] == "sample-KR.html"

    def test_서버_사정은_안_싣는다(self, db: Session, guides: Any, tmp_path: Path) -> None:
        """`id`·시각을 실으면 다른 서버에서 뜻이 없거나 충돌한다."""
        guides.load(db, seed(), replace=False)
        document = db.scalar(select(GuideDocument).where(GuideDocument.key == "sample-guide"))
        assert document is not None

        _script("export_guides").dump(db, document, tmp_path)

        written = json.loads((tmp_path / "sample-guide.json").read_text(encoding="utf-8"))
        assert set(written) == {
            "key",
            "kind",
            "topic",
            "title",
            "summary",
            "source_filename",
            "sections",
            "assets",
        }
        assert set(written["sections"][0]) == {"key", "title", "position", "body"}
