"""시편 치수 API — **칸 목록은 규격이 정한다.**

화면에 두께·폭·게이지 세 칸을 박아 두면 환봉을 영영 못 담는다. 실제로 그랬다 —
`specimens` 에 직경 컬럼이 없어서, 봉재 시편은 직경을 적을 자리가 없었다.

그래서 화면이 아니라 **규격이 칸을 낸다**(ADR 0010). 이 파일이 지키는 것:

    잰 값이 이긴다        규격 공칭이 실측을 조용히 덮으면 안 된다
    공칭을 복사 안 한다   복사하면 규격을 고쳐도 시편은 옛 값을 든다
    0 을 안 받는다        '쟀는데 0' 과 '안 쟀다' 는 다르다
    못 낸 이유를 낸다     빈 칸만 보여 주면 어디를 채울지 모른다
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.vocabulary.definitions import (
    ensure_builtin_axis_fields,
    ensure_builtin_specimen_categories,
    ensure_builtin_vocabularies,
)

MM = 0.001

ROUND_FIELD = {
    "key": "diameter",
    "label": "직경",
    "dimension": "length",
    "si_unit": "m",
    "is_required": False,
    "help": None,
}

#: 인장 분류의 필수 기본 칸. **안 채우면 규격을 저장할 수 없다** — 그게 맞다.
BASE = {"gauge_length": 0.05}


@pytest.fixture
def seeded(db: Session) -> None:
    ensure_builtin_vocabularies(db)
    ensure_builtin_axis_fields(db)
    ensure_builtin_specimen_categories(db)
    ensure_builtin_test_types(db)
    db.commit()


def make_standard(
    client: TestClient,
    headers: dict[str, str],
    value: str,
    *,
    attributes: dict[str, float] | None = None,
    extra_fields: list[dict[str, Any]] | None = None,
    cross_section: str | None = None,
    ratio_checks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """규격 하나. 칸을 먼저 만들고 값을 넣는다 — 서버가 스키마 밖을 거절한다."""
    created = client.post(
        "/api/vocabularies/specimen_standard/terms",
        json={"value": value, "parent_value": "인장"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    term: dict[str, Any] = created.json()

    body: dict[str, Any] = {}
    if extra_fields is not None:
        body["extra_fields"] = extra_fields
    if attributes is not None:
        body["attributes"] = {**BASE, **attributes}
    if cross_section is not None:
        body["cross_section"] = cross_section
    if ratio_checks is not None:
        body["ratio_checks"] = ratio_checks
    if body:
        updated = client.patch(
            f"/api/vocabularies/specimen_standard/terms/{term['id']}",
            json=body,
            headers=headers,
        )
        assert updated.status_code == 200, updated.text
        term = updated.json()
    return term


def make_specimen(
    client: TestClient, headers: dict[str, str], *, standard: str | None = None
) -> dict[str, Any]:
    material = client.post(
        "/api/materials",
        json={"family": "Metal", "category": "Steel", "grade": "SECC", "spec_thickness": 1.0},
        headers=headers,
    )
    assert material.status_code == 201, material.text
    sample = client.post(
        f"/api/materials/{material.json()['id']}/samples", json={}, headers=headers
    )
    assert sample.status_code == 201, sample.text
    body: dict[str, Any] = {"orientation": "MD"}
    if standard is not None:
        body["standard"] = standard
    created = client.post(
        f"/api/samples/{sample.json()['id']}/specimens", json=body, headers=headers
    )
    assert created.status_code == 201, created.text
    specimen: dict[str, Any] = created.json()
    return specimen


def dimensions_of(client: TestClient, headers: dict[str, str], specimen_id: str) -> Any:
    found = client.get(f"/api/specimens/{specimen_id}/dimensions", headers=headers)
    assert found.status_code == 200, found.text
    return found.json()


def field_named(payload: Any, key: str) -> Any:
    return next((item for item in payload["fields"] if item["key"] == key), None)


class TestFields:
    def test_규격이_칸을_정한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**이 파일의 이유.** 환봉 규격이면 직경 칸이 나온다."""
        make_standard(
            client, admin_headers, "ASTM E8 R1", extra_fields=[ROUND_FIELD], attributes={}
        )
        specimen = make_specimen(client, admin_headers, standard="ASTM E8 R1")

        payload = dimensions_of(client, admin_headers, specimen["id"])
        assert field_named(payload, "diameter") is not None
        assert payload["standard"] == "ASTM E8 R1"

    def test_분류가_준_칸을_표시한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """지우려면 어디로 가야 하는지가 다르다 — 분류 것은 여기서 못 지운다."""
        make_standard(client, admin_headers, "ASTM E8", attributes={})
        specimen = make_specimen(client, admin_headers, standard="ASTM E8")

        payload = dimensions_of(client, admin_headers, specimen["id"])
        gauge = field_named(payload, "gauge_length")
        assert gauge is not None and gauge["inherited"] is True

    def test_규격이_없으면_칸도_없다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        specimen = make_specimen(client, admin_headers)
        assert dimensions_of(client, admin_headers, specimen["id"])["fields"] == []


class TestValues:
    def test_공칭은_따로_낸다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**합쳐서 하나로 내면 사람은 전부 실측으로 읽는다.**"""
        make_standard(client, admin_headers, "ASTM E8", attributes={"gauge_length": 0.05})
        specimen = make_specimen(client, admin_headers, standard="ASTM E8")

        gauge = field_named(
            dimensions_of(client, admin_headers, specimen["id"]), "gauge_length"
        )
        assert gauge["nominal"] == pytest.approx(0.05)
        assert gauge["measured"] is None
        assert gauge["source"] == "nominal"

    def test_잰_값이_이긴다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        make_standard(client, admin_headers, "ASTM E8", attributes={"gauge_length": 0.05})
        specimen = make_specimen(client, admin_headers, standard="ASTM E8")

        saved = client.put(
            f"/api/specimens/{specimen['id']}/dimensions",
            json={"dimensions": {"gauge_length": 0.0498}},
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text
        gauge = field_named(saved.json(), "gauge_length")
        assert gauge["measured"] == pytest.approx(0.0498)
        assert gauge["nominal"] == pytest.approx(0.05)  # 규격은 안 덮인다
        assert gauge["source"] == "measured"

    def test_비우면_다시_공칭으로_돌아간다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**실측을 지울 길이 있어야 한다.** 잘못 잰 값이 영영 남으면 안 된다."""
        make_standard(client, admin_headers, "ASTM E8", attributes={"gauge_length": 0.05})
        specimen = make_specimen(client, admin_headers, standard="ASTM E8")
        client.put(
            f"/api/specimens/{specimen['id']}/dimensions",
            json={"dimensions": {"gauge_length": 0.0498}},
            headers=admin_headers,
        )

        cleared = client.put(
            f"/api/specimens/{specimen['id']}/dimensions",
            json={"dimensions": {}},
            headers=admin_headers,
        )
        assert cleared.status_code == 200, cleared.text
        gauge = field_named(cleared.json(), "gauge_length")
        assert gauge["measured"] is None
        assert gauge["source"] == "nominal"

    def test_0_은_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """0 으로 나눈 응력은 무한대다. '안 쟀다' 는 칸을 비우는 것으로 말한다."""
        make_standard(client, admin_headers, "ASTM E8", attributes={})
        specimen = make_specimen(client, admin_headers, standard="ASTM E8")

        refused = client.put(
            f"/api/specimens/{specimen['id']}/dimensions",
            json={"dimensions": {"width": 0.0}},
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "MNX-MATERIALS-0016"

    def test_옛_컬럼도_함께_적는다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """아직 `thickness_m` 을 읽는 코드가 있다(ADR 0010 Expand)."""
        make_standard(client, admin_headers, "ASTM E8", attributes={})
        specimen = make_specimen(client, admin_headers, standard="ASTM E8")
        client.put(
            f"/api/specimens/{specimen['id']}/dimensions",
            json={"dimensions": {"thickness": 0.00098, "width": 0.0125}},
            headers=admin_headers,
        )

        read = client.get(f"/api/specimens/{specimen['id']}", headers=admin_headers)
        assert read.status_code == 200, read.text
        assert read.json()["thickness"] == pytest.approx(0.98)  # mm 로 나온다
        assert read.json()["width"] == pytest.approx(12.5)

    def test_규격에서_사라진_칸도_보인다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**숨기면 안 지워지는 값이 된다.** 규격을 바꿔도 옛 실측은 남는다."""
        standard = make_standard(
            client, admin_headers, "ASTM E8 R1", extra_fields=[ROUND_FIELD], attributes={}
        )
        specimen = make_specimen(client, admin_headers, standard="ASTM E8 R1")
        client.put(
            f"/api/specimens/{specimen['id']}/dimensions",
            json={"dimensions": {"diameter": 0.0125}},
            headers=admin_headers,
        )

        dropped = client.patch(
            f"/api/vocabularies/specimen_standard/terms/{standard['id']}",
            json={"extra_fields": []},
            headers=admin_headers,
        )
        assert dropped.status_code == 200, dropped.text

        payload = dimensions_of(client, admin_headers, specimen["id"])
        left = field_named(payload, "diameter")
        assert left is not None and left["measured"] == pytest.approx(0.0125)


class TestArea:
    def test_환봉은_원_식으로_낸다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """12.5 mm 환봉 = 122.7 mm². 평판 식으로는 나올 수 없는 값이다."""
        make_standard(
            client,
            admin_headers,
            "ASTM E8 R1",
            extra_fields=[ROUND_FIELD],
            attributes={"diameter": 0.0125},
            cross_section="circle",
        )
        specimen = make_specimen(client, admin_headers, standard="ASTM E8 R1")

        payload = dimensions_of(client, admin_headers, specimen["id"])
        assert payload["area"] == pytest.approx(math.pi * 0.00625**2, rel=1e-12)
        assert payload["cross_section_label"]
        assert payload["area_problem"] is None

    def test_못_내면_이유를_낸다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**빈 칸만 보여 주면 어디를 채워야 하는지 모른다.**"""
        make_standard(client, admin_headers, "ASTM E8", attributes={})
        specimen = make_specimen(client, admin_headers, standard="ASTM E8")

        payload = dimensions_of(client, admin_headers, specimen["id"])
        assert payload["area"] is None
        assert payload["area_problem"]


class TestOnlyNumbers:
    def test_판과_모드는_시편_치수가_아니다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**그 규격의 성질이지 이 시편을 잰 값이 아니다.** 시편 화면에 입력
        칸으로 나오면 사람은 거기에 무엇을 적어야 하는지 알 수 없다."""
        make_standard(client, admin_headers, "ASTM E8", attributes={})
        specimen = make_specimen(client, admin_headers, standard="ASTM E8")

        payload = dimensions_of(client, admin_headers, specimen["id"])
        assert field_named(payload, "edition") is None
        assert field_named(payload, "gauge_length") is not None


class TestRatioWarnings:
    """**어긴 채로 쟀다는 것이 보여야 한다. 다만 막지는 않는다.**

    규격이 권장값을 주는데 장비가 못 맞추는 일이 실제로 있다 — ISO 6721-4 는
    클램프 간 50~100 mm 를 권하지만 Netzsch 15 · Mettler 20 · TA 30 이 한계라
    어느 장비도 만족하지 못한다. 막으면 실제로 잰 데이터를 못 넣고, 그러면
    사람은 시스템 밖에서 일한다.
    """

    def _standard(self, client: TestClient, headers: dict[str, str]) -> None:
        make_standard(
            client,
            headers,
            "ISO 6721-3",
            extra_fields=[
                {"key": "thickness", "label": "두께"},
            ],
            attributes={},
            # L/h >= 50 — 저장탄성률 ±5 % 정확도가 여기 달려 있다.
            ratio_checks=[
                {
                    "numerator": "gauge_length",
                    "denominator": "thickness",
                    "minimum": 50,
                    "help": "저장탄성률 ±5 % 정확도 확보",
                }
            ],
        )

    def test_어기면_말하되_저장은_시킨다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        self._standard(client, admin_headers)
        specimen = make_specimen(client, admin_headers, standard="ISO 6721-3")
        saved = client.put(
            f"/api/specimens/{specimen['id']}/dimensions",
            # 게이지 50 mm · 두께 5 mm → 10 배. 50 을 한참 밑돈다.
            json={"dimensions": {"gauge_length": 0.05, "thickness": 0.005}},
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text

        (warning,) = saved.json()["warnings"]
        assert warning["actual"] == pytest.approx(10)
        # **키를 그대로 띄우면 못 읽는다.**
        assert "게이지 길이" in warning["condition"] and "두께" in warning["condition"]
        assert warning["help"] == "저장탄성률 ±5 % 정확도 확보"

    def test_지키면_조용하다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        self._standard(client, admin_headers)
        specimen = make_specimen(client, admin_headers, standard="ISO 6721-3")
        saved = client.put(
            f"/api/specimens/{specimen['id']}/dimensions",
            json={"dimensions": {"gauge_length": 0.05, "thickness": 0.0005}},
            headers=admin_headers,
        )
        assert saved.json()["warnings"] == []

    def test_안_잰_칸이_있으면_판정하지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        """**못 잰 것과 어긴 것은 다르다.** 0 으로 치면 경고가 소음이 된다."""
        self._standard(client, admin_headers)
        specimen = make_specimen(client, admin_headers, standard="ISO 6721-3")
        assert dimensions_of(client, admin_headers, specimen["id"])["warnings"] == []


class TestBriefSizes:
    """접힌 줄이 치수를 말한다 — **이름과 출처를 함께.**

    전에는 두께·폭·게이지 세 값을 이름 없이 늘어놓았다. 칸이 규격마다 다른
    지금은 자리로 외울 수가 없다 — 환봉 규격의 첫 값은 직경이고 평판 규격의
    첫 값은 폭이다. 그리고 규격의 공칭과 잰 값을 합쳐서 보여 주면 전부
    실측으로 읽힌다.
    """

    def test_목록이_치수를_이름과_함께_낸다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        make_standard(
            client,
            admin_headers,
            "ASTM E8 R1",
            extra_fields=[ROUND_FIELD],
            attributes={"diameter": 0.0125},
        )
        specimen = make_specimen(client, admin_headers, standard="ASTM E8 R1")
        client.put(
            f"/api/specimens/{specimen['id']}/dimensions",
            json={"dimensions": {"diameter": 0.01248}},
            headers=admin_headers,
        )

        listed = client.get(
            f"/api/samples/{specimen['sample_id']}/specimens", headers=admin_headers
        )
        assert listed.status_code == 200, listed.text
        sizes = {item["key"]: item for item in listed.json()[0]["sizes"]}

        # 잰 값이 이긴다.
        assert sizes["diameter"]["value"] == pytest.approx(0.01248)
        assert sizes["diameter"]["source"] == "measured"
        assert sizes["diameter"]["label"] == "직경"
        # 규격이 준 것은 그 사실이 함께 온다 — 화면이 흐리게 그린다.
        assert sizes["gauge_length"]["source"] == "nominal"

    def test_규격이_없으면_적을_것도_없다(
        self, client: TestClient, admin_headers: dict[str, str], seeded: None
    ) -> None:
        specimen = make_specimen(client, admin_headers)
        listed = client.get(
            f"/api/samples/{specimen['sample_id']}/specimens", headers=admin_headers
        )
        assert listed.json()[0]["sizes"] == []
