"""공개 피로 반입을 위한 받는 쪽 — **수집기 요청(2026-10-24, ADR 0071)**.

산점은 점 하나도 받는다            1점 벌 274벌 — 산점의 점은 대표값에서 빠진다(곡선은 둘부터)
같은 출처를 여러 묶음이 쓴다         첫 묶음을 지워도 남고, 마지막 묶음을 지우면 함께 사라진다
원본 정의에 축을 덧붙인다            균열 성장률에 ΔK — 이관을 다시 돌려도 남는다
조건 칸 목록 밖은 경고만             받지만 미리보기가 센다
"""

from __future__ import annotations

import copy
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_catalog import make_snapshot
from test_catalog_batches import KEY, _import, bundle, defs  # noqa: F401  (픽스처)

from app.modules.catalog import importer, parameters
from app.modules.catalog.local_definitions import (
    axis_extensions,
    condition_keys,
    ensure_axis_extensions,
    ensure_local_definitions,
    extended_axes,
    load_seed,
)
from app.modules.catalog.models import (
    CatalogDefinition,
    CatalogSource,
    CatalogValue,
)
from matcore import units

CRACK = "mechanical.crack_growth_rate"
OTHER = "materialcollector/fatigue-literature-second/2026-10-24"


@pytest.mark.usefixtures("defs")
class Test산점_1점:
    def test_산점은_점_하나도_받고_곡선은_둘부터(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        one = bundle()
        one["series"][0]["rows"] = [[1e7, 250]]
        one["series"][0]["row_conditions"] = [{"runout": True}]
        shown = _import(client, admin_headers, one, apply=False).json()
        assert shown["problems"] == [] and shown["points"] == 1

        curve = copy.deepcopy(one)
        curve["series"][0]["kind"] = "curve"
        curve["series"][0]["row_conditions"] = None
        shown = _import(client, admin_headers, curve, apply=False).json()
        assert "2개 이상" in shown["problems"][0]["message"]


def _second() -> dict[str, Any]:
    """같은 DOI 출처를 쓰는 두 번째 묶음 — 재료 이름은 달라야 한다(같은 이름은 거절)."""
    body = bundle()
    body["batch"]["key"] = OTHER
    body["materials"][0]["name"] = "AISI 304 sheet, annealed (second lot)"
    return body


def _sources(db: Session) -> int:
    db.expire_all()
    return int(
        db.scalar(
            select(func.count())
            .select_from(CatalogSource)
            .where(CatalogSource.doi == "10.3390/met-test-1")
        )
        or 0
    )


@pytest.mark.usefixtures("defs")
class Test공유_출처:
    @pytest.mark.parametrize("first", [KEY, OTHER])
    def test_마지막_묶음을_지울_때_출처가_사라진다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        first: str,
    ) -> None:
        assert _import(client, admin_headers, bundle(), apply=True).status_code == 200
        assert _import(client, admin_headers, _second(), apply=True).status_code == 200
        assert _sources(db) == 1
        last = OTHER if first == KEY else KEY

        gone = client.delete(
            f"/api/catalog/batches/{first}?dry_run=false", headers=admin_headers
        )
        assert gone.status_code == 200, gone.text
        # 아직 남은 묶음의 값이 그 출처를 쓴다 — 지우지 않는다.
        assert _sources(db) == 1
        source_id = db.scalar(
            select(CatalogSource.id).where(CatalogSource.doi == "10.3390/met-test-1")
        )
        assert db.scalar(
            select(func.count())
            .select_from(CatalogValue)
            .where(CatalogValue.source_id == source_id)
        )

        gone = client.delete(
            f"/api/catalog/batches/{last}?dry_run=false", headers=admin_headers
        )
        assert gone.status_code == 200, gone.text
        assert _sources(db) == 0


@pytest.mark.usefixtures("defs")
class Test조건_칸:
    def test_목록_밖의_조건_칸만_경고한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        body = bundle()
        body["values"][0]["conditions"] = {
            "temperature_k": 296.15,
            "thickness_mm": 1.0,
            "aging_weeks": 2,
        }
        body["values"][1]["conditions"] = {"cycles": 1e7, "aging_weeks": 4}
        shown = _import(client, admin_headers, body, apply=False).json()
        assert shown["problems"] == []
        assert [(one["key"], one["count"], one["example"]) for one in shown["warnings"]] == [
            ("aging_weeks", 2, "v-uts")
        ]

    def test_목록을_누구나_읽는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        got = client.get("/api/catalog/condition-fields", headers=admin_headers)
        assert got.status_code == 200, got.text
        keys = {one["key"] for one in got.json()}
        assert {"loading_mode", "stress_basis", "aging_hours", "weld_zone"} <= keys
        assert "aging_weeks" not in keys
        assert keys == condition_keys()


class Test새_키와_축:
    def test_씨앗의_새_키는_단위가_단위표에_있고_없는_것만_만든다(self, db: Session) -> None:
        seed = load_seed()
        for row in seed:
            if row.get("si_unit") is not None:
                assert units.canonical(row["si_unit"]) is not None, row["key"]
        made = ensure_local_definitions(db)
        assert "local.mechanical.welded_joint_fatigue_strength" in made
        assert "local.mechanical.fatigue_crack_growth_threshold" in made
        threshold = db.scalar(
            select(CatalogDefinition).where(
                CatalogDefinition.key == "local.mechanical.fatigue_crack_growth_threshold"
            )
        )
        assert threshold is not None and threshold.si_unit == units.canonical("Pa·m^0.5")

    def test_원본_축_뒤에_덧붙이고_이관을_다시_돌려도_남는다(
        self, db: Session, tmp_path: Path
    ) -> None:
        snapshot = make_snapshot(tmp_path)
        con = sqlite3.connect(snapshot)
        con.execute(
            "insert into property_definition values (99, 'mechanical.crack_growth_rate', "
            "'mechanical', '균열 성장률', 'da/dN', 'm/cycle', 'numeric', null, null, "
            "'[\"thermal_cycle_profile\", \"statistic\"]', '2026-07-01 00:00:00')"
        )
        con.commit()
        con.close()
        for _ in range(2):
            importer.run(db, snapshot)
            db.commit()
            db.expire_all()
            axes = db.scalar(
                select(CatalogDefinition.condition_axes).where(CatalogDefinition.key == CRACK)
            )
            # 원본 축은 그대로 앞에, 덧붙인 축은 뒤에.
            assert axes is not None and axes[:2] == ["thermal_cycle_profile", "statistic"]
            assert "delta_k_pa_sqrt_m" in axes
        assert ensure_axis_extensions(db) == []

    def test_덧붙이기는_빠진_것만_한_번(self) -> None:
        extra = {CRACK: ["delta_k_pa_sqrt_m", "statistic"]}
        assert extended_axes(CRACK, ["statistic"], extra) == ["statistic", "delta_k_pa_sqrt_m"]
        assert extended_axes("other.key", ["a"], extra) == ["a"]
        assert "delta_k_pa_sqrt_m" in axis_extensions()[CRACK]

    @pytest.mark.usefixtures("defs")
    def test_균열_성장률_곡선은_ΔK_를_MPa_m05_로_받아_Pa_m05_로(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
    ) -> None:
        db.add(
            CatalogDefinition(
                mt_id=177,
                key=CRACK,
                name="균열 성장률",
                domain="mechanical",
                si_unit="m/cycle",
                value_type="numeric",
                condition_axes=["thermal_cycle_profile"],
            )
        )
        db.commit()
        assert ensure_axis_extensions(db) == [CRACK]
        db.commit()
        parameters.forget()
        body = bundle()
        body["values"] = []
        body["series"] = [
            {
                "key": "dadn-1",
                "material": "mat-304",
                "source": "src-smith",
                "kind": "curve",
                "label": "da/dN-ΔK R=0.1",
                "x_key": "delta_k_pa_sqrt_m",
                "x_unit": "MPa·m^0.5",
                "columns": [{"property_key": CRACK, "unit": "m/cycle"}],
                "rows": [[5.0, 1e-9], [10.0, 1e-8], [20.0, 1e-7]],
                "conditions": {"stress_ratio_R": 0.1},
                "quality_tier": 3,
                "method": "digitized",
            }
        ]
        applied = _import(client, admin_headers, body, apply=True)
        assert applied.status_code == 200, applied.text
        points = db.scalars(
            select(CatalogValue).where(CatalogValue.property_key == CRACK)
        ).all()
        assert sorted((one.conditions or {})["delta_k_pa_sqrt_m"] for one in points) == [
            pytest.approx(5.0e6),
            pytest.approx(1.0e7),
            pytest.approx(2.0e7),
        ]
