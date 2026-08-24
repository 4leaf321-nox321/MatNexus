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

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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
        "plugin": "tensile.elastic_modulus",
        "options": {"method": "linear_regression", "lower": 0.0002, "upper": 0.002},
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
                    "value": 1.0,
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
                    "value": 1.17e-05,
                    "input_unit": "1/K",
                    "source": "standard",
                    "reference": "ASM Handbook Vol.1",
                    "temperature_k": 293.15,
                },
                {
                    "item": "비열",
                    "value": 462,
                    "input_unit": "J/(kg.K)",
                    "source": "standard",
                    "reference": "ASM Handbook Vol.1",
                    "temperature_k": 293.15,
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
                    "value": 462,
                    "input_unit": "J/(kg.K)",
                    "source": "standard",
                    "reference": "A",
                    "temperature_k": 293.15,
                },
                {
                    "item": "열전도도",
                    "value": 45,
                    "input_unit": "W/(m.K)",
                    "source": "standard",
                    "reference": "A",
                    "temperature_k": 373.15,
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
                    "value": 45,
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
