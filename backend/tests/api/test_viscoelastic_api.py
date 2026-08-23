"""점탄성 — **DMA 파일을 올려 카드 계수까지 한 줄기로.**

`matcore` 쪽은 답을 아는 합성 곡선으로 이미 검산했다(`test_viscoelastic.py`,
`test_prony.py`). 여기서 보는 것은 그 계산이 **저장소와 이어지는가** 다.

  - 한 시험의 어느 곡선이 온도 스윕인가
  - 온도는 어느 채널에서 어떻게 읽는가(한 스윕 안에서도 흔들린다)
  - 장비가 계산한 TTS 를 원본으로 착각하지 않는가
  - **그 계수가 솔버 덱까지 가는가** — 형식은 v1.14.0 에 있었는데 거기로 가는
    카드가 없어서, 한 번도 불릴 수 없는 상태였다
"""

from __future__ import annotations

import math
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests import services as test_services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.legacy_profiles import ensure_builtin_format_profiles
from app.modules.viscoelastic import services
from matcore import cards, export
from matcore.registry import Produced

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FREQ_TEMP = FIXTURES / "dma_freq_temp.csv"


@pytest.fixture
def dma_run(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    """DMA 파일을 올려 읽힌 시험 하나."""
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()

    material = client.post(
        "/api/materials",
        json={"family": "Polymer", "category": "EPDM", "grade": "VE01", "spec_thickness": 1.0},
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    specimen = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": "MD"},
        headers=admin_headers,
    ).json()
    created = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen["id"], "test_type": "dma_sweep", "conditions": "{}"},
        files={"file": ("Example FreqTemp2.csv", FREQ_TEMP.read_bytes())},
        headers=admin_headers,
    ).json()
    assert test_services.parse_run(db, uuid.UUID(created["id"])) == "parsed"
    run: dict[str, Any] = created
    return run


class Test겹칠_후보:
    def test_측정_스윕만_보여_준다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**장비가 계산한 TTS 는 후보가 아니다.** 그것을 겹치면 마스터커브에
        또 마스터커브를 씌우게 된다."""
        found = client.get(
            f"/api/viscoelastic/runs/{dma_run['id']}/sweeps", headers=admin_headers
        ).json()
        assert len(found["items"]) == 6
        for item in found["items"]:
            assert "TTS" not in (item["label"] or "")

    def test_온도를_대푯값으로_준다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """한 스윕 안에서도 온도가 흔들린다(실측 -40.00 ~ -40.99). 기준 온도를
        고르려면 스윕마다 값이 하나여야 한다."""
        found = client.get(
            f"/api/viscoelastic/runs/{dma_run['id']}/sweeps", headers=admin_headers
        ).json()
        celsius = sorted(round(item["temperature_k"] - 273.15) for item in found["items"])
        assert celsius == [-40, -30, -20, -10, 0, 10]

    def test_주파수_창을_함께_준다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**각주파수만 있는 표가 실제로 있다.** 첫 스윕에만 `Frequency` 열이
        있고 나머지 여섯에는 없어서, 각주파수에서 만들어야 한다."""
        found = client.get(
            f"/api/viscoelastic/runs/{dma_run['id']}/sweeps", headers=admin_headers
        ).json()
        for item in found["items"]:
            assert item["minimum_frequency_hz"] > 0
            assert item["maximum_frequency_hz"] > item["minimum_frequency_hz"]


class Test마스터커브:
    def test_사람이_준_이동인자로_겹친다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """장비가 계산해 준 이동인자를 넣는 자리다. 실측 파일은 온도별 곡선이
        거의 같아서(강판) WLF 로는 이동이 0 이 나온다 — 그래서 여기서는 `manual`
        로 경로를 본다."""
        sweeps = client.get(
            f"/api/viscoelastic/runs/{dma_run['id']}/sweeps", headers=admin_headers
        ).json()["items"]
        shifts = {
            str(item["temperature_k"]): -1.0 * index
            for index, item in enumerate(sorted(sweeps, key=lambda x: x["temperature_k"]))
        }
        reference = min(item["temperature_k"] for item in sweeps)
        response = client.post(
            f"/api/viscoelastic/runs/{dma_run['id']}/master-curves",
            json={
                "reference_temperature_k": reference,
                "method": "manual",
                "manual_shifts": shifts,
            },
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        curve = response.json()
        assert curve["method"] == "manual"
        assert len(curve["source_curve_keys"]) == 6
        assert curve["point_count"] > 0
        # 겹쳤으니 한 스윕보다 넓어야 한다.
        window = sweeps[0]["maximum_frequency_hz"] / sweeps[0]["minimum_frequency_hz"]
        widened = curve["maximum_frequency_hz"] / curve["minimum_frequency_hz"]
        assert widened > window

    def test_기준_온도가_없으면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**없는 온도의 곡선을 지어내지 않는다.**"""
        response = client.post(
            f"/api/viscoelastic/runs/{dma_run['id']}/master-curves",
            json={"reference_temperature_k": 500.0, "method": "wlf"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "잰 온도에 없습니다" in response.json()["error"]["message"]

    def test_점을_읽어_그릴_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        curve = self._make(client, admin_headers, dma_run)
        points = client.get(
            f"/api/viscoelastic/master-curves/{curve['id']}/points", headers=admin_headers
        ).json()
        assert set(points) >= {"frequency", "storage_modulus", "loss_modulus"}
        assert len(points["frequency"]) == curve["point_count"]

    def test_목록에_남는다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**만들고 나면 안 고친다.** 기준 온도를 바꾸면 새로 만들고, 둘 다 남는다."""
        self._make(client, admin_headers, dma_run)
        self._make(client, admin_headers, dma_run)
        listed = client.get(
            f"/api/viscoelastic/runs/{dma_run['id']}/master-curves", headers=admin_headers
        ).json()
        assert len(listed) == 2

    @staticmethod
    def _make(
        client: TestClient, headers: dict[str, str], run: dict[str, Any]
    ) -> dict[str, Any]:
        sweeps = client.get(
            f"/api/viscoelastic/runs/{run['id']}/sweeps", headers=headers
        ).json()["items"]
        ordered = sorted(sweeps, key=lambda x: x["temperature_k"])
        shifts = {
            str(item["temperature_k"]): -1.0 * index for index, item in enumerate(ordered)
        }
        response = client.post(
            f"/api/viscoelastic/runs/{run['id']}/master-curves",
            json={
                "reference_temperature_k": ordered[0]["temperature_k"],
                "method": "manual",
                "manual_shifts": shifts,
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        created: dict[str, Any] = response.json()
        return created


class TestProny:
    def test_후보를_재고_고른다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        curve = Test마스터커브._make(client, admin_headers, dma_run)
        response = client.post(
            f"/api/viscoelastic/master-curves/{curve['id']}/prony",
            json={},
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        fit = response.json()
        # **고른 것만 주지 않는다.** 사람이 다시 고를 수 있어야 한다.
        assert len(fit["candidates"]) > 1
        assert fit["bic"] == min(item["bic"] for item in fit["candidates"])
        assert fit["instantaneous_pa"] > fit["equilibrium_pa"]

    def test_항_수를_정해_줄_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        curve = Test마스터커브._make(client, admin_headers, dma_run)
        fit = client.post(
            f"/api/viscoelastic/master-curves/{curve['id']}/prony",
            json={"terms": 2},
            headers=admin_headers,
        ).json()
        assert len(fit["terms"]) == 2
        taus = [term["relaxation_time_s"] for term in fit["terms"]]
        assert taus == sorted(taus)

    def test_목록에_남는다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        curve = Test마스터커브._make(client, admin_headers, dma_run)
        client.post(
            f"/api/viscoelastic/master-curves/{curve['id']}/prony",
            json={"terms": 2},
            headers=admin_headers,
        )
        listed = client.get(
            f"/api/viscoelastic/master-curves/{curve['id']}/prony", headers=admin_headers
        ).json()
        assert len(listed) == 1


class Test커널과이어진다:
    def test_저장한_곡선이_커널이_낸_것과_같다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        dma_run: dict[str, Any],
    ) -> None:
        """저장·재읽기에서 값이 틀어지면 **계수만 보고는 절대 못 찾는다.**"""
        curve = Test마스터커브._make(client, admin_headers, dma_run)
        row = services.curve_or_404(db, uuid.UUID(curve["id"]))
        columns = services.read_master_curve(row)
        assert len(columns["frequency"]) == row.point_count
        assert math.isclose(
            float(np.min(columns["frequency"])), row.minimum_frequency_hz, rel_tol=1e-9
        )
        assert float(np.min(columns["storage_modulus"])) > 0


class Test점탄성카드:
    """**형식이 있는데 거기로 가는 길이 없었다.**

    `abaqus_viscoelastic` 은 v1.14.0 에 등록됐는데 `fitting` 에 prony 를 아는
    코드가 한 줄도 없어서, 만들어 둔 렌더러가 한 번도 불릴 수 없었다.
    """

    @staticmethod
    def _fit(
        client: TestClient, headers: dict[str, str], run: dict[str, Any]
    ) -> dict[str, Any]:
        curve = Test마스터커브._make(client, headers, run)
        fit: dict[str, Any] = client.post(
            f"/api/viscoelastic/master-curves/{curve['id']}/prony",
            json={"terms": 2},
            headers=headers,
        ).json()
        return fit

    def test_적합에서_카드가_나온다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**묶음을 받지 않는다** — 재료·방향은 적합에서 체인을 따라간다."""
        fit = self._fit(client, admin_headers, dma_run)
        response = client.post(
            "/api/fitting/cards/viscoelastic",
            json={"prony_fit_id": fit["id"], "label": "EPDM 점탄성", "poisson_ratio": 0.45},
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        card = response.json()
        assert card["orientation"] == "MD"
        assert card["source"]["sample_count"] == 1
        assert card["source"]["prony_fit_id"] == fit["id"]

    def test_순간_탄성률이_탄성_블록에_든다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """평형 탄성률이 실리면 재료가 통째로 무르게 계산되는데 **덱은 멀쩡히
        돌고 결과도 그럴듯하다.** 나중에 알 수 없는 종류의 틀림이다."""
        fit = self._fit(client, admin_headers, dma_run)
        card = client.post(
            "/api/fitting/cards/viscoelastic",
            json={"prony_fit_id": fit["id"], "label": "E0", "poisson_ratio": 0.45},
            headers=admin_headers,
        ).json()
        elastic = card["blocks"]["elastic"]["values"]
        assert elastic["youngs_modulus"] == pytest.approx(fit["instantaneous_pa"])
        assert elastic["youngs_modulus_source"] == "prony"
        assert (
            elastic["youngs_modulus"]
            > card["blocks"]["viscoelastic"]["values"]["equilibrium_pa"]
        )

    def test_점탄성_형식이_열린다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**누르기 전에 알아야 한다.** 소성 표가 없으니 인장 덱은 안 열린다."""
        fit = self._fit(client, admin_headers, dma_run)
        card = client.post(
            "/api/fitting/cards/viscoelastic",
            json={"prony_fit_id": fit["id"], "label": "형식", "poisson_ratio": 0.45},
            headers=admin_headers,
        ).json()
        assert "abaqus_viscoelastic" in card["available_formats"]
        assert "abaqus" not in card["available_formats"]
        assert card["problem"] is None

    def test_덱이_실제로_나온다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """여기가 v1.14.0 이 만들어 두고 못 부르던 자리다."""
        fit = self._fit(client, admin_headers, dma_run)
        card = client.post(
            "/api/fitting/cards/viscoelastic",
            json={"prony_fit_id": fit["id"], "label": "덱", "poisson_ratio": 0.45},
            headers=admin_headers,
        ).json()
        deck = client.get(
            f"/api/fitting/cards/{card['id']}/export",
            params={"format": "abaqus_viscoelastic"},
            headers=admin_headers,
        )
        assert deck.status_code == 200, deck.text
        assert "*VISCOELASTIC" in deck.text
        assert "*ELASTIC" in deck.text
        # **기준 온도가 덱에 적혀 있어야 한다** — 다른 온도에 쓰면 안 된다.
        assert "master curve reference temperature" in deck.text

    def test_푸아송비가_없으면_그렇게_말한다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**DMA 는 푸아송비를 재지 않는다.** 0.3 으로 채우지 않고 못 낸다고 한다."""
        fit = self._fit(client, admin_headers, dma_run)
        card = client.post(
            "/api/fitting/cards/viscoelastic",
            json={"prony_fit_id": fit["id"], "label": "없음"},
            headers=admin_headers,
        ).json()
        assert card["available_formats"] == ["json"]
        failed = client.get(
            f"/api/fitting/cards/{card['id']}/export",
            params={"format": "abaqus_viscoelastic"},
            headers=admin_headers,
        )
        assert failed.status_code == 422
        assert "푸아송비" in failed.text

    def test_없는_적합은_404(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        response = client.post(
            "/api/fitting/cards/viscoelastic",
            json={"prony_fit_id": str(uuid.uuid4()), "label": "없다"},
            headers=admin_headers,
        )
        assert response.status_code == 404


class Test블록선언:
    def test_화면이_블록_이름을_모른다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**선언만으로 그린다.** 여기 없는 것은 화면에도 없다."""
        listed = client.get("/api/fitting/blocks", headers=admin_headers).json()
        by_key = {item["key"]: item for item in listed}
        assert {"elastic", "hardening", "table", "viscoelastic"} <= set(by_key)
        for item in listed:
            assert item["label"] and item["help"]
            for one in (*item["produces"], *item["rows"]):
                assert one["label"], one["key"]
        # **경화식은 덱에 안 실린다** — 표로 나가고 식은 주석에만 남는다.
        assert by_key["hardening"]["in_deck"] is False
        assert by_key["viscoelastic"]["in_deck"] is True


class TestD7:
    """**새 물성 1종에 드는 것이 블록 선언과 렌더러뿐인가.**

    ADR 0012 의 주장이고 Phase 5 의 수용 기준이다. 사람이 세지 않고 기계가 센다 —
    "마이그레이션 없이 붙는다" 는 말은 지키기 쉬운 대신 **어긴 것을 눈치채기가
    어렵다.** 컬럼 하나를 슬쩍 더하면 그 순간 주장이 무너지는데 아무도 모른다.
    """

    def test_블록과_렌더러만으로_API_까지_따라온다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        blocks = cards.list_blocks()
        renderers = export.list_renderers()
        try:
            # ── 새 물성 1종을 더하는 전부다. 아래로 아무것도 안 고친다 ──────
            cards.register_block(
                cards.BlockSpec(
                    key="pretend_hyperelastic",
                    label="지어낸 초탄성",
                    help="D7 을 재려고 지어냈다. 실제 물성이 아니다.",
                    produces=(Produced(key="mu_1", label="μ₁", si_unit="Pa"),),
                    rows=(Produced(key="alpha", label="지수", si_unit="1"),),
                )
            )

            @export.register_renderer(
                key="pretend_solver",
                label="지어낸 솔버",
                extension="txt",
                describe="D7 을 재려고 지어냈다.",
                keywords=("*PRETEND",),
                needs=(export.Need("pretend_hyperelastic", values=("mu_1",)),),
            )
            def render(deck: export.Deck) -> export.Rendered:
                mu = deck.number("pretend_hyperelastic", "mu_1")
                return export.Rendered(text=f"*PRETEND\n{mu}\n")

            # ── 여기서부터는 전부 따라와야 한다 ────────────────────────────
            listed = client.get("/api/fitting/blocks", headers=admin_headers).json()
            mine = next(one for one in listed if one["key"] == "pretend_hyperelastic")
            assert mine["label"] == "지어낸 초탄성"
            assert mine["produces"][0]["si_unit"] == "Pa"
            assert mine["rows"][0]["label"] == "지수"
            # **덱에 실리는지는 렌더러가 정한다.** 블록이 스스로 말하지 않는다.
            assert mine["in_deck"] is True

            formats = client.get("/api/fitting/formats", headers=admin_headers).json()
            solver = next(one for one in formats if one["key"] == "pretend_solver")
            assert solver["label"] == "지어낸 솔버"
            # **누르기 전에 알려 준다** — 무엇이 있어야 하는지를 값 이름으로.
            # 블록 이름("지어낸 초탄성")이 아니라 값 이름("μ₁")이다: 사람이 찾는
            # 것은 "이 카드에 뭐가 빠졌나" 이지 "어느 블록이냐" 가 아니다.
            assert solver["requires"] == ["μ₁"]

            # 덱까지 실제로 나온다.
            deck = export.Deck(
                name="M",
                solver_id=1,
                blocks={"pretend_hyperelastic": {"values": {"mu_1": 1.0}}},
            )
            assert "pretend_solver" in export.available_formats(deck)
            assert "*PRETEND" in export.render("pretend_solver", deck).text

            # 값이 없으면 못 낸다고 말한다.
            empty = export.Deck(name="M", solver_id=1, blocks={})
            assert export.missing_for(empty, "pretend_solver") == ("지어낸 초탄성",)
        finally:
            cards.clear()
            for spec in blocks:
                cards.register_block(spec)
            export.clear_renderers()
            for item in renderers:
                export.add_renderer(item)
