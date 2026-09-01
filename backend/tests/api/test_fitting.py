"""적합과 물성 카드 — **근거를 들고 있는가, 함부로 확정되지 않는가.**

계산 자체는 `tests/unit/test_fitting.py` 가 답을 아는 곡선으로 검산한다. 여기서
보는 것은 API 의 태도다.

1. **카드가 자기 근거를 들고 있다.** 어느 시험 몇 건에서 나왔는지, 적합 구간이
   어디까지인지, 그 식이 데이터와 얼마나 맞는지 — 카드 안에 있어야 한다.
   나중에 "이 값 어디서 나왔어?" 에 답할 수 없으면 그 숫자는 근거가 없다.
2. **확정은 부서 관리자만**(D12). 만드는 것은 누구나 할 수 있다 — 초안은 아직
   아무 해석에도 안 들어간다.
3. **확정된 카드는 지워지지 않는다.** 그 값으로 해석이 돌았을 수 있다.
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.fitting.routes import NO_TEST
from app.modules.tests import services
from app.modules.tests.definitions import ensure_builtin_test_types

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

#: 진응력·진소성변형률까지 내는 레시피. **경화식은 공칭이 아니라 진값에 맞춘다** —
#: 솔버가 받는 것이 이쪽이고, 공칭으로 맞춘 파라미터를 넣으면 조용히 틀린 해석이 된다.
STEPS: list[dict[str, Any]] = [
    {"plugin": "tensile.engineering", "options": {"gauge_length": 0.05, "area": 12.12e-6}},
    {
        "plugin": "curve.sort_unique",
        "options": {"x": "strain_engineering", "duplicate_policy": "mean"},
    },
    {"plugin": "tensile.strength", "options": {}},
    {
        # **직접 입력이다.** `Example.tra` 는 18점짜리 발췌본이라 탄성 창에 점이
        # 한둘밖에 안 들어간다 — 회귀로는 값이 안 나온다(그래서 안 내도록 막았다,
        # `MIN_TRUSTWORTHY_POINTS`). 이 파일의 시험들은 **카드·덱을 보는 것**이지
        # 탄성계수 적합을 보는 것이 아니므로, 아는 값을 넣고 그 뒤를 시험한다.
        #
        # (전에는 `lower`·`upper` 를 줬는데 그런 이름의 칸이 없어 조용히 무시되고
        # 기본 창이 쓰였다. 그러고도 값이 나왔던 것이 지금 막은 그 문제다.)
        "plugin": "tensile.elastic_modulus",
        "options": {"method": "manual", "manual_modulus": 200e9},
    },
    {"plugin": "tensile.true_plastic", "options": {"youngs_modulus": "@youngs_modulus"}},
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
            "grade": "FIT",
            "details": "MDOI",
            "spec_thickness": 1.0,
        },
        headers=admin_headers,
    ).json()
    return created


def _adopted(
    client: TestClient, headers: dict[str, str], db: Session, material_id: str, count: int
) -> None:
    for _ in range(count):
        sample = client.post(
            f"/api/materials/{material_id}/samples", json={}, headers=headers
        ).json()
        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD"},
            headers=headers,
        ).json()
        run = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
            files={"file": ("Example.tra", TRA.read_bytes())},
            headers=headers,
        ).json()
        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"
        stored = client.post(
            "/api/processing/results",
            json={"test_run_id": run["id"], "steps": STEPS},
            headers=headers,
        )
        assert stored.status_code == 201, stored.text
        client.post(f"/api/processing/results/{stored.json()['id']}/adopt", headers=headers)


@pytest.fixture
def ready(
    client: TestClient, admin_headers: dict[str, str], db: Session, material: dict[str, Any]
) -> dict[str, Any]:
    _adopted(client, admin_headers, db, material["id"], 3)
    return material


def values(card: dict[str, Any], block: str) -> dict[str, Any]:
    """카드에서 블록의 값 묶음을 꺼낸다.

    **화면도 이렇게 읽는다.** 카드가 `elastic`·`hardening` 을 컬럼으로 들고
    있던 때에는 응답에서 바로 꺼냈는데, 물성의 갈래가 데이터가 되면서 한 겹
    들어갔다 — 그 대신 새 물성이 마이그레이션 없이 붙는다.
    """
    return dict(card["blocks"][block]["values"])


def rows(card: dict[str, Any], block: str) -> list[dict[str, Any]]:
    """블록의 표. 경화식 파라미터와 소성 표가 여기 있다."""
    return list(card["blocks"][block]["rows"])


class Test경화식목록:
    def test_화면이_이_응답만으로_목록을_그린다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        body = client.get("/api/fitting/families", headers=admin_headers).json()
        keys = {item["key"] for item in body}
        assert {"voce", "swift", "hockett_sherby"} <= keys
        for item in body:
            # 파라미터 이름과 단위를 함께 준다 — 프론트가 손으로 적으면 어긋난다.
            assert len(item["parameter_names"]) == len(item["parameter_units"])
            assert item["describe"]


class Test미리보기:
    def test_여러_식을_나란히_주고_고르지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**어느 것이 맞는지 서버가 정하지 않는다.**

        상대 RMSE 순으로 정렬만 한다 — Swift 와 Voce 는 적합 구간에서 비슷해도
        그 밖에서 갈리고, 어디까지 쓸 것인지는 해석하는 사람이 안다.
        """
        response = client.post(
            "/api/fitting/preview",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["sample_count"] == 3
        assert len(body["fits"]) >= 2
        errors = [item["relative_rmse"] for item in body["fits"]]
        assert errors == sorted(errors)

    def test_적합_구간을_결과에_박아_둔다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        # **이 밖은 외삽이고 식마다 전혀 다른 값이 나온다.**
        fit = client.post(
            "/api/fitting/preview",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "families": ["voce"],
            },
            headers=admin_headers,
        ).json()["fits"][0]
        assert fit["strain_min"] < fit["strain_max"]
        assert any("적합 구간 밖에서 검증되지 않았습니다" in note for note in fit["notes"])
        assert len(fit["curve"]) > 1

    def test_채택이_하나도_없으면_무엇을_하면_되는지_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        # 시험은 있는데 채택만 안 한 상태 — 사용자가 가장 자주 서는 자리다.
        # (묶음 자체가 없으면 404 다. 그건 다른 이야기다.)
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        ).json()
        specimen = client.post(
            f"/api/samples/{sample['id']}/specimens",
            json={"orientation": "MD"},
            headers=admin_headers,
        ).json()
        run = client.post(
            "/api/test-runs",
            data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
            files={"file": ("Example.tra", TRA.read_bytes())},
            headers=admin_headers,
        ).json()
        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"

        response = client.post(
            "/api/fitting/preview",
            json={
                "material_id": material["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text
        assert "채택" in response.json()["error"]["message"]

    def test_1건이면_적합하되_그_사실을_근거에_남긴다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        material: dict[str, Any],
    ) -> None:
        """**막지 않는다. 대신 말한다.**

        한 번 재고 해석부터 돌려 보는 것은 정상 작업이다. 막으면 사람은 시스템
        밖에서 계산해 카드 없이 덱을 만들고, 그러면 근거가 아무 데도 안 남는다 —
        막아서 얻는 것보다 잃는 것이 크다.
        """
        _adopted(client, admin_headers, db, material["id"], 1)
        body = client.post(
            "/api/fitting/preview",
            json={
                "material_id": material["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
            },
            headers=admin_headers,
        ).json()

        assert body["sample_count"] == 1
        assert body["fits"], "1건이어도 적합은 된다"
        assert any("시편 1개" in note for note in body["notes"])


class Test물성카드:
    def test_초안_카드는_이름을_고칠_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**불변이 오타까지 지키고 있었다.**

        값을 못 바꾸는 것은 맞다. 그런데 이름을 고칠 길도 없어서 오타 하나에
        카드를 지우고 적합을 다시 돌려야 했다 — 불변이 지키려던 것과 무관하다.
        """
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "오타난이름",
            },
            headers=admin_headers,
        ).json()

        fixed = client.patch(
            f"/api/fitting/cards/{card['id']}",
            json={"label": "인장 MD (상온)", "note": "메모"},
            headers=admin_headers,
        )
        assert fixed.status_code == 200, fixed.text
        assert fixed.json()["label"] == "인장 MD (상온)"
        # **값은 그대로다.** 여기가 흔들리면 카드를 믿을 근거가 사라진다.
        assert values(fixed.json(), "elastic") == values(card, "elastic")
        assert fixed.json()["point_count"] == card["point_count"]

    def test_확정된_카드는_이름도_못_바꾼다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """그 이름으로 덱이 이미 나갔을 수 있다."""
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "확정할 카드",
            },
            headers=admin_headers,
        ).json()
        client.post(f"/api/fitting/cards/{card['id']}/publish", headers=admin_headers)

        denied = client.patch(
            f"/api/fitting/cards/{card['id']}",
            json={"label": "바꾸기"},
            headers=admin_headers,
        )
        assert denied.status_code == 409, denied.text

    def test_식을_안_골라도_표로_카드가_된다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**많은 솔버가 식보다 표를 그대로 받는다.**

        게다가 덱의 소성 블록에 들어가는 것은 어느 쪽을 고르든 표다 — 식은
        파라미터와 적합도로 카드에 남고 덱에는 참고 주석으로 들어간다. 식이 안
        맞는 재료(항복 근처가 꺾이는 것, 이중 항복)에서는 억지로 맞춘 식보다
        표가 정확하다.
        """
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "표만",
                "poisson_ratio": 0.3,
            },
            headers=admin_headers,
        )
        assert card.status_code == 201, card.text
        body = card.json()
        assert not body["blocks"].get("hardening"), "식을 안 골랐으면 비어 있어야 한다"
        assert body["point_count"] > 1, "표는 언제나 저장한다"

        deck = client.get(
            f"/api/fitting/cards/{body['id']}/export?format=abaqus", headers=admin_headers
        )
        assert deck.status_code == 200, deck.text
        text = deck.content.decode("utf-8")
        assert "*PLASTIC" in text
        assert "경화식" not in text, "안 고른 식을 덱에 적지 않는다"

    def test_카드가_자기_근거를_들고_있다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**"이 값 어디서 나왔어?" 에 카드 혼자 답할 수 있어야 한다.**

        통계가 지워지거나 시험이 늘어도 카드 안의 근거는 그대로다.
        """
        response = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "FIT MD 인장",
                "family": "voce",
            },
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        card = response.json()

        assert card["status"] == "draft"
        assert card["source"]["sample_count"] == 3
        assert len(card["source"]["test_run_ids"]) == 3
        # **적합도를 함께 저장한다.** 파라미터만 남기면 그 값이 데이터와 얼마나
        # 맞는지 다시 알 수 없다.
        assert values(card, "hardening")["family"] == "voce"
        assert "relative_rmse" in values(card, "hardening")
        assert values(card, "hardening")["strain_max"] > 0
        for item in rows(card, "hardening"):
            # 경계와 초기값이 없으면 같은 데이터로 다시 돌려도 재현이 안 된다.
            assert item["lower"] <= item["value"] <= item["upper"]

    def test_표는_식을_안_골라도_저장한다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """많은 솔버가 식보다 표를 그대로 받는다. 식이 안 맞는 재료도 있다."""
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "표만",
            },
            headers=admin_headers,
        ).json()
        assert "hardening" not in card["blocks"]
        assert card["point_count"] == len(rows(card, "table")) > 0
        assert {"plastic_strain", "true_stress"} == set(rows(card, "table")[0])

    def test_없는_값은_넣지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**푸아송비는 인장시험이 주지 않는다.**

        0.3 으로 채우면 그것이 측정값인지 기본값인지 나중에 알 수 없다.
        """
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "탄성만",
            },
            headers=admin_headers,
        ).json()
        assert "poisson_ratio" not in values(card, "elastic")
        # 탄성계수는 시험이 준다 — 통계 평균이 들어간다.
        assert values(card, "elastic")["youngs_modulus"] > 0

    def test_넣은_값은_그대로_들어간다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "손으로 넣은 값",
                "poisson_ratio": 0.29,
                "density": 7850.0,
            },
            headers=admin_headers,
        ).json()
        assert values(card, "elastic")["poisson_ratio"] == pytest.approx(0.29)
        assert values(card, "elastic")["density"] == pytest.approx(7850.0)


class Test묶음_내보내기:
    """**해석 하나에 재료가 여럿 들어간다.**

    한 장씩 내려받아 사람이 폴더에 모으면 그 묶음이 무엇이었는지가 아무 데도 안
    남는다. 해석자가 물을 것은 하나다 — 「내가 받은 이 덱이 그때 그 카드가 맞나」.
    묶음은 그 물음에 답하려고 있다(ADR 0024 ②).
    """

    @pytest.fixture
    def two_cards(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> list[dict[str, Any]]:
        made = []
        for label in ("가", "나"):
            made.append(
                client.post(
                    "/api/fitting/cards",
                    json={
                        "material_id": ready["id"],
                        "test_type_key": "tensile",
                        "orientation": "MD",
                        "label": f"묶음 시험 {label}",
                        "family": "voce",
                        "poisson_ratio": 0.3,
                        "density": 7850.0,
                    },
                    headers=admin_headers,
                ).json()
            )
        return made

    def _open(self, response: Any) -> zipfile.ZipFile:
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/zip"
        return zipfile.ZipFile(io.BytesIO(response.content))

    def _bundle(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        cards: list[dict[str, Any]],
        **extra: Any,
    ) -> Any:
        return client.post(
            "/api/fitting/cards/bundle",
            json={"card_ids": [one["id"] for one in cards], "format": "abaqus", **extra},
            headers=admin_headers,
        )

    def test_덱과_manifest_와_체크섬이_함께_온다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        two_cards: list[dict[str, Any]],
    ) -> None:
        archive = self._open(self._bundle(client, admin_headers, two_cards))
        names = set(archive.namelist())
        assert {"manifest.json", "SHA256SUMS"} <= names
        assert len([one for one in names if one.startswith("decks/")]) == 2

    def test_체크섬이_실제_덱과_맞는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        two_cards: list[dict[str, Any]],
    ) -> None:
        """**받은 쪽이 검산할 수 있어야 한다.** 안 맞으면 그 숫자는 장식이다."""
        archive = self._open(self._bundle(client, admin_headers, two_cards))
        manifest = json.loads(archive.read("manifest.json"))
        for entry in manifest["cards"]:
            digest = hashlib.sha256(archive.read(entry["file"])).hexdigest()
            assert digest == entry["sha256"], entry["file"]

        # `SHA256SUMS` 도 같은 값을 적는다 — 표준 도구로 검산하는 사람이 있다.
        sums = archive.read("SHA256SUMS").decode("utf-8")
        for entry in manifest["cards"]:
            assert f"{entry['sha256']}  {entry['file']}" in sums

    def test_무엇을_어떻게_뽑았는지_적힌다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        two_cards: list[dict[str, Any]],
    ) -> None:
        """형식·단위계·사람·시각이 없으면 「그때 그 덱」 을 되짚을 수 없다."""
        archive = self._open(
            self._bundle(client, admin_headers, two_cards, units="mm_n_tonne")
        )
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format"] == "abaqus"
        assert manifest["units"] == "mm_n_tonne"
        assert manifest["exported_by"]
        assert manifest["exported_at"]
        assert manifest["app_version"]
        assert len(manifest["cards"]) == 2

    def test_초안이_섞이면_말한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        two_cards: list[dict[str, Any]],
    ) -> None:
        """**초안도 담는다** — 돌려 보는 것이 검토의 실체다(낱장과 같은 판단).
        다만 압축을 풀기 전에도 알아야 한다."""
        response = self._bundle(client, admin_headers, two_cards)
        archive = self._open(response)
        manifest = json.loads(archive.read("manifest.json"))
        assert any("초안" in one for one in manifest["warnings"])
        assert response.headers["x-matnexus-warnings"] == "1"

    def test_덱_바이트가_매번_같다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        two_cards: list[dict[str, Any]],
    ) -> None:
        """**체크섬이 뜻을 가지려면 덱이 결정적이어야 한다.**

        압축 파일 자체는 다르다 — manifest 에 시각과 사람이 들어간다. 검산에 쓰는
        것은 덱의 해시지 압축 파일의 해시가 아니다.
        """
        first = self._open(self._bundle(client, admin_headers, two_cards))
        second = self._open(self._bundle(client, admin_headers, two_cards))
        decks = sorted(one for one in first.namelist() if one.startswith("decks/"))
        assert decks == sorted(one for one in second.namelist() if one.startswith("decks/"))
        for name in decks:
            assert first.read(name) == second.read(name)

    def test_고른_순서와_무관하게_같은_차례로_담는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        two_cards: list[dict[str, Any]],
    ) -> None:
        """화면에서 고른 순서가 파일 차례를 바꾸면 diff 가 매번 통째로 바뀐다."""
        forward = self._open(self._bundle(client, admin_headers, two_cards))
        backward = self._open(self._bundle(client, admin_headers, list(reversed(two_cards))))
        assert forward.namelist() == backward.namelist()

        # **이름만 보면 못 잡는다.** 같은 재료의 카드는 덱 이름이 겹쳐 뒤엣것에
        # 번호가 붙는데(`_2`), 차례가 뒤집히면 **어느 카드가 그 번호를 받았는지**가
        # 바뀐다 — 파일 목록은 그대로다. manifest 의 차례로 본다.
        def order(archive: zipfile.ZipFile) -> list[str]:
            return [
                one["card_id"] for one in json.loads(archive.read("manifest.json"))["cards"]
            ]

        assert order(forward) == order(backward)

    def test_모르는_형식은_있는_것을_알려_준다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        two_cards: list[dict[str, Any]],
    ) -> None:
        response = self._bundle(client, admin_headers, two_cards, format="없는형식")
        assert response.status_code == 422, response.text
        assert "있는 것" in response.json()["error"]["message"]

    def test_카드를_안_주면_막는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """빈 묶음은 빈 zip 이 아니라 실수다."""
        response = client.post(
            "/api/fitting/cards/bundle",
            json={"card_ids": [], "format": "abaqus"},
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text


class Test내보내기:
    """**여기서 나온 텍스트가 그대로 솔버 덱에 들어간다.**

    형식 자체는 `tests/unit/test_export.py` 가 칸과 순서까지 본다. 여기서는 카드에
    담긴 값이 제 자리로 가는지, 근거가 파일 안에 들어가는지를 본다.
    """

    @pytest.fixture
    def card(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> dict[str, Any]:
        created: dict[str, Any] = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "내보내기 시험",
                "family": "voce",
                "poisson_ratio": 0.3,
                "density": 7850.0,
            },
            headers=admin_headers,
        ).json()
        return created

    def test_형식_목록이_필요한_값을_함께_준다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**내려받기를 누른 뒤에 "푸아송비가 없습니다" 를 보는 것은 늦다.**"""
        body = client.get("/api/fitting/formats", headers=admin_headers).json()
        by_key = {item["key"]: item for item in body}
        assert {"abaqus", "openradioss", "json"} <= set(by_key)
        assert "밀도" in by_key["openradioss"]["requires"]
        # Abaqus 의 *DENSITY 는 선택 키워드다 — 없어도 내보낼 수 있다.
        assert "밀도" not in by_key["abaqus"]["requires"]

    def test_abaqus_덱이_나온다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        response = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=abaqus", headers=admin_headers
        )
        assert response.status_code == 200, response.text
        assert "attachment" in response.headers["content-disposition"]
        text = response.text
        assert "*MATERIAL, NAME=" in text
        assert "*ELASTIC, TYPE=ISOTROPIC" in text
        assert "*PLASTIC" in text
        # **근거가 파일 안에 있다.** 덱만 받은 사람이 되짚을 수 있어야 한다.
        assert "시편 3개" in text
        assert "적합 구간" in text

    def test_단위계를_고를_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        """판재 CAE 는 관행이 mm·N·tonne 이다. SI 덱만 내면 해석자가 매번 손으로
        환산하게 되는데, **그 손이 바로 사고의 자리**다."""
        si = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=abaqus&units=si",
            headers=admin_headers,
        )
        mm = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=abaqus&units=mm_n_tonne",
            headers=admin_headers,
        )
        assert si.status_code == 200 and mm.status_code == 200, mm.text
        assert "kg, m, s, Pa" in si.text
        assert "tonne, mm, s, MPa" in mm.text
        assert si.text != mm.text, "값이 안 바뀌었습니다"
        # **파일 이름에 계가 들어간다.** 두 계가 한 폴더에 섞이면 어느 쪽이
        # 어느 계인지 파일을 열어야 알게 된다.
        assert "_si." in si.headers["content-disposition"]
        assert "_mm_n_tonne." in mm.headers["content-disposition"]

    def test_안_고르면_SI_다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        """**전과 같은 것이 나가야 한다.** 기본이 바뀌면 어제 받은 덱과 오늘
        받은 덱이 다른 계인데 이름도 같다."""
        plain = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=abaqus", headers=admin_headers
        )
        told = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=abaqus&units=si",
            headers=admin_headers,
        )
        assert plain.text == told.text

    def test_모르는_단위계는_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        """조용히 SI 로 떨어지면 안 된다 — 사람은 자기가 고른 계로 받았다고
        믿고, 그 믿음은 덱을 열어도 안 깨진다(숫자가 그럴듯하다)."""
        response = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=abaqus&units=mks",
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "mm_n_tonne" in response.json()["error"]["message"]

    def test_쓸_수_있는_단위계를_알려_준다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """화면이 목록을 손으로 적으면 계가 늘 때 뒤처지고, 그때 사람은 그
        계로 못 낸다는 것을 **목록에 없다는 사실로만** 안다."""
        rows = client.get("/api/fitting/unit-systems", headers=admin_headers).json()
        by_key = {row["key"]: row for row in rows}
        assert {"si", "mm_n_tonne"} <= set(by_key)
        assert by_key["si"]["is_default"] is True
        assert by_key["mm_n_tonne"]["declaration"] == "tonne, mm, s, MPa"

    def test_초안이면_덱에_그렇게_적는다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        """확정 전에 덱에 넣어 한 번 돌려 보는 것이 검토의 실체다. 다만 초안인
        덱이 돌아다닐 수 있으므로 파일 안에 적어 둔다."""
        text = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=abaqus", headers=admin_headers
        ).text
        assert "초안" in text

    def test_openradioss_는_밀도가_없으면_거부한다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        # LAW36 은 RHO_I 가 자리 있는 필드다. 0 을 채워 내보내면 그것이 측정값인지
        # 덱만 봐서는 알 수 없다.
        bare = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "밀도 없음",
            },
            headers=admin_headers,
        ).json()
        response = client.get(
            f"/api/fitting/cards/{bare['id']}/export?format=openradioss",
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text
        assert "밀도" in response.json()["error"]["message"]

    def test_중립_JSON_은_아무것도_요구하지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        """우리가 만들지 않은 솔버를 쓰는 사람이 직접 덱을 만든다."""
        body = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=json", headers=admin_headers
        ).json()
        # **/2 는 정해진 칸을 없앤 판이다.** 전에는 `elastic`·`plasticity` 를
        # 손으로 적어서 물성이 늘면 이 함수도 커졌다. 지금은 카드에 실린 블록을
        # 그대로 내고, 값의 이름·단위 선언을 같이 싣는다.
        assert body["schema"] == "matnexus.property-card/2"
        assert body["units"]["stress"] == "Pa"
        elastic = body["blocks"]["elastic"]
        assert elastic["values"]["youngs_modulus"] > 0
        # **스스로 설명한다** — 값 옆에 이름과 단위가 함께 실린다.
        assert elastic["declared"]["youngs_modulus"]["si_unit"] == "Pa"
        assert len(body["blocks"]["table"]["rows"]) >= 2


class Test상태:
    @pytest.fixture
    def card(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> dict[str, Any]:
        created: dict[str, Any] = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "상태 시험",
                "family": "voce",
            },
            headers=admin_headers,
        ).json()
        return created

    def test_확정하면_누가_언제인지_남는다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        response = client.post(
            f"/api/fitting/cards/{card['id']}/publish", headers=admin_headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "published"
        assert response.json()["published_at"] is not None

    def test_두_번_확정하지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        client.post(f"/api/fitting/cards/{card['id']}/publish", headers=admin_headers)
        again = client.post(f"/api/fitting/cards/{card['id']}/publish", headers=admin_headers)
        assert again.status_code == 409, again.text

    def test_확정된_카드는_지워지지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        """**그 값으로 해석이 돌았을 수 있다.** 내리기만 된다."""
        client.post(f"/api/fitting/cards/{card['id']}/publish", headers=admin_headers)
        removed = client.delete(f"/api/fitting/cards/{card['id']}", headers=admin_headers)
        assert removed.status_code == 409, removed.text

        dropped = client.post(
            f"/api/fitting/cards/{card['id']}/deprecate", headers=admin_headers
        )
        assert dropped.status_code == 200
        assert dropped.json()["status"] == "deprecated"
        # 내려도 남아 있다 — 지워지지 않는다.
        remains = client.get(f"/api/fitting/cards/{card['id']}", headers=admin_headers)
        assert remains.status_code == 200
        assert values(remains.json(), "hardening")["family"] == "voce"

    def test_확정은_부서_관리자만(
        self,
        client: TestClient,
        db: Session,
        workspace: Any,
        card: dict[str, Any],
    ) -> None:
        """**만드는 것은 누구나, 확정은 관리자만**(D12).

        초안은 아직 아무 해석에도 안 들어간다 — 만드는 데까지 권한을 걸면 실제로
        시험한 사람이 자기 데이터로 카드를 못 만든다. 막을 곳은 확정이다.
        """
        from app.modules.accounts.models import User
        from app.modules.auth import security
        from app.modules.workspaces.models import WorkspaceMember

        user = User(
            email="worker",
            password_hash=security.hash_password("member-password-1"),
            display_name="시험 담당자",
            status="active",
            home_workspace_id=workspace.id,
        )
        db.add(user)
        db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="member"))
        db.commit()
        token = client.post(
            "/api/auth/login", json={"email": "worker", "password": "member-password-1"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 보이기는 한다 — 같은 부서 재료다.
        assert (
            client.get(f"/api/fitting/cards/{card['id']}", headers=headers).status_code == 200
        )
        blocked = client.post(f"/api/fitting/cards/{card['id']}/publish", headers=headers)
        assert blocked.status_code == 403, blocked.text

    def test_초안은_지울_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        removed = client.delete(f"/api/fitting/cards/{card['id']}", headers=admin_headers)
        assert removed.status_code == 204, removed.text
        assert (
            client.get(f"/api/fitting/cards/{card['id']}", headers=admin_headers).status_code
            == 404
        )


class Test물려받기:
    """**같은 값을 두 곳에 적게 하지 않는다.**

    전에는 재료·시료에 밀도와 푸아송비가 있는데도 카드 모달에서 다시 받았고,
    카드는 모달 값만 썼다. 두 곳이 갈리면 어느 쪽이 맞는지 판정할 근거가 없다.
    """

    def test_재료에_적힌_값을_카드가_물려받는다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        client.patch(
            f"/api/materials/{ready['id']}",
            json={"poisson_ratio": 0.29, "density": 7830, "density_unit": "kg/m3"},
            headers=admin_headers,
        )
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "물려받기",
            },
            headers=admin_headers,
        ).json()

        assert values(card, "elastic")["poisson_ratio"] == 0.29
        assert values(card, "elastic")["density"] == 7830
        # **출처를 함께 박는다.** 재료를 나중에 고쳐도 이 카드가 무엇을 썼는지는
        # 그대로 남아야 한다 — 카드는 불변이다.
        assert values(card, "elastic")["poisson_ratio_source"] == "material"
        assert values(card, "elastic")["density_source"] == "material"

    def test_시료에서_잰_밀도가_재료_공칭값을_이긴다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        ready: dict[str, Any],
    ) -> None:
        """복합재·발포재·소결재는 로트마다 밀도가 실제로 다르다."""
        client.patch(
            f"/api/materials/{ready['id']}",
            json={"density": 7830, "density_unit": "kg/m3"},
            headers=admin_headers,
        )
        samples = client.get(
            f"/api/materials/{ready['id']}/samples", headers=admin_headers
        ).json()
        for sample in samples:
            client.patch(
                f"/api/samples/{sample['id']}",
                json={"density": 7812, "density_unit": "kg/m3"},
                headers=admin_headers,
            )

        body = client.post(
            "/api/fitting/preview",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
            },
            headers=admin_headers,
        ).json()
        density = next(row for row in body["elastic"] if row["key"] == "density")
        assert density["value"] == 7812
        assert density["source"] == "sample"

    def test_시료마다_밀도가_다르면_말없이_고르지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        ready: dict[str, Any],
    ) -> None:
        """어느 로트의 값을 썼는지 모르는 카드는 근거가 없는 것과 같다."""
        samples = client.get(
            f"/api/materials/{ready['id']}/samples", headers=admin_headers
        ).json()
        assert len(samples) >= 2
        for index, sample in enumerate(samples):
            client.patch(
                f"/api/samples/{sample['id']}",
                json={"density": 7800 + index * 10, "density_unit": "kg/m3"},
                headers=admin_headers,
            )

        body = client.post(
            "/api/fitting/preview",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
            },
            headers=admin_headers,
        ).json()
        density = next(row for row in body["elastic"] if row["key"] == "density")
        assert density["value"] is None
        assert density["source"] == "conflict"
        assert "다릅니다" in (density["detail"] or "")

    def test_직접_넣은_값이_물려받은_값을_이긴다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        client.patch(
            f"/api/materials/{ready['id']}",
            json={"poisson_ratio": 0.29},
            headers=admin_headers,
        )
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "직접",
                "poisson_ratio": 0.33,
            },
            headers=admin_headers,
        ).json()
        assert values(card, "elastic")["poisson_ratio"] == 0.33
        assert values(card, "elastic")["poisson_ratio_source"] == "manual"


class Test초탄성:
    """고무 카드가 **같은 엔드포인트로** 나온다.

    점탄성은 별도 라우트가 필요했다(Prony 는 시험 1건에 매달린다). 초탄성은 경화
    카드와 **같은 묶음·같은 대표 곡선**에서 나오고 축만 다르다 — 그래서 축을 식이
    선언하게 하니 새 엔드포인트가 필요 없었다. 그 사실을 여기서 지킨다.

    **물리는 여기서 안 본다.** 계수가 되돌아오는지는 답을 아는 합성 곡선으로
    `tests/unit/test_hyperelastic.py` 가 본다. 여기 데이터는 강판이고, Ogden 을
    강판에 맞춘 값은 뜻이 없다 — 이 시험이 보는 것은 **경로**다.
    """

    @pytest.fixture
    def rubber(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> dict[str, Any]:
        ensure_builtin_test_types(db)
        db.commit()
        created: dict[str, Any] = client.post(
            "/api/materials",
            json={
                "family": "Polymer",
                "category": "EPDM",
                "grade": "HYPER",
                "details": "MD",
                "spec_thickness": 2.0,
            },
            headers=admin_headers,
        ).json()
        _adopted(client, admin_headers, db, created["id"], 2)
        return created

    def test_재료군이_식_목록을_가른다(
        self, client: TestClient, admin_headers: dict[str, str], rubber: dict[str, Any]
    ) -> None:
        """**Voce 와 Ogden 을 한 목록에 섞어 RMSE 로 줄 세우면 안 된다.**"""
        listed = client.get(
            "/api/fitting/families",
            params={"material_id": rubber["id"]},
            headers=admin_headers,
        ).json()
        keys = {item["key"] for item in listed}
        assert "ogden_1" in keys
        assert "voce" not in keys

    def test_고무는_공칭_축에_맞춘다(
        self, client: TestClient, admin_headers: dict[str, str], rubber: dict[str, Any]
    ) -> None:
        """**축이 금속과 반대다.** 화면의 축 라벨이 여기서 온다."""
        seen = client.post(
            "/api/fitting/preview",
            json={
                "material_id": rubber["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
            },
            headers=admin_headers,
        )
        assert seen.status_code == 200, seen.text
        fits = seen.json()["fits"]
        assert fits, "고무 식이 하나도 안 맞았습니다"
        for item in fits:
            assert item["x_label"] == "공칭 변형률"
            assert item["y_label"] == "공칭 응력"

    def test_미리보기와_저장이_같은_답을_한다(
        self, client: TestClient, admin_headers: dict[str, str], rubber: dict[str, Any]
    ) -> None:
        """**보여 준 것을 저장 못 하면 안 된다.**

        저장은 초탄성에 늘리기를 422 로 거절한다(소성 표를 만드는 식이 아니다).
        그런데 미리보기가 늘어난 곡선을 그려 주면, 사람은 그 곡선을 보고 정한 뒤
        저장 버튼에서 거절당한다 — 이 저장소가 반복해서 데인 자리다.

        화면이 칸을 잠그는 근거로 `block` 도 함께 준다.
        """
        body = {
            "material_id": rubber["id"],
            "test_type_key": "tensile",
            "orientation": "MD",
            "extrapolate_to": 3.0,
        }
        fits = client.post("/api/fitting/preview", json=body, headers=admin_headers).json()[
            "fits"
        ]
        assert fits, "고무 식이 하나도 안 맞았습니다"
        for item in fits:
            assert item["block"] == "hyperelastic"
            # 늘려 달라고 했는데 안 늘렸다 — 그것이 맞다.
            assert item["extrapolated_to"] is None

        # 저장도 같은 이유로 거절한다. 둘이 어긋나면 화면이 거짓말을 한다.
        refused = client.post(
            "/api/fitting/cards",
            json={**body, "label": "늘리려는 고무", "family": "ogden_1"},
            headers=admin_headers,
        )
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "MNX-FITTING-0014"

    def test_금속은_그대로_늘어난다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """막은 것이 초탄성이지 늘리기 자체가 아니다."""
        fits = client.post(
            "/api/fitting/preview",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "extrapolate_to": 1.0,
                "families": ["voce"],
            },
            headers=admin_headers,
        ).json()["fits"]
        assert fits[0]["block"] == "hardening"
        assert fits[0]["extrapolated_to"] == 1.0

    def test_카드가_초탄성_블록을_든다(
        self, client: TestClient, admin_headers: dict[str, str], rubber: dict[str, Any]
    ) -> None:
        made = client.post(
            "/api/fitting/cards",
            json={
                "material_id": rubber["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "EPDM 초탄성",
                "family": "ogden_1",
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        card = made.json()
        assert "hyperelastic" in card["blocks"]
        assert "hardening" not in card["blocks"]
        block = values(card, "hyperelastic")
        assert block["family"] == "ogden_1"
        # **식이 자기 요약값을 낸다** — RMSE 하나로는 안 보이는 것이다.
        assert block["shear_modulus"] > 0
        assert block["mode"] == "단축 인장"

    def test_소성_표를_안_만든다(
        self, client: TestClient, admin_headers: dict[str, str], rubber: dict[str, Any]
    ) -> None:
        """공칭 축에 맞춘 점을 `*PLASTIC` 자리에 넣으면 **덱은 돌고 재료만 딴판**이다."""
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": rubber["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "표 없음",
                "family": "neo_hookean",
            },
            headers=admin_headers,
        ).json()
        assert "table" not in card["blocks"]
        assert card["point_count"] == 0
        assert "abaqus" not in card["available_formats"]
        assert "abaqus_hyperelastic" in card["available_formats"]

    def test_덱이_나온다(
        self, client: TestClient, admin_headers: dict[str, str], rubber: dict[str, Any]
    ) -> None:
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": rubber["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "덱",
                "family": "ogden_1",
            },
            headers=admin_headers,
        ).json()
        deck = client.get(
            f"/api/fitting/cards/{card['id']}/export",
            params={"format": "abaqus_hyperelastic"},
            headers=admin_headers,
        )
        assert deck.status_code == 200, deck.text
        assert "*HYPERELASTIC, OGDEN, N=1" in deck.text
        # **단축 하나로 맞췄다는 사실이 덱까지 따라가야 한다.**
        assert "단축 인장 하나로 맞춘 계수" in deck.text
        # **D=0 은 요소 종류를 강제한다.** 모르면 "덱이 안 돌아간다" 로만 보인다.
        assert "hybrid elements" in deck.text

    def test_금속_식은_고무에_안_준다(
        self, client: TestClient, admin_headers: dict[str, str], rubber: dict[str, Any]
    ) -> None:
        """섞이면 **조용히 틀린 카드**가 나온다 — 진응력 축에 맞춘 값이 고무 카드에
        들어앉는다. 여기서는 대표 곡선을 못 만들거나 목록에 없다고 말해야 한다."""
        made = client.post(
            "/api/fitting/preview",
            json={
                "material_id": rubber["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "families": ["voce"],
            },
            headers=admin_headers,
        )
        assert made.status_code == 404
        assert "재료군" in made.text


class Test외삽:
    """**측정 구간만 내보내는 것도 결정이다.**

    솔버는 표 밖에서 마지막 응력을 붙들고 가는데, 금속은 계속 경화하므로 그 구간에서
    하중을 낮게 계산한다. 지어내지 않는 것이 아니라 다른 값을 조용히 지어내는 것이다.

    통상적으로 하는 일이고 이름이 있다 — 유동곡선 외삽.
    """

    def _card(
        self,
        client: TestClient,
        headers: dict[str, str],
        material_id: str,
        **extra: Any,
    ) -> Any:
        return client.post(
            "/api/fitting/cards",
            json={
                "material_id": material_id,
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "외삽",
                "family": "voce",
                # 덱까지 내보내는 시험이 있어 인장이 안 주는 값을 함께 넣는다.
                "poisson_ratio": 0.3,
                "density": 7850.0,
                **extra,
            },
            headers=headers,
        )

    def test_비우면_측정_구간_그대로다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**기본값을 두지 않는다.** 얼마까지 필요한지는 해석하는 사람이 안다."""
        card = self._card(client, admin_headers, ready["id"]).json()
        assert values(card, "table")["source"] == "측정"
        assert "extrapolated_to" not in values(card, "table")

    def test_늘리면_표가_길어지고_카드가_그렇게_말한다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        plain = self._card(client, admin_headers, ready["id"]).json()
        made = self._card(client, admin_headers, ready["id"], extrapolate_to=1.0)
        assert made.status_code == 201, made.text
        card = made.json()

        assert card["point_count"] > plain["point_count"]
        table = values(card, "table")
        assert table["source"] == "외삽"
        assert table["extrapolated_to"] == pytest.approx(1.0)
        # **여기까지가 시험이 답한 범위다.** 그 위는 식이 답한 것이다.
        assert table["measured_max"] < 1.0
        assert rows(card, "table")[-1]["plastic_strain"] == pytest.approx(1.0)

    def test_늘렸다는_사실이_덱까지_간다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**덱만 받은 사람이 알아야 한다.** 어디까지가 시험이고 어디부터가 식인지
        표만 봐서는 구별이 안 된다 — 점이 나란히 있을 뿐이다."""
        card = self._card(client, admin_headers, ready["id"], extrapolate_to=1.0).json()
        # **Abaqus 가 아니라 JSON 으로 본다.** 이 픽스처의 실측 곡선은 네킹 뒤가
        # 섞여 있어 응력이 떨어지고, 소성 덱은 그것을 **거절하는 것이 맞다**
        # (눕혀 내보내면 실제와 다른 재료가 된다). 근거 줄은 형식과 무관하게
        # 카드에서 나오므로 여기서는 그것만 본다.
        deck = client.get(
            f"/api/fitting/cards/{card['id']}/export",
            params={"format": "json"},
            headers=admin_headers,
        )
        assert deck.status_code == 200, deck.text
        joined = " ".join(deck.json()["provenance"])
        assert "까지는 측정" in joined
        assert "외삽 구간은 시험으로 검증되지 않았습니다" in joined

    def test_식을_안_골랐으면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """표만 저장하면 늘릴 근거가 없다."""
        made = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "근거 없음",
                "extrapolate_to": 1.0,
            },
            headers=admin_headers,
        )
        assert made.status_code == 422
        assert "늘릴 식을 안 골랐습니다" in made.text

    def test_측정_끝보다_짧게_늘리면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        made = self._card(client, admin_headers, ready["id"], extrapolate_to=0.0001)
        assert made.status_code == 422
        assert "늘릴 구간이 없습니다" in made.text


class Test혼합:
    """두 식을 섞어 외삽을 조정한다 — 고장력강 카드의 표준 기법이다."""

    def _make(
        self,
        client: TestClient,
        headers: dict[str, str],
        material_id: str,
        **extra: Any,
    ) -> Any:
        return client.post(
            "/api/fitting/cards",
            json={
                "material_id": material_id,
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "혼합",
                "family": "voce",
                **extra,
            },
            headers=headers,
        )

    def test_섞은_식이_카드에_남는다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        made = self._make(
            client, admin_headers, ready["id"], blend_with="swift", blend_weight=0.6
        )
        assert made.status_code == 201, made.text
        block = values(made.json(), "hardening")
        assert block["family"] == "voce+swift"
        assert block["blend_with"] == "swift"
        assert block["blend_weight"] == pytest.approx(0.6)
        assert "Voce" in block["label"] and "Swift" in block["label"]

    def test_어느_식의_계수인지_이름에_남긴다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**둘이 섞여 들어오므로 이름만으로는 구별이 안 된다.**"""
        card = self._make(
            client, admin_headers, ready["id"], blend_with="swift", blend_weight=0.5
        ).json()
        names = [row["name"] for row in rows(card, "hardening")]
        assert any(name.startswith("Voce") for name in names)
        assert any(name.startswith("Swift") for name in names)

    def test_섞은_곡선으로_늘린다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """외삽이 혼합의 목적이다 — 늘릴 때 섞인 곡선을 써야 한다."""
        card = self._make(
            client,
            admin_headers,
            ready["id"],
            blend_with="swift",
            blend_weight=0.5,
            extrapolate_to=1.0,
        ).json()
        table = values(card, "table")
        assert table["source"] == "외삽"
        assert "Voce" in table["family"] and "Swift" in table["family"]

    def test_비중을_안_주면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**데이터가 정하지 못하는 값이라 기본값을 두지 않는다.**"""
        made = self._make(client, admin_headers, ready["id"], blend_with="swift")
        assert made.status_code == 422
        assert "비중을 함께" in made.text

    def test_섞을_수_없는_식은_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """초탄성은 축이 달라 경화식과 못 섞는다."""
        made = self._make(
            client, admin_headers, ready["id"], blend_with="ogden_1", blend_weight=0.5
        )
        assert made.status_code == 422
        assert "섞을 수 있는" in made.text


class Test재현기록:
    """**카드가 자기 근거를 들고 있다** 는 원칙의 나머지 절반.

    값이 무엇에서 나왔는지에 더해 **무엇 위에서 계산됐는지**. 적합은
    `scipy.optimize.least_squares` 를 쓰고, scipy 가 바뀌면 같은 데이터에서 다른
    파라미터가 나올 수 있다.
    """

    def test_카드가_환경을_들고_있다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "재현",
                "family": "voce",
            },
            headers=admin_headers,
        ).json()
        got = card["source"]["runtime"]
        assert {"python", "numpy", "scipy", "pyarrow", "digest"} <= set(got)
        assert got["scipy"] != "없음"


class Test미리보기외삽:
    """**194 MPa 가 갈리는 결정을 눈으로 못 보고 내리면 안 된다.**

    측정 구간에서 거의 같은 두 식이 외삽에서 갈리는데, 저장 뒤에야 결과를 보면
    판단할 자리가 없다. 미리보기가 늘린 곡선과 섞은 곡선을 그려 준다.
    """

    def _preview(
        self,
        client: TestClient,
        headers: dict[str, str],
        material_id: str,
        **extra: Any,
    ) -> Any:
        return client.post(
            "/api/fitting/preview",
            json={
                "material_id": material_id,
                "test_type_key": "tensile",
                "orientation": "MD",
                **extra,
            },
            headers=headers,
        )

    def test_비우면_적합_구간까지만_그린다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        body = self._preview(client, admin_headers, ready["id"]).json()
        for fit in body["fits"]:
            assert fit["extrapolated_to"] is None
            assert fit["curve"][-1][0] == pytest.approx(fit["strain_max"], rel=1e-6)

    def test_늘리면_그_너머까지_그린다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        got = self._preview(client, admin_headers, ready["id"], extrapolate_to=1.0)
        assert got.status_code == 200, got.text
        for fit in got.json()["fits"]:
            assert fit["extrapolated_to"] == pytest.approx(1.0)
            assert fit["curve"][-1][0] == pytest.approx(1.0)
            # **경계가 보여야 한다** — 어디까지가 시험인지 구별이 안 되면 안 된다.
            assert fit["strain_max"] < 1.0

    def test_저장하지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """미리보기는 아무것도 안 쓴다 — 견주는 동안 카드가 쌓이면 안 된다."""
        before = len(client.get("/api/fitting/cards", headers=admin_headers).json())
        self._preview(client, admin_headers, ready["id"], extrapolate_to=1.0)
        after = len(client.get("/api/fitting/cards", headers=admin_headers).json())
        assert before == after

    def test_섞은_곡선이_후보에_하나_더_붙는다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**가중치는 데이터가 정해 주지 않는다** — 눈으로 봐야 고를 수 있다."""
        plain = self._preview(client, admin_headers, ready["id"]).json()
        mixed = self._preview(
            client,
            admin_headers,
            ready["id"],
            blend_primary="voce",
            blend_with="swift",
            blend_weight=0.5,
        ).json()
        assert len(mixed["fits"]) == len(plain["fits"]) + 1
        blended = [f for f in mixed["fits"] if f["family"] == "voce+swift"]
        assert len(blended) == 1
        assert "Voce" in blended[0]["label"] and "Swift" in blended[0]["label"]
        # 계수는 두 식의 것이 이름을 달고 나란히 온다.
        names = [p["name"] for p in blended[0]["parameters"]]
        assert any(n.startswith("Voce") for n in names)
        assert any(n.startswith("Swift") for n in names)

    def test_비중이_곡선_끝을_옮긴다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """슬라이더를 움직이면 끝이 움직이는 것이 보여야 한다."""
        ends = []
        for weight in (1.0, 0.0):
            body = self._preview(
                client,
                admin_headers,
                ready["id"],
                extrapolate_to=1.0,
                blend_primary="voce",
                blend_with="swift",
                blend_weight=weight,
            ).json()
            blended = next(f for f in body["fits"] if f["family"] == "voce+swift")
            ends.append(blended["curve"][-1][1])
        assert ends[0] != pytest.approx(ends[1])


def declare(
    client: TestClient,
    headers: dict[str, str],
    material_id: str,
    rows: list[dict[str, Any]],
) -> None:
    """재료에 선언 물성을 적어 둔다(ADR 0016)."""
    saved = client.patch(
        f"/api/materials/{material_id}",
        json={"declared_properties": rows},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text


class Test선언물성이_덱까지:
    """**시험이 안 준 값이 덱에 실린다.**

    1단계는 넣을 자리만 만들었다 — 넣어 두고 안 쓰는 기능이었다. 여기가 쓸모가
    생기는 지점이다: 재료에 적은 문헌값이 카드 블록이 되고 솔버 키워드가 된다.
    """

    @pytest.fixture(autouse=True)
    def _axis(self, db: Session) -> None:
        """물성 항목 축을 시드한다 — 항목 목록은 기준정보가 정한다(D7)."""
        from app.modules.vocabulary.definitions import (
            ensure_builtin_axis_fields,
            ensure_builtin_property_items,
            ensure_builtin_vocabularies,
        )

        ensure_builtin_vocabularies(db)
        ensure_builtin_axis_fields(db)
        ensure_builtin_property_items(db)
        db.commit()

    def test_시험이_준_값이_이긴다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**잰 값이 있으면 적은 값은 안 쓴다.** 순서가 뒤집히면 실측을 해 놓고
        문헌값으로 해석하게 되는데, 카드는 멀쩡해 보인다."""
        declare(
            client,
            admin_headers,
            ready["id"],
            [
                {
                    "item": "탄성계수",
                    "points": [{"value": 1.0}],
                    "input_unit": "GPa",
                    "source": "estimate",
                    "reference": "일부러 틀린 값",
                }
            ],
        )
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "측정이 이긴다",
            },
            headers=admin_headers,
        ).json()
        elastic = values(card, "elastic")
        assert elastic["youngs_modulus_source"] == "measured"
        assert elastic["youngs_modulus"] > 1e10

    def test_열물성_블록이_생긴다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        declare(
            client,
            admin_headers,
            ready["id"],
            [
                {
                    "item": "열팽창계수",
                    "points": [{"value": 1.17e-05, "temperature_k": 293.15}],
                    "input_unit": "1/K",
                    "source": "standard",
                    "reference": "ASM Handbook Vol.1",
                },
                {
                    "item": "비열",
                    "points": [{"value": 462, "temperature_k": 293.15}],
                    "input_unit": "J/(kg.K)",
                    "source": "standard",
                    "reference": "ASM Handbook Vol.1",
                },
            ],
        )
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "열물성",
                "poisson_ratio": 0.3,
                "density": 7850.0,
            },
            headers=admin_headers,
        ).json()
        thermal = values(card, "thermal")
        assert thermal["thermal_expansion"] == pytest.approx(1.17e-05)
        assert thermal["specific_heat"] == pytest.approx(462.0)
        # **출처가 값 옆에 박힌다.** 재료를 나중에 고쳐도 이 카드가 무엇을
        # 썼는지는 그대로 남는다.
        assert thermal["specific_heat_source"] == "declared:standard"
        assert thermal["reference_temperature"] == pytest.approx(293.15)
        # 안 적은 것은 안 생긴다 — 0 으로 채우면 측정값인지 알 수 없다.
        assert "thermal_conductivity" not in thermal
        # 근거 문서가 카드에 남는다.
        notes = " ".join(card["source"]["notes"])
        assert "ASM Handbook Vol.1" in notes

    def test_온도가_서로_다르면_기준_온도를_안_적는다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """하나를 골라 적으면 나머지가 그 온도의 값인 것처럼 보인다."""
        declare(
            client,
            admin_headers,
            ready["id"],
            [
                {
                    "item": "비열",
                    "points": [{"value": 462, "temperature_k": 293.15}],
                    "input_unit": "J/(kg.K)",
                    "source": "standard",
                    "reference": "A",
                },
                {
                    "item": "열전도도",
                    "points": [{"value": 45, "temperature_k": 373.15}],
                    "input_unit": "W/(m.K)",
                    "source": "standard",
                    "reference": "A",
                },
            ],
        )
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "온도가 다르다",
            },
            headers=admin_headers,
        ).json()
        assert "reference_temperature" not in values(card, "thermal")

    def test_덱에_실린다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**여기가 이 기능의 끝이다.** 시험이 하나도 안 주는 값으로 해석용
        키워드가 나간다."""
        declare(
            client,
            admin_headers,
            ready["id"],
            [
                {
                    "item": "열전도도",
                    "points": [{"value": 45}],
                    "input_unit": "W/(m.K)",
                    "source": "literature",
                    "reference": "ASM Handbook Vol.1 p.123",
                }
            ],
        )
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "덱까지",
                "poisson_ratio": 0.3,
                "density": 7850.0,
            },
            headers=admin_headers,
        ).json()
        text = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=abaqus", headers=admin_headers
        ).text
        assert "*CONDUCTIVITY, TYPE=ISO" in text
        assert "source=declared:literature" in text
        assert "ASM Handbook Vol.1 p.123" in text


class Test시험_없이_카드:
    """**시험이 하나도 없는 재료에서 덱이 나간다**(ADR 0016, 2단계 마무리).

    `POST /cards` 는 대표 곡선에서 시작하므로 시험이 없으면 아무것도 못 만든다.
    그런데 탄성계수·열물성은 인장시험이 주지 않는 값이고, 개발 DB 의 재료 94개
    중 14개는 시험이 하나도 없다 — 그 재료의 선언 물성은 갈 데가 없었다.
    """

    @pytest.fixture(autouse=True)
    def _axis(self, db: Session) -> None:
        from app.modules.vocabulary.definitions import (
            ensure_builtin_axis_fields,
            ensure_builtin_property_items,
            ensure_builtin_vocabularies,
        )

        ensure_builtin_vocabularies(db)
        ensure_builtin_axis_fields(db)
        ensure_builtin_property_items(db)
        db.commit()

    @pytest.fixture
    def bare(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> dict[str, Any]:
        """**시험도 시료도 없는 재료.** `ready` 와 대비되는 자리다."""
        declare(
            client,
            admin_headers,
            material["id"],
            [
                {
                    "item": "탄성계수",
                    "points": [{"value": 206}],
                    "input_unit": "GPa",
                    "source": "literature",
                    "reference": "ASM Handbook Vol.1 p.12",
                },
                {
                    "item": "열전도도",
                    "points": [{"value": 45}],
                    "input_unit": "W/(m.K)",
                    "source": "literature",
                    "reference": "ASM Handbook Vol.1 p.12",
                },
            ],
        )
        return material

    def test_시험이_없어도_카드가_나온다(
        self, client: TestClient, admin_headers: dict[str, str], bare: dict[str, Any]
    ) -> None:
        made = client.post(
            "/api/fitting/cards/declared",
            json={"material_id": bare["id"], "label": "문헌값", "poisson_ratio": 0.3},
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        card = made.json()
        assert values(card, "elastic")["youngs_modulus"] == pytest.approx(206e9)
        assert values(card, "elastic")["youngs_modulus_source"] == "declared:literature"
        assert values(card, "thermal")["thermal_conductivity"] == pytest.approx(45.0)
        # **적합이 없으므로 표도 없다.**
        assert "table" not in card["blocks"]
        assert card["point_count"] == 0

    def test_시험종류를_안_지어낸다(
        self, client: TestClient, admin_headers: dict[str, str], bare: dict[str, Any]
    ) -> None:
        """아무 시험종류나 채우면 그 카드가 인장시험에서 나온 것처럼 보이고,
        **덱을 받은 사람은 그 숫자를 잰 값으로 읽는다.**"""
        card = client.post(
            "/api/fitting/cards/declared",
            json={"material_id": bare["id"], "label": "문헌값"},
            headers=admin_headers,
        ).json()
        assert card["test_type_key"] is None
        assert card["orientation"] is None
        assert card["source"]["declared_only"] is True
        # 표본 0 을 보고 "시험이 지워졌나" 를 묻지 않게 문장으로 적는다.
        assert any(
            "시험에서 나온 값이 하나도 없습니다" in line for line in card["source"]["notes"]
        )

    def test_적어_둔_것이_없으면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """**빈 카드를 안 만든다.** 값이 없는 카드는 근거가 없는 것을 넘어서,
        목록에서 「이 재료는 물성이 있다」고 말하는 거짓말이 된다."""
        response = client.post(
            "/api/fitting/cards/declared",
            json={"material_id": material["id"], "label": "빈 것"},
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text
        assert "선언 물성" in response.json()["error"]["message"]

    def test_소성_표가_필요한_형식은_안_뜬다(
        self, client: TestClient, admin_headers: dict[str, str], bare: dict[str, Any]
    ) -> None:
        """**누르기 전에 안다.** 이 카드로는 `*PLASTIC` 을 낼 수 없다 — 형식
        목록이 그것을 스스로 말해야 한다(렌더러의 `Need` 가 정한다)."""
        card = client.post(
            "/api/fitting/cards/declared",
            json={
                "material_id": bare["id"],
                "label": "문헌값",
                "poisson_ratio": 0.3,
                "density": 7850.0,
            },
            headers=admin_headers,
        ).json()
        assert "abaqus" not in card["available_formats"]
        assert "json" in card["available_formats"]

    def test_덱에_시험에서_안_나왔다고_적힌다(
        self, client: TestClient, admin_headers: dict[str, str], bare: dict[str, Any]
    ) -> None:
        """**덱만 받은 사람이 알아야 한다.** 이 값들은 잰 것이 아니다."""
        card = client.post(
            "/api/fitting/cards/declared",
            json={"material_id": bare["id"], "label": "문헌값", "poisson_ratio": 0.3},
            headers=admin_headers,
        ).json()
        text = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=json", headers=admin_headers
        ).text
        assert "*CONDUCTIVITY" not in text  # json 은 키워드를 안 쓴다
        assert "ASM Handbook Vol.1 p.12" in text
        # **덱 이름에 방향을 안 붙인다.** 선언 물성 카드에는 방향이 없는데
        # 그대로 이어 붙이면 `..._None` 이 된다.
        assert "None" not in text
        # `?` 는 "있었는데 못 찾았다" 로 읽힌다 — 여기는 처음부터 없다.
        assert "· ?" not in text
        assert "시험에서 나온 값이 하나도 없습니다" in text

    def test_무엇이_실릴지_누르기_전에_말한다(
        self, client: TestClient, admin_headers: dict[str, str], bare: dict[str, Any]
    ) -> None:
        """**만들기를 누른 뒤에 "적어 둔 물성이 없습니다" 를 보는 것은 늦다.**"""
        body = client.get(
            f"/api/fitting/cards/declared/preview?material_id={bare['id']}",
            headers=admin_headers,
        )
        assert body.status_code == 200, body.text
        found = body.json()
        assert set(found["blocks"]) == {"elastic", "thermal"}
        by_key = {row["key"]: row for row in found["values"]}
        assert by_key["youngs_modulus"]["value"] == pytest.approx(206e9)
        assert by_key["youngs_modulus"]["source"] == "declared:literature"
        assert "ASM Handbook Vol.1 p.12" in by_key["thermal_conductivity"]["detail"]

    def test_미리보기와_저장이_같은_값을_말한다(
        self, client: TestClient, admin_headers: dict[str, str], bare: dict[str, Any]
    ) -> None:
        """**화면이 "실린다" 고 한 값이 안 실리면 화면을 믿을 근거가 없다.**
        둘이 같은 함수를 쓰는지 여기서 확인한다."""
        found = client.get(
            f"/api/fitting/cards/declared/preview?material_id={bare['id']}",
            headers=admin_headers,
        ).json()
        card = client.post(
            "/api/fitting/cards/declared",
            json={"material_id": bare["id"], "label": "문헌값"},
            headers=admin_headers,
        ).json()
        assert set(found["blocks"]) == set(card["blocks"])
        for row in found["values"]:
            block = "thermal" if row["key"] in values(card, "thermal") else "elastic"
            assert values(card, block)[row["key"]] == pytest.approx(row["value"])

    def test_적어_둔_것이_없으면_미리보기가_빈다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        found = client.get(
            f"/api/fitting/cards/declared/preview?material_id={material['id']}",
            headers=admin_headers,
        ).json()
        assert found["blocks"] == []

    def test_시료_실측_밀도를_여전히_먼저_본다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        bare: dict[str, Any],
    ) -> None:
        """**같은 재료가 어느 버튼을 눌렀느냐에 따라 다른 밀도를 가지면 안 된다.**"""
        made = client.post(
            f"/api/materials/{bare['id']}/samples",
            json={"lot": "L1", "density": 7900.0, "density_unit": "kg/m3"},
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text
        card = client.post(
            "/api/fitting/cards/declared",
            json={"material_id": bare["id"], "label": "문헌값"},
            headers=admin_headers,
        ).json()
        assert values(card, "elastic")["density"] == pytest.approx(7900.0)
        assert values(card, "elastic")["density_source"] == "sample"


class Test카드_목록:
    """전역 카드 목록 — **재료를 거치지 않고 찾는다.**

    지금까지 카드에 닿는 길은 재료 상세뿐이었다. *"지난주에 만든 그 카드가 어느
    재료였더라"* 를 물으면 재료 94개를 뒤져야 했다.
    """

    @pytest.fixture
    def several(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> list[dict[str, Any]]:
        made = []
        for label in ("첫째", "둘째", "셋째"):
            card = client.post(
                "/api/fitting/cards",
                json={
                    "material_id": ready["id"],
                    "test_type_key": "tensile",
                    "orientation": "MD",
                    "label": label,
                },
                headers=admin_headers,
            )
            assert card.status_code == 201, card.text
            made.append(card.json())
        return made

    def test_페이지로_준다(
        self, client: TestClient, admin_headers: dict[str, str], several: list[dict[str, Any]]
    ) -> None:
        """**상한을 서버가 강제한다.** `?limit=1000000` 한 번에 서버가 죽으면 안
        된다 — 악의가 없어도 화면이 '전부 보기' 를 구현하면서 큰 수를 넣는다."""
        body = client.get("/api/fitting/cards?limit=2", headers=admin_headers).json()
        assert len(body["items"]) == 2
        # **`total` 이 있어야** 화면이 "다음 장이 있나" 를 알려고 한 건 더
        # 요청하는 편법을 안 쓴다.
        assert body["total"] >= 3
        assert body["limit"] == 2

        # **상한 밖은 거절한다.** 조용히 200 으로 줄여 주면 화면은 100만 장을
        # 받았다고 믿고 "이게 전부" 라고 그린다.
        over = client.get("/api/fitting/cards?limit=999999", headers=admin_headers)
        assert over.status_code == 422

    def test_상태로_거른다(
        self, client: TestClient, admin_headers: dict[str, str], several: list[dict[str, Any]]
    ) -> None:
        client.post(f"/api/fitting/cards/{several[0]['id']}/publish", headers=admin_headers)
        body = client.get("/api/fitting/cards?status=published", headers=admin_headers).json()
        assert [item["label"] for item in body["items"]] == ["첫째"]
        assert body["total"] == 1

    def test_시험_없는_카드를_따로_거른다(
        self, client: TestClient, admin_headers: dict[str, str], several: list[dict[str, Any]]
    ) -> None:
        """**`null` 을 쿼리로 못 보낸다.** 이 값이 없으면 선언 물성 카드가 어느
        시험종류 필터에도 안 걸려 목록에서 사라진다 — 거르는 축에 없는 것은
        없는 것이 된다."""
        assert several
        yes = client.get(
            "/api/fitting/cards?test_type_key=tensile", headers=admin_headers
        ).json()
        assert yes["total"] == 3
        none = client.get(
            f"/api/fitting/cards?test_type_key={NO_TEST}", headers=admin_headers
        ).json()
        assert none["total"] == 0

    def test_모르는_종류를_물으면_0건이다(
        self, client: TestClient, admin_headers: dict[str, str], several: list[dict[str, Any]]
    ) -> None:
        """**필터를 무시하고 전부 주면 안 된다.** 그러면 화면이 「이 종류에
        이만큼 있다」고 말하게 된다."""
        assert several
        body = client.get(
            "/api/fitting/cards?test_type_key=없는종류", headers=admin_headers
        ).json()
        assert body["total"] == 0

    def test_이름으로_찾는다(
        self, client: TestClient, admin_headers: dict[str, str], several: list[dict[str, Any]]
    ) -> None:
        """**검색은 서버가 한다.** 앞 50장만 받아 화면에서 거르면 뒤엣것이 없는
        카드가 된다."""
        assert several
        body = client.get("/api/fitting/cards?q=둘째", headers=admin_headers).json()
        assert [item["label"] for item in body["items"]] == ["둘째"]

        # 재료 이름으로도 찾는다 — 카드 이름을 기억 못 하는 것이 보통이다.
        by_material = client.get("/api/fitting/cards?q=FIT_MDOI", headers=admin_headers).json()
        assert by_material["total"] >= 3

    def test_소유_부서를_함께_낸다(
        self, client: TestClient, admin_headers: dict[str, str], several: list[dict[str, Any]]
    ) -> None:
        """**부서로 나누려면 소유가 보여야 한다.** 카드에 따로 안 두고 재료를
        따라간다 — 두 곳에 두면 재료를 옮겼을 때 둘이 갈린다."""
        assert several
        item = client.get("/api/fitting/cards", headers=admin_headers).json()["items"][0]
        assert "is_global" in item and "owner_workspace_name" in item

    def test_거를_수_있는_것과_그_수를_준다(
        self, client: TestClient, admin_headers: dict[str, str], several: list[dict[str, Any]]
    ) -> None:
        assert several
        found = client.get("/api/fitting/cards/facets", headers=admin_headers)
        assert found.status_code == 200, found.text
        body = found.json()
        by_key = {row["key"]: row["count"] for row in body["test_types"]}
        assert by_key["tensile"] == 3
        assert {row["key"] for row in body["statuses"]} == {"draft"}

    def test_개수는_페이지가_아니라_전체를_센다(
        self, client: TestClient, admin_headers: dict[str, str], several: list[dict[str, Any]]
    ) -> None:
        """**여기가 이 엔드포인트가 따로 있는 이유다.** 화면이 한 페이지에서
        세면 「인장시험 1」이라고 적히는데 실제로는 3장이다 — 필터 옆의 숫자가
        거짓말을 하면 필터 자체를 못 믿는다."""
        assert several
        page = client.get("/api/fitting/cards?limit=1", headers=admin_headers).json()
        assert len(page["items"]) == 1
        body = client.get("/api/fitting/cards/facets", headers=admin_headers).json()
        assert {row["key"]: row["count"] for row in body["test_types"]}["tensile"] == 3

    def test_필터를_걸어도_셈은_안_줄어든다(
        self, client: TestClient, admin_headers: dict[str, str], several: list[dict[str, Any]]
    ) -> None:
        """「무엇이 있나」를 답하는 자리다. 필터를 걸 때마다 다른 축의 숫자가
        같이 줄면 **필터를 풀기 전에는 그 축에 무엇이 있는지 알 수 없다.**"""
        client.post(f"/api/fitting/cards/{several[0]['id']}/publish", headers=admin_headers)
        body = client.get("/api/fitting/cards/facets", headers=admin_headers).json()
        assert {row["key"]: row["count"] for row in body["test_types"]}["tensile"] == 3
        assert {row["key"] for row in body["statuses"]} == {"draft", "published"}


class Test온도표:
    """**한 줄이 표를 든다** — 항목은 하나이고 그 하나가 온도에 따라 변한다.

    강판 탄성계수는 상온 206 GPa 가 400 °C 에서 170 GPa 쯤으로 떨어지고, 열간
    성형·용접·화재 해석은 그 곡선이 필요하다.
    """

    @pytest.fixture(autouse=True)
    def _axis(self, db: Session) -> None:
        from app.modules.vocabulary.definitions import (
            ensure_builtin_axis_fields,
            ensure_builtin_property_items,
            ensure_builtin_vocabularies,
        )

        ensure_builtin_vocabularies(db)
        ensure_builtin_axis_fields(db)
        ensure_builtin_property_items(db)
        db.commit()

    def _card(
        self, client: TestClient, headers: dict[str, str], material_id: str
    ) -> dict[str, Any]:
        made = client.post(
            "/api/fitting/cards/declared",
            json={"material_id": material_id, "label": "온도표"},
            headers=headers,
        )
        assert made.status_code == 201, made.text
        card: dict[str, Any] = made.json()
        return card

    def test_카드에_표가_실린다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        declare(
            client,
            admin_headers,
            material["id"],
            [
                {
                    "item": "탄성계수",
                    "points": [
                        {"value": 206, "temperature_k": 293.15},
                        {"value": 170, "temperature_k": 673.15},
                    ],
                    "input_unit": "GPa",
                    "source": "standard",
                    "reference": "EN 1993-1-2 표 3.1",
                },
                {
                    "item": "전단탄성계수",
                    "points": [{"value": 79, "temperature_k": 293.15}],
                    "input_unit": "GPa",
                    "source": "standard",
                    "reference": "EN 1993-1-2 표 3.1",
                },
            ],
        )
        card = self._card(client, admin_headers, material["id"])
        rows = card["blocks"]["elastic"]["rows"]
        assert [row["temperature"] for row in rows] == [293.15, 673.15]
        assert rows[0]["youngs_modulus"] == pytest.approx(206e9)
        assert rows[1]["youngs_modulus"] == pytest.approx(170e9)
        # **대푯값은 남는다.** 표를 못 먹는 형식이 그것을 쓴다.
        assert values(card, "elastic")["youngs_modulus"] == pytest.approx(206e9)

    def test_한_점짜리는_모든_온도에_같은_값으로_편다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """**지어내는 것이 아니라 명시된 모형 가정이다**(상수). 빼 두면 솔버가
        그 온도에서 푸아송비를 모른다."""
        client.patch(
            f"/api/materials/{material['id']}",
            json={"poisson_ratio": 0.3},
            headers=admin_headers,
        )
        declare(
            client,
            admin_headers,
            material["id"],
            [
                {
                    "item": "탄성계수",
                    "points": [
                        {"value": 206, "temperature_k": 293.15},
                        {"value": 170, "temperature_k": 673.15},
                    ],
                    "input_unit": "GPa",
                    "source": "standard",
                    "reference": "EN 1993-1-2",
                }
            ],
        )
        card = self._card(client, admin_headers, material["id"])
        text = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=json", headers=admin_headers
        ).text
        assert "206000000000" in text and "170000000000" in text

    def test_열물성은_서로_다른_온도여도_된다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """**키워드가 갈리므로 각자 자기 표를 갖는다.** 열팽창을 두 온도에서,
        비열을 세 온도에서 적어도 아무 문제가 없다 — 같은 격자를 강제하면 실제로
        그렇게 적힌 핸드북을 못 넣는다."""
        declare(
            client,
            admin_headers,
            material["id"],
            [
                {
                    "item": "열팽창계수",
                    "points": [
                        {"value": 1.17e-05, "temperature_k": 293.15},
                        {"value": 1.42e-05, "temperature_k": 773.15},
                    ],
                    "input_unit": "1/K",
                    "source": "standard",
                    "reference": "A",
                },
                {
                    "item": "비열",
                    "points": [
                        {"value": 462, "temperature_k": 293.15},
                        {"value": 550, "temperature_k": 673.15},
                    ],
                    "input_unit": "J/(kg.K)",
                    "source": "standard",
                    "reference": "B",
                },
            ],
        )
        card = self._card(client, admin_headers, material["id"])
        rows = card["blocks"]["thermal"]["rows"]
        # 온도는 합집합, 값이 없는 칸은 **비어 있다** — 0 으로 채우면 비열 0 인
        # 재료가 된다.
        assert [row["temperature"] for row in rows] == [293.15, 673.15, 773.15]
        assert "specific_heat" not in rows[2]
        assert "thermal_expansion" not in rows[1]

    def test_점이_여럿이면_온도가_전부_있어야_한다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """온도 없는 점이 섞이면 **그 값이 어느 온도에서 유효한지 알 방법이
        없다.** 상온으로 치는 것은 지어내는 일이다."""
        refused = client.patch(
            f"/api/materials/{material['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "탄성계수",
                        "points": [{"value": 206}, {"value": 170, "temperature_k": 673.15}],
                        "input_unit": "GPa",
                        "source": "standard",
                        "reference": "A",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text
        assert "온도 없는 값" in refused.json()["error"]["message"]

    def test_같은_온도를_두_번_못_적는다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """**솔버는 둘 중 하나를 조용히 고른다.** 어느 쪽인지 우리가 정해 두어야
        한다."""
        refused = client.patch(
            f"/api/materials/{material['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "탄성계수",
                        "points": [
                            {"value": 206, "temperature_k": 293.15},
                            {"value": 200, "temperature_k": 293.15},
                        ],
                        "input_unit": "GPa",
                        "source": "standard",
                        "reference": "A",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text
        assert "같은 온도가 두 번" in refused.json()["error"]["message"]

    def test_온도순으로_고쳐_담는다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """뒤섞인 채로 솔버에 나가면 **Abaqus 가 조용히 이상한 보간을 한다** —
        오류를 내지 않고 결과만 틀린다."""
        saved = client.patch(
            f"/api/materials/{material['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "탄성계수",
                        "points": [
                            {"value": 170, "temperature_k": 673.15},
                            {"value": 206, "temperature_k": 293.15},
                        ],
                        "input_unit": "GPa",
                        "source": "standard",
                        "reference": "A",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert saved.status_code == 200, saved.text
        points = saved.json()["declared_properties"][0]["points"]
        assert [point["temperature_k"] for point in points] == [293.15, 673.15]

    def test_값이_없으면_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        refused = client.patch(
            f"/api/materials/{material['id']}",
            json={
                "declared_properties": [
                    {
                        "item": "탄성계수",
                        "points": [],
                        "input_unit": "GPa",
                        "source": "standard",
                        "reference": "A",
                    }
                ]
            },
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text


class Test되짚어_찾은_것:
    """전체 훑기에서 나온 것들(2026-08-25). **넷 다 재현해서 고쳤다.**

    공통점이 있다: 넷 중 셋이 *"덱은 멀쩡히 돌고 값만 틀리는"* 종류다 —
    이 저장소가 가장 경계하는 실패이고, 시험이 없으면 아무도 모른다.
    """

    @pytest.fixture(autouse=True)
    def _axis(self, db: Session) -> None:
        from app.modules.vocabulary.definitions import (
            ensure_builtin_axis_fields,
            ensure_builtin_property_items,
            ensure_builtin_vocabularies,
        )

        ensure_builtin_vocabularies(db)
        ensure_builtin_axis_fields(db)
        ensure_builtin_property_items(db)
        db.commit()

    def test_ZERO_는_열팽창_자신의_온도에서만_나온다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """**`ZERO` 는 열변형이 0 이 되는 온도다.** 비열을 잰 온도와 아무 관계가
        없는데, 온도를 한 통에 모아 두었더니 그것이 `ZERO` 로 나갔다.

        열팽창이 표면 어디서 변형이 0 인지 **표가 말해 주지 않는다** — 안 적으면
        Abaqus 가 해석의 초기 온도를 쓰고, 그것이 맞는 기본값이다.
        """
        declare(
            client,
            admin_headers,
            material["id"],
            [
                {
                    "item": "열팽창계수",
                    "points": [
                        {"value": 1.17e-05, "temperature_k": 293.15},
                        {"value": 1.55e-05, "temperature_k": 873.15},
                    ],
                    "input_unit": "1/K",
                    "source": "standard",
                    "reference": "A",
                },
                {
                    "item": "비열",
                    "points": [{"value": 500, "temperature_k": 400.0}],
                    "input_unit": "J/(kg.K)",
                    "source": "standard",
                    "reference": "B",
                },
            ],
        )
        card = client.post(
            "/api/fitting/cards/declared",
            json={"material_id": material["id"], "label": "ZERO"},
            headers=admin_headers,
        ).json()
        thermal = values(card, "thermal")
        # 비열의 400 K 가 기준 온도로 새어 나오면 안 된다.
        assert "reference_temperature" not in thermal
        assert "thermal_expansion_temperature" not in thermal

        text = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=abaqus", headers=admin_headers
        ).text
        assert "ZERO" not in text, text[: text.find("*PLASTIC")]

    def test_열팽창이_한_점이면_그_온도가_ZERO_다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """반대쪽도 지킨다 — 열팽창 자신의 온도는 **써야 한다.**"""
        declare(
            client,
            admin_headers,
            material["id"],
            [
                {
                    "item": "열팽창계수",
                    "points": [{"value": 1.17e-05, "temperature_k": 293.15}],
                    "input_unit": "1/K",
                    "source": "standard",
                    "reference": "A",
                },
                {
                    "item": "비열",
                    "points": [{"value": 500, "temperature_k": 400.0}],
                    "input_unit": "J/(kg.K)",
                    "source": "standard",
                    "reference": "B",
                },
            ],
        )
        card = client.post(
            "/api/fitting/cards/declared",
            json={"material_id": material["id"], "label": "ZERO2", "poisson_ratio": 0.3},
            headers=admin_headers,
        ).json()
        assert values(card, "thermal")["thermal_expansion_temperature"] == pytest.approx(
            293.15
        )
        # 비열의 400 K 는 새어 나오지 않는다 — 온도가 갈리므로 기준 온도는 없다.
        assert "reference_temperature" not in values(card, "thermal")

    def test_지운_시료의_밀도는_안_쓴다(
        self, client: TestClient, admin_headers: dict[str, str], material: dict[str, Any]
    ) -> None:
        """**밀도를 잘못 적어 지운 시료의 값이 「실측」으로 카드에 박혔다.**
        지운 그 값으로 해석을 돌리게 된다."""
        sample = client.post(
            f"/api/materials/{material['id']}/samples",
            json={"lot_no": "BAD", "density": 7000.0, "density_unit": "kg/m3"},
            headers=admin_headers,
        ).json()
        gone = client.delete(f"/api/samples/{sample['id']}", headers=admin_headers)
        assert gone.status_code == 204, gone.text

        declare(
            client,
            admin_headers,
            material["id"],
            [
                {
                    "item": "탄성계수",
                    "points": [{"value": 206}],
                    "input_unit": "GPa",
                    "source": "literature",
                    "reference": "A",
                }
            ],
        )
        card = client.post(
            "/api/fitting/cards/declared",
            json={"material_id": material["id"], "label": "지운 시료"},
            headers=admin_headers,
        ).json()
        assert "density" not in values(card, "elastic")

    def test_부서_값이_이상하면_422_다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**손으로 고친 URL 이 500 을 내면 안 된다.** 사람은 「서버가
        고장났다」로 읽는데 실제로는 필터 값이 틀린 것이다(낡은 북마크)."""
        refused = client.get("/api/fitting/cards?owner=abc", headers=admin_headers)
        assert refused.status_code == 422, refused.text
        assert "부서 값" in refused.json()["error"]["message"]

        # 전역은 그대로 돈다.
        fine = client.get("/api/fitting/cards?owner=global", headers=admin_headers)
        assert fine.status_code == 200, fine.text

    def test_두_OpenRadioss_덱의_파일_이름이_다르다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """한 카드가 `/MAT/LAW36` 과 `/HEAT/MAT` 을 함께 내는데 둘 다 `.rad` 라,
        이름이 같으면 받는 쪽에 `(1)` 이 붙고 **어느 쪽이 열인지 알 수 없다.**"""
        declare(
            client,
            admin_headers,
            ready["id"],
            [
                {
                    "item": "비열",
                    "points": [{"value": 462}],
                    "input_unit": "J/(kg.K)",
                    "source": "standard",
                    "reference": "A",
                },
                {
                    "item": "열전도도",
                    "points": [{"value": 45}],
                    "input_unit": "W/(m.K)",
                    "source": "standard",
                    "reference": "A",
                },
            ],
        )
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "두 덱",
                "poisson_ratio": 0.3,
                "density": 7850.0,
            },
            headers=admin_headers,
        ).json()
        assert {"openradioss", "openradioss_thermal"} <= set(card["available_formats"])

        names = {}
        for form in ("openradioss", "openradioss_thermal"):
            got = client.get(
                f"/api/fitting/cards/{card['id']}/export?format={form}", headers=admin_headers
            )
            assert got.status_code == 200, got.text
            names[form] = got.headers["content-disposition"]
        assert names["openradioss"] != names["openradioss_thermal"], names
        # 이름에 형식과 **단위계**가 함께 들어간다(v1.110.0).
        assert "_thermal_si.rad" in names["openradioss_thermal"]


class Test네킹을_안_자르면:
    """**네킹 뒤는 균일 변형이 아니다.**

    진응력 변환식이 성립하지 않는 구간인데, 안 자르고 변환하면 그 구간의 진응력이
    실제보다 낮게 나오고 그 표가 그대로 `*PLASTIC` 으로 간다 — **덱은 멀쩡히
    돌고 재료만 무르게 계산된다.**

    막지는 않는다. 어디서 네킹이 시작됐는지는 곡선만 봐서는 확정할 수 없고(그래서
    그 단계가 「후보」다), 막으면 사람은 시스템 밖에서 계산해 카드 없이 덱을
    만든다 — 그러면 근거가 아무 데도 안 남는다.
    """

    def test_카드가_그_사실을_적는다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "안 자름",
                "poisson_ratio": 0.3,
                "density": 7850.0,
            },
            headers=admin_headers,
        )
        assert card.status_code == 201, card.text
        notes = " ".join(card.json()["source"]["notes"])
        assert "네킹을 안 자른" in notes
        # **무엇을 하라는지 말한다.** "섞여 있습니다" 만으로는 어디를 만져야
        # 하는지 모른다.
        assert "지정한 위치에서 자름" in notes

    def test_덱에도_따라간다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**소성 표만 봐서는 구별할 방법이 없다** — 점이 나란히 있을 뿐이다."""
        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "안 자름",
                "poisson_ratio": 0.3,
                "density": 7850.0,
            },
            headers=admin_headers,
        ).json()
        text = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=abaqus", headers=admin_headers
        ).text
        assert "네킹을 안 자른" in text

    def test_막지는_않는다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """한 번 재고 해석부터 돌려 보는 것은 정상 작업이다. 막으면 사람은
        시스템 밖에서 계산하고, 그러면 근거가 아무 데도 안 남는다."""
        made = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "그래도 만든다",
            },
            headers=admin_headers,
        )
        assert made.status_code == 201, made.text

    def test_자른_곡선에는_안_적는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        ready: dict[str, Any],
    ) -> None:
        """**늘 적으면 그 문장이 경고로 안 읽힌다.**"""
        from app.modules.processing.models import ProcessingResult

        # 이 재료의 처리 결과를 「자른 것」으로 바꿔 둔다.
        for result in db.scalars(select(ProcessingResult)):
            steps = [dict(step) for step in result.steps_snapshot or []]
            for step in steps:
                if step.get("plugin") == "tensile.true_plastic":
                    step["options"] = {
                        **(step.get("options") or {}),
                        "necking_policy": "manual_index",
                        "manual_index": 50,
                    }
            result.steps_snapshot = steps
        db.commit()

        card = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "잘랐다",
                "poisson_ratio": 0.3,
            },
            headers=admin_headers,
        ).json()
        notes = " ".join(card["source"]["notes"])
        assert "네킹을 안 자른" not in notes, notes


class Test쓸_시험_고르기:
    """*"이상치 둘 빼고 8건으로 뽑은 것과 10건으로 뽑은 것을 둘 다 카드로"* —
    실사용에서 나온 물음이다.

    지금까지는 그 결정을 적을 자리가 없어서 **시험의 채택을 푸는 수밖에**
    없었다. 그러면 통계 화면과 나중에 만들 카드까지 전부 따라 바뀌어서, 두 장을
    나란히 두고 견줄 수가 없다.
    """

    def _runs(
        self, client: TestClient, headers: dict[str, str], material_id: str
    ) -> list[str]:
        body = client.get(f"/api/statistics/materials/{material_id}", headers=headers).json()
        group = next(
            item
            for item in body["groups"]
            if item["test_type_key"] == "tensile" and item["orientation"] == "MD"
        )
        return [str(one) for one in group["test_run_ids"]]

    def _card(
        self,
        client: TestClient,
        headers: dict[str, str],
        material_id: str,
        label: str,
        run_ids: list[str] | None = None,
    ) -> Any:
        body: dict[str, Any] = {
            "material_id": material_id,
            "test_type_key": "tensile",
            "orientation": "MD",
            "label": label,
        }
        if run_ids is not None:
            body["test_run_ids"] = run_ids
        return client.post("/api/fitting/cards", json=body, headers=headers)

    def test_안_고르면_채택된_전부를_쓴다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**전과 같이 동작한다.** 고르는 칸은 더한 것이지 바꾼 것이 아니다."""
        made = self._card(client, admin_headers, ready["id"], "전부")
        assert made.status_code == 201, made.text
        assert made.json()["source"]["sample_count"] == 3

    def test_고른_것만_쓴다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        runs = self._runs(client, admin_headers, ready["id"])
        assert len(runs) == 3

        made = self._card(client, admin_headers, ready["id"], "둘만", runs[:2])
        assert made.status_code == 201, made.text
        source = made.json()["source"]
        assert source["sample_count"] == 2
        assert set(source["test_run_ids"]) == set(runs[:2])

    def test_두_장을_나란히_둘_수_있다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**이 기능의 요점이다.** 8건짜리와 10건짜리가 각자의 근거를 들고
        같은 재료 밑에 함께 산다."""
        runs = self._runs(client, admin_headers, ready["id"])
        whole = self._card(client, admin_headers, ready["id"], "3건").json()
        part = self._card(client, admin_headers, ready["id"], "2건", runs[:2]).json()

        assert whole["id"] != part["id"]
        assert whole["source"]["sample_count"] == 3
        assert part["source"]["sample_count"] == 2

        listed = client.get(
            f"/api/fitting/cards?material_id={ready['id']}", headers=admin_headers
        ).json()
        assert {item["id"] for item in listed["items"]} >= {whole["id"], part["id"]}

    def test_뺐다는_사실을_근거에_남긴다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**표본 수만 적으면** 「원래 2건이었나 하나를 뺐나」 를 나중에 아무도
        답할 수 없다."""
        runs = self._runs(client, admin_headers, ready["id"])
        made = self._card(client, admin_headers, ready["id"], "둘만", runs[:2]).json()
        joined = " ".join(made["source"]["notes"])
        assert "3건 중 2건" in joined, joined

    def test_모르는_시험을_적으면_막는다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**조용히 넘기지 않는다.** 열 건 중 둘을 빼려다 하나가 오타면, 말없이
        아홉 건짜리 카드가 만들어지고 그 카드는 자기가 아홉 건짜리인 줄 안다."""
        runs = self._runs(client, admin_headers, ready["id"])
        ghost = "00000000-0000-0000-0000-000000000000"
        blocked = self._card(client, admin_headers, ready["id"], "오타", [runs[0], ghost])
        assert blocked.status_code == 422
        assert blocked.json()["error"]["code"] == "MNX-FITTING-0022"

    def test_하나도_안_고르면_막는다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        blocked = self._card(client, admin_headers, ready["id"], "빈 것", [])
        assert blocked.status_code == 422
        assert blocked.json()["error"]["code"] == "MNX-FITTING-0021"

    def test_대표_곡선_뒤에_원곡선이_함께_온다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**대표만 보여 주면 그것이 적절한지 알 방법이 없다.** 셋이 겹쳐 있는데
        하나가 딴 데로 가서 평균이 끌려간 것인지, 애초에 흩어짐이 그만큼인지
        평균값 하나로는 같아 보인다."""
        seen = client.post(
            "/api/fitting/preview",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "families": ["swift"],
            },
            headers=admin_headers,
        ).json()

        assert len(seen["members"]) == 3
        for member in seen["members"]:
            assert member["record_name"]
            assert len(member["points"]) >= 2
            # **그리기 좋게 솎는다.** 한 곡선이 수천 점이고 시편이 열이면
            # 차트가 버벅인다.
            assert len(member["points"]) <= 300

    def test_고른_시험의_곡선만_깔린다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """뺀 시편의 곡선이 뒤에 남아 있으면, 그것이 평균에 들어갔다고 읽힌다."""
        runs = self._runs(client, admin_headers, ready["id"])
        seen = client.post(
            "/api/fitting/preview",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "families": ["swift"],
                "test_run_ids": runs[:2],
            },
            headers=admin_headers,
        ).json()
        assert {str(one["test_run_id"]) for one in seen["members"]} == set(runs[:2])

    def test_미리보기도_같은_것을_본다(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> None:
        """**저장하고 나서야 알면 늦다.** 뺀 것과 안 뺀 것의 적합이 어떻게
        다른지 눈으로 보고 정해야 한다."""
        runs = self._runs(client, admin_headers, ready["id"])
        seen = client.post(
            "/api/fitting/preview",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "families": ["swift"],
                "test_run_ids": runs[:2],
            },
            headers=admin_headers,
        )
        assert seen.status_code == 200, seen.text
        assert seen.json()["sample_count"] == 2


class Test덱_미리보기:
    """정의를 **저장하기 전에** 실제 카드로 그려 본다 (ADR 0023 3단계).

    장비 파일 쪽이 이미 같은 일을 한다 — 실제 파일을 받아 무엇으로 읽히는지 먼저
    보여 준다(ADR 0006). 덱 쪽에서 더 필요하다: **틀린 덱은 솔버가 오류로 알려
    주지 않는다.** 칸이 어긋나면 다른 필드로 읽히고, 해석은 그대로 돌아 그럴듯한
    결과를 낸다.

    무는 자리 넷:

      1. **미리보기와 실제 내려받기가 같은 덱이다.** 다르면 미리보기의 뜻이 없다.
      2. **못 냈어도 200 이다.** 못 낸 이유를 보여 주는 것이 미리보기의 절반이다.
      3. **정의가 틀린 것과 카드가 빈 것을 구별한다.** 안 하면 멀쩡한 정의를
         고치며 시간을 버린다 — 실제로 할 일은 다른 카드를 고르는 것이다.
      4. **아무것도 저장하지 않는다.**
    """

    @pytest.fixture
    def card(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> dict[str, Any]:
        created: dict[str, Any] = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "미리보기 시험",
                "family": "voce",
                "poisson_ratio": 0.3,
                "density": 7850.0,
            },
            headers=admin_headers,
        ).json()
        return created

    def _preview(
        self,
        client: TestClient,
        headers: dict[str, str],
        card: dict[str, Any],
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        response = client.post(
            "/api/fitting/export-profiles/preview",
            json={"definition": definition, "card_id": card["id"]},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def test_미리보기가_실제_덱과_같다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        """**여기가 이 기능의 전부다.** 미리보기가 「이렇게 나온다」 를 보여 주고
        실제로 다른 것이 나가면, 사람은 미리보기를 한 번 믿고 두 번 안 믿는다."""
        from matcore import export

        body = self._preview(
            client,
            admin_headers,
            card,
            {
                "key": "미리보기",
                "label": "Abaqus 그대로",
                "extension": "inp",
                "describe": "코드 렌더러를 정의로 옮긴 것.",
                "lines": export.ABAQUS_TEMPLATE["lines"],
            },
        )
        real = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=abaqus", headers=admin_headers
        )
        assert real.status_code == 200, real.text
        assert body["text"] == real.text

    def test_못_내도_200_이고_이유를_말한다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        """422 로 던지면 화면은 오류 상자 하나를 띄우고, 사람은 정의의 어느 줄이
        문제인지 모른 채 돌아간다."""
        body = self._preview(client, admin_headers, card, {"label": "줄이 없다"})
        assert body["text"] is None
        assert body["error"]
        assert "lines" in body["error"], body["error"]

    def test_모르는_칸_형식도_이유가_된다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        body = self._preview(
            client,
            admin_headers,
            card,
            {
                "key": "x",
                "label": "x",
                "extension": "x",
                "describe": "x",
                "lines": [{"fields": [{"value": "elastic.density", "format": "nastran"}]}],
            },
        )
        assert body["text"] is None
        assert "nastran" in (body["error"] or "")

    def test_카드가_빈_것과_정의가_틀린_것을_가른다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        """**둘을 안 가르면 멀쩡한 정의를 고치며 시간을 버린다.** 실제로 할 일은
        다른 카드를 고르는 것이다."""
        body = self._preview(
            client,
            admin_headers,
            card,
            {
                "key": "x",
                "label": "x",
                "extension": "x",
                "describe": "x",
                "needs": [{"block": "viscoelastic", "values": ["없는값"]}],
                "lines": [{"text": "*MATERIAL, NAME={name}"}],
            },
        )
        assert body["missing"], "카드에 모자란 것을 안 알려 줍니다"
        assert body["error"] is None or body["text"] is None

    def test_아무것도_저장하지_않는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        card: dict[str, Any],
        db: Session,
    ) -> None:
        from app.modules.fitting.models import ExportProfile

        before = db.query(ExportProfile).count()
        self._preview(
            client,
            admin_headers,
            card,
            {
                "key": "저장되면_안_된다",
                "label": "x",
                "extension": "x",
                "describe": "x",
                "lines": [{"text": "*MATERIAL, NAME={name}"}],
            },
        )
        assert db.query(ExportProfile).count() == before

    def test_덱을_만들며_한_일을_함께_준다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        # **조용히 하지 않았다는 증거다.** 표를 정리했으면 그것을 저장 전에 본다.
        from matcore import export

        body = self._preview(
            client,
            admin_headers,
            card,
            {
                "key": "x",
                "label": "x",
                "extension": "inp",
                "describe": "x",
                "lines": export.ABAQUS_TEMPLATE["lines"],
            },
        )
        assert body["text"]
        assert isinstance(body["notes"], list)


class Test예제_덱_읽기:
    """**빈 폼에서 시작하지 않게** (ADR 0023 4단계 보강).

    덱을 붙이려는 사람에게는 대개 그 솔버의 덱 파일이 이미 있다 — 해석을 돌려 본
    사람이니까. 장비 파일 정의가 같은 문제를 이미 풀었고(ADR 0006), 여기도 같은
    선이다: **구조는 코드가 읽고 「이 값이 무엇인가」 만 사람이 정한다.**
    """

    @pytest.fixture
    def card(
        self, client: TestClient, admin_headers: dict[str, str], ready: dict[str, Any]
    ) -> dict[str, Any]:
        created: dict[str, Any] = client.post(
            "/api/fitting/cards",
            json={
                "material_id": ready["id"],
                "test_type_key": "tensile",
                "orientation": "MD",
                "label": "덱 읽기 시험",
                "family": "voce",
                "poisson_ratio": 0.3,
                "density": 7850.0,
            },
            headers=admin_headers,
        ).json()
        return created

    def test_내가_낸_덱을_다시_읽어_초안이_된다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        """**답을 아는 입력이다.** 방금 내보낸 덱을 그대로 먹여, 나온 초안이 그
        덱의 구조와 같은지 본다."""
        deck = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=abaqus", headers=admin_headers
        )
        assert deck.status_code == 200, deck.text

        response = client.post(
            "/api/fitting/export-profiles/scan",
            json={"text": deck.text, "card_id": card["id"]},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        kinds = [one["kind"] for one in body["lines"]]
        assert "text" in kinds, "키워드 줄을 못 읽었습니다"
        assert "rows" in kinds, "소성 표를 표로 못 봤습니다"

    def test_카드_값에_이름을_붙인다(
        self, client: TestClient, admin_headers: dict[str, str], card: dict[str, Any]
    ) -> None:
        """**여기가 「막연하다」 를 없애는 자리다.** 화면은 숫자만 보지만, 덱을
        올린 사람은 그것이 자기 재료의 덱임을 안다."""
        deck = client.get(
            f"/api/fitting/cards/{card['id']}/export?format=abaqus", headers=admin_headers
        )
        body = client.post(
            "/api/fitting/export-profiles/scan",
            json={"text": deck.text, "card_id": card["id"]},
            headers=admin_headers,
        ).json()
        named = {
            cell["suggested"]
            for one in body["lines"]
            for cell in one["cells"]
            if cell["suggested"]
        }
        assert "elastic.density" in named, named
        assert any("짐작" in said for said in body["notes"])

    def test_카드를_안_줘도_구조는_읽는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        # 남의 솔버 덱을 먼저 붙여 놓고 카드는 나중에 고르는 것이 정상이다.
        body = client.post(
            "/api/fitting/export-profiles/scan",
            json={"text": "*MATERIAL, NAME=X\n1.0, 2.0\n"},
            headers=admin_headers,
        ).json()
        assert [one["kind"] for one in body["lines"]] == ["text", "fields"]
        assert body["lines"][0]["text"] == "*MATERIAL, NAME=X"

    def test_아무것도_저장하지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        from app.modules.fitting.models import ExportProfile

        before = db.query(ExportProfile).count()
        client.post(
            "/api/fitting/export-profiles/scan",
            json={"text": "*MATERIAL\n1.0\n"},
            headers=admin_headers,
        )
        assert db.query(ExportProfile).count() == before
