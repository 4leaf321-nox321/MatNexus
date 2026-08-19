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
        assert fixed.json()["elastic"] == card["elastic"]
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
        assert not body["hardening"], "식을 안 골랐으면 비어 있어야 한다"
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
        assert card["hardening"]["family"] == "voce"
        assert "relative_rmse" in card["hardening"]
        assert card["hardening"]["strain_max"] > 0
        for item in card["hardening"]["parameters"]:
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
        assert card["hardening"] == {}
        assert card["point_count"] == len(card["table"]) > 0
        assert {"plastic_strain", "true_stress"} == set(card["table"][0])

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
        assert "poisson_ratio" not in card["elastic"]
        # 탄성계수는 시험이 준다 — 통계 평균이 들어간다.
        assert card["elastic"]["youngs_modulus"] > 0

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
        assert card["elastic"]["poisson_ratio"] == pytest.approx(0.29)
        assert card["elastic"]["density"] == pytest.approx(7850.0)


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
        assert body["schema"] == "matnexus.property-card/1"
        assert body["units"]["stress"] == "Pa"
        assert body["elastic"]["youngs_modulus_pa"] > 0
        assert len(body["plasticity"]["points"]) >= 2


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
        assert remains.json()["hardening"]["family"] == "voce"

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

        assert card["elastic"]["poisson_ratio"] == 0.29
        assert card["elastic"]["density"] == 7830
        # **출처를 함께 박는다.** 재료를 나중에 고쳐도 이 카드가 무엇을 썼는지는
        # 그대로 남아야 한다 — 카드는 불변이다.
        assert card["elastic"]["poisson_ratio_source"] == "material"
        assert card["elastic"]["density_source"] == "material"

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
        assert card["elastic"]["poisson_ratio"] == 0.33
        assert card["elastic"]["poisson_ratio_source"] == "manual"
