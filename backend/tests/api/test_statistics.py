"""재료 단위 통계 — **묶음이 맞는가, 아무것도 조용히 빠지지 않는가.**

이 파일이 지키는 것은 둘이다.

1. **묶음은 재료 + 시험종류 + 방향이다.** 인장은 압연 방향에 따라 물성이 다르다
   — MD 와 TD 를 섞으면 CV 가 크게 나오는데 그것은 산포가 아니라 다른 것을
   섞은 것이다.

2. **빠진 것을 말한다.** 채택 안 된 시험, 이상치, 격자가 달라 못 낸 곡선 —
   전부 이유와 함께 남는다. 조용히 빠지면 n 이 왜 그 수인지 알 수 없다.

계산 자체는 `tests/unit/test_statistics.py` 가 손으로 검산한 값으로 본다.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.tests import services
from app.modules.tests.definitions import ensure_builtin_test_types

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

STEPS: list[dict[str, Any]] = [
    {"plugin": "tensile.engineering", "options": {"gauge_length": 0.05, "area": 12.12e-6}},
    {
        "plugin": "curve.sort_unique",
        "options": {"x": "strain_engineering", "duplicate_policy": "mean"},
    },
    {"plugin": "tensile.strength", "options": {}},
]


@pytest.fixture
def material(client: TestClient, admin_headers: dict[str, str], db: Session) -> dict[str, Any]:
    ensure_builtin_test_types(db)
    db.commit()
    created: dict[str, Any] = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": "STAT",
            "details": "MDOI",
            "spec_thickness": 1.0,
        },
        headers=admin_headers,
    ).json()
    return created


def _run(
    client: TestClient,
    headers: dict[str, str],
    db: Session,
    material_id: str,
    orientation: str,
) -> str:
    sample = client.post(
        f"/api/materials/{material_id}/samples", json={}, headers=headers
    ).json()
    specimen = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": orientation},
        headers=headers,
    ).json()
    created = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=headers,
    ).json()
    assert services.parse_run(db, uuid.UUID(created["id"])) == "parsed"
    return str(created["id"])


def _run_in(
    client: TestClient,
    headers: dict[str, str],
    db: Session,
    sample_id: str,
    orientation: str,
) -> str:
    """이미 만든 시료에 시편·시험을 붙인다. `_run` 은 시료도 새로 만든다."""
    specimen = client.post(
        f"/api/samples/{sample_id}/specimens",
        json={"orientation": orientation},
        headers=headers,
    ).json()
    created = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=headers,
    ).json()
    assert services.parse_run(db, uuid.UUID(created["id"])) == "parsed"
    return str(created["id"])


def _adopt(client: TestClient, headers: dict[str, str], run_id: str) -> None:
    stored = client.post(
        "/api/processing/results",
        json={"test_run_id": run_id, "steps": STEPS},
        headers=headers,
    ).json()
    client.post(f"/api/processing/results/{stored['id']}/adopt", headers=headers)


class Test묶음:
    def test_방향을_섞지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        """**압연 방향에 따라 물성이 다르다.**

        MD 와 TD 를 한 통계로 묶으면 CV 가 크게 나오는데, 그것은 산포가 아니라
        서로 다른 것을 섞은 것이다. 강판은 20% 넘게 차이 나기도 한다.
        """
        for orientation in ("MD", "MD", "TD"):
            _adopt(
                client,
                admin_headers,
                _run(client, admin_headers, db, material["id"], orientation),
            )

        body = client.get(
            f"/api/statistics/materials/{material['id']}", headers=admin_headers
        ).json()
        by_orientation = {group["orientation"]: group for group in body["groups"]}
        assert set(by_orientation) == {"MD", "TD"}
        assert by_orientation["MD"]["sample_count"] == 2
        assert by_orientation["TD"]["sample_count"] == 1

    def test_채택_안_된_시험은_빠지고_그_사실을_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        # **조용히 빼면 n 이 왜 그 수인지 모른다.**
        _adopt(client, admin_headers, _run(client, admin_headers, db, material["id"], "MD"))
        _adopt(client, admin_headers, _run(client, admin_headers, db, material["id"], "MD"))
        _run(client, admin_headers, db, material["id"], "MD")  # 채택 안 함

        group = client.get(
            f"/api/statistics/materials/{material['id']}", headers=admin_headers
        ).json()["groups"][0]
        assert group["sample_count"] == 2
        assert group["skipped_unadopted"] == 1
        assert any("채택되지 않은 시험 1건" in note for note in group["notes"])


class Test통계값:
    @pytest.fixture
    def three(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> dict[str, Any]:
        for _ in range(3):
            _adopt(
                client, admin_headers, _run(client, admin_headers, db, material["id"], "MD")
            )
        groups = client.get(
            f"/api/statistics/materials/{material['id']}", headers=admin_headers
        ).json()["groups"]
        return dict(groups[0])

    def test_항목마다_흩어짐을_낸다(self, three: dict[str, Any]) -> None:
        keys = {row["key"] for row in three["scalars"]}
        assert "tensile_strength" in keys
        row = next(row for row in three["scalars"] if row["key"] == "tensile_strength")
        assert row["count"] == 3
        assert row["ci95_low"] is not None and row["ci95_high"] is not None
        assert row["median"] == pytest.approx(row["mean"])

    def test_평균이_뜻없는_항목은_빼놓는다(self, three: dict[str, Any]) -> None:
        """`necking_candidate_index` 는 배열 위치다. 평균 14.0 은 아무 뜻이 없다."""
        keys = {row["key"] for row in three["scalars"]}
        assert not any(key.endswith("_index") for key in keys)
        assert "elastic_r_squared" not in keys
        assert "proof_offset" not in keys

    def test_곡선_통계가_나온다(self, three: dict[str, Any]) -> None:
        # 같은 파일이라 격자가 같다 — 실무에서는 재샘플을 거쳐야 이 상태가 된다.
        assert three["curve"] is not None
        assert three["curve"]["x"] == "strain_engineering"
        assert len(three["curve"]["mean"]) == len(three["curve"]["median"])
        assert len(three["curve"]["sd"]) == len(three["curve"]["mean"])


class Test저장:
    def test_불변으로_남긴다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        """**쓴 시험을 함께 박아 둔다.**

        나중에 시험이 늘면 평균이 달라지는데, 어제 보고서에 적은 값은 어제의
        표본으로 나온 것이다.
        """
        for _ in range(2):
            _adopt(
                client, admin_headers, _run(client, admin_headers, db, material["id"], "MD")
            )

        saved = client.post(
            "/api/statistics/ensembles",
            json={
                "material_id": material["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
            },
            headers=admin_headers,
        )
        assert saved.status_code == 201, saved.text
        assert saved.json()["sample_count"] == 2
        assert len(saved.json()["test_run_ids"]) == 2

        # 시험을 하나 더 채택해도 저장된 것은 그대로다.
        _adopt(client, admin_headers, _run(client, admin_headers, db, material["id"], "MD"))
        listed = client.get(
            f"/api/statistics/ensembles?material_id={material['id']}", headers=admin_headers
        ).json()
        assert len(listed) == 1
        assert listed[0]["sample_count"] == 2

    def test_표본이_모자라면_남기지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        _adopt(client, admin_headers, _run(client, admin_headers, db, material["id"], "MD"))
        response = client.post(
            "/api/statistics/ensembles",
            json={
                "material_id": material["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text
        assert "2건 이상" in response.json()["error"]["message"]


class Test적은_표본:
    """**1건이라고 빈 화면을 주지 않는다.**

    설치 현장에서 나온 보고: 처리하고 채택까지 했는데 물성 탭이 텅 비었다. 값이
    분명히 있는데 아무것도 안 뜨니 고장으로 읽힌다. 원인은 커널이 1건을 거부하고
    (통계가 아니니 맞다) 그 거부를 표 전체를 버리는 것으로 처리한 것이었다.

    답은 **값과 흩어짐을 나누는 것**이다. 값은 준다 — 그 시편의 값이다.
    흩어짐은 안 준다 — 한 번 재서는 알 수 없다. 그리고 그 차이를 글로 적는다.
    """

    def test_채택_1건이면_값은_주고_흩어짐은_주지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        _adopt(client, admin_headers, _run(client, admin_headers, db, material["id"], "MD"))

        group = client.get(
            f"/api/statistics/materials/{material['id']}", headers=admin_headers
        ).json()["groups"][0]

        assert group["sample_count"] == 1
        assert group["scalars"], "1건이어도 그 시편의 값은 나와야 한다"
        row = next(item for item in group["scalars"] if item["key"] == "tensile_strength")
        assert row["count"] == 1
        assert row["mean"] == row["median"] == row["minimum"] == row["maximum"]

        # **0 이 아니라 없는 것이다.** 0 은 "여러 번 재서 같았다" 로 읽힌다.
        for key in ("sample_sd", "mad", "iqr", "coefficient_of_variation", "ci95_low"):
            assert row[key] is None, key
        assert row["outliers"] == []

        assert any("1건" in note for note in group["notes"])

    def test_채택_1건이면_그_곡선이_대표다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        """**평균 낼 상대가 없는 것과 그릴 곡선이 없는 것은 다르다.**

        1건이면 격자를 맞출 이유도 없다 — 맞출 상대가 없으니 재샘플 없이도
        그릴 수 있다. 전에는 문턱값(2건) 때문에 있는 곡선을 안 보여 줬다.
        """
        _adopt(client, admin_headers, _run(client, admin_headers, db, material["id"], "MD"))

        group = client.get(
            f"/api/statistics/materials/{material['id']}", headers=admin_headers
        ).json()["groups"][0]

        curve = group["curve"]
        assert curve is not None, "1건이어도 곡선은 나와야 한다"
        assert curve["mean"] == curve["median"], "한 점의 평균도 중앙값도 그 점이다"
        # **흩어짐은 내지 않는다.** 0 을 넣으면 "여러 번 재서 같았다" 로 읽힌다.
        assert curve["sd"] == []
        assert all(count == 1.0 for _, count in curve["count"])
        assert any("시편 1개" in note for note in group["notes"])

    def test_채택이_없으면_무엇을_해야_하는지_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        # 채택하지 않고 시험만 올린다 — 사용자가 가장 자주 서는 자리다.
        _run(client, admin_headers, db, material["id"], "MD")

        group = client.get(
            f"/api/statistics/materials/{material['id']}", headers=admin_headers
        ).json()["groups"][0]
        assert group["sample_count"] == 0
        assert group["scalars"] == []
        assert any("채택" in note for note in group["notes"])

    def test_2건_안내가_화면에_뜨는_것과_어긋나지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        """안내가 "변동계수를 내지 않았습니다" 인데 CV 열에는 값이 떠 있었다.

        커널은 2건부터 CV 를 내고 막는 것은 이상치뿐이다. 안내와 화면이 어긋나면
        둘 중 어느 쪽을 믿어야 하는지 알 수 없다.
        """
        for _ in range(2):
            _adopt(
                client, admin_headers, _run(client, admin_headers, db, material["id"], "MD")
            )

        group = client.get(
            f"/api/statistics/materials/{material['id']}", headers=admin_headers
        ).json()["groups"][0]
        row = next(item for item in group["scalars"] if item["key"] == "tensile_strength")
        assert row["coefficient_of_variation"] is not None
        assert not any("변동계수와 이상치는 내지 않" in note for note in group["notes"])
        assert any("이상치는 가려내지 않" in note for note in group["notes"])


class Test제조사섞임:
    """**묶음이 시료를 안 본다.**

    통계 묶음은 재료 + 시험종류 + 방향이라, 포스코 로트와 현대제철 로트가 한
    평균에 들어간다. 그때 CV 는 산포가 아니라 다른 것을 섞은 값이다 — MD 와 TD 를
    안 섞는 것과 같은 이유다. 갈라 주지는 않는다. 사람이 판단할 근거만 준다.
    """

    def test_제조사가_갈리면_말해_준다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        for maker in ("포스코", "현대제철"):
            sample = client.post(
                f"/api/materials/{material['id']}/samples",
                json={"manufacturer": maker},
                headers=admin_headers,
            ).json()
            _adopt(
                client,
                admin_headers,
                _run_in(client, admin_headers, db, sample["id"], "MD"),
            )

        group = client.get(
            f"/api/statistics/materials/{material['id']}", headers=admin_headers
        ).json()["groups"][0]
        assert group["sample_count"] == 2
        assert any("제조사가 시료마다 다릅니다" in note for note in group["notes"])

    def test_같은_제조사면_조용하다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        """**늘 켜져 있는 경고는 아무도 안 읽는다.**"""
        for _ in range(2):
            sample = client.post(
                f"/api/materials/{material['id']}/samples",
                json={"manufacturer": "포스코"},
                headers=admin_headers,
            ).json()
            _adopt(
                client,
                admin_headers,
                _run_in(client, admin_headers, db, sample["id"], "MD"),
            )

        group = client.get(
            f"/api/statistics/materials/{material['id']}", headers=admin_headers
        ).json()["groups"][0]
        assert not any("제조사" in note for note in group["notes"])


class Test요약:
    """홈에 뿌리는 요약 — **세는 일을 서버가 한다.**

    목록 엔드포인트만 있으면 화면이 재료 94개를 세려고 94행을 받는다. 홈은 매일
    열리는 화면이라 그 비용이 매일 든다.

    **부서 범위는 각 항목이 원래 따르는 규칙 그대로다.** 여기서 새 규칙을 만들면
    홈의 숫자와 목록 화면의 숫자가 갈리고, 그때 어느 쪽이 맞는지 알 방법이 없다.
    """

    def test_아무것도_없으면_전부_0_이다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        body = client.get("/api/statistics/overview", headers=admin_headers).json()
        assert body["material_count"] == 0
        assert body["card_total"] == 0
        assert body["families"] == []
        # **0 은 0 이라고 말한다.** 화면이 "안 보이게" 정하는 것이지 서버가
        # 감추면 "못 셌다" 와 구별이 안 된다.
        assert body["parse_failed"] == 0

    def test_넣은_만큼_센다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        run_id = _run(client, admin_headers, db, material["id"], "MD")

        body = client.get("/api/statistics/overview", headers=admin_headers).json()
        assert body["material_count"] == 1
        # `_run` 이 시료를 새로 만든다. 재료 픽스처는 시료를 안 만든다.
        assert body["sample_count"] == 1
        assert body["specimen_count"] == 1
        assert body["run_count"] == 1
        assert [(item["label"], item["count"]) for item in body["families"]] == [("Metal", 1)]
        assert [(item["label"], item["count"]) for item in body["test_types"]] == [
            ("인장시험", 1)
        ]

        # **채택 전이면 처리 대기다.** 이것이 2단계에 남은 일이다.
        assert body["waiting_to_process"] == 1
        _adopt(client, admin_headers, run_id)
        after = client.get("/api/statistics/overview", headers=admin_headers).json()
        assert after["waiting_to_process"] == 0

    def test_카드를_상태별로_가른다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session, material: Any
    ) -> None:
        """**초안과 확정을 한 숫자로 뭉치면 남은 일이 안 보인다.**

        개발 DB 가 초안 10 · 확정 1 이었다 — 만들어 놓고 승인을 안 받은 것이
        열이라는 뜻인데, 합쳐 놓으면 「카드 11」로만 보인다.

        카드를 API 로 만들려면 진응력 열까지 처리해야 한다. 여기서 보는 것은
        **세는 방식**이지 카드 만들기가 아니므로 행을 직접 넣는다.
        """
        from app.modules.fitting.models import PropertyCard
        from app.modules.tests.models import TestType

        test_type = db.scalar(select(TestType).where(TestType.key == "tensile"))
        assert test_type is not None
        card = PropertyCard(
            material_id=uuid.UUID(material["id"]),
            test_type_id=test_type.id,
            orientation="MD",
            label="요약용",
            status="draft",
        )
        db.add(card)
        db.commit()

        body = client.get("/api/statistics/overview", headers=admin_headers).json()
        assert body["card_total"] == 1
        assert body["card_draft"] == 1
        assert body["card_published"] == 0
        # 덮인 정도. 재료 1개 중 1개에 카드가 있다.
        assert body["materials_with_card"] == 1

        card.status = "published"
        db.commit()
        after = client.get("/api/statistics/overview", headers=admin_headers).json()
        assert after["card_draft"] == 0
        assert after["card_published"] == 1

    def test_안_보이는_재료는_안_센다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """**홈의 숫자와 목록 화면의 숫자가 갈리면 안 된다.**

        재료 목록이 `visible_materials` 로 좁히는데 요약이 전부 세면, 목록에
        94개가 뜨는데 홈은 120이라고 말한다. 그때 어느 쪽이 맞는지 알 방법이 없다.
        """
        client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "OV3",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        )
        listed = client.get(
            "/api/materials", params={"limit": 1}, headers=admin_headers
        ).json()
        body = client.get("/api/statistics/overview", headers=admin_headers).json()
        assert body["material_count"] == listed["total"]
