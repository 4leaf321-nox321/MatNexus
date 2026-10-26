"""문헌 재료 상세는 **벌의 점을 싣지 않는다**(ADR 0072).

2026-10-24 실측: 점 9,105개인 재료(Ti-6Al-4V L-PBF) 상세가 16 MB · 1.6 초였다 — 점마다 출처 ·
조건 · 갈리는 조건을 되풀이해 실었다. 값 검색은 S-N 점이 많은 재료 하나가 50줄 창을 채웠다.

    대표는 숨긴 점까지 넣고 고른다     빼고 고르면 상세의 대표가 비교 · 덱의 대표와 갈린다
    곡선 점은 대표로 뽑힌 것만         실온 점이 대표면 그 하나가 요약에 선다
    점은 벌마다 따로                   축 차례, 없는 벌은 404
    값 검색은 벌의 점을 한 줄로         점 수 · 범위 · 가장 가까운 점, 낱값은 그대로
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_catalog_batches import _import, bundle, defs  # noqa: F401  (픽스처)
from test_catalog_series import SOURCE, _curve, _post, lit  # noqa: F401  (픽스처)

from app.modules.catalog.models import CatalogMaterial

FATIGUE = "mechanical.fatigue_strength"
MODULUS = "mechanical.youngs_modulus"


@pytest.mark.usefixtures("lit")
class Test상세의_대표:
    def test_숨긴_곡선_점도_대표를_고르는_데_든다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        material = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 910001))
        assert material is not None
        hot = client.post(
            f"/api/catalog/materials/{material.id}/values",
            json={
                "property_key": MODULUS,
                "value_num": 30,
                "unit": "GPa",
                "conditions": {"temperature_k": 573.15},
                "method": "measured",
                "quality_tier": 1,
                "source": SOURCE,
            },
            headers=admin_headers,
        )
        assert hot.status_code == 201, hot.text
        made = _post(client, admin_headers, material, _curve())
        assert made.status_code == 201, made.text
        series_id = made.json()["series"]["id"]

        detail = client.get(
            f"/api/catalog/materials/{material.id}", headers=admin_headers
        ).json()
        modulus = [one for one in detail["values"] if one["property_key"] == MODULUS]
        # 실온 곡선 점(50 GPa)이 573 K 낱값을 이긴다 — 숨긴 점을 빼고 골랐다면 낱값이 대표다.
        heads = [one for one in modulus if one["representative"]]
        assert [(one["value_num"], one["series_id"]) for one in heads] == [
            (pytest.approx(5.0e10), series_id)
        ]
        # 나머지 곡선 점 둘은 안 실린다 — 낱값은 진 후보로 그대로 선다.
        assert len(modulus) == 2
        (loser,) = [one for one in modulus if not one["representative"]]
        assert loser["series_id"] is None and loser["value_num"] == pytest.approx(3.0e10)
        # 후보는 낱값과 곡선 벌마다 앞선 점 하나 — 숨긴 점 전부가 아니다.
        assert {one["n_candidates"] for one in modulus} == {2}

        # 비교 표의 대표와 같다(비교는 둘부터라 빈 재료를 곁에 둔다).
        other = CatalogMaterial(mt_id=910002, name="빈 재료", category="metal")
        db.add(other)
        db.commit()
        compare = client.get(
            "/api/catalog/compare",
            params={"ids": f"{material.id},{other.id}"},
            headers=admin_headers,
        ).json()
        (row,) = [one for one in compare["rows"] if one["property_key"] == MODULUS]
        assert row["cells"][0]["value_num"] == pytest.approx(5.0e10)
        # 후보 수도 상세와 같다 — 곡선 한 벌이 후보 하나다.
        assert row["cells"][0]["n_candidates"] == 2

    def test_출처를_한_번만_싣는_모양은_고를_때만(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """ADR 0073 — 출처 3종이 값 · 벌 1,200개에 되풀이됐다. 안 고르면 모양이 그대로다."""
        material = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 910001))
        assert material is not None
        assert _post(client, admin_headers, material, _curve()).status_code == 201
        url = f"/api/catalog/materials/{material.id}"

        inline = client.get(url, headers=admin_headers).json()
        assert inline["sources"] == []
        assert all(one["source"]["title"] == SOURCE["title"] for one in inline["series"])
        assert all(one["source"] is not None for one in inline["values"])

        once = client.get(url, params={"source_once": "true"}, headers=admin_headers).json()
        assert [one["title"] for one in once["sources"]] == [SOURCE["title"]]
        source_id = once["sources"][0]["id"]
        for one in [*once["values"], *once["series"]]:
            assert one["source"] is None and one["source_id"] == source_id
        # 출처 말고는 같은 응답이다.
        assert [one["id"] for one in once["values"]] == [one["id"] for one in inline["values"]]

    def test_짧은_머리는_셈에_쓰는_칸만_머리_전부는_쪽으로(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """ADR 0073 후속 — 벌 555개의 머리가 872 KB 였고 절반이 메모 · 조건이었다."""
        material = db.scalar(select(CatalogMaterial).where(CatalogMaterial.mt_id == 910001))
        assert material is not None
        labels = [f"곡선 {index}" for index in range(3)]
        for label in labels:
            made = _post(
                client,
                admin_headers,
                material,
                _curve(label=label, notes="원 논문 메모", conditions={"strain_rate_s": 0.001}),
            )
            assert made.status_code == 201, made.text
        url = f"/api/catalog/materials/{material.id}"

        full = client.get(url, params={"source_once": "true"}, headers=admin_headers).json()
        brief = client.get(
            url, params={"source_once": "true", "series_brief": "true"}, headers=admin_headers
        ).json()
        assert brief["series"] == [] and len(brief["series_brief"]) == 3
        assert full["series_brief"] == []
        for short, whole in zip(brief["series_brief"], full["series"], strict=True):
            # 셈에 쓰는 칸은 같고, 이름 · 메모 · 조건은 안 실린다.
            assert set(short) == {
                "id", "kind", "x_key", "x_unit", "x_min", "x_max", "columns",
                "point_count", "method", "quality_tier", "source", "source_id",
            }  # fmt: skip
            assert {key: whole[key] for key in short} == short
        assert [one["id"] for one in brief["values"]] == [one["id"] for one in full["values"]]

        first = client.get(f"{url}/series", params={"limit": 2}, headers=admin_headers).json()
        assert (first["total"], first["limit"], first["offset"]) == (3, 2, 0)
        rest = client.get(
            f"{url}/series", params={"limit": 2, "offset": 2}, headers=admin_headers
        ).json()
        paged = [*first["items"], *rest["items"]]
        # 상세와 같은 차례, 머리 전부(이름 · 메모 · 조건 · 출처까지).
        assert [one["id"] for one in paged] == [one["id"] for one in full["series"]]
        assert [one["label"] for one in paged] == labels
        assert all(one["notes"] == "원 논문 메모" for one in paged)
        assert all(one["source"]["title"] == SOURCE["title"] for one in paged)

        sets = client.get(
            f"{url}/series", params={"kind": "parameter_set"}, headers=admin_headers
        ).json()
        assert sets["total"] == 0 and sets["items"] == []
        too_many = client.get(f"{url}/series", params={"limit": 101}, headers=admin_headers)
        assert too_many.status_code == 422
        missing = client.get(
            f"/api/catalog/materials/{uuid.uuid4()}/series", headers=admin_headers
        )
        assert missing.status_code == 404

    def test_없는_벌의_점은_404(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        got = client.get(f"/api/catalog/series/{uuid.uuid4()}/points", headers=admin_headers)
        assert got.status_code == 404
        assert got.json()["error"]["code"] == "MNX-CATALOG-0071"


@pytest.mark.usefixtures("defs")
class Test값_검색의_벌:
    def _search(
        self, client: TestClient, headers: dict[str, str], **params: object
    ) -> list[dict[str, object]]:
        got = client.get(
            "/api/catalog/properties/search",
            params={"q": FATIGUE, "unit": "MPa", **params},
            headers=headers,
        )
        assert got.status_code == 200, got.text
        return [one for one in got.json()["hits"] if one["world"] == "catalog"]

    def test_산점은_한_줄로_묶이고_낱값은_따로다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        assert _import(client, admin_headers, bundle(), apply=True).status_code == 200
        hits = self._search(client, admin_headers, min=200, max=450)
        # 낱값 240 하나와 S-N 점 넷을 묶은 한 줄 — 점 넷이 넷 줄로 서지 않는다.
        assert len(hits) == 2
        (single,) = [one for one in hits if one["series"] is None]
        (grouped,) = [one for one in hits if one["series"] is not None]
        assert single["value"] == pytest.approx(240) and single["count"] == 1
        assert grouped["series"] == "S-N R=-1"
        assert grouped["count"] == 4
        assert (grouped["low"], grouped["high"]) == pytest.approx((245, 400))
        # 기준이 없으면 가장 작은 점 — 값 오름차순이라 낱값 240 이 먼저다.
        assert grouped["value"] == pytest.approx(245)
        assert [one["value"] for one in hits] == pytest.approx([240, 245])

    def test_근처로_물으면_창에_든_점만_세고_가장_가까운_점이_값이다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        assert _import(client, admin_headers, bundle(), apply=True).status_code == 200
        # 260 ±10% = 234 ~ 286 — S-N 점 중 250 · 245 만 든다.
        hits = self._search(client, admin_headers, near=260)
        assert [(one["series"], one["count"], one["value"]) for one in hits] == [
            ("S-N R=-1", 2, pytest.approx(250)),
            (None, 1, pytest.approx(240)),
        ]
        assert (hits[0]["low"], hits[0]["high"]) == pytest.approx((245, 250))
        # 366 ±10% = 329.4 ~ 402.6 — 330(36 아래)보다 400(34 위)이 가깝다.
        hits = self._search(client, admin_headers, near=366)
        assert [(one["count"], one["value"]) for one in hits] == [(2, pytest.approx(400))]
