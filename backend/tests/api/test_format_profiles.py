"""형식 프로파일 — **코드 없이 새 장비를 붙일 수 있는가.**

이 파일이 증명하려는 것은 하나다: TA DMA850 이라는, 인장기와 아무 상관 없는
장비의 파일을 **파서 코드 한 줄 없이** 읽어 곡선까지 만들 수 있는가.

되지 않으면 "장비가 늘 때마다 파서를 짠다" 로 돌아가고, 그러면 현장 파일이
개발자에게 오기를 기다리는 왕복이 영원히 남는다.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.tests import services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import Curve, TestRun, TestType

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
STRAIN_SWEEP = FIXTURES / "dma_strain_sweep.csv"
FREQ_TEMP = FIXTURES / "dma_freq_temp.csv"

#: 사람이 화면에서 만들 내용. **코드가 아니라 데이터다.**
DMA_PROFILE: dict[str, Any] = {
    "match": {"extensions": [".csv"], "header_any": ["Angular frequency"]},
    "tables": {"mode": "all", "include": "^Temperature Sweep|^Strain Sweep"},
    "columns": {
        "Angular frequency": {"channel": "angular_frequency"},
        "Step time": {"channel": "step_time"},
        "Temperature": {"channel": "temperature"},
        "Oscillation strain": {"channel": "strain"},
        "Oscillation stress": {"channel": "stress"},
        "Tan(delta)": {"channel": "tan_delta"},
        "Storage modulus": {"channel": "storage_modulus"},
        "Loss modulus": {"channel": "loss_modulus"},
        "Frequency": {"channel": "frequency"},
    },
    "specimen": {
        "Length": "gauge_length",
        "Width": "specimen_width",
        "Thickness": "specimen_thickness",
    },
    "metadata": ["rundate", "Instrument name", "Operator", "Sample name"],
}

DMA_TYPE: dict[str, Any] = {
    "key": "dma_sweep",
    "label": "DMA 스윕",
    "abbr": "DMA",
    "parser_key": None,
    "channels": [
        {
            "key": "angular_frequency",
            "label": "각주파수",
            "dimension": "angular_frequency",
            "si_unit": "rad/s",
        },
        {"key": "temperature", "label": "온도", "dimension": "temperature", "si_unit": "K"},
        {
            "key": "storage_modulus",
            "label": "저장탄성률",
            "dimension": "stress",
            "si_unit": "Pa",
        },
        {
            "key": "loss_modulus",
            "label": "손실탄성률",
            "dimension": "stress",
            "si_unit": "Pa",
            "is_required": False,
        },
        {
            "key": "strain",
            "label": "변형률",
            "dimension": "strain",
            "si_unit": "1",
            "is_required": False,
        },
        {
            "key": "stress",
            "label": "응력",
            "dimension": "stress",
            "si_unit": "Pa",
            "is_required": False,
        },
        {
            "key": "tan_delta",
            "label": "손실계수",
            "dimension": "dimensionless",
            "si_unit": "1",
            "is_required": False,
        },
        {
            "key": "step_time",
            "label": "구간 시간",
            "dimension": "time",
            "si_unit": "s",
            "is_required": False,
        },
        {
            "key": "frequency",
            "label": "주파수",
            "dimension": "frequency",
            "si_unit": "Hz",
            "is_required": False,
        },
    ],
    "conditions": [],
}


@pytest.fixture
def dma(client: TestClient, admin_headers: dict[str, str]) -> None:
    """시험 종류와 프로파일을 **API 로** 만든다 — 코드 수정도 배포도 없다."""
    created = client.post("/api/test-types", json=DMA_TYPE, headers=admin_headers)
    assert created.status_code == 201, created.text
    saved = client.post(
        "/api/formats",
        json={
            "key": "ta_dma850",
            "label": "TA DMA850 CSV",
            "test_type_key": "dma_sweep",
            "definition": DMA_PROFILE,
            "priority": 10,
        },
        headers=admin_headers,
    )
    assert saved.status_code == 201, saved.text


@pytest.fixture
def tensile(db: Session) -> None:
    """파서가 있는 종류. 확장자 경로를 확인하는 데 쓴다."""
    ensure_builtin_test_types(db)
    db.commit()


@pytest.fixture
def specimen(client: TestClient, admin_headers: dict[str, str]) -> dict[str, Any]:
    material = client.post(
        "/api/materials",
        json={"family": "Metal", "category": "Steel", "grade": "SECC", "spec_thickness": 1.0},
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    result: dict[str, Any] = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": "TD"},
        headers=admin_headers,
    ).json()
    return result


class TestPreview:
    def test_저장하지_않고_구조를_읽는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """새 장비 파일이 왔을 때 가장 먼저 하는 일. 아직 어느 시편의 것인지도
        모르므로 저장하지 않는다."""
        response = client.post(
            "/api/formats/preview",
            files={"file": ("Example FreqTemp.csv", FREQ_TEMP.read_bytes())},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["encoding"] == "utf-8-sig"
        assert body["delimiter"] == ","
        assert len(body["tables"]) == 8  # [step] 8개가 그대로 잡힌다
        assert body["tables"][0]["name"] == "Temperature Sweep (Multifrequency) - 2"
        assert "Angular frequency" in body["tables"][0]["header"]
        assert body["tables"][0]["units"][0] == "rad/s"
        assert body["tables"][0]["sample_rows"]  # 사람이 눈으로 볼 근거
        assert ("Operator", "박용진") in [tuple(pair) for pair in body["meta"]]
        assert body["matched_profile"] is None  # 아직 프로파일이 없다

    def test_인코딩을_추측했으면_말한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """자동 감지가 틀릴 수 있다는 사실 자체를 드러낸다."""
        cp949 = FREQ_TEMP.read_text(encoding="utf-8").encode("cp949")
        response = client.post(
            "/api/formats/preview",
            files={"file": ("cp949.csv", cp949)},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["encoding"] == "cp949"
        assert any("추측" in warning for warning in response.json()["warnings"])

    def test_이미_있는_프로파일이_잡히면_알려_준다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """새로 만들 필요가 없다는 것을 알려 주는 편이 낫다."""
        response = client.post(
            "/api/formats/preview",
            files={"file": ("Example.csv", STRAIN_SWEEP.read_bytes())},
            headers=admin_headers,
        )
        assert response.json()["matched_profile"] == "ta_dma850"


class TestTryBeforeSave:
    def test_저장_전에_적용해_본다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """저장하고 나서 틀린 것을 아는 것과 저장 전에 아는 것은 다르다."""
        response = client.post(
            "/api/formats/try",
            data={"definition": json.dumps(DMA_PROFILE)},
            files={"file": ("Example.csv", STRAIN_SWEEP.read_bytes())},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["curves"]) == 1
        channels = {c["key"]: c for c in body["curves"][0]["channels"]}
        # 25°C -> 298.15 K. 오프셋을 빠뜨리면 25 K(-248℃)가 된다.
        assert channels["temperature"]["first"] == pytest.approx(298.15)
        assert channels["temperature"]["source_unit"] == "°C"
        # 9.99711e-4 % -> 9.99711e-06 (무차원)
        assert channels["strain"]["first"] == pytest.approx(9.99711e-06)
        # rad/s 는 Hz 로 환산하지 않는다 — 장비가 각각 실측한 별개 값이다
        assert channels["angular_frequency"]["first"] == pytest.approx(6.28319)
        assert body["metadata"]["specimen_thickness"] == "0.989 mm"

    def test_메타를_전부_버리기로_정할_수_있다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**"규칙이 없음" 과 "하나도 안 보관하기로 정함" 은 다르다.**

        화면은 메타 한 줄마다 역할을 고르게 하므로, 사람이 전부 '버림' 으로 고르면
        빈 목록이 온다. 그것을 "규칙 없음" 과 같게 다루면 정반대로 전부 보관된다.
        """
        rule = {**DMA_PROFILE, "metadata": [], "specimen": {}}
        response = client.post(
            "/api/formats/try",
            data={"definition": json.dumps(rule)},
            files={"file": ("Example.csv", STRAIN_SWEEP.read_bytes())},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["metadata"] == {}

        # 키 자체가 없으면 예전처럼 전부 보관한다 — 메타에 관심 없는 프로파일.
        loose = {key: value for key, value in DMA_PROFILE.items() if key != "metadata"}
        kept = client.post(
            "/api/formats/try",
            data={"definition": json.dumps(loose)},
            files={"file": ("Example.csv", STRAIN_SWEEP.read_bytes())},
            headers=admin_headers,
        ).json()["metadata"]
        assert kept["instrument_location"] == "SAMSUNG"

    def test_지문이_없으면_저장을_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """지문 없는 프로파일은 **모든 파일에 맞는다.** 다른 장비 파일까지
        이 규칙으로 읽혀 조용히 엉뚱한 곡선이 생긴다."""
        response = client.post(
            "/api/formats",
            json={
                "key": "no_fingerprint",
                "label": "지문 없음",
                "test_type_key": "dma_sweep",
                "definition": {"columns": {"A": {"channel": "a"}}},
            },
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "지문" in response.json()["error"]["message"]


class TestDetect:
    """**고르는 일을 없앤다.** 종류가 늘수록 매번 드롭다운에서 찾는 비용이 커지는데,
    그 답은 파일이 이미 갖고 있다."""

    def test_지문으로_종류를_고른다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """확장자로는 못 한다. **DMA 종류는 파서가 없어 확장자가 비어 있다** —
        프로파일을 만들어 두고도 매번 손으로 골라야 했던 이유다."""
        response = client.post(
            "/api/test-types/detect",
            files={"file": ("Example.csv", STRAIN_SWEEP.read_bytes())},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["test_type_key"] == "dma_sweep"
        assert body["profile_key"] == "ta_dma850"
        assert body["source"] == "profile"

    def test_머리_조각만으로도_알아본다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """화면은 파일 앞부분만 보낸다. 20개짜리 배치를 통째로 두 번 올릴 이유가
        없다 — 지문은 메타·헤더에 있다."""
        head = STRAIN_SWEEP.read_bytes()[:2048]
        response = client.post(
            "/api/test-types/detect",
            files={"file": ("Example.csv", head)},
            headers=admin_headers,
        )
        assert response.json()["test_type_key"] == "dma_sweep"

    def test_프로파일이_없으면_확장자로_내려간다(
        self, client: TestClient, admin_headers: dict[str, str], tensile: None
    ) -> None:
        response = client.post(
            "/api/test-types/detect",
            files={"file": ("Example.TRA", (FIXTURES / "Example.tra").read_bytes())},
            headers=admin_headers,
        )
        body = response.json()
        assert body["test_type_key"] == "tensile"
        assert body["source"] == "extension"

    def test_모르면_고르지_않는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**하나를 찍으면 그럴듯해 보이는데 틀린다.** 못 정했다고 말하고 사람이
        고르게 한다. 이유도 함께 준다."""
        response = client.post(
            "/api/test-types/detect",
            files={"file": ("메모.txt", b"hello\nworld\n")},
            headers=admin_headers,
        )
        body = response.json()
        assert body["test_type_key"] is None
        assert body["source"] == "none"
        assert body["reason"]

    def test_중단된_종류는_고르지_않는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], dma: None
    ) -> None:
        """더 쓰지 않기로 한 종류에 새 시험이 붙으면 안 된다."""
        test_type = db.scalar(select(TestType).where(TestType.key == "dma_sweep"))
        assert test_type is not None
        test_type.is_active = False
        db.commit()

        response = client.post(
            "/api/test-types/detect",
            files={"file": ("Example.csv", STRAIN_SWEEP.read_bytes())},
            headers=admin_headers,
        )
        assert response.json()["test_type_key"] is None


class TestEndToEnd:
    def test_코드_없이_DMA_를_읽어_곡선까지_만든다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
    ) -> None:
        """**이 프로젝트의 확장성이 성립하는지를 가르는 시험이다.**

        시험 종류도 프로파일도 API 로 만들었다. `matcore` 에 DMA 를 아는 코드는
        한 줄도 없다.
        """
        response = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "dma_sweep",
                "conditions": "{}",
            },
            files={"file": ("Example FreqTemp.csv", FREQ_TEMP.read_bytes())},
            headers=admin_headers,
        )
        assert response.status_code == 202, response.text
        run_id = uuid.UUID(response.json()["id"])

        assert services.parse_run(db, run_id) == "parsed"
        run = db.get(TestRun, run_id)
        assert run is not None
        assert run.parser_version == "profile:ta_dma850"  # 무엇으로 읽었는지 남는다

        curve_rows = list(db.scalars(select(Curve).where(Curve.test_run_id == run_id)))
        # 측정 구간 6개. TTS 표 2개는 규칙에 안 맞아 빠진다.
        assert len(curve_rows) == 6
        assert all(curve.row_count == 8 for curve in curve_rows)
        assert "temperature_sweep_multifrequency_2" in {curve.key for curve in curve_rows}

        # 시편 치수가 `50.0 mm` 에서 값+단위로 갈려 나온다
        assert run.source_metadata["specimen_thickness"] == "0.989 mm"
        # 건너뛴 표를 조용히 버리지 않는다
        assert "TTS" in run.source_metadata.get("_warnings", "")

    def test_단위가_정의와_다르면_등록이_실패한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
    ) -> None:
        """**저장 단계는 단위를 확인하지 않는다.** Parquet 에는 숫자만 들어가고
        읽을 때는 정의의 `si_unit` 을 믿는다. 여기서 안 막으면 무차원으로 읽힌
        값이 Pa 인 척 저장된다 — 숫자는 멀쩡해 보이고 뜻만 바뀐다.

        이 파일은 저장탄성률의 단위 칸이 비어 있어 무차원으로 읽힌다. 프로파일
        쪽(matcore)은 단위가 '해결' 됐으므로 못 잡는다 — 시험 종류를 아는 이쪽만
        잡을 수 있다.
        """
        broken = (
            "[step]\n"
            "Strain Sweep - 1\n"
            "Angular frequency,Temperature,Storage modulus\n"
            "rad/s,°C,\n"  # ← 저장탄성률 단위 칸이 비어 있다
            "6.28319,25.00,201242\n"
            "6.29319,25.05,201243\n"
        ).encode()
        created = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "dma_sweep",
                "conditions": "{}",
            },
            files={"file": ("Broken.csv", broken)},
            headers=admin_headers,
        ).json()

        assert services.parse_run(db, uuid.UUID(created["id"])) == "failed"
        run = db.get(TestRun, uuid.UUID(created["id"]))
        assert run is not None
        assert "단위" in (run.parse_error or "")
        # 무엇이 어떻게 어긋났는지까지 남는다 — 사람이 고칠 근거다.
        assert "dimensionless" in (run.parse_error or "")
        assert "stress" in (run.parse_error or "")

    def test_곡선을_화면이_읽을_수_있다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
    ) -> None:
        created = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "dma_sweep",
                "conditions": "{}",
            },
            files={"file": ("Example.csv", STRAIN_SWEEP.read_bytes())},
            headers=admin_headers,
        ).json()
        services.parse_run(db, uuid.UUID(created["id"]))

        curve = client.get(
            f"/api/test-runs/{created['id']}/curve?x=strain&y=storage_modulus",
            headers=admin_headers,
        )
        assert curve.status_code == 200, curve.text
        assert curve.json()["row_count"] == 10
        assert len(curve.json()["points"]) == 10
