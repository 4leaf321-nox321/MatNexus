"""곡선 출처 · 곡선 점검 — 덱 카드에서 복원한 곡선이 실측처럼 쓰이던 것(2026-11-17, ADR 0096).

무는 것:

    출처를 적는다           올릴 때 · 고칠 때, 모르는 코드는 거절, 고치면 감사에 남는다
    경고만 한다             실측이 아닌 시험의 카드에 근거 경고 · 덱 머리 줄 — 카드는 선다
    곡선 점검               잰 공칭 곡선은 nominal, 출처는 실측인데 소성 표 모양이면 경고
"""

from __future__ import annotations

import math
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_card_stats_fixes import TRA, _process, _run

from app.modules.audit.models import AuditEntry
from app.modules.processing.models import ProcessingResult
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun
from app.shared import filestore
from matcore import curves
from matcore.parsers import Channel


@pytest.fixture
def steel(client: TestClient, admin_headers: dict[str, str], db: Session) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    db.commit()
    created = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": f"ORIGIN-{uuid.uuid4().hex[:6]}",
            "spec_thickness": 1.0,
            "poisson_ratio": 0.3,
            "density": 7850,
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    return dict(created.json())


class Test출처를_적는다:
    def test_올릴_때_적고_모르는_코드는_거절(
        self, client: TestClient, admin_headers: dict[str, str], steel: dict[str, Any]
    ) -> None:
        sample = client.post(
            f"/api/materials/{steel['id']}/samples", json={}, headers=admin_headers
        ).json()
        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD"},
            headers=admin_headers,
        ).json()

        def upload(origin: str) -> Any:
            return client.post(
                "/api/test-runs",
                data={
                    "specimen_id": specimen["id"],
                    "test_type": "tensile",
                    "conditions": "{}",
                    "curve_origin": origin,
                },
                files={"file": (TRA.name, TRA.read_bytes())},
                headers=admin_headers,
            )

        made = upload("deck_restored")
        assert made.status_code == 202, made.text
        assert made.json()["curve_origin"] == "deck_restored"
        assert made.json()["curve_origin_label"] == "해석 덱 카드에서 복원"
        refused = upload("from_deck")
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "MNX-TESTS-0047"

    def test_고치면_감사에_남는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        steel: dict[str, Any],
    ) -> None:
        run_id = _run(client, admin_headers, db, steel["id"])
        assert (
            client.get(f"/api/test-runs/{run_id}", headers=admin_headers).json()[
                "curve_origin"
            ]
            == "measured"
        )
        fixed = client.patch(
            f"/api/test-runs/{run_id}",
            json={"curve_origin": "digitized"},
            headers=admin_headers,
        )
        assert fixed.status_code == 200, fixed.text
        assert fixed.json()["curve_origin"] == "digitized"
        entry = db.scalar(
            select(AuditEntry)
            .where(AuditEntry.target_id == uuid.UUID(run_id))
            .order_by(AuditEntry.created_at.desc())
        )
        assert entry is not None
        assert entry.changes["curve_origin"] == {"before": "measured", "after": "digitized"}
        # 안 보내면 그대로다.
        kept = client.patch(
            f"/api/test-runs/{run_id}", json={"note": "메모"}, headers=admin_headers
        ).json()
        assert kept["curve_origin"] == "digitized"


class Test경고만_한다:
    def test_실측이_아닌_시험으로_만든_카드에_근거_경고와_덱_머리_줄(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        steel: dict[str, Any],
    ) -> None:
        runs = [_run(client, admin_headers, db, steel["id"]) for _ in range(2)]
        for run_id in runs:
            _process(client, admin_headers, run_id)
        restored = db.get(TestRun, uuid.UUID(runs[1]))
        assert restored is not None
        restored.curve_origin = "deck_restored"
        db.commit()
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": steel["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "출처 섞임",
            },
            headers=admin_headers,
        )
        # **막지 않는다** — 카드는 선다.
        assert card.status_code == 201, card.text
        warnings = card.json()["source"]["warnings"]
        assert [(one["record_name"], one["label"]) for one in warnings] == [
            (restored.record_name, "실측이 아닌 곡선")
        ]
        deck = client.get(
            f"/api/fitting/cards/{card.json()['id']}/export?format=dyna", headers=admin_headers
        )
        assert deck.status_code == 200, deck.text
        assert f"실측이 아닌 곡선: {restored.record_name}" in deck.text


class Test곡선_점검:
    def test_잰_공칭_곡선은_nominal_이고_출처와_어긋나면_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        steel: dict[str, Any],
    ) -> None:
        """결과 곡선을 바꿔 쓰며 본다 — 고정물(Example.tra)은 13점에 첫 점이 최대의 57 % 라
        그 자체가 탄성 구간 없는 곡선이다(그것을 공칭으로 기대하면 틀린 시험이 된다)."""
        run_id = _run(client, admin_headers, db, steel["id"])
        result_id = _process(client, admin_headers, run_id)
        result = db.get(ProcessingResult, uuid.UUID(result_id))
        assert result is not None

        def rewrite(strain: list[float], stress: list[float]) -> Any:
            filestore.resolve(result.storage_path).write_bytes(
                curves.to_parquet(
                    [
                        Channel("strain_engineering", "공칭 변형률", "1", tuple(strain)),
                        Channel("stress_engineering", "공칭 응력", "Pa", tuple(stress)),
                    ]
                )
            )
            got = client.get(
                f"/api/processing/test-runs/{run_id}/curve-quality", headers=admin_headers
            )
            assert got.status_code == 200, got.text
            return got.json()

        # 잰 공칭 곡선 — 원점에서 탄성(200 GPa) → 300 MPa 에서 꺾여 경화, 잡음.
        strain = [index * 0.00005 for index in range(3000)]
        stress = [
            (200e9 * e if e < 0.0015 else 300e6 + 900e6 * (e - 0.0015))
            + 1e6 * math.sin(index * 1.7)
            for index, e in enumerate(strain)
        ]
        body = rewrite(strain, stress)
        assert body["result_id"] == result_id and body["adopted"] is True
        assert body["curve_origin"] == "measured"
        assert body["shape"] == "nominal", body["checks"]
        assert not any(one["key"] == "agreement" for one in body["checks"])

        # 소성 표 모양(변형률 0 에 σy) — 출처는 실측 그대로라 어긋남을 말한다.
        table = [index * 0.005 for index in range(40)]
        again = rewrite(table, [300e6 + 600e6 * (1 - math.exp(-e / 0.05)) for e in table])
        assert again["shape"] == "plastic_table", again["checks"]
        agreement = [one for one in again["checks"] if one["key"] == "agreement"]
        assert agreement and agreement[0]["verdict"] == "warn"

    def test_처리_결과가_없으면_출처만_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        steel: dict[str, Any],
    ) -> None:
        run_id = _run(client, admin_headers, db, steel["id"])
        body = client.get(
            f"/api/processing/test-runs/{run_id}/curve-quality", headers=admin_headers
        ).json()
        assert body["result_id"] is None and body["shape"] == "unclear"
        assert body["checks"][0]["key"] == "origin"
        assert "처리 결과가 없습니다" in body["notes"][0]
