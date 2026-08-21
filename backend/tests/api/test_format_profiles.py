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

from app.modules.accounts.models import User
from app.modules.auth import security
from app.modules.tests import services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.legacy_profiles import ensure_builtin_format_profiles
from app.modules.tests.models import Curve, TestRun, TestType
from app.modules.workspaces.models import Workspace, WorkspaceMember

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
STRAIN_SWEEP = FIXTURES / "dma_strain_sweep.csv"
FREQ_TEMP = FIXTURES / "dma_freq_temp.csv"
LEGACY_MTET = FIXTURES / "legacy_tensile.mtet"

#: 사람이 화면에서 만들 내용. **코드가 아니라 데이터다.**
DMA_PROFILE: dict[str, Any] = {
    "match": {"extensions": [".csv"], "header_any": ["Angular frequency"]},
    "tables": {
        "mode": "all",
        "include": "^Temperature Sweep|^Strain Sweep",
        "derived": "^TTS",
    },
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
        # **버리지도 섞지도 않는다.** 측정 6벌 + 장비가 계산해 준 TTS 2벌.
        assert len(curve_rows) == 8
        kinds = {curve.kind for curve in curve_rows}
        assert kinds == {"measured", "derived"}
        assert sum(1 for curve in curve_rows if curve.kind == "derived") == 2
        assert all(curve.row_count == 8 for curve in curve_rows if curve.kind == "measured")
        assert "temperature_sweep_multifrequency_2" in {curve.key for curve in curve_rows}

        # 시편 치수가 `50.0 mm` 에서 값+단위로 갈려 나온다
        assert run.source_metadata["specimen_thickness"] == "0.989 mm"

    def test_옛_앱_JSON_을_기본_프로파일로_읽는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """**설치하면 바로 읽힌다.** 사람이 정의를 손으로 적지 않는다.

        MatNexus 를 쓰기 시작한다는 것은 옛 앱에 쌓인 것을 옮긴다는 뜻이고, 그
        파일 형식은 하나다. 설치마다 40줄짜리 정의를 다시 적게 두면 그 손이
        틀리는 날이 온다.
        """
        created = ensure_builtin_format_profiles(db)
        assert "legacy_mtet" in created
        db.commit()

        response = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "tensile",
                "conditions": "{}",
            },
            files={"file": ("Test1.mtet", LEGACY_MTET.read_bytes())},
            headers=admin_headers,
        )
        assert response.status_code == 202, response.text
        run_id = uuid.UUID(response.json()["id"])

        assert services.parse_run(db, run_id) == "parsed"
        run = db.get(TestRun, run_id)
        assert run is not None
        # **확장자가 아니라 프로파일로 읽혔다.** `.mtet` 은 zwick 파서가 모른다.
        assert run.parser_version == "profile:legacy_mtet"

        curve_rows = list(db.scalars(select(Curve).where(Curve.test_run_id == run_id)))
        assert len(curve_rows) == 1
        assert curve_rows[0].row_count == 5

        # 옛 앱이 계산한 값이 함께 들어온다 — 같은 곡선에 대한 우리 결과와
        # 나란히 놓고 볼 수 있다.
        assert run.source_metadata["specimen_thickness"] == "0.986"

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


class Test곡선이여럿일때:
    """**저장은 되는데 화면에서 안 보이던 자리.**

    실측으로 걸렸다. 개발 서버에 DMA 주파수-온도 스윕을 올렸더니 곡선 6벌이
    저장됐는데 상세는 `row_count=None, channels=[]` 이었고 차트는 404 였다 —
    목록·상세·차트가 전부 `raw` 키만 찾았고, 표가 여럿인 파일에는 그 키가 없다.
    """

    def test_상세가_곡선을_전부_보여_준다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
    ) -> None:
        created = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen["id"], "test_type": "dma_sweep", "conditions": "{}"},
            files={"file": ("Example FreqTemp.csv", FREQ_TEMP.read_bytes())},
            headers=admin_headers,
        ).json()
        assert services.parse_run(db, uuid.UUID(created["id"])) == "parsed"

        detail = client.get(f"/api/test-runs/{created['id']}", headers=admin_headers).json()
        assert len(detail["curves"]) == 8
        assert detail["curves"][0]["label"].startswith("Temperature Sweep")
        assert detail["curves"][0]["row_count"] == 8
        # 무엇으로 읽었는지도 준다 — 곡선이 이상할 때 가장 먼저 보는 값이다.
        assert detail["parser_version"] == "profile:ta_dma850"

    def test_곡선을_골라_그린다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
    ) -> None:
        created = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen["id"], "test_type": "dma_sweep", "conditions": "{}"},
            files={"file": ("Example FreqTemp.csv", FREQ_TEMP.read_bytes())},
            headers=admin_headers,
        ).json()
        services.parse_run(db, uuid.UUID(created["id"]))

        detail = client.get(f"/api/test-runs/{created['id']}", headers=admin_headers).json()
        key = detail["curves"][2]["key"]

        chosen = client.get(
            f"/api/test-runs/{created['id']}/curve"
            f"?x=temperature&y=storage_modulus&curve={key}",
            headers=admin_headers,
        )
        assert chosen.status_code == 200, chosen.text
        assert chosen.json()["returned"] == 8

        # 안 고르면 첫 곡선. 표가 하나뿐인 파일에서는 예전과 같다.
        default = client.get(
            f"/api/test-runs/{created['id']}/curve?x=temperature&y=storage_modulus",
            headers=admin_headers,
        )
        assert default.status_code == 200

    def test_없는_곡선을_고르면_있는_것을_알려_준다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
    ) -> None:
        created = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen["id"], "test_type": "dma_sweep", "conditions": "{}"},
            files={"file": ("Example.csv", STRAIN_SWEEP.read_bytes())},
            headers=admin_headers,
        ).json()
        services.parse_run(db, uuid.UUID(created["id"]))

        response = client.get(
            f"/api/test-runs/{created['id']}/curve?x=strain&y=storage_modulus&curve=nope",
            headers=admin_headers,
        )
        assert response.status_code == 404
        assert "raw" in response.json()["error"]["message"]


class Test성격이다른곡선:
    """**한 파일에 성격이 다른 곡선이 섞여 온다.**

    실사용 보고에서 나왔다: "곡선이 여러 스타일이 있는 경우가 있어" — 경고가
    `TTS - shift factors`, `TTS - master curve` 를 건너뛰었다고 알려 준 것.

    버리면 장비가 계산해 준 결과를 잃고, 섞으면 Phase 3 의 처리가 마스터 곡선을
    원본으로 착각한다. 그래서 **무엇인지 적어 둔다.**
    """

    def test_처리결과를_버리지_않는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
    ) -> None:
        created = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen["id"], "test_type": "dma_sweep", "conditions": "{}"},
            files={"file": ("Example FreqTemp.csv", FREQ_TEMP.read_bytes())},
            headers=admin_headers,
        ).json()
        services.parse_run(db, uuid.UUID(created["id"]))

        detail = client.get(f"/api/test-runs/{created['id']}", headers=admin_headers).json()
        by_kind: dict[str, list[dict[str, Any]]] = {}
        for curve in detail["curves"]:
            by_kind.setdefault(curve["kind"], []).append(curve)

        assert len(by_kind["measured"]) == 6
        assert len(by_kind["derived"]) == 2
        assert {curve["label"] for curve in by_kind["derived"]} == {
            "TTS - shift factors",
            "TTS - master curve (20.0 °C)",
        }

    def test_측정이_먼저_온다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
    ) -> None:
        """**기본으로 그려지는 곡선이 마스터 곡선이면 안 된다** — 사람은 그것이
        원본인 줄 안다."""
        created = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen["id"], "test_type": "dma_sweep", "conditions": "{}"},
            files={"file": ("Example FreqTemp.csv", FREQ_TEMP.read_bytes())},
            headers=admin_headers,
        ).json()
        services.parse_run(db, uuid.UUID(created["id"]))

        detail = client.get(f"/api/test-runs/{created['id']}", headers=admin_headers).json()
        assert detail["curves"][0]["kind"] == "measured"

    def test_처리결과의_열도_읽는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
    ) -> None:
        """마스터 곡선에는 측정에 없는 열이 있다 — 복소 컴플라이언스(1/MPa),
        위상각(°), 역온도(1/K). 단위표가 그것들을 알아야 읽힌다."""
        rule = {**DMA_PROFILE, "tables": {"mode": "all", "derived": "^TTS"}}
        response = client.post(
            "/api/formats/try",
            data={"definition": json.dumps(rule)},
            files={"file": ("Example FreqTemp.csv", FREQ_TEMP.read_bytes())},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        master = next(
            curve
            for curve in response.json()["curves"]
            if curve["label"] and "master" in curve["label"]
        )
        channels = {c["key"]: c for c in master["channels"]}
        assert channels["complex_compliance"]["si_unit"] == "1/Pa"
        assert channels["phase_angle"]["si_unit"] == "rad"
        assert channels["1_temperature"]["si_unit"] == "1/K"


class Test부서가장비를붙인다:
    """**관리자 전용으로 두었더니 실무가 막혔다.**

    장비는 부서마다 다른데, 남의 부서 파일을 어떻게 읽을지를 시스템 관리자가 알
    리 없다 — 그 지식은 사업부에 있다. 그래서 재료와 같은 모델을 쓴다: 부서가
    만들고, 전역 승격은 관리자(ADR 0004).
    """

    @pytest.fixture
    def manager(
        self,
        client: TestClient,
        db: Session,
        workspace: Workspace,
        admin_headers: dict[str, str],
    ) -> dict[str, str]:
        """다른 부서의 관리자. 시스템 관리자가 아니다."""
        user = User(
            email="lead",
            password_hash=security.hash_password("member-password-1"),
            display_name="사업부 관리자",
            status="active",
        )
        db.add(user)
        db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="manager"))
        db.commit()
        response = client.post(
            "/api/auth/login", json={"email": "lead", "password": "member-password-1"}
        )
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    @pytest.fixture
    def plain_member(
        self, client: TestClient, db: Session, workspace: Workspace
    ) -> dict[str, str]:
        user = User(
            email="worker",
            password_hash=security.hash_password("member-password-1"),
            display_name="시험 담당자",
            status="active",
        )
        db.add(user)
        db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="member"))
        db.commit()
        response = client.post(
            "/api/auth/login", json={"email": "worker", "password": "member-password-1"}
        )
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _payload(self, **overrides: Any) -> dict[str, Any]:
        return {
            "key": "dept_dma",
            "label": "우리 부서 DMA",
            "test_type_key": "dma_sweep",
            "definition": DMA_PROFILE,
            "priority": 10,
            **overrides,
        }

    def test_부서_관리자가_만든다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        manager: dict[str, str],
        workspace: Workspace,
        dma: None,
    ) -> None:
        response = client.post(
            "/api/formats",
            json=self._payload(owner_workspace_slug=workspace.slug),
            headers=manager,
        )
        assert response.status_code == 201, response.text
        assert response.json()["owner_workspace_slug"] == workspace.slug
        assert response.json()["is_global"] is False

    def test_평범한_멤버는_못_만든다(
        self,
        client: TestClient,
        plain_member: dict[str, str],
        workspace: Workspace,
        dma: None,
    ) -> None:
        """만드는 것은 부서의 판단이다. 아무나 만들면 같은 장비 프로파일이
        여럿 생겨 어느 것이 이기는지 모르게 된다."""
        response = client.post(
            "/api/formats",
            json=self._payload(owner_workspace_slug=workspace.slug),
            headers=plain_member,
        )
        assert response.status_code == 403

    def test_전역은_시스템_관리자만(
        self,
        client: TestClient,
        manager: dict[str, str],
        dma: None,
    ) -> None:
        """전역은 **여러 부서가 함께 쓴다.** 한 부서가 만들거나 고치면 다른 부서의
        파일이 다르게 읽힌다."""
        blocked = client.post("/api/formats", json=self._payload(), headers=manager)
        assert blocked.status_code == 403
        assert "부서를 고르세요" in blocked.json()["error"]["message"]

    def test_전역_프로파일은_부서_관리자가_못_고친다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        manager: dict[str, str],
        dma: None,
    ) -> None:
        # `dma` 픽스처가 만든 ta_dma850 은 전역이다.
        response = client.put(
            "/api/formats/ta_dma850",
            json={
                "label": "몰래 고치기",
                "test_type_key": "dma_sweep",
                "definition": DMA_PROFILE,
            },
            headers=manager,
        )
        assert response.status_code == 403
        assert "여러 부서가 함께" in response.json()["error"]["message"]

    def test_남의_부서_프로파일은_보이지도_않는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        manager: dict[str, str],
        dma: None,
    ) -> None:
        other = Workspace(slug="other", name="다른 부서")
        db.add(other)
        db.commit()

        client.post(
            "/api/formats",
            json=self._payload(key="other_dma", owner_workspace_slug="other"),
            headers=admin_headers,
        )

        keys = {row["key"] for row in client.get("/api/formats", headers=manager).json()}
        assert "other_dma" not in keys
        assert "ta_dma850" in keys  # 전역은 보인다

    def test_내_부서_것이_전역보다_먼저_읽는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        workspace: Workspace,
        dma: None,
        specimen: dict[str, Any],
    ) -> None:
        """같은 장비라도 부서마다 소프트웨어 설정이 달라 열 이름이 조금씩 다른
        일이 있다. 부서가 자기 것을 만들어 뒀는데 전역이 이기면 만든 뜻이 없다."""
        client.post(
            "/api/formats",
            json=self._payload(
                key="dept_dma", owner_workspace_slug=workspace.slug, priority=1
            ),
            headers=admin_headers,
        )

        created = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen["id"], "test_type": "dma_sweep", "conditions": "{}"},
            files={"file": ("Example.csv", STRAIN_SWEEP.read_bytes())},
            headers=admin_headers,
        ).json()
        assert services.parse_run(db, uuid.UUID(created["id"])) == "parsed"

        run = db.get(TestRun, uuid.UUID(created["id"]))
        assert run is not None
        # 전역(ta_dma850, priority 10)보다 부서 것(priority 1)이 이긴다.
        assert run.parser_version == "profile:dept_dma"
