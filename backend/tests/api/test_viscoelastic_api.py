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
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.tests import services as test_services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.legacy_profiles import ensure_builtin_format_profiles
from app.modules.tests.models import FormatProfile
from app.modules.viscoelastic import services
from matcore import cards, export
from matcore.registry import Produced

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FREQ_TEMP = FIXTURES / "dma_freq_temp.csv"


def _dma_run(
    client: TestClient, db: Session, admin_headers: dict[str, str], *, grade: str = "VE01"
) -> dict[str, Any]:
    """DMA 파일을 올려 읽힌 시험 하나. **프로파일을 바꿔 가며 여러 번 만든다.**

    자동 등록은 읽을 때 한 번 일어나므로, 규칙을 바꾼 뒤에는 **새로 올려 읽어야**
    그 규칙이 걸린 결과를 볼 수 있다.
    """
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()

    material = client.post(
        "/api/materials",
        json={"family": "Polymer", "category": "EPDM", "grade": grade, "spec_thickness": 1.0},
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


@pytest.fixture
def dma_run(client: TestClient, db: Session, admin_headers: dict[str, str]) -> dict[str, Any]:
    """DMA 파일을 올려 읽힌 시험 하나."""
    return _dma_run(client, db, admin_headers)


def _drop_rule(db: Session) -> None:
    """기본 프로파일에서 **마스터커브 자동 등록 규칙만** 걷는다."""
    ensure_builtin_test_types(db)
    ensure_builtin_format_profiles(db)
    db.commit()
    profile = db.scalar(select(FormatProfile).where(FormatProfile.key == "ta_dma850"))
    assert profile is not None
    tables = {
        key: value
        for key, value in profile.definition["tables"].items()
        if key != "master_curve"
    }
    profile.definition = {**profile.definition, "tables": tables}
    db.commit()


@pytest.fixture
def dma_run_plain(
    client: TestClient, db: Session, admin_headers: dict[str, str]
) -> dict[str, Any]:
    """자동 등록을 **끄고** 읽은 시험.

    프로파일에 규칙이 있으면 읽자마자 마스터커브가 생긴다 — 그게 기본 동작이고,
    `Test읽자마자_마스터커브가_된다` 가 그것을 본다. 여기 시험들이 보려는 것은 그
    **앞 단계**(사람이 손으로 만들 때의 규칙)라, 빈 상태에서 시작해야 한다.
    """
    _drop_rule(db)
    return _dma_run(client, db, admin_headers, grade="PLAIN")


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
        self, client: TestClient, admin_headers: dict[str, str], dma_run_plain: dict[str, Any]
    ) -> None:
        """**만들고 나면 안 고친다.** 기준 온도를 바꾸면 새로 만들고, 둘 다 남는다.

        수를 세므로 **자동 등록이 없는 시험**으로 본다 — 프로파일에 규칙이 있으면
        읽자마자 한 벌이 이미 들어 있어서, 「둘 다 남는다」 가 3이 된다.
        """
        self._make(client, admin_headers, dma_run_plain)
        self._make(client, admin_headers, dma_run_plain)
        listed = client.get(
            f"/api/viscoelastic/runs/{dma_run_plain['id']}/master-curves",
            headers=admin_headers,
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


class Test시험_목록이_마스터커브를_센다:
    """**글로벌 피팅은 마스터커브가 있는 시험만 쓸 수 있다.**

    그런데 없는 시험을 후보 목록에 두면 골라 보고서야 안다. 더 나쁜 것은
    **변형률 스윕처럼 애초에 만들 수 없는 시험**도 같은 목록에 섞이는 것이다 —
    둘 다 시험종류가 `dma_sweep` 이라 종류로는 못 가른다(2026-08-30).

    그래서 시험 목록이 그 수를 함께 준다. 시험마다 세지 않고 한 번에 집계한다.
    """

    def test_안_만들었으면_0(
        self, client: TestClient, admin_headers: dict[str, str], dma_run_plain: dict[str, Any]
    ) -> None:
        body = client.get("/api/test-runs", headers=admin_headers).json()
        mine = next(one for one in body["items"] if one["id"] == dma_run_plain["id"])
        assert mine["master_curve_count"] == 0

    def test_만들면_센다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma_run_plain: dict[str, Any],
    ) -> None:
        sweeps = client.get(
            f"/api/viscoelastic/runs/{dma_run_plain['id']}/sweeps", headers=admin_headers
        ).json()["items"]
        shifts = {
            str(item["temperature_k"]): -1.0 * index
            for index, item in enumerate(sorted(sweeps, key=lambda x: x["temperature_k"]))
        }
        made = client.post(
            f"/api/viscoelastic/runs/{dma_run_plain['id']}/master-curves",
            json={
                "reference_temperature_k": min(one["temperature_k"] for one in sweeps),
                "method": "manual",
                "manual_shifts": shifts,
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text

        body = client.get("/api/test-runs", headers=admin_headers).json()
        mine = next(one for one in body["items"] if one["id"] == dma_run_plain["id"])
        assert mine["master_curve_count"] == 1


class Test읽자마자_마스터커브가_된다:
    """**프로파일 규칙이 있으면 자동으로 등록한다**(ADR 0023 의 B).

    장비가 겹쳐 준 표를 사람이 화면에서 한 건씩 가져오는 길은 있다. 그런데 파일
    100개면 100번이다. 기준 온도를 어디서 읽을지 프로파일에 적어 두면 읽는 김에
    등록할 수 있다.

    **짐작은 안 한다.** 틀린 온도로 등록해도 곡선은 멀쩡하고 계산도 돌고 덱도
    나간다 — 아무 데서도 안 걸린다. 그래서 규칙이 있을 때만, 규칙이 읽힐 때만.
    """

    def test_규칙이_있으면_읽는_김에_등록한다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """기본 프로파일(TA DMA850)이 규칙을 들고 있다 — 실측 파일의 표 이름이
        `TTS - master curve (20.0 °C)` 이고 파일 머리에는 그 온도가 없다."""
        curves = client.get(
            f"/api/viscoelastic/runs/{dma_run['id']}/master-curves", headers=admin_headers
        ).json()
        assert len(curves) == 1, curves
        assert curves[0]["method"] == "imported"
        assert curves[0]["reference_temperature_k"] == pytest.approx(293.15)
        # 첫 곡선이므로 대표가 된다 — 재료의 글로벌 피팅이 이것을 읽는다.
        assert curves[0]["is_primary"] is True

    def test_손실_탄성률까지_담는다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**묶음 Prony 는 저장·손실을 함께 맞춘다.**

        손실을 안 담으면 가져온 곡선이 글로벌 피팅에서 거절된다
        (`MNX-GROUPING-0006`) — 「가져오기는 됐는데 묶이지가 않는다」 가 되고,
        원인이 곡선 파일 안에 있어 화면 어디에도 안 보인다. 자동 등록을 켠 날
        묶음 시험 여섯이 이것으로 떨어졌다(2026-08-31).
        """
        curves = client.get(
            f"/api/viscoelastic/runs/{dma_run['id']}/master-curves", headers=admin_headers
        ).json()
        points = client.get(
            f"/api/viscoelastic/master-curves/{curves[0]['id']}/points", headers=admin_headers
        ).json()
        assert set(points) >= {"frequency", "storage_modulus", "loss_modulus"}

    def test_어디서_읽은_온도인지_남긴다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**사람이 적은 값과 규칙이 읽은 값은 뜻이 다르다.** 나중에 「이 온도 어디서
        났나」 를 물을 때 카드까지 따라가야 한다."""
        curves = client.get(
            f"/api/viscoelastic/runs/{dma_run['id']}/master-curves", headers=admin_headers
        ).json()
        notes = " ".join(curves[0]["notes"])
        assert "표 이름에서 읽었습니다" in notes
        assert "20.0" in notes

    def test_등록했다는_사실이_시험에_남는다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """조용히 만들지 않는다 — 사람이 안 시킨 일이라 더 그렇다."""
        body = client.get(f"/api/test-runs/{dma_run['id']}", headers=admin_headers).json()
        assert any("마스터커브로 등록" in one for one in body["warnings"]), body["warnings"]

    def test_다시_읽어도_늘지_않는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        dma_run: dict[str, Any],
    ) -> None:
        """재파싱은 곡선을 새로 쓰지만 마스터커브는 남아 있다. 같은 곡선으로 또
        만들면 재파싱마다 하나씩 늘고, 그중 어느 것이 대표인지가 흔들린다."""
        assert test_services.parse_run(db, uuid.UUID(dma_run["id"])) == "parsed"
        curves = client.get(
            f"/api/viscoelastic/runs/{dma_run['id']}/master-curves", headers=admin_headers
        ).json()
        assert len(curves) == 1

    def test_규칙이_없으면_등록하지_않는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**기본은 안 하는 쪽이다.** 프로파일이 온도를 어디서 읽을지 안 적었으면
        우리는 모르는 것이고, 모르는 값을 지어내지 않는다."""
        _drop_rule(db)
        run = _dma_run(client, db, admin_headers, grade="NORULE")
        curves = client.get(
            f"/api/viscoelastic/runs/{run['id']}/master-curves", headers=admin_headers
        ).json()
        assert curves == []

    def test_규칙이_안_맞으면_말하고_넘어간다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**등록 안 함 + 이유**가 조용히 틀린 온도보다 낫다. 앞은 화면에 뜨고
        뒤는 덱까지 간다."""
        ensure_builtin_test_types(db)
        ensure_builtin_format_profiles(db)
        db.commit()
        profile = db.scalar(select(FormatProfile).where(FormatProfile.key == "ta_dma850"))
        assert profile is not None
        profile.definition = {
            **profile.definition,
            "tables": {
                **profile.definition["tables"],
                "master_curve": {"pattern": r"기준온도 ([\d.]+)", "unit": "degC"},
            },
        }
        db.commit()

        run = _dma_run(client, db, admin_headers, grade="NOMATCH")
        curves = client.get(
            f"/api/viscoelastic/runs/{run['id']}/master-curves", headers=admin_headers
        ).json()
        assert curves == []

        body = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        assert any("기준 온도를 못 읽어" in one for one in body["warnings"]), body["warnings"]


class Test온도_단_수:
    """**겹칠 수 있는 시험인지 읽을 때 세어 둔다.**

    DMA 는 같은 시험종류 아래 성격이 다른 둘이 온다 — 주파수-온도 스윕(온도 여러
    단)과 변형률 스윕(한 단). 시험종류 키로는 못 가른다.

    재료 화면이 「마스터커브가 없는 DMA n건」 이라고 재촉할 때 변형률 스윕이 섞여
    있으면 **할 수 없는 일을 남은 일로 적는 셈**이다. 목록에서 다시 재려면 시험마다
    Parquet 을 열어야 하므로 읽을 때 센다.
    """

    def test_읽으면_세어_둔다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        body = client.get(f"/api/test-runs/{dma_run['id']}", headers=admin_headers).json()
        # 실측 파일(TA DMA850)은 -40~10 °C 를 여섯 단으로 잰다.
        assert body["temperature_step_count"] == 6

    def test_목록에도_실린다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**목록이 이 값을 본다.** 상세에만 있으면 재료 화면이 시험마다 상세를
        불러야 하고, 그러면 20건짜리 재료에서 20번을 부른다."""
        rows = client.get("/api/test-runs", headers=admin_headers).json()["items"]
        mine = next(one for one in rows if one["id"] == dma_run["id"])
        assert mine["temperature_step_count"] == 6

    def test_장비가_계산한_표는_안_센다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """마스터커브·이동인자 표에도 온도 열이 있는데 그것은 **잰 단이 아니라 겹친
        결과**다. 함께 세면 한 단짜리 파일이 여러 단으로 보인다.

        실측 파일의 측정 곡선은 여섯이고 처리결과 표가 둘이다 — 처리결과의 온도까지
        셌다면 6보다 커진다.
        """
        body = client.get(f"/api/test-runs/{dma_run['id']}", headers=admin_headers).json()
        derived = [one for one in body["curves"] if one["kind"] == "derived"]
        assert derived, "이 파일에는 처리결과 표가 있다"
        assert body["temperature_step_count"] == 6


class Test대표_마스터커브:
    """**시험마다 대표 하나.** 재료의 글로벌 피팅이 그것을 읽는다.

    전에는 「가장 최근 것」 을 말없이 썼다. 편의 같지만 조용히 틀리는 자리다 —
    20 °C 로 만들어 쓰다가 30 °C 로 하나 더 만들면, 그 순간부터 재료 쪽 계산이
    30 °C 것으로 바뀌는데 화면 어디에도 그 전환이 안 보인다.

    처리 결과의 **채택**과 같은 문법이기도 하다. 「여러 벌 만들고 하나를 고른다」
    하나만 배우면 값 쪽과 점탄성 쪽이 같아진다.
    """

    def _make(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        run: dict[str, Any],
        reference: float,
    ) -> dict[str, Any]:
        response = client.post(
            f"/api/viscoelastic/runs/{run['id']}/master-curves",
            json={"reference_temperature_k": reference, "method": "wlf"},
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        made: dict[str, Any] = response.json()
        return made

    def _temperatures(
        self, client: TestClient, admin_headers: dict[str, str], run: dict[str, Any]
    ) -> list[float]:
        sweeps = client.get(
            f"/api/viscoelastic/runs/{run['id']}/sweeps", headers=admin_headers
        ).json()["items"]
        return sorted(float(item["temperature_k"]) for item in sweeps)

    def test_첫_곡선은_만들면서_대표가_된다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run_plain: dict[str, Any]
    ) -> None:
        """고를 것이 하나뿐인데 고르라고 하면 그것은 일이 아니라 절차다."""
        temperatures = self._temperatures(client, admin_headers, dma_run_plain)
        made = self._make(client, admin_headers, dma_run_plain, temperatures[0])
        assert made["is_primary"] is True

    def test_둘째는_자동으로_대표가_되지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run_plain: dict[str, Any]
    ) -> None:
        """**이것이 이 기능의 요점이다.** 새로 만든 것이 자동으로 대표가 되면
        「최근 것이 대표」 라는 옛 동작이 이름만 바꿔 그대로 남는다."""
        temperatures = self._temperatures(client, admin_headers, dma_run_plain)
        first = self._make(client, admin_headers, dma_run_plain, temperatures[0])
        second = self._make(client, admin_headers, dma_run_plain, temperatures[-1])
        assert second["is_primary"] is False

        listed = {
            one["id"]: one
            for one in client.get(
                f"/api/viscoelastic/runs/{dma_run_plain['id']}/master-curves",
                headers=admin_headers,
            ).json()
        }
        assert listed[first["id"]]["is_primary"] is True

    def test_옮기면_앞의_것이_내려온다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run_plain: dict[str, Any]
    ) -> None:
        """대표가 둘이면 「어느 계수로 나온 물성인가」 에 답할 수 없다."""
        temperatures = self._temperatures(client, admin_headers, dma_run_plain)
        first = self._make(client, admin_headers, dma_run_plain, temperatures[0])
        second = self._make(client, admin_headers, dma_run_plain, temperatures[-1])

        moved = client.post(
            f"/api/viscoelastic/master-curves/{second['id']}/primary", headers=admin_headers
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["is_primary"] is True

        listed = {
            one["id"]: one
            for one in client.get(
                f"/api/viscoelastic/runs/{dma_run_plain['id']}/master-curves",
                headers=admin_headers,
            ).json()
        }
        assert listed[first["id"]]["is_primary"] is False
        assert sum(1 for one in listed.values() if one["is_primary"]) == 1

    def test_가져온_곡선도_대표가_된다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run_plain: dict[str, Any]
    ) -> None:
        """장비가 만든 것만 있는 파일도 재료로 나가야 한다 — 그 시험에는 겹친
        곡선이 아예 없으므로, 가져온 것이 대표가 되지 않으면 대표가 영영 빈다."""
        listed = client.get(
            f"/api/viscoelastic/runs/{dma_run_plain['id']}/importable-curves",
            headers=admin_headers,
        ).json()
        usable = next(one for one in listed if one["usable"])
        made = client.post(
            f"/api/viscoelastic/runs/{dma_run_plain['id']}/master-curves/import",
            json={"curve_key": usable["curve_key"], "reference_temperature_k": 293.15},
            headers=admin_headers,
        ).json()
        assert made["is_primary"] is True


class Test가져올_수_있는_표를_보여_준다:
    """**고르기 전에 무엇이 있는지 보인다.**

    `derived` 에는 마스터커브만 오는 것이 아니다 — 이동인자 표가 같은 칸에 들어온다
    (TA DMA850 은 둘 다 낸다). 못 쓰는 것을 목록에서 빼 버리면 「내 파일에 있는 그
    표가 왜 안 보이지」 가 되고, 이유 없이 그냥 두면 골라 놓고 나서야 거절을 본다.
    """

    def _listed(
        self, client: TestClient, admin_headers: dict[str, str], run: dict[str, Any]
    ) -> list[dict[str, Any]]:
        response = client.get(
            f"/api/viscoelastic/runs/{run['id']}/importable-curves", headers=admin_headers
        )
        assert response.status_code == 200, response.text
        items: list[dict[str, Any]] = response.json()
        return items

    def test_측정_곡선은_안_나온다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**측정을 가져오기 후보로 두면 안 된다.** 그것은 겹치기의 원본이고,
        마스터커브로 등록하면 한 온도의 좁은 창이 넓은 곡선 행세를 한다."""
        keys = {one["curve_key"] for one in self._listed(client, admin_headers, dma_run)}
        assert keys == {"tts_master_curve_20_0_c", "tts_shift_factors"}

    def test_쓸_수_있는_것과_아닌_것을_가른다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        listed = {
            one["curve_key"]: one for one in self._listed(client, admin_headers, dma_run)
        }
        assert listed["tts_master_curve_20_0_c"]["usable"] is True
        assert listed["tts_master_curve_20_0_c"]["note"] is None
        # 이동인자 표는 온도와 aT 뿐이라 마스터커브가 될 수 없다.
        assert listed["tts_shift_factors"]["usable"] is False

    def test_못_쓰는_이유에_없는_열과_있는_열이_함께_있다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """「쓸 수 없습니다」 만으로는 다음에 할 일을 모른다 — 무엇이 없고 무엇이
        있는지 함께 적어야 장비 파일 정의에서 어느 열을 매핑할지 안다."""
        listed = {
            one["curve_key"]: one for one in self._listed(client, admin_headers, dma_run)
        }
        note = listed["tts_shift_factors"]["note"]
        assert "저장 탄성률" in note
        assert "temperature" in note  # 있는 열도 보인다

    def test_보여_준_것은_실제로_가져와진다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """**목록과 등록이 같은 판단을 써야 한다.** 갈라지면 「쓸 수 있다」 고 적힌
        것을 골랐는데 거절당한다."""
        usable = [one for one in self._listed(client, admin_headers, dma_run) if one["usable"]]
        assert usable, "쓸 수 있는 표가 하나는 있어야 한다"
        for one in usable:
            made = client.post(
                f"/api/viscoelastic/runs/{dma_run['id']}/master-curves/import",
                json={"curve_key": one["curve_key"], "reference_temperature_k": 293.15},
                headers=admin_headers,
            )
            assert made.status_code == 201, made.text

    def test_못_쓴다고_적힌_것은_실제로_거절된다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run: dict[str, Any]
    ) -> None:
        """반대쪽도 같아야 한다 — 목록이 관대하면 사람이 그것을 믿고 고른다."""
        blocked = [
            one for one in self._listed(client, admin_headers, dma_run) if not one["usable"]
        ]
        assert blocked, "이 파일에는 이동인자 표가 있다"
        for one in blocked:
            response = client.post(
                f"/api/viscoelastic/runs/{dma_run['id']}/master-curves/import",
                json={"curve_key": one["curve_key"], "reference_temperature_k": 293.15},
                headers=admin_headers,
            )
            assert response.status_code == 422, response.text


class Test장비가_겹친_곡선을_가져온다:
    """**마스터커브만 내보낸 파일도 쓸 수 있어야 한다.**

    TA TRIOS 같은 장비는 시간-온도 중첩을 제 소프트웨어에서 하고 마스터커브를 함께
    내보낸다. 프로파일이 그 표를 읽어 두기는 했지만(`derived`) `MasterCurve` 행이
    되지 않아, **그런 파일은 Prony 도 글로벌 피팅도 못 썼다**(2026-08-30).

    ## 겹치기를 다시 하지 않는다

    장비가 쓴 이동인자를 모른다. 다시 겹치면 **다른 곡선이 나오는데 둘 다
    그럴듯하다** — 그래서 점을 그대로 받고 그 사실을 적는다.
    """

    def _curve_key(
        self, client: TestClient, admin_headers: dict[str, str], run: dict[str, Any]
    ) -> str:
        body = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        return str(body["curves"][0]["key"]) if body.get("curves") else "raw"

    def test_가져오면_마스터커브가_된다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run_plain: dict[str, Any]
    ) -> None:
        sweeps = client.get(
            f"/api/viscoelastic/runs/{dma_run_plain['id']}/sweeps", headers=admin_headers
        ).json()["items"]
        made = client.post(
            f"/api/viscoelastic/runs/{dma_run_plain['id']}/master-curves/import",
            json={
                "curve_key": sweeps[0]["curve_key"],
                "reference_temperature_k": 293.15,
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        assert made.json()["method"] == "imported"

    def test_이동인자를_안_지어낸다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run_plain: dict[str, Any]
    ) -> None:
        """**모르는 것을 채우지 않는다.** 장비가 무엇으로 겹쳤는지 우리는 모르고,
        그 자리에 값을 넣으면 나중에 그것이 관측인지 짐작인지 알 수 없다."""
        sweeps = client.get(
            f"/api/viscoelastic/runs/{dma_run_plain['id']}/sweeps", headers=admin_headers
        ).json()["items"]
        body = client.post(
            f"/api/viscoelastic/runs/{dma_run_plain['id']}/master-curves/import",
            json={
                "curve_key": sweeps[0]["curve_key"],
                "reference_temperature_k": 293.15,
            },
            headers=admin_headers,
        ).json()
        assert body["shifts"] == []
        assert any("이동인자는 이 시스템이 모릅니다" in said for said in body["notes"])

    def test_사람이_적은_온도라고_남긴다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run_plain: dict[str, Any]
    ) -> None:
        # **틀린 온도로 등록하면 그 덱은 조용히 다른 온도의 해석에 쓰인다.**
        sweeps = client.get(
            f"/api/viscoelastic/runs/{dma_run_plain['id']}/sweeps", headers=admin_headers
        ).json()["items"]
        body = client.post(
            f"/api/viscoelastic/runs/{dma_run_plain['id']}/master-curves/import",
            json={
                "curve_key": sweeps[0]["curve_key"],
                "reference_temperature_k": 293.15,
            },
            headers=admin_headers,
        ).json()
        assert any("사람이 적은 값" in said for said in body["notes"])

    def test_가져온_것도_시험_목록이_센다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run_plain: dict[str, Any]
    ) -> None:
        """**이것이 이 기능의 요점이다.** 세어지지 않으면 글로벌 피팅 후보에 안 뜬다."""
        sweeps = client.get(
            f"/api/viscoelastic/runs/{dma_run_plain['id']}/sweeps", headers=admin_headers
        ).json()["items"]
        client.post(
            f"/api/viscoelastic/runs/{dma_run_plain['id']}/master-curves/import",
            json={
                "curve_key": sweeps[0]["curve_key"],
                "reference_temperature_k": 293.15,
            },
            headers=admin_headers,
        )
        rows = client.get("/api/test-runs", headers=admin_headers).json()["items"]
        mine = next(one for one in rows if one["id"] == dma_run_plain["id"])
        assert mine["master_curve_count"] == 1

    def test_열을_못_찾으면_어디를_고칠지_말한다(
        self, client: TestClient, admin_headers: dict[str, str], dma_run_plain: dict[str, Any]
    ) -> None:
        """「못 찾았습니다」 만으로는 사람이 다음에 할 일을 모른다 — 매핑을 고치는
        자리를 함께 적는다."""
        response = client.post(
            f"/api/viscoelastic/runs/{dma_run_plain['id']}/master-curves/import",
            json={"curve_key": "없는곡선", "reference_temperature_k": 293.15},
            headers=admin_headers,
        )
        assert response.status_code in (404, 422), response.text
