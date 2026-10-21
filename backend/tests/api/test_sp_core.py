"""SP 코어 온톨로지 받기 · 대조 · 연결(ADR 0063, 2026-10-21).

SP 는 흉내 낸다(`httpx.MockTransport`) — 연동 지침서 §4.2 의 봉투 그대로(`as_of` · `next` ·
`items` · `deleted` · `merged_into` · `renamed_from` · `previous_keys` · `reset`, 404 코드 둘).

**조용히 틀리는 자리를 먼저 본다** — 끝까지 안 받았는데 `as_of` 를 옮기면 남은 쪽을 영영 안
받고, 키가 바뀌었는데 연결을 안 옮기면 같은 것이 둘이 된다. 둘 다 오류 없이 지나간다.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jobs.models import Job
from app.modules.audit.models import AuditEntry
from app.modules.catalog.models import CatalogDefinition
from app.modules.catalog.taxonomy_models import PropertyField, PropertyGroup
from app.modules.sp_core import sync
from app.modules.sp_core.client import SpCoreClient
from app.modules.sp_core.models import SpCoreLink, SpCoreObject, SpCoreRelation, SpCoreType
from app.modules.vocabulary import services as vocabulary_services
from app.modules.vocabulary.definitions import ensure_builtin_vocabularies
from app.modules.vocabulary.models import Vocabulary, VocabularyAlias
from app.shared.text import compare_key

BASE = "http://sp.test/api/core"


class FakeSp:
    """SP 코어 창구 흉내 — 쪽 크기를 작게 두어 쪽 넘기기를 늘 지나게 한다."""

    def __init__(self) -> None:
        self.page_size = 2
        self.clock = 1
        self.types: list[dict[str, Any]] = []
        self.rows: dict[str, dict[str, dict[str, Any]]] = {}
        self.tombs: dict[str, list[dict[str, Any]]] = {}
        self.edges: dict[str, dict[tuple[str, str, str, str], dict[str, Any]]] = {}
        self.unpublished: set[str] = set()
        self.fail_after: int | None = None
        self.bad_cursor_once = False
        self.reset_once = False
        self.calls: list[str] = []
        self._pages = 0

    def stamp(self) -> str:
        self.clock += 1
        return f"2026-10-21T00:00:{self.clock:02d}.000000Z"

    def add_type(self, slug: str, label: str, relations: list[str] | None = None) -> None:
        self.types.append(
            {
                "slug": slug,
                "label": label,
                "count": 0,
                "properties": [{"key": "code", "label": "코드", "data_type": "text"}],
                "endpoint": f"{BASE}/{slug}",
                "relations": relations or [],
                "relation_kinds": [],
            }
        )
        self.rows.setdefault(slug, {})
        self.tombs.setdefault(slug, [])
        self.edges.setdefault(slug, {})

    def put(self, slug: str, key: str, label: str, **extra: Any) -> None:
        self.rows[slug][key] = {
            "key": key,
            "label": label,
            "updated_at": self.stamp(),
            **extra,
        }

    def drop(
        self, slug: str, key: str, *, merged_into: str | None = None, quiet: bool = False
    ) -> None:
        self.rows[slug].pop(key, None)
        if not quiet:
            self.tombs[slug].append(
                {
                    "key": key,
                    "label": "",
                    "deleted": True,
                    "merged_into": merged_into,
                    "updated_at": self.stamp(),
                }
            )

    def rename(self, slug: str, old: str, new: str) -> None:
        row = self.rows[slug].pop(old)
        self.rows[slug][new] = {
            **row,
            "key": new,
            "renamed_from": old,
            "previous_keys": [old],
            "updated_at": self.stamp(),
        }

    def link(
        self,
        slug: str,
        src: str,
        relation: str,
        dst: str,
        dst_type: str,
        *,
        deleted: bool = False,
    ) -> None:
        self.edges[slug][(src, relation, dst, dst_type)] = {
            "src": src,
            "relation": relation,
            "dst": dst,
            "dst_type": dst_type,
            "updated_at": self.stamp(),
            "deleted": deleted,
        }

    # ── HTTP ──
    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/core").strip("/")
        self.calls.append(f"{path}?since={request.url.params.get('since')}")
        if request.headers.get("Authorization") != "Bearer tok":
            return httpx.Response(401, json={"error": {"code": "APP-AUTH-0001"}})
        if not path:
            types = [{**one, "count": len(self.rows[one["slug"]])} for one in self.types]
            return httpx.Response(
                200,
                json={
                    "system": "sp-test",
                    "revision": "r1",
                    "as_of": self.now(),
                    "types": types,
                },
            )
        parts = path.split("/")
        slug = parts[0]
        if slug in self.unpublished:
            return httpx.Response(
                404, json={"error": {"code": "APP-CORE-0001", "message": "x"}}
            )
        since = request.url.params.get("since")
        cursor = request.url.params.get("cursor")
        if cursor and self.bad_cursor_once:
            self.bad_cursor_once = False
            return httpx.Response(
                404, json={"error": {"code": "APP-CORE-0002", "message": "x"}}
            )
        self._pages += 1
        if self.fail_after is not None and self._pages > self.fail_after:
            raise httpx.ConnectError("끊김")
        if len(parts) == 2 and parts[1] == "relations":
            if since and self.reset_once:
                self.reset_once = False
                return httpx.Response(
                    200,
                    json={
                        "type_slug": slug,
                        "as_of": None,
                        "next": None,
                        "items": [],
                        "reset": True,
                    },
                )
            items = [
                one
                for one in sorted(self.edges[slug].values(), key=lambda e: e["updated_at"])
                if (since is None or one["updated_at"] > since)
                and (since or not one["deleted"])
            ]
        else:
            live = [one for one in self.rows[slug].values()]
            if since:
                live = [one for one in live if one["updated_at"] > since] + [
                    one for one in self.tombs[slug] if one["updated_at"] > since
                ]
            items = sorted(live, key=lambda r: r["updated_at"])
        start = int(cursor or 0)
        chunk = items[start : start + self.page_size]
        more = start + self.page_size < len(items)
        return httpx.Response(
            200,
            json={
                "type_slug": slug,
                "as_of": None if more else self.now(),
                "next": str(start + self.page_size) if more else None,
                "items": chunk,
            },
        )

    def now(self) -> str:
        return f"2026-10-21T00:00:{self.clock:02d}.500000Z"


def _pull(db: Session, fake: FakeSp, **kw: Any) -> Any:
    with SpCoreClient(BASE, "tok", transport=httpx.MockTransport(fake.handle)) as client:
        return sync.pull(db, client, **kw)


def _obj(db: Session, slug: str, key: str) -> SpCoreObject | None:
    db.expire_all()
    return db.scalar(
        select(SpCoreObject).where(SpCoreObject.type_slug == slug, SpCoreObject.key == key)
    )


@pytest.fixture
def fake() -> FakeSp:
    sp = FakeSp()
    sp.add_type("dept", "부서")
    sp.add_type("plm_model", "개발모델", relations=["plm_derived_from"])
    for index in range(5):
        sp.put("dept", f"D{index}", f"부서{index}")
    sp.put("plm_model", "M1", "모델 1")
    sp.put("plm_model", "M2", "모델 2")
    sp.link("plm_model", "M2", "plm_derived_from", "M1", "plm_model")
    return sp


class Test받기:
    def test_처음엔_전부_받고_끝까지_받은_뒤에만_as_of_를_저장한다(
        self, db: Session, fake: FakeSp
    ) -> None:
        run = _pull(db, fake)
        assert run.ok, run.error
        assert run.system == "sp-test" and run.revision == "r1"
        db.expire_all()
        dept = db.scalar(select(SpCoreType).where(SpCoreType.slug == "dept"))
        assert dept is not None
        assert dept.rows_as_of == fake.now()
        alive = db.scalars(select(SpCoreObject).where(SpCoreObject.type_slug == "dept")).all()
        assert sorted(one.key for one in alive) == [f"D{i}" for i in range(5)]
        assert run.counts["dept"]["rows"] == 5
        edges = db.scalars(select(SpCoreRelation)).all()
        assert [(e.src, e.relation, e.dst) for e in edges] == [
            ("M2", "plm_derived_from", "M1")
        ]

    def test_중간에_끊기면_as_of_를_안_옮기고_다음에_다시_받는다(
        self, db: Session, fake: FakeSp
    ) -> None:
        """**규칙 2** — 쪽이 남았는데 시계를 옮기면 남은 쪽을 영영 안 받는다."""
        fake.fail_after = 1
        run = _pull(db, fake)
        assert run.ok is False and "dept" in (run.error or "")
        db.expire_all()
        dept = db.scalar(select(SpCoreType).where(SpCoreType.slug == "dept"))
        assert dept is not None and dept.rows_as_of is None
        fake.fail_after = None
        again = _pull(db, fake)
        assert again.ok, again.error
        assert (
            len(db.scalars(select(SpCoreObject).where(SpCoreObject.type_slug == "dept")).all())
            == 5
        )

    def test_다음엔_바뀐_것만_받는다(self, db: Session, fake: FakeSp) -> None:
        _pull(db, fake)
        since = fake.now()
        fake.put("dept", "D9", "새 부서")
        fake.calls.clear()
        run = _pull(db, fake)
        assert run.counts["dept"]["rows"] == 1
        # 지난 as_of 를 그대로 `since` 로 — 우리 시계로 만들지 않는다(규칙 1).
        assert f"dept?since={since}" in fake.calls

    def test_지운_것은_표시만_하고_선을_끊는다_되살아나면_살린다(
        self, db: Session, fake: FakeSp
    ) -> None:
        """**규칙 4 · 8 · 9.**"""
        _pull(db, fake)
        fake.drop("plm_model", "M1", merged_into="M2")
        run = _pull(db, fake)
        gone = _obj(db, "plm_model", "M1")
        assert gone is not None and gone.deleted and gone.merged_into == "M2"
        assert run.counts["plm_model"]["deleted"] == 1
        edge = db.scalar(select(SpCoreRelation).where(SpCoreRelation.dst == "M1"))
        assert edge is not None and edge.deleted, (
            "사라진 객체를 끝점으로 하는 선은 이쪽이 끊는다"
        )
        fake.put("plm_model", "M1", "모델 1 다시")
        _pull(db, fake)
        back = _obj(db, "plm_model", "M1")
        assert back is not None and not back.deleted and back.merged_into is None

    def test_키가_바뀌면_받은_행과_선과_연결을_함께_옮긴다(
        self, db: Session, fake: FakeSp
    ) -> None:
        """**규칙 4** — 안 옮기면 같은 것이 둘이 되고 연결이 옛 키에 남는다."""
        _pull(db, fake)
        db.add(
            SpCoreLink(
                sp_type="plm_model", sp_key="M2", target_kind="property", target_ref="x.y"
            )
        )
        db.commit()
        fake.rename("plm_model", "M2", "M2-NEW")
        run = _pull(db, fake)
        assert run.counts["plm_model"]["renamed"] == 1
        assert _obj(db, "plm_model", "M2") is None
        moved = _obj(db, "plm_model", "M2-NEW")
        assert moved is not None and moved.previous_keys == ["M2"]
        link = db.scalar(select(SpCoreLink))
        assert link is not None and link.sp_key == "M2-NEW"
        edge = db.scalar(select(SpCoreRelation))
        assert edge is not None and edge.src == "M2-NEW"

    def test_전량을_받으면_이번에_안_온_것을_사라진_것으로(
        self, db: Session, fake: FakeSp
    ) -> None:
        """**규칙 7** — 표식 없이 빠진 것(토큰 주인의 소속이 줄었다)은 전량 대조로만 안다."""
        _pull(db, fake)
        fake.drop("dept", "D3", quiet=True)
        incremental = _pull(db, fake)
        still = _obj(db, "dept", "D3")
        assert still is not None and not still.deleted
        assert incremental.counts["dept"].get("absent", 0) == 0
        whole = _pull(db, fake, full=True)
        gone = _obj(db, "dept", "D3")
        assert gone is not None and gone.deleted
        assert whole.counts["dept"]["absent"] == 1

    def test_커서를_못_읽으면_커서_없이_다시_받는다(self, db: Session, fake: FakeSp) -> None:
        """**규칙 11** — 404 하나로 타입을 통째로 멈추지 않는다."""
        fake.bad_cursor_once = True
        run = _pull(db, fake)
        assert run.ok, run.error
        assert run.counts["dept"]["cursor_restart"] == 1
        assert (
            len(db.scalars(select(SpCoreObject).where(SpCoreObject.type_slug == "dept")).all())
            == 5
        )

    def test_공개가_풀린_타입은_멈추고_알리되_받은_것은_남긴다(
        self, db: Session, fake: FakeSp
    ) -> None:
        _pull(db, fake)
        fake.unpublished.add("dept")
        run = _pull(db, fake)
        assert run.ok, "다른 타입은 그대로 받는다"
        assert any("dept" in one for one in run.warnings)
        db.expire_all()
        dept = db.scalar(select(SpCoreType).where(SpCoreType.slug == "dept"))
        assert dept is not None and dept.published is False
        assert (
            len(db.scalars(select(SpCoreObject).where(SpCoreObject.type_slug == "dept")).all())
            == 5
        )

    def test_선이_reset_이면_처음부터_받고_안_온_선을_끊는다(
        self, db: Session, fake: FakeSp
    ) -> None:
        _pull(db, fake)
        fake.put("plm_model", "M3", "모델 3")
        fake.edges["plm_model"].clear()
        fake.link("plm_model", "M3", "plm_derived_from", "M1", "plm_model")
        fake.reset_once = True
        run = _pull(db, fake)
        assert run.counts["plm_model"]["relations_reset"] == 1
        db.expire_all()
        live = {(e.src, e.dst) for e in db.scalars(select(SpCoreRelation)) if not e.deleted}
        assert live == {("M3", "M1")}

    def test_토큰이_틀리면_기록에_이유를_남긴다(self, db: Session, fake: FakeSp) -> None:
        with SpCoreClient(BASE, "wrong", transport=httpx.MockTransport(fake.handle)) as client:
            run = sync.pull(db, client)
        assert run.ok is False and "core:read" in (run.error or "")


# ── API ─────────────────────────────────────────────────────────────────────


def _member(client: TestClient, admin_headers: dict[str, str]) -> dict[str, str]:
    """자료 관리자가 아닌 사람."""
    made = client.post(
        "/api/workspaces",
        json={"name": "SP 시험 부서", "slug": "sp-test"},
        headers=admin_headers,
    )
    assert made.status_code == 201, made.text
    account = client.post(
        "/api/accounts",
        json={
            "email": "plain@sp.com",
            "display_name": "보통",
            "workspace_slug": "sp-test",
            "role": "member",
        },
        headers=admin_headers,
    )
    assert account.status_code in (200, 201), account.text
    token = client.post(
        "/api/auth/login",
        json={"email": "plain@sp.com", "password": account.json()["temporary_password"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def received(db: Session) -> None:
    """받은 원본을 바로 심는다 — API 시험은 받기를 다시 시험하지 않는다."""
    db.add_all(
        [
            SpCoreType(slug="property", label="물성"),
            SpCoreType(slug="organization", label="기관"),
            SpCoreObject(
                type_slug="property", key="mechanical.yield_strength", label="항복강도"
            ),
            SpCoreObject(type_slug="property", key="sp-0002", label="인장강도"),
            SpCoreObject(type_slug="property", key="sp-0003", label="경도"),
            SpCoreObject(type_slug="property", key="sp-0099", label="없는 물성"),
            SpCoreObject(type_slug="organization", key="ORG-1", label="포스코"),
            SpCoreObject(
                type_slug="organization", key="ORG-2", label="현대제철", deleted=True
            ),
        ]
    )
    db.add_all(
        [
            CatalogDefinition(
                key="mechanical.yield_strength",
                domain="mechanical",
                name="Yield strength",
                value_type="numeric",
                si_unit="Pa",
            ),
            CatalogDefinition(
                key="mechanical.tensile_strength",
                domain="mechanical",
                name="인장강도",
                value_type="numeric",
                si_unit="Pa",
            ),
            CatalogDefinition(
                key="mechanical.hardness_hv",
                domain="mechanical",
                name="경도",
                value_type="numeric",
            ),
            CatalogDefinition(
                key="mechanical.hardness_hb",
                domain="mechanical",
                name="경도",
                value_type="numeric",
            ),
        ]
    )
    field = PropertyField(key="mechanical", name="기계")
    db.add(field)
    db.flush()
    db.add(PropertyGroup(key="pg-strength", name="강도", field_id=field.id))
    db.commit()


def _term(db: Session, axis_slug: str, value: str, *aliases: str) -> str:
    ensure_builtin_vocabularies(db)
    axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == axis_slug))
    assert axis is not None
    term = vocabulary_services.resolve_or_create(db, axis, value, created_by_id=None)
    assert term is not None
    for alias in aliases:
        db.add(
            VocabularyAlias(
                vocabulary_id=axis.id,
                term_id=term.id,
                alias=alias,
                normalized=compare_key(alias),
            )
        )
    db.commit()
    return str(term.id)


class TestAPI:
    def test_설정이_없으면_상태가_말하고_받기를_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], received: None
    ) -> None:
        status = client.get("/api/sp-core/status", headers=admin_headers).json()
        assert status["configured"] is False
        assert {one["slug"] for one in status["types"]} == {"property", "organization"}
        got = client.post("/api/sp-core/sync", json={}, headers=admin_headers)
        assert got.status_code == 409
        assert got.json()["error"]["code"] == "MNX-SPCORE-0001"

    def test_받기를_부르면_큐에_넣고_남긴다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "sp_core_url", BASE)
        monkeypatch.setattr(settings, "sp_core_token", "tok")
        got = client.post("/api/sp-core/sync", json={"full": True}, headers=admin_headers)
        assert got.status_code == 202, got.text
        job = db.get(Job, uuid.UUID(got.json()["job_id"]))
        assert job is not None and job.kind == "sp_core.pull" and job.payload["full"] is True
        status = client.get("/api/sp-core/status", headers=admin_headers).json()
        assert status["configured"] is True and status["source"] == "http://sp.test"
        assert "tok" not in str(status), "토큰은 상태에 안 싣는다"

    def test_대조는_키_이름_별칭이_하나에만_맞는_것을_후보로(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        received: None,
    ) -> None:
        got = client.get(
            "/api/sp-core/match",
            params={"sp_type": "property", "target": "property"},
            headers=admin_headers,
        )
        assert got.status_code == 200, got.text
        body = got.json()
        matched = {one["sp_key"]: (one["target_ref"], one["by"]) for one in body["matched"]}
        assert matched == {
            "mechanical.yield_strength": ("mechanical.yield_strength", "key"),
            "sp-0002": ("mechanical.tensile_strength", "name"),
        }
        # 「경도」 는 둘에 맞는다 — 후보가 아니라 애매함이다(짐작해서 잇지 않는다).
        assert [one["sp_key"] for one in body["ambiguous"]] == ["sp-0003"]
        assert [one["sp_key"] for one in body["sp_only"]] == ["sp-0099"]

        term_id = _term(db, "manufacturer", "POSCO", "포스코")
        terms = client.get(
            "/api/sp-core/match",
            params={"sp_type": "organization", "target": "term", "vocabulary": "manufacturer"},
            headers=admin_headers,
        ).json()
        assert [(one["sp_key"], one["target_ref"], one["by"]) for one in terms["matched"]] == [
            ("ORG-1", term_id, "alias")
        ]
        # 지워진 SP 객체(ORG-2)는 대조에 안 선다.
        assert terms["sp_total"] == 1

    def test_잇기는_미리보기가_기본이고_오류가_하나라도_있으면_하나도_안_잇는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        received: None,
    ) -> None:
        good = {
            "sp_type": "property",
            "sp_key": "sp-0002",
            "target": "property",
            "target_ref": "mechanical.tensile_strength",
        }
        bad = {**good, "sp_key": "sp-0099", "target_ref": "mechanical.nothing"}
        gone = {
            "sp_type": "organization",
            "sp_key": "ORG-2",
            "target": "property_field",
            "target_ref": "mechanical",
        }
        preview = client.post(
            "/api/sp-core/links", json={"items": [good]}, headers=admin_headers
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["applied"] is False and preview.json()["new"] == 1
        assert db.scalar(select(SpCoreLink)) is None, "미리보기는 안 쓴다"

        refused = client.post(
            "/api/sp-core/links",
            json={"items": [good, bad, gone], "dry_run": False},
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "MNX-SPCORE-0004"
        assert db.scalar(select(SpCoreLink)) is None, "오류가 있으면 좋은 줄도 안 잇는다"
        reasons = {
            one["sp_key"]: one["reason"] for one in refused.json()["error"]["details"]["rows"]
        }
        assert "없습니다" in reasons["sp-0099"] and "사라진" in reasons["ORG-2"]

        made = client.post(
            "/api/sp-core/links",
            json={"items": [good], "dry_run": False, "note": "이름이 같다"},
            headers=admin_headers,
        )
        assert made.status_code == 200, made.text
        assert made.json()["applied"] is True
        link = db.scalar(select(SpCoreLink))
        assert link is not None and link.target_ref == "mechanical.tensile_strength"
        audit = db.scalar(select(AuditEntry).where(AuditEntry.action == "sp_core.linked"))
        assert audit is not None and audit.target_id == link.id

        again = client.post(
            "/api/sp-core/links",
            json={"items": [good], "dry_run": False},
            headers=admin_headers,
        )
        assert again.json()["exists"] == 1 and again.json()["new"] == 0

        detail = client.get(
            "/api/sp-core/objects/property/sp-0002", headers=admin_headers
        ).json()
        assert [one["target_label"] for one in detail["links"]] == ["인장강도"]
        matched = client.get(
            "/api/sp-core/match",
            params={"sp_type": "property", "target": "property"},
            headers=admin_headers,
        ).json()
        assert matched["linked_total"] == 1

        removed = client.post(
            "/api/sp-core/links/remove",
            json={"ids": [str(link.id)], "dry_run": False},
            headers=admin_headers,
        )
        assert removed.status_code == 200, removed.text
        db.expire_all()
        assert db.scalar(select(SpCoreLink)) is None
        assert db.scalar(select(AuditEntry).where(AuditEntry.action == "sp_core.unlinked"))

    def test_잇기_끊기_받기는_자료_관리자만(
        self, client: TestClient, admin_headers: dict[str, str], received: None
    ) -> None:
        plain = _member(client, admin_headers)
        item = {
            "sp_type": "property",
            "sp_key": "sp-0002",
            "target": "property",
            "target_ref": "mechanical.tensile_strength",
        }
        assert (
            client.post(
                "/api/sp-core/links", json={"items": [item]}, headers=plain
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/sp-core/links/remove", json={"ids": [str(uuid.uuid4())]}, headers=plain
            ).status_code
            == 403
        )
        assert client.post("/api/sp-core/sync", json={}, headers=plain).status_code == 403
        # 읽기는 누구나 — 바깥 시스템의 공개 목록이다.
        assert client.get("/api/sp-core/status", headers=plain).status_code == 200
        listed = client.get(
            "/api/sp-core/objects", params={"type": "property", "q": "강도"}, headers=plain
        ).json()
        assert {one["key"] for one in listed["items"]} == {
            "mechanical.yield_strength",
            "sp-0002",
        }
