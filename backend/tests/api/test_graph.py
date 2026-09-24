"""지식 그래프 — **큰 데이터를 통째로 안 주고, 안 보이는 것은 없는 것과 같다.**

무는 것:

    구조       종류·관계 종류만 — 객체가 몇이든 노드는 종류 수. 걸린 수가 붙는다
    시작점     찾기(전체 검색과 같은 함수)와 훑기(이름순 쪽)
    이웃       depth·fanout·limit 상한을 서버가 강제하고, 잘리면 잘렸다고 말한다
    노드       요약과 방향에 맞는 관계 이름
    가시성     잠근 부서의 재료는 남에게 노드도 선도 수도 없다 — MCP 온톨로지와 같은 규칙
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_ontology import _chain, _login_member_of

OVERVIEW = "/api/graph/overview"


def _node(kind: str, ident: str) -> str:
    return f"{kind}:{ident}"


class Test구조:
    def test_종류가_노드이고_관계_종류가_선이다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        _chain(client, db, admin_headers, owner_slug=None)
        body = client.get(OVERVIEW, headers=admin_headers).json()
        slugs = {one["slug"] for one in body["nodes"]}
        assert {"material", "sample", "specimen", "test_run", "property", "source"} <= slugs
        counts = {one["slug"]: one["count"] for one in body["nodes"]}
        assert counts["material"] >= 1 and counts["test_run"] >= 1
        edges = {one["relation"]: one for one in body["edges"]}
        # 관계는 레지스트리의 것 그대로 — 실린 자리가 없는 `edge` 는 빠진다.
        assert edges["derived_from"]["src_type"] == "sample"
        assert edges["derived_from"]["dst_type"] == "material"
        assert edges["derived_from"]["count"] >= 1
        # 정의만 있고 아직 안 이어진 선은 0 으로 드러난다 — 화면이 점선으로 그린다.
        assert edges["set_of"]["count"] == 0
        assert body["object_count"] == sum(counts.values())
        # 상세 화면 주소는 목록 서식으로(`{id}` 없이).
        assert (
            next(one for one in body["nodes"] if one["slug"] == "material")["detail_path"]
            == "/materials"
        )


class Test시작점:
    def test_찾기는_종류를_가리지_않는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        made = _chain(client, db, admin_headers, owner_slug=None)
        material = client.get(
            f"/api/materials/{made['material']}", headers=admin_headers
        ).json()
        hits = client.get(
            "/api/graph/search", params={"q": material["grade"]}, headers=admin_headers
        ).json()
        ids = {one["id"] for one in hits}
        assert _node("material", made["material"]) in ids
        # 재료 이름을 물려받은 시료·시편도 걸린다 — 종류가 다르다.
        assert {one["type_slug"] for one in hits} >= {"material", "sample"}
        first = next(one for one in hits if one["id"] == _node("material", made["material"]))
        assert first["type_label"] == "재료"
        assert first["key"] == material["code"]

    def test_훑기는_이름순_쪽이다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        for _ in range(3):
            _chain(client, db, admin_headers, owner_slug=None)
        page = client.get(
            "/api/graph/browse",
            params={"type": "material", "limit": 2, "offset": 0},
            headers=admin_headers,
        ).json()
        assert page["total"] >= 3 and len(page["items"]) == 2
        labels = [one["label"] for one in page["items"]]
        assert labels == sorted(labels)
        assert (
            client.get(
                "/api/graph/browse", params={"type": "no_such"}, headers=admin_headers
            ).status_code
            == 404
        )


class Test이웃:
    def test_한_단계씩_상한_안에서_잘렸다고_말한다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        made = _chain(client, db, admin_headers, owner_slug=None)
        focus = _node("material", made["material"])
        one_hop = client.get(
            "/api/graph/neighborhood",
            params={"focus": focus, "depth": 1},
            headers=admin_headers,
        ).json()
        assert one_hop["focus"] == focus
        types = {n["type_slug"] for n in one_hop["nodes"]}
        assert "sample" in types and "specimen" not in types
        # 시료는 아래에 시편이 더 있다 — 화면에 안 실렸으니 「+N」 의 근거가 선다.
        sample = next(n for n in one_hop["nodes"] if n["type_slug"] == "sample")
        assert sample["degree"] == 2 and sample["truncated"] is True
        assert one_hop["truncated"] is True

        two_hops = client.get(
            "/api/graph/neighborhood",
            params={"focus": focus, "depth": 2},
            headers=admin_headers,
        ).json()
        assert {n["type_slug"] for n in two_hops["nodes"]} >= {
            "material",
            "sample",
            "specimen",
        }
        edge = next(e for e in two_hops["edges"] if e["relation"] == "derived_from")
        assert edge["src"] == _node("sample", made["sample"]) and edge["dst"] == focus
        assert edge["label"] == "이 시료가 나온 재료"

        # 클라이언트가 보낸 상한은 서버가 깎는다.
        capped = client.get(
            "/api/graph/neighborhood",
            params={"focus": focus, "depth": 99, "fanout": 99999, "limit": 999999},
            headers=admin_headers,
        ).json()
        assert (
            capped["depth"] == 6 and capped["fanout"] == 500 and capped["node_limit"] == 20000
        )

    def test_관계와_종류로_거른다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        made = _chain(client, db, admin_headers, owner_slug=None)
        focus = _node("test_run", made["test_run"])
        only = client.get(
            "/api/graph/neighborhood",
            params={"focus": focus, "depth": 1, "types": "test_type"},
            headers=admin_headers,
        ).json()
        assert {n["type_slug"] for n in only["nodes"]} == {"test_run", "test_type"}
        none = client.get(
            "/api/graph/neighborhood",
            params={"focus": focus, "depth": 1, "relations": "card_of"},
            headers=admin_headers,
        ).json()
        assert [n["id"] for n in none["nodes"]] == [focus]

    def test_없는_노드는_404(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        for focus in ("material:00000000-0000-0000-0000-000000000000", "nope:1", "garbage"):
            assert (
                client.get(
                    "/api/graph/neighborhood", params={"focus": focus}, headers=admin_headers
                ).status_code
                == 404
            )


class Test부분그래프와_노드:
    def test_한_종류_전부를_쪽으로_그_사이_선과_함께(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        made = _chain(client, db, admin_headers, owner_slug=None)
        body = client.get(
            "/api/graph/subgraph",
            params={"types": "material,sample", "limit": 100},
            headers=admin_headers,
        ).json()
        ids = {n["id"] for n in body["nodes"]}
        assert _node("material", made["material"]) in ids
        assert _node("sample", made["sample"]) in ids
        assert any(
            e["relation"] == "derived_from" and e["dst"] == _node("material", made["material"])
            for e in body["edges"]
        )
        assert body["total"] >= 2

    def test_노드_요약과_방향에_맞는_관계_이름(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        made = _chain(client, db, admin_headers, owner_slug=None)
        body = client.get(
            "/api/graph/node",
            params={"id": _node("sample", made["sample"])},
            headers=admin_headers,
        ).json()
        assert body["type_label"] == "시료"
        assert {f["label"] for f in body["facts"]} >= {"종류", "상태"}
        labels = {(r["label"], r["outgoing"]) for r in body["related"]}
        # 나가는 선은 label, 들어오는 선은 inverse_label.
        assert ("이 시료가 나온 재료", True) in labels
        assert ("이 시료에서 자른 시편", False) in labels
        assert body["related_total"] == 2
        assert body["detail_path"] is None  # 시료는 제 화면이 없다


class Test가시성:
    def test_다른_부서의_재료도_노드와_선과_수에_든다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**보기는 전원이다**(ADR 0035) — MCP 온톨로지와 같은 규칙(`visible_ids`).

        그래프가 따로 가리면 「목록에는 있는데 그림에는 없다」 가 되고, 구조 그림의 수가
        사람마다 달라진다 — 그때 어느 쪽이 맞는지 알 방법이 없다."""
        for slug, name in (("dept-a", "A 부서"), ("dept-b", "B 부서")):
            client.post(
                "/api/workspaces", json={"name": name, "slug": slug}, headers=admin_headers
            )
        made = _chain(client, db, admin_headers, owner_slug="dept-a")
        outsider = _login_member_of(
            client, admin_headers, slug="dept-b", email="graph-outsider@example.com"
        )
        focus = _node("material", made["material"])
        for path, params in (
            ("/api/graph/neighborhood", {"focus": focus}),
            ("/api/graph/node", {"id": focus}),
            ("/api/graph/neighborhood", {"focus": _node("specimen", made["specimen"])}),
        ):
            assert client.get(path, params=params, headers=outsider).status_code == 200
        material = client.get(
            f"/api/materials/{made['material']}", headers=admin_headers
        ).json()
        hits = client.get(
            "/api/graph/search", params={"q": material["grade"]}, headers=outsider
        )
        assert any(one["id"] == focus for one in hits.json())

        mine = client.get(OVERVIEW, headers=outsider).json()
        theirs = client.get(OVERVIEW, headers=admin_headers).json()

        def count(body: dict[str, Any], slug: str) -> int:
            return int(next(n["count"] for n in body["nodes"] if n["slug"] == slug))

        assert count(mine, "material") == count(theirs, "material")
