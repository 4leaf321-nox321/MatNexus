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
from app.modules.tests.models import Curve, FormatProfile, TestRun, TestType
from app.modules.vocabulary.models import Vocabulary
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
    # **실제 정의와 같게 둔다**(`definitions.py`). 비워 두었더니 「파일이 조건을
    # 채운다」를 시험할 수가 없었다 — 채울 칸이 없는 종류였다.
    "conditions": [
        {
            "key": "reference_temperature",
            "label": "기준 온도",
            "value_type": "number",
            "dimension": "temperature",
            "si_unit": "K",
            "is_required": False,
        },
        {
            "key": "preload",
            "label": "예하중",
            "value_type": "number",
            "dimension": "force",
            "si_unit": "N",
            "is_required": False,
        },
        {"key": "clamp", "label": "지그", "value_type": "text", "is_required": False},
    ],
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

    def test_모르는_단위를_적으면_저장을_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """**저장할 때 본다.** 안 보면 저장은 되고 등록에서 실패하는데, 그
        실패는 파일을 올린 다음에야 보이고 원인은 편집 화면에 있다 — 사람은
        두 화면을 왕복하며 짐작하게 된다."""
        bad = {**DMA_PROFILE, "columns": {"A": {"channel": "a", "unit": "mmm"}}}
        response = client.post(
            "/api/formats",
            json={
                "key": "bad_unit",
                "label": "모르는 단위",
                "test_type_key": "dma_sweep",
                "definition": bad,
            },
            headers=admin_headers,
        )
        assert response.status_code == 422
        message = response.json()["error"]["message"]
        assert "'A'" in message and "mmm" in message

    def test_아는_단위는_통과한다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """무차원은 빈 칸이 아니라 `1` 이다. 서버는 별칭(`Mpa`)도 알아본다."""
        good = {
            **DMA_PROFILE,
            "columns": {
                "Angular frequency": {"channel": "angular_frequency", "unit": "rad/s"},
                "Tan(delta)": {"channel": "tan_delta", "unit": "1"},
            },
        }
        response = client.post(
            "/api/formats",
            json={
                "key": "good_unit",
                "label": "단위 지정",
                "test_type_key": "dma_sweep",
                "definition": good,
            },
            headers=admin_headers,
        )
        assert response.status_code == 201

    def test_없는_칸을_가리키면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """오타 하나가 조용히 아무것도 안 하는 규칙이 되면, 사람은 "왜 안
        채워지지" 를 파일 쪽에서 찾는다."""
        response = client.post(
            "/api/formats",
            json={
                "key": "bad_field",
                "label": "없는 칸",
                "test_type_key": "dma_sweep",
                "definition": {**DMA_PROFILE, "record": {"Operator": {"field": "seq_no"}}},
            },
            headers=admin_headers,
        )
        assert response.status_code == 422
        message = response.json()["error"]["message"]
        assert "seq_no" in message and "operator" in message  # 쓸 수 있는 칸을 알려 준다

    def test_한_칸을_둘이_가리키면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """어느 쪽이 이길지는 dict 순서가 정하는데, 그건 사람이 정한 것이 아니다."""
        response = client.post(
            "/api/formats",
            json={
                "key": "two_fields",
                "label": "둘이 하나를",
                "test_type_key": "dma_sweep",
                "definition": {
                    **DMA_PROFILE,
                    "record": {
                        "Operator": {"field": "operator"},
                        "Instrument name": {"field": "operator"},
                    },
                },
            },
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "시험자" in response.json()["error"]["message"]

    def test_시도가_채울_값을_미리_보여_준다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """저장하고 나서 아는 것과 저장 전에 아는 것은 다르다."""
        rule = {
            **DMA_PROFILE,
            "record": {"Operator": {"field": "operator"}},
            "identity": {"Sample name": {"field": "material_grade"}},
        }
        tried = client.post(
            "/api/formats/try",
            data={"definition": json.dumps(rule)},
            files={"file": ("Example.csv", STRAIN_SWEEP.read_bytes())},
            headers=admin_headers,
        ).json()
        assert tried["record"].get("operator")
        assert tried["identity"].get("material_grade")

    def test_매달린_시험이_있으면_지우지_못한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
    ) -> None:
        """**실측으로 걸렸다**(2026-08-27).

        그 형식으로 읽은 시험이 하나 있는 채로 지우면 FK 가 막고, 그것이 그대로
        500 이 됐다 — 사람은 "서버 오류가 발생했습니다" 만 보고 무엇이 걸렸는지
        알 수 없다. 시험 종류 삭제는 이미 같은 것을 막고 있었다.
        """
        made = client.post(
            "/api/formats",
            json={
                "key": "to_delete",
                "label": "지울 것",
                "test_type_key": "dma_sweep",
                "definition": DMA_PROFILE,
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text

        # 아무것도 안 매달렸으면 지워진다 — 막는 것이 목적이 아니다.
        assert (
            client.delete("/api/formats/to_delete", headers=admin_headers).status_code == 204
        )

        client.post(
            "/api/formats",
            json={
                "key": "to_delete",
                "label": "지울 것",
                "test_type_key": "dma_sweep",
                "definition": DMA_PROFILE,
            },
            headers=admin_headers,
        )
        # **참조를 직접 만든다.** `reparse` 는 큐에만 넣고 실제로 잇는 것은
        # 워커인데, 시험에는 워커가 없다. 여기서 볼 것은 "참조가 있을 때 어떻게
        # 되는가" 이므로 참조를 만드는 방법은 상관없다.
        run = _upload_dma(client, admin_headers, specimen["id"])
        profile = db.scalar(select(FormatProfile).where(FormatProfile.key == "to_delete"))
        assert profile is not None
        stored = db.scalar(select(TestRun).where(TestRun.id == uuid.UUID(run["id"])))
        assert stored is not None
        stored.parse_profile_id = profile.id
        db.commit()

        response = client.delete("/api/formats/to_delete", headers=admin_headers)
        assert response.status_code == 409, response.text
        message = response.json()["error"]["message"]
        # **무엇이 걸렸는지 말한다.** 개수만 주면 어디를 치울지 모른다.
        assert "시험" in message or "test_runs" in message

    def test_재료_시료도_없는_칸을_가리키면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """이관 경로만 읽는 자리지만 **저장할 때** 본다.

        오타를 이관 당일에 알면, 그때는 파일 수백 개를 앞에 두고 있다.
        """
        for where, wrong in (("material", "grade"), ("sample", "lot_no")):
            response = client.post(
                "/api/formats",
                json={
                    "key": f"bad_{where}",
                    "label": "없는 칸",
                    "test_type_key": "dma_sweep",
                    "definition": {**DMA_PROFILE, where: {"Operator": {"field": wrong}}},
                },
                headers=admin_headers,
            )
            assert response.status_code == 422, where
            # **열쇠는 여기 없다.** grade·lot_no 는 「어느 재료인가」 를 정하는
            # 것이라 `identity` 쪽이고, 여기에 두면 시험이 재료를 옮겨 버린다.
            assert wrong in response.json()["error"]["message"]

    def test_재료_시료의_모르는_단위를_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """JSON 에는 단위 줄이 없다. 프로파일이 적은 것이 유일한 근거다."""
        response = client.post(
            "/api/formats",
            json={
                "key": "bad_material_unit",
                "label": "모르는 단위",
                "test_type_key": "dma_sweep",
                "definition": {
                    **DMA_PROFILE,
                    "material": {"T": {"field": "spec_thickness", "unit": "inch"}},
                },
            },
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "inch" in response.json()["error"]["message"]

    def test_시도가_재료_시료를_미리_보여_준다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """**업로드는 이 값을 안 쓴다.** 그래서 미리보기가 유일하게 보이는
        자리다 — 여기서 안 보여 주면 이관을 돌리기 전까지 확인할 방법이 없다."""
        rule = {
            **DMA_PROFILE,
            "material": {"Sample name": {"field": "details"}},
            "sample": {"Operator": {"field": "manufacturer"}},
        }
        tried = client.post(
            "/api/formats/try",
            data={"definition": json.dumps(rule)},
            files={"file": ("Example.csv", STRAIN_SWEEP.read_bytes())},
            headers=admin_headers,
        ).json()
        assert tried["material"].get("details")
        assert tried["sample"].get("manufacturer")

    def test_시편_규격도_붙일_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """**규격이 치수 칸을 정한다**(ADR 0010). 이관에서 규격을 못 붙이면 그
        시편은 치수를 받을 자리조차 없다 — 실사용에서 걸렸다."""
        rule = {**DMA_PROFILE, "specimen_props": {"Sample name": {"field": "standard"}}}
        tried = client.post(
            "/api/formats/try",
            data={"definition": json.dumps(rule)},
            files={"file": ("Example.csv", STRAIN_SWEEP.read_bytes())},
            headers=admin_headers,
        ).json()
        assert tried["specimen_props"].get("standard")

    def test_시편_속성에_방향은_없다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """방향·번호는 **어느 시편인가**를 정하는 열쇠라 짚기 쪽이다. 두 곳에
        두면 어긋날 때 답이 없다."""
        response = client.post(
            "/api/formats",
            json={
                "key": "bad_specimen_props",
                "label": "방향",
                "test_type_key": "dma_sweep",
                "definition": {
                    **DMA_PROFILE,
                    "specimen_props": {"Operator": {"field": "orientation"}},
                },
            },
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "orientation" in response.json()["error"]["message"]

    def test_적용_제품과_부위를_붙일_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """옛 DB 는 「적용 제품」 을 갖고 있다. 붙일 자리가 없으면 그 값은 이관에서
        통째로 사라진다."""
        rule = {
            **DMA_PROFILE,
            "material": {"Sample name": {"field": "applied_products"}},
        }
        tried = client.post(
            "/api/formats/try",
            data={"definition": json.dumps(rule)},
            files={"file": ("Example.csv", STRAIN_SWEEP.read_bytes())},
            headers=admin_headers,
        ).json()
        assert tried["material"].get("applied_products")


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

    def test_DMA_도_기본_프로파일로_읽는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        specimen: dict[str, Any],
    ) -> None:
        """**설치하면 DMA 도 바로 읽힌다.** 시험 종류·프로파일 둘 다 시드다.

        위의 `dma` 픽스처는 "코드 없이 API 로 만들 수 있는가" 를 보는 것이고,
        여기는 "설치 상태에서 그냥 되는가" 를 본다. 둘은 다른 질문이다.
        """
        ensure_builtin_test_types(db)
        created = ensure_builtin_format_profiles(db)
        assert "ta_dma850" in created
        db.commit()

        response = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "dma_sweep",
                "conditions": "{}",
            },
            files={"file": ("Example FreqTemp2.csv", FREQ_TEMP.read_bytes())},
            headers=admin_headers,
        )
        assert response.status_code == 202, response.text
        run_id = uuid.UUID(response.json()["id"])

        assert services.parse_run(db, run_id) == "parsed"
        run = db.get(TestRun, run_id)
        assert run is not None
        assert run.parser_version == "profile:ta_dma850"

        curve_rows = list(db.scalars(select(Curve).where(Curve.test_run_id == run_id)))
        # 측정 6벌 + 장비가 계산한 TTS 2벌. **버리지도 섞지도 않는다.**
        assert len(curve_rows) == 8
        assert sum(1 for curve in curve_rows if curve.kind == "derived") == 2

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


class Test받는_확장자:
    """**화면이 「무엇을 받는가」 를 말할 수 있어야 한다.**

    일괄 등록 화면이 파서가 선언한 확장자만 적어서 `.tra` 만 지원하는 것처럼
    보였다 — 실제로는 프로파일이 `.csv`·`.mtet` 도 읽는다.
    """

    def test_프로파일의_확장자가_종류에_실린다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        del dma
        types = {
            item["key"]: item
            for item in client.get("/api/test-types", headers=admin_headers).json()
        }
        assert types["dma_sweep"]["profile_extensions"] == [".csv"]

    def test_파서_확장자와_섞지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """프로파일은 **내용을 보고** 정한다. 확장자가 같아도 헤더가 안 맞으면
        안 읽히므로, 이 목록으로 종류를 찍으면 안 된다 — 그래서 칸을 나눈다."""
        del dma
        types = {
            item["key"]: item
            for item in client.get("/api/test-types", headers=admin_headers).json()
        }
        # DMA 종류는 파서가 없다 — 파서 쪽 목록은 비어 있어야 한다.
        assert types["dma_sweep"]["extensions"] == []
        assert types["dma_sweep"]["profile_extensions"] == [".csv"]


def _upload_dma(client: TestClient, headers: dict[str, str], specimen_id: str) -> Any:
    """DMA 파일 하나를 올린다. 파싱은 부르는 쪽이 한다."""
    response = client.post(
        "/api/test-runs",
        data={"specimen_id": specimen_id, "test_type": "dma_sweep", "conditions": "{}"},
        files={"file": ("Example FreqTemp.csv", FREQ_TEMP.read_bytes())},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return response.json()


class Test읽을_형식_고르기:
    """*"읽기 실패한 것을 옵션을 바꿔 다시 읽으려는데 「다시 읽기」 만 있다"* —
    실사용에서 나왔다.

    자동 선택이 틀리는 자리가 있다. 그때 「다시 읽기」 는 **같은 선택을 그대로
    반복한다** — 고칠 자리가 없었다.
    """

    def test_고른_형식으로_읽는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        del dma
        run = _upload_dma(client, admin_headers, specimen["id"])
        again = client.post(
            f"/api/test-runs/{run['id']}/reparse",
            json={"profile_key": "ta_dma850"},
            headers=admin_headers,
        )
        assert again.status_code == 202, again.text
        assert again.json()["profile_key"] == "ta_dma850"

        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"
        detail = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        assert detail["parse_profile_key"] == "ta_dma850"
        assert detail["parser_version"] == "profile:ta_dma850"

    def test_자동이_고를_것과_다른_것을_고를_수_있다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        """**이 기능의 요점이다.** 자동이 이기는 프로파일이 따로 있을 때, 그것을
        제치고 내가 고른 것으로 읽혀야 한다 — 안 그러면 골라도 소용이 없다.

        같은 장비의 형식이 조금 달라져 프로파일을 하나 더 만들면 지문이 겹치고,
        우선순위가 높은 쪽이 이긴다. 실제로 생기는 자리다.
        """
        del dma
        # 우선순위가 더 높은 쌍둥이. 자동은 이쪽을 고른다.
        made = client.post(
            "/api/formats",
            json={
                "key": "ta_dma850_hi",
                "label": "TA DMA850 (우선)",
                "test_type_key": "dma_sweep",
                "definition": DMA_PROFILE,
                "priority": 99,
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text

        run = _upload_dma(client, admin_headers, specimen["id"])
        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"
        auto = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        assert auto["parser_version"] == "profile:ta_dma850_hi", "자동이 우선순위를 안 봤다"

        # 낮은 쪽을 고르면 그것으로 읽혀야 한다.
        client.post(
            f"/api/test-runs/{run['id']}/reparse",
            json={"profile_key": "ta_dma850"},
            headers=admin_headers,
        )
        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"
        pinned = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        assert pinned["parser_version"] == "profile:ta_dma850"
        assert pinned["parse_profile_key"] == "ta_dma850"

    def test_고른_것이_남아서_다음에도_이어진다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        """**큐 페이로드에만 실으면 재시도에서 사라진다.** 나중에 누가 그냥
        「다시 읽기」 를 눌러도 그 결정이 이어져야 한다."""
        del dma
        run = _upload_dma(client, admin_headers, specimen["id"])
        client.post(
            f"/api/test-runs/{run['id']}/reparse",
            json={"profile_key": "ta_dma850"},
            headers=admin_headers,
        )
        services.parse_run(db, uuid.UUID(run["id"]))

        # 형식을 안 적고 다시 읽어도 고정은 그대로다.
        client.post(f"/api/test-runs/{run['id']}/reparse", json={}, headers=admin_headers)
        detail = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        assert detail["parse_profile_key"] == "ta_dma850"

    def test_비워_보내면_고정을_푼다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        """프로파일을 고친 뒤 자동으로 되돌리는 길이다."""
        del dma
        run = _upload_dma(client, admin_headers, specimen["id"])
        client.post(
            f"/api/test-runs/{run['id']}/reparse",
            json={"profile_key": "ta_dma850"},
            headers=admin_headers,
        )
        client.post(
            f"/api/test-runs/{run['id']}/reparse",
            json={"profile_key": None},
            headers=admin_headers,
        )
        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"
        detail = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        assert detail["parse_profile_key"] is None

    def test_다른_종류의_형식은_못_고른다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma: None,
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """**다른 종류로 읽으면 채널 이름이 안 맞아 어차피 실패한다.** 그 실패는
        「형식이 틀렸다」 로 안 읽히므로 여기서 막는다."""
        del dma, tensile
        run = _upload_dma(client, admin_headers, specimen["id"])
        blocked = client.post(
            f"/api/test-runs/{run['id']}/reparse",
            json={"profile_key": "없는형식"},
            headers=admin_headers,
        )
        assert blocked.status_code == 422
        assert blocked.json()["error"]["code"] == "MNX-TESTS-0022"

    def test_고를_수_있는_형식을_목록으로_준다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """**무엇을 고를 수 있는지 화면이 알아야 한다.** 키를 외워서 치게 할 수는
        없다 — 이미 있는 목록 엔드포인트를 그대로 쓴다."""
        del dma
        found = client.get(
            "/api/formats", params={"test_type": "dma_sweep"}, headers=admin_headers
        ).json()
        assert [item["key"] for item in found] == ["ta_dma850"]


class Test종류가_틀린_파일:
    """**막다른 길을 가리키지 않는다.**

    인장 `.tra` 가 DMA 종류로 올라온 일이 있었다. 그때 안내는 「형식 프로파일을
    만들거나 파서를 등록하세요」 였는데, 그 말을 따라 프로파일을 만들어도 영영
    안 읽힌다 — 그 파일은 이미 읽을 줄 아는 파서가 있고 틀린 것은 종류였다.
    """

    def test_다른_종류가_읽을_수_있으면_그렇게_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma: None,
        tensile: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        del dma, tensile
        # 인장 파일을 DMA 종류로 올린다 — 실제로 난 일이다.
        made = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "dma_sweep",
                "conditions": "{}",
            },
            files={"file": ("Example.tra", (FIXTURES / "Example.tra").read_bytes())},
            headers=admin_headers,
        )
        assert made.status_code == 202, made.text

        assert services.parse_run(db, uuid.UUID(made.json()["id"])) == "failed"
        detail = client.get(
            f"/api/test-runs/{made.json()['id']}", headers=admin_headers
        ).json()
        message = detail["parse_error"]
        # **무엇이 틀렸는지·무엇을 하면 되는지가 다 들어 있어야 한다.**
        assert "인장시험" in message, message
        assert "zwick_tra" in message, message
        assert "시험 종류" in message, message

    def test_아무도_못_읽으면_전과_같이_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        """**없는 단서를 지어내지 않는다.** 정말 읽을 방법이 없으면 프로파일을
        만들라는 안내가 맞다."""
        del dma
        made = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "dma_sweep",
                "conditions": "{}",
            },
            files={"file": ("mystery.xyz", b"who knows what this is")},
            headers=admin_headers,
        )
        assert made.status_code == 202, made.text
        assert services.parse_run(db, uuid.UUID(made.json()["id"])) == "failed"
        detail = client.get(
            f"/api/test-runs/{made.json()['id']}", headers=admin_headers
        ).json()
        assert "형식 프로파일을" in detail["parse_error"]
        assert "시험 종류가 잘못" not in detail["parse_error"]


class Test시험_종류_바로잡기:
    """올릴 때 종류를 잘못 고른 시험. **지우고 다시 올리지 않아도 되게.**

    파일은 이미 올라와 있고 시편 연결도 끝났다 — 틀린 것은 종류 하나다.
    """

    def _wrong(
        self, client: TestClient, headers: dict[str, str], specimen_id: str
    ) -> dict[str, Any]:
        """인장 파일을 DMA 종류로 올린다 — 실제로 난 일이다."""
        made = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen_id, "test_type": "dma_sweep", "conditions": "{}"},
            files={"file": ("Example.tra", (FIXTURES / "Example.tra").read_bytes())},
            headers=headers,
        )
        assert made.status_code == 202, made.text
        return dict(made.json())

    def test_종류를_바꾸면_이름도_바뀐다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma: None,
        tensile: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        """**종류는 이름의 한 칸이다**(ADR 0004)."""
        del dma, tensile
        run = self._wrong(client, admin_headers, specimen["id"])
        assert services.parse_run(db, uuid.UUID(run["id"])) == "failed"

        fixed = client.post(
            f"/api/test-runs/{run['id']}/test-type",
            json={"test_type_key": "tensile"},
            headers=admin_headers,
        )
        assert fixed.status_code == 202, fixed.text
        assert fixed.json()["record_name"] != run["record_name"]
        assert "TEN" in fixed.json()["record_name"]

        # 그리고 이제 읽힌다 — 그게 이 기능의 요점이다.
        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"

    def test_새_종류_안에서_다시_채번한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma: None,
        tensile: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        """**회차는 종류별이다.** 옛 번호를 들고 가면 새 종류에서 이미 쓰인
        번호와 부딪힌다 — 같은 이름이 둘 생긴다."""
        del dma, tensile
        # 이 시편에 인장 1회차가 이미 있다.
        first = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
            files={"file": ("Example.tra", (FIXTURES / "Example.tra").read_bytes())},
            headers=admin_headers,
        )
        assert first.status_code == 202, first.text
        assert first.json()["record_name"].endswith("TEN_01")

        # 잘못 올린 것은 DMA 1회차다 — 옛 번호를 들고 가면 TEN_01 이 둘이 된다.
        wrong = self._wrong(client, admin_headers, specimen["id"])
        assert wrong["record_name"].endswith("_01")
        assert services.parse_run(db, uuid.UUID(wrong["id"])) == "failed"

        fixed = client.post(
            f"/api/test-runs/{wrong['id']}/test-type",
            json={"test_type_key": "tensile"},
            headers=admin_headers,
        )
        assert fixed.status_code == 202, fixed.text
        assert fixed.json()["record_name"].endswith("TEN_02"), fixed.json()["record_name"]
        assert fixed.json()["record_name"] != first.json()["record_name"]

    def test_읽힌_시험은_막는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma: None,
        tensile: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        """**말없이 지워 주지 않는다.** 곡선과 결과가 무엇의 것인지 알 수 없게
        되는데, 그 사람은 무엇이 사라졌는지 모른 채 새 이름을 얻는다."""
        del dma
        del tensile
        made = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
            files={"file": ("Example.tra", (FIXTURES / "Example.tra").read_bytes())},
            headers=admin_headers,
        )
        assert services.parse_run(db, uuid.UUID(made.json()["id"])) == "parsed"

        blocked = client.post(
            f"/api/test-runs/{made.json()['id']}/test-type",
            json={"test_type_key": "dma_sweep"},
            headers=admin_headers,
        )
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "MNX-TESTS-0023"
        # 이름은 그대로여야 한다 — 막았으면 아무것도 안 바뀌어야 한다.
        after = client.get(f"/api/test-runs/{made.json()['id']}", headers=admin_headers).json()
        assert after["record_name"] == made.json()["record_name"]

    def test_새_종류에_없는_조건은_버리고_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma: None,
        tensile: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        """**조용히 버리지 않는다.** 사람이 적은 값이고, 없어진 것을 나중에
        결과에서 알면 그때는 되돌릴 수 없다."""
        del dma, tensile
        made = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "tensile",
                # 인장에만 있는 칸이다 — DMA 로 바꾸면 버려진다.
                "conditions": '{"temperature": 23}',
                "condition_units": '{"temperature": "degC"}',
            },
            files={"file": ("mystery.xyz", b"who knows what this is")},
            headers=admin_headers,
        )
        assert made.status_code == 202, made.text
        assert services.parse_run(db, uuid.UUID(made.json()["id"])) == "failed"

        fixed = client.post(
            f"/api/test-runs/{made.json()['id']}/test-type",
            json={"test_type_key": "dma_sweep"},
            headers=admin_headers,
        )
        assert fixed.status_code == 202, fixed.text
        assert fixed.json()["dropped_conditions"] == ["temperature"]
        assert "조건 1칸" in fixed.json()["message"]

    def test_같은_종류로는_안_바꾼다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
    ) -> None:
        del dma
        run = self._wrong(client, admin_headers, specimen["id"])
        blocked = client.post(
            f"/api/test-runs/{run['id']}/test-type",
            json={"test_type_key": "dma_sweep"},
            headers=admin_headers,
        )
        assert blocked.status_code == 422
        assert blocked.json()["error"]["code"] == "MNX-TESTS-0024"

    def test_옛_종류의_형식_고정을_푼다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma: None,
        tensile: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        """**고정은 옛 종류의 것이다.** 그대로 두면 새 종류로 못 읽는다."""
        del dma, tensile
        run = self._wrong(client, admin_headers, specimen["id"])
        client.post(
            f"/api/test-runs/{run['id']}/reparse",
            json={"profile_key": "ta_dma850"},
            headers=admin_headers,
        )
        client.post(
            f"/api/test-runs/{run['id']}/test-type",
            json={"test_type_key": "tensile"},
            headers=admin_headers,
        )
        detail = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        assert detail["parse_profile_key"] is None


class Test파일이_시험_조건을_채운다:
    """*"시험 종류에서 정해 놓은 칸에 연결해서 넣는 것도 가능한가"* — 실사용에서
    나왔다.

    채널은 표의 **열**이라 값 하나가 못 간다. 갈 곳은 시험 종류가 선언한
    **조건**이다 — 인장은 속도·예하중, DMA 는 기준 온도·지그. 그 자리가 비어
    있었다.
    """

    @pytest.fixture
    def told(self, client: TestClient, admin_headers: dict[str, str], dma: None) -> None:
        del dma
        rule = {
            **DMA_PROFILE,
            # `Geometry name` 은 글자 조건, `Test1` 은 숫자 조건에 넣어 본다.
            "conditions": {
                "Geometry name": {"field": "clamp"},
                "Test1": {"field": "preload", "unit": "kN"},
            },
        }
        made = client.post(
            "/api/formats",
            json={
                "key": "dma_conditions",
                "label": "조건을 채우는 DMA",
                "test_type_key": "dma_sweep",
                "definition": rule,
                "priority": 90,
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text

    def test_선언된_조건을_채운다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        told: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        del told
        run = _upload_dma(client, admin_headers, specimen["id"])
        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"
        detail = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        assert detail["conditions"]["clamp"] == "3 Point Bending Clamp"
        # 1 kN → 1000 N. **파일의 단위로 읽고 SI 로 저장한다.**
        assert detail["conditions"]["preload"] == pytest.approx(1000.0)
        # **무엇으로 입력했는지 남긴다**(ADR 0004). 폼으로 온 조건과 같다.
        saved = db.get(TestRun, uuid.UUID(run["id"]))
        assert saved is not None
        assert saved.input_units["preload"] == "kN"

    def test_사람이_적은_조건을_안_덮는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        told: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        """다시 읽기가 있다. 덮어쓰면 고쳐 놓은 값이 매번 되돌아간다."""
        del told
        response = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "dma_sweep",
                "conditions": json.dumps({"clamp": "내가 적은 지그"}),
            },
            files={"file": ("Example FreqTemp.csv", FREQ_TEMP.read_bytes())},
            headers=admin_headers,
        )
        assert response.status_code == 202, response.text
        run = response.json()
        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"
        detail = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        assert detail["conditions"]["clamp"] == "내가 적은 지그"
        # 비어 있던 칸은 채워진다 — 안 채우면 이 기능이 아무것도 안 하는 것이다.
        assert detail["conditions"]["preload"] == pytest.approx(1000.0)

    def test_조건이_안_맞아도_곡선은_들어온다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        """**채우기는 거들기이지 읽기가 아니다.** 파일의 값이 정의와 안 맞으면
        (모르는 단위·목록에 없는 선택지) 그냥 두면 파싱 실패가 되어 파일은
        멀쩡히 읽혔는데 곡선까지 통째로 잃는다."""
        del dma
        bad = {
            **DMA_PROFILE,
            # 힘 자리에 길이 단위. `normalize_conditions` 가 차원으로 막는다.
            "conditions": {"Test1": {"field": "preload", "unit": "mm"}},
        }
        made = client.post(
            "/api/formats",
            json={
                "key": "dma_bad_unit",
                "label": "차원이 틀린 조건",
                "test_type_key": "dma_sweep",
                "definition": bad,
                "priority": 95,
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text

        run = _upload_dma(client, admin_headers, specimen["id"])
        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"
        detail = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        assert detail["curves"], "곡선을 잃으면 안 된다"
        assert "preload" not in (detail["conditions"] or {})
        assert "시험 조건" in " ".join(detail["warnings"])

    def test_없는_조건을_가리키면_저장을_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], dma: None
    ) -> None:
        """조건은 **시험 종류마다 다르다.** 고정 목록으로는 못 검사한다."""
        del dma
        response = client.post(
            "/api/formats",
            json={
                "key": "dma_no_field",
                "label": "없는 조건",
                "test_type_key": "dma_sweep",
                "definition": {
                    **DMA_PROFILE,
                    # `speed_elastic` 은 인장의 조건이지 DMA 의 것이 아니다.
                    "conditions": {"Test1": {"field": "speed_elastic"}},
                },
            },
            headers=admin_headers,
        )
        assert response.status_code == 422
        message = response.json()["error"]["message"]
        assert "speed_elastic" in message and "clamp" in message


class Test파일이_시험_칸을_채운다:
    """*"시험데이터나 그 상위의 시료·시편·재료 데이터와 매칭시키는 기능은 없어?"*
    — 실사용에서 나왔다.

    답은 갈라진다. **시험 칸은 채우고, 식별자는 짚기만 한다.** 시험자를 잘못
    채우면 고치면 되지만, 곡선이 남의 재료에 붙으면 그 시험은 만들 때 그 시편
    id 에 묶여 있어 칸을 고쳐 되돌릴 수 없다.
    """

    @pytest.fixture
    def told(self, client: TestClient, admin_headers: dict[str, str], dma: None) -> None:
        del dma
        rule = {
            **DMA_PROFILE,
            "record": {
                "Operator": {"field": "operator"},
                "Instrument name": {"field": "instrument"},
            },
        }
        made = client.post(
            "/api/formats",
            json={
                "key": "dma_record",
                "label": "칸을 채우는 DMA",
                "test_type_key": "dma_sweep",
                "definition": rule,
                "priority": 90,  # 기본 프로파일보다 먼저 잡히게
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text

    def test_빈_칸을_채운다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        told: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        del told
        run = _upload_dma(client, admin_headers, specimen["id"])
        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"
        detail = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        assert detail["operator"]
        assert detail["instrument"]

    def test_사람이_적은_값을_파일이_안_덮는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        told: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        """**다시 읽기가 있다.** 덮어쓰면 사람이 고쳐 놓은 장비 이름이 다시
        읽을 때마다 파일 값으로 되돌아간다."""
        del told
        response = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "dma_sweep",
                "conditions": "{}",
                "operator": "내가 적은 사람",
            },
            files={"file": ("Example FreqTemp.csv", FREQ_TEMP.read_bytes())},
            headers=admin_headers,
        )
        assert response.status_code == 202, response.text
        run = response.json()
        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"
        detail = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        assert detail["operator"] == "내가 적은 사람"
        # 비어 있던 칸은 채워진다 — 안 채우면 이 기능이 아무것도 안 하는 것이다.
        assert detail["instrument"]

    def test_선언이_없으면_아무것도_안_채운다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        dma: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        """**하위 호환.** 기존 프로파일에 이 자리가 없으면 전과 똑같아야 한다."""
        del dma
        run = _upload_dma(client, admin_headers, specimen["id"])
        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"
        detail = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        assert not detail["operator"]
        assert not detail["instrument"]

    def test_기준정보가_막혀도_곡선은_들어온다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        told: None,
        specimen: dict[str, Any],
        db: Session,
    ) -> None:
        """채우기는 **거들기이지 읽기가 아니다.**

        장비 축을 닫아 두면 `resolve_or_create` 가 `AppError` 를 낸다. 그것을
        그냥 두면 파싱 실패가 되어 **파일은 멀쩡히 읽혔는데 곡선까지 통째로
        잃는다.** 그 값을 못 넣었다는 말만 남기고 넘어가야 한다.
        """
        del told
        # 장비 축을 닫는다. 화면에서 여는 길은 없고 기준정보 설계가 정한다.
        axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == "instrument"))
        assert axis is not None
        axis.entry_policy = "closed"
        db.commit()

        run = _upload_dma(client, admin_headers, specimen["id"])
        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"

        detail = client.get(f"/api/test-runs/{run['id']}", headers=admin_headers).json()
        assert detail["curves"], "곡선을 잃으면 안 된다"
        assert not detail["instrument"]
        # 무슨 일이 있었는지 남긴다 — 조용히 비면 사람이 원인을 못 찾는다.
        # `_warnings` 는 상세 응답에서 `warnings` 로 갈라 나온다.
        assert "장비" in " ".join(detail["warnings"])
