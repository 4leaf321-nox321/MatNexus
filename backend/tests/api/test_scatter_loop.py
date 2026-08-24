"""**답을 아는 산포 데이터로 한 바퀴 전체를 검산한다.**

지금까지의 시험은 같은 파일을 여러 번 올려 구조만 봤다. 그래서 CV 가 1e-14% 로
나오고, 이상치 후보가 없고, 대표 곡선이 시편 하나와 똑같았다 — **통계도 적합도
"돌아간다" 밖에 증명하지 못했다.**

여기서는 시편마다 얼마나 흩어지게 넣었는지 알고 만든다. 그러면 화면이 낸 CV·
이상치·경화식 파라미터가 그 값으로 돌아오는지 볼 수 있다.

    탄성      sigma = E * eps
    소성(진)  sigma = sigma_0 + Q(1 - exp(-b*eps_p))     ← Voce, 참값을 안다
    네킹      Considere 조건에서 시작, 하중이 떨어진다

이 파일이 지키는 것:

1. 배치가 시편마다 **자기 단면적**을 쓴다 (`@specimen_area`)
2. 통계 CV 가 넣은 산포와 맞고, 넣은 이상치를 잡고, MD 와 TD 를 안 섞는다
3. 적합이 **참 Voce 파라미터를 되찾는다**
4. 네킹이 섞인 표를 내보내기가 **거부한다** — 자른 뒤에는 통과한다
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests import services
from app.modules.tests.definitions import ensure_builtin_test_types

#: 참값. 시편마다 이 둘레로 흩어뜨린다.
TRUE_E = 200e9
TRUE_SIGMA0 = 340e6
TRUE_Q = 180e6
TRUE_B = 15.0

#: 넣는 산포. 실제 강판 인장시험에서 보는 크기다.
YIELD_CV = 0.025
OUTLIER_FACTOR = 0.88
"""이상치 시편 — 다른 코일이 섞여 들어온 상황. **버리지 않고 표시만 해야 한다.**"""
TD_FACTOR = 1.08
"""압연 방향 이방성. MD 와 섞으면 CV 가 산포가 아니라 '섞은 것' 이 된다."""

POINTS = 600
GAUGE_M = 0.05
SEED = 20260817


@dataclass(frozen=True)
class Truth:
    name: str
    orientation: str
    thickness_mm: float
    width_mm: float
    e: float
    sigma0: float
    q: float
    b: float
    fracture: float
    outlier: bool


def _draw(
    rng: np.random.Generator, count: int, orientation: str, outlier_at: int | None
) -> list[Truth]:
    items = []
    for index in range(count):
        factor = TD_FACTOR if orientation == "TD" else 1.0
        outlier = index == outlier_at
        items.append(
            Truth(
                name=f"{orientation}{index + 1}",
                orientation=orientation,
                thickness_mm=float(rng.normal(1.00, 0.010)),
                width_mm=float(rng.normal(12.50, 0.030)),
                e=float(rng.normal(TRUE_E, TRUE_E * 0.02)),
                sigma0=float(rng.normal(TRUE_SIGMA0, TRUE_SIGMA0 * YIELD_CV))
                * factor
                * (OUTLIER_FACTOR if outlier else 1.0),
                q=float(rng.normal(TRUE_Q, TRUE_Q * 0.04)),
                b=float(rng.normal(TRUE_B, TRUE_B * 0.06)),
                fracture=float(rng.normal(0.30, 0.015)),
                outlier=outlier,
            )
        )
    return items


def _necking_strain(item: Truth) -> float:
    """Considere 조건 — 진응력의 기울기가 진응력과 같아지는 소성변형률.

    여기가 UTS 이고, **이 뒤로는 진응력 변환식이 성립하지 않는다**(균일 변형 전제).
    """
    grid = np.linspace(1e-6, 0.6, 20000)
    sigma = item.sigma0 + item.q * (1.0 - np.exp(-item.b * grid))
    slope = item.q * item.b * np.exp(-item.b * grid)
    return float(grid[int(np.argmax(slope <= sigma))])


def _tra(item: Truth, rng: np.random.Generator) -> bytes:
    """장비가 내는 것과 같은 모양의 `.tra` — 변위(mm)·하중(N)·시편폭(mm)."""
    plastic_uts = _necking_strain(item)
    stress_uts = item.sigma0 + item.q * (1.0 - np.exp(-item.b * plastic_uts))
    eng_uts = math.expm1(plastic_uts + stress_uts / item.e)

    yield_strain = item.sigma0 / item.e
    elastic = np.linspace(0.0, yield_strain, int(POINTS * 0.15), endpoint=False)
    plastic = np.linspace(0.0, plastic_uts, int(POINTS * 0.6))
    true_stress = item.sigma0 + item.q * (1.0 - np.exp(-item.b * plastic))
    uniform = np.expm1(plastic + true_stress / item.e)
    neck = np.linspace(eng_uts, item.fracture, POINTS - len(elastic) - len(plastic) + 1)[1:]
    drop = (neck - eng_uts) / max(item.fracture - eng_uts, 1e-9)

    strain = np.concatenate([elastic, uniform, neck])
    stress = np.concatenate(
        [
            item.e * elastic,
            true_stress / (1.0 + uniform),
            (true_stress[-1] / (1.0 + eng_uts)) * (1.0 - 0.14 * drop**1.6),
        ]
    )
    area = item.thickness_mm * item.width_mm * 1e-6
    force = stress * area
    # 로드셀 잡음. 없으면 탄성 구간 적합이 비현실적으로 좋다.
    force = force + rng.normal(0.0, float(np.max(force)) * 0.0012, size=force.shape)
    width = item.width_mm * np.exp(-0.5 * np.log1p(np.maximum(strain, 0.0)))

    lines = [
        f'"Specimen thickness a0",{item.thickness_mm:.3f},"mm"',
        f'"Specimen width b0",{item.width_mm:.3f},"mm"',
        '"Standard extensometer ","Standard load cell ","Specimen width"',
        '"mm","N","mm"',
    ]
    lines += [
        f"{e * GAUGE_M * 1000:.6g},{f:.6g},{w:.6g}"
        for e, f, w in zip(strain, force, width, strict=True)
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _steps(end: float) -> list[dict[str, Any]]:
    """**한 벌의 옵션으로 시편 전부를 돈다.** 치수는 참조로 건다."""
    return [
        {
            "plugin": "tensile.engineering",
            "options": {
                "gauge_length": "@specimen_gauge_length",
                "area": "@specimen_area",
            },
        },
        {
            "plugin": "curve.sort_unique",
            "options": {"x": "strain_engineering", "duplicate_policy": "mean"},
        },
        {
            "plugin": "tensile.elastic_modulus",
            # **재샘플 앞이어야 한다.** 뒤에 두면 균등 격자 간격이 탄성 창보다
            # 넓어 창 안에 점이 하나만 남는다.
            "options": {
                "method": "linear_regression",
                "minimum_strain": 0.0005,
                "maximum_strain": 0.0013,
            },
        },
        {
            "plugin": "tensile.proof_stress",
            "options": {"offset_strain": 0.002, "youngs_modulus": "@youngs_modulus"},
        },
        {"plugin": "tensile.strength", "options": {}},
        {
            # 토우 구간. 하중이 0 근처인 첫 몇 점은 잡음이 부호를 넘나든다.
            "plugin": "curve.crop",
            "options": {"x": "strain_engineering", "start": 0.0002, "end": 1.0},
        },
        {
            "plugin": "tensile.true_plastic",
            "options": {
                "youngs_modulus": "@youngs_modulus",
                "necking_policy": "observed_full_domain",
                "negative_policy": "clip_zero",
            },
        },
        {
            # 쌓인 0 을 항복점 하나로 접는다. 안 하면 x 중복이라 격자를 못 만든다.
            "plugin": "curve.sort_unique",
            "options": {"x": "strain_true_plastic", "duplicate_policy": "last"},
        },
        {
            # **적합에 쓸 축에서 맞춘다.** 공칭 축에서 맞춰 놔도 진소성변형률은
            # 시편마다 sigma/E 를 뺀 값이라 격자가 어긋난다.
            "plugin": "curve.resample",
            "options": {"x": "strain_true_plastic", "start": 0.0, "end": end, "count": 60},
        },
    ]


#: MD 시편 수. **8개인 데는 이유가 있다.**
#:
#: 5개로 해 보니 -12% 이상치를 못 잡았다 — modified z 가 2.63 으로 기본 임계
#: 3.5 에 못 미친다. MAD 기반 검출의 성질이지 결함이 아니다(표본이 적으면 MAD 가
#: 이상치 쪽으로 끌려간다). 실제 랩이 5~10개를 뜨는데, **몇 개부터 잡히는지**를
#: 알고 쓰는 것과 모르고 쓰는 것은 다르다.
MD_COUNT = 8


@pytest.fixture(scope="module")
def population() -> list[Truth]:
    rng = np.random.default_rng(SEED)
    return _draw(rng, MD_COUNT, "MD", outlier_at=5) + _draw(rng, 3, "TD", outlier_at=None)


@pytest.fixture
def loaded(
    client: TestClient,
    admin_headers: dict[str, str],
    db: Session,
    population: list[Truth],
) -> dict[str, Any]:
    """산포 시편들을 **실제 API 로** 올리고 파싱한다."""
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": "SCAT",
            "details": "DP600",
            "spec_thickness": 1.0,
        },
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()

    rng = np.random.default_rng(SEED + 1)
    run_ids: list[str] = []
    for item in population:
        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={
                "orientation": item.orientation,
                # **시편마다 치수가 다르다.** 배치가 각자 자기 단면적을 쓰는지가
                # 이 시험의 한 축이다.
                "thickness": round(item.thickness_mm, 3),
                "width": round(item.width_mm, 3),
                "gauge_length": GAUGE_M * 1000,
                "length_unit": "mm",
            },
            headers=admin_headers,
        ).json()
        run = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "tensile",
                "conditions": "{}",
            },
            files={"file": (f"{item.name}.tra", _tra(item, rng))},
            headers=admin_headers,
        ).json()
        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"
        run_ids.append(run["id"])
    return {"material_id": material["id"], "run_ids": run_ids}


def _process(
    client: TestClient, headers: dict[str, str], loaded: dict[str, Any], end: float
) -> list[dict[str, Any]]:
    body = client.post(
        "/api/processing/batch",
        json={"test_run_ids": loaded["run_ids"], "steps": _steps(end)},
        headers=headers,
    ).json()
    failures = [item for item in body["items"] if not item["result_id"]]
    assert not failures, [f"{item['record_name']}: {item['error']}" for item in failures]
    for item in body["items"]:
        client.post(f"/api/processing/results/{item['result_id']}/adopt", headers=headers)
    return list(body["items"])


#: 네킹 앞에서 자른 소성변형률 상한. UTS 가 소성변형률 0.114 근처다.
UNIFORM_END = 0.10
#: 네킹이 섞이는 상한.
NECKED_END = 0.22


class Test배치:
    def test_시편마다_자기_단면적을_쓴다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        loaded: dict[str, Any],
        population: list[Truth],
    ) -> None:
        """**한 벌의 옵션으로 도는데 값은 각자 다르다.**

        고정 숫자를 박으면 8개가 전부 같은 단면적으로 계산되고, 그 오차는
        응력에 그대로 실려 아무도 못 본다.
        """
        items = _process(client, admin_headers, loaded, UNIFORM_END)
        areas = set()
        for item in items:
            results = client.get(
                f"/api/processing/results?test_run_id={item['test_run_id']}",
                headers=admin_headers,
            ).json()
            result = next(r for r in results if r["id"] == item["result_id"])
            stage = next(s for s in result["stages"] if s["plugin"] == "tensile.engineering")
            areas.add(round(float(stage["options"]["area"]), 12))
        assert len(areas) == len(population)


class Test통계:
    @pytest.fixture
    def groups(
        self, client: TestClient, admin_headers: dict[str, str], loaded: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        _process(client, admin_headers, loaded, UNIFORM_END)
        body = client.get(
            f"/api/statistics/materials/{loaded['material_id']}", headers=admin_headers
        ).json()
        return {group["orientation"]: group for group in body["groups"]}

    def test_넣은_산포가_그대로_나온다(
        self, groups: dict[str, dict[str, Any]], population: list[Truth]
    ) -> None:
        """**이 시험이 지금까지 없던 것이다.** 같은 파일만 올릴 때는 CV 가
        1e-14% 라 통계가 맞는지 알 방법이 없었다."""
        row = next(r for r in groups["MD"]["scalars"] if r["key"] == "proof_stress")
        truth = [item.sigma0 for item in population if item.orientation == "MD"]
        expected_cv = float(np.std(truth, ddof=1) / np.mean(truth))

        assert row["count"] == len(truth)
        # 0.2% 오프셋 항복강도는 sigma_0 보다 조금 위다. 흩어짐은 같이 간다.
        assert row["mean"] == pytest.approx(float(np.mean(truth)), rel=0.05)
        assert row["coefficient_of_variation"] == pytest.approx(expected_cv, rel=0.25)

    def test_탄성계수를_되찾는다(self, groups: dict[str, dict[str, Any]]) -> None:
        row = next(r for r in groups["MD"]["scalars"] if r["key"] == "youngs_modulus")
        assert row["mean"] == pytest.approx(TRUE_E, rel=0.03)

    def test_넣은_이상치를_잡는다(
        self, groups: dict[str, dict[str, Any]], population: list[Truth]
    ) -> None:
        """**버리지 않는다 — 표시만 한다.** 재료 특성인지 시험 실수인지는 사람이 안다."""
        row = next(r for r in groups["MD"]["scalars"] if r["key"] == "proof_stress")
        flagged = {item["record_name"] for item in row["outliers"]}
        assert flagged, "넣은 이상치를 하나도 못 잡았다"
        expected = next(item for item in population if item.outlier)
        # 이름은 `..._MD_04__TEN_01` 처럼 붙는다. 몇 번째 시편인지로 확인한다.
        index = [item for item in population if item.orientation == "MD"].index(expected)
        assert any(f"MD_{index + 1:02d}__" in name for name in flagged)

    def test_MD_와_TD_를_섞지_않는다(self, groups: dict[str, dict[str, Any]]) -> None:
        """섞으면 CV 가 산포가 아니라 **다른 것을 섞은 값**이 된다."""
        md = next(r for r in groups["MD"]["scalars"] if r["key"] == "proof_stress")
        td = next(r for r in groups["TD"]["scalars"] if r["key"] == "proof_stress")
        assert td["mean"] / md["mean"] == pytest.approx(TD_FACTOR, rel=0.05)


class Test분포:
    """흩어짐에 **모양**을 붙인다. 위의 `Test통계` 는 얼마나 큰지를 봤다.

    **여기서도 답을 안다.** `_draw` 가 정규분포로 시편을 흩뜨리므로, 정규가
    후보에서 밀려나면 안 된다 — 다만 *1등이어야 한다* 고는 못 한다(단위 시험의
    `test_정규_표본에서는_1등을_고를_수_없다` 에 실측을 적어 뒀다: 재료 시험의
    좁은 CV 에서는 로그정규가 수치적으로 거의 같은 곡선이라 n=200 으로도 안
    갈린다).
    """

    @pytest.fixture
    def report(
        self, client: TestClient, admin_headers: dict[str, str], loaded: dict[str, Any]
    ) -> dict[str, Any]:
        _process(client, admin_headers, loaded, UNIFORM_END)
        # 부트스트랩을 낮춘다 — p 의 정밀도만 떨어지고 통계량은 그대로다.
        response = client.get(
            f"/api/statistics/materials/{loaded['material_id']}/distributions",
            params={
                "test_type_key": "tensile",
                "orientation": "MD",
                "scalar_key": "proof_stress",
                "bootstrap": 99,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        return dict(response.json())

    def test_넣은_모양이_후보에_남는다(
        self, report: dict[str, Any], population: list[Truth]
    ) -> None:
        assert report["count"] == len([i for i in population if i.orientation == "MD"])
        normal = next(item for item in report["candidates"] if item["key"] == "normal")
        assert normal["status"] == "succeeded"
        # 정규로 흩뜨렸으므로 정규가 거절당하면 안 된다.
        assert normal["p_value"] is None or normal["p_value"] > 0.05

    def test_하위_5퍼센트를_준다(self, report: dict[str, Any]) -> None:
        """**설계가 묻는 것은 파라미터가 아니라 하위 5% 다.**"""
        winner = next(item for item in report["candidates"] if item["key"] == report["best"])
        quantiles = winner["quantiles"]
        assert quantiles["p05"] < quantiles["p50"] < quantiles["p95"]
        # 항복강도이므로 Pa 단위의 그럴듯한 값이어야 한다.
        assert 100e6 < quantiles["p05"] < 1000e6

    def test_어느_시편이_쓰였는지_되짚는다(self, report: dict[str, Any]) -> None:
        """조용히 빼면 "왜 8개죠" 를 답할 수 없다."""
        assert len(report["observations"]) == report["count"]
        assert all(item["specimen_label"] for item in report["observations"])
        assert {item["status"] for item in report["observations"]} == {"observed"}

    def test_물어볼_수_있는_항목을_먼저_알려_준다(
        self, client: TestClient, admin_headers: dict[str, str], loaded: dict[str, Any]
    ) -> None:
        """**눌러 보고 나서 "모자랍니다" 를 받는 것보다 미리 아는 것이 낫다.**"""
        _process(client, admin_headers, loaded, UNIFORM_END)
        body = client.get(
            f"/api/statistics/materials/{loaded['material_id']}/distributable",
            params={"test_type_key": "tensile", "orientation": "MD"},
            headers=admin_headers,
        ).json()
        keys = {item["key"]: item for item in body}
        assert "proof_stress" in keys
        assert keys["proof_stress"]["count"] == MD_COUNT
        assert keys["proof_stress"]["si_unit"] == "Pa"

    def test_표본이_적은_묶음은_대상이_아니라고_한다(
        self, client: TestClient, admin_headers: dict[str, str], loaded: dict[str, Any]
    ) -> None:
        """TD 는 3건이다. **적합 실패가 아니라 물음이 성립하지 않는 것**이고,
        그 둘을 한 칸에 넣으면 나중에 못 가른다."""
        _process(client, admin_headers, loaded, UNIFORM_END)
        body = client.get(
            f"/api/statistics/materials/{loaded['material_id']}/distributions",
            params={
                "test_type_key": "tensile",
                "orientation": "TD",
                "scalar_key": "proof_stress",
                "bootstrap": 0,
            },
            headers=admin_headers,
        ).json()
        assert body["best"] is None
        assert {item["status"] for item in body["candidates"]} == {"not_eligible"}
        assert any("모자란 것이지" in note for note in body["notes"])

    def test_없는_항목은_404_다(
        self, client: TestClient, admin_headers: dict[str, str], loaded: dict[str, Any]
    ) -> None:
        _process(client, admin_headers, loaded, UNIFORM_END)
        response = client.get(
            f"/api/statistics/materials/{loaded['material_id']}/distributions",
            params={
                "test_type_key": "tensile",
                "orientation": "MD",
                "scalar_key": "없는값",
                "bootstrap": 0,
            },
            headers=admin_headers,
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "MNX-STATISTICS-0003"


class Test적합:
    def test_참_Voce_파라미터를_되찾는다(
        self, client: TestClient, admin_headers: dict[str, str], loaded: dict[str, Any]
    ) -> None:
        """**여기가 이 파일의 핵심이다.**

        답을 아는 곡선을 시편마다 흩어뜨려 만들고, 그것을 파일로 써서, 파서와
        처리와 통계를 통과시킨 뒤 적합했을 때 참값이 돌아오는가.
        """
        _process(client, admin_headers, loaded, UNIFORM_END)
        body = client.post(
            "/api/fitting/preview",
            json={
                "material_id": loaded["material_id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "families": ["voce"],
            },
            headers=admin_headers,
        )
        assert body.status_code == 200, body.text
        fit = body.json()["fits"][0]
        values = {item["name"]: item["value"] for item in fit["parameters"]}

        assert fit["r_squared"] > 0.999
        assert fit["relative_rmse"] < 0.01
        assert values["sigma_0"] == pytest.approx(TRUE_SIGMA0, rel=0.05)
        assert values["q"] == pytest.approx(TRUE_Q, rel=0.10)
        assert values["b"] == pytest.approx(TRUE_B, rel=0.20)

    def test_네킹이_섞이면_적합이_나빠진다(
        self, client: TestClient, admin_headers: dict[str, str], loaded: dict[str, Any]
    ) -> None:
        """**이것이 '자르지 않으면 이런 일이 난다' 의 근거다.**

        진응력 변환식은 균일 변형을 전제한다. 네킹 뒤를 함께 적합하면 파라미터가
        참값에서 멀어진다 — 그런데 곡선은 여전히 그럴듯하게 그려진다.
        """
        _process(client, admin_headers, loaded, NECKED_END)
        fit = client.post(
            "/api/fitting/preview",
            json={
                "material_id": loaded["material_id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "families": ["voce"],
            },
            headers=admin_headers,
        ).json()["fits"][0]
        values = {item["name"]: item["value"] for item in fit["parameters"]}
        # 균일 구간만 썼을 때는 20% 안에 들어온다(위 시험). 네킹을 섞으면 벗어난다.
        assert abs(values["b"] / TRUE_B - 1) > 0.20


class Test내보내기:
    def _card(
        self, client: TestClient, headers: dict[str, str], material_id: str
    ) -> dict[str, Any]:
        created = client.post(
            "/api/fitting/cards",
            json={
                "material_id": material_id,
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "산포 MD",
                "family": "voce",
                "poisson_ratio": 0.3,
                "density": 7850.0,
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        return dict(created.json())

    def test_네킹이_섞인_표를_거부한다(
        self, client: TestClient, admin_headers: dict[str, str], loaded: dict[str, Any]
    ) -> None:
        """**눕혀서 내보내면 그 덱은 실제와 다른 재료가 된다.**

        네킹 뒤에는 진응력이 떨어지는 구간이 생긴다. 솔버는 단조 증가를 기대하므로
        조용히 고칠 수 있지만, 고치면 아무도 그 사실을 모른다.
        """
        _process(client, admin_headers, loaded, NECKED_END)
        card = self._card(client, admin_headers, loaded["material_id"])
        response = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=abaqus", headers=admin_headers
        )
        assert response.status_code == 422, response.text
        message = response.json()["error"]["message"]
        assert "응력이 떨어집니다" in message
        assert "네킹" in message

    def test_자른_뒤에는_덱이_나온다(
        self, client: TestClient, admin_headers: dict[str, str], loaded: dict[str, Any]
    ) -> None:
        """위 거부의 안내를 따라가면 한 바퀴가 닫힌다."""
        _process(client, admin_headers, loaded, UNIFORM_END)
        card = self._card(client, admin_headers, loaded["material_id"])

        deck = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=abaqus", headers=admin_headers
        )
        assert deck.status_code == 200, deck.text
        text = deck.text
        assert "*PLASTIC" in text
        # 첫 소성 점이 항복점이다. 참 sigma_0 근처여야 한다.
        first = text.split("EXTRAPOLATION=CONSTANT\n")[1].splitlines()[0]
        stress, strain = (float(value) for value in first.split(","))
        assert strain == 0.0
        assert stress == pytest.approx(TRUE_SIGMA0, rel=0.06)

        radioss = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=openradioss",
            headers=admin_headers,
        )
        assert radioss.status_code == 200, radioss.text
        assert "/MAT/LAW36" in radioss.text
