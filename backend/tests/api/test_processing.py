"""처리 API — **저장 전에 볼 수 있는가, 저장한 것이 안 바뀌는가.**

두 가지가 이 파일의 전부다.

1. `/preview` 는 아무것도 저장하지 않는다. 처리가 잘못되면 곡선이 조용히
   이상해지는데, 저장한 뒤에는 찾기가 매우 어렵다(ADR 0005 의 `/try` 와 같은 판단).

2. 저장된 결과는 **불변**이다. 레시피를 고쳐도, 레시피를 지워도, 어제 뽑은
   항복강도가 무엇으로 나온 값인지 여전히 알 수 있어야 한다 — 그 값은 이미
   보고서에 들어가 있다.

계산 자체의 정확성은 `tests/unit/test_processing.py` 가 답을 아는 곡선으로 본다.
여기서는 **HTTP 를 지나면서 깨지는 것**을 본다.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.models import Specimen
from app.modules.processing.models import ProcessingResult
from app.modules.tests import services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import TestRun

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"

#: 시편 치수를 숫자로 직접 주는 단계. 참조(`@`)는 따로 시험한다.
STEPS: list[dict[str, Any]] = [
    {"plugin": "tensile.engineering", "options": {"gauge_length": 0.05, "area": 12.12e-6}},
    {
        "plugin": "curve.sort_unique",
        "options": {"x": "strain_engineering", "duplicate_policy": "mean"},
    },
    {"plugin": "tensile.strength", "options": {}},
]


@pytest.fixture
def run_id(client: TestClient, admin_headers: dict[str, str], db: Session) -> str:
    """파싱까지 끝난 인장 시험 하나."""
    ensure_builtin_test_types(db)
    db.commit()
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": "PROC",
            "details": "MDOI",
            "spec_thickness": 1.0,
        },
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
        data={"specimen_id": specimen["id"], "test_type": "tensile", "conditions": "{}"},
        files={"file": ("Example.tra", TRA.read_bytes())},
        headers=admin_headers,
    ).json()
    assert services.parse_run(db, uuid.UUID(created["id"])) == "parsed"
    return str(created["id"])


class Test단계목록:
    def test_화면이_이_응답만으로_폼을_그린다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        response = client.get("/api/processing/steps", headers=admin_headers)
        assert response.status_code == 200, response.text
        steps = {item["id"]: item for item in response.json()}
        assert "tensile.elastic_modulus" in steps

        # **ParamSpec 이 곧 입력 칸이다.** 프론트에 목록을 하드코딩하면 계산을
        # 추가할 때 두 곳을 고쳐야 하고, 그러면 한 곳을 빠뜨린다.
        params = {p["name"]: p for p in steps["tensile.elastic_modulus"]["params"]}
        assert params["method"]["type"] == "choice"
        assert "linear_regression" in params["method"]["choices"]
        assert params["minimum_strain"]["unit"] == "1"

    def test_시험_종류로_거를_수_있다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        # 인장 레시피가 DMA 곡선에 걸리면 '변형률 열이 없습니다' 로 실패하는데,
        # 그 전에 목록에서 안 보이는 편이 낫다.
        response = client.get("/api/processing/steps?test_type=tensile", headers=admin_headers)
        ids = {item["id"] for item in response.json()}
        assert "tensile.elastic_modulus" in ids
        # 시험을 가리지 않는 단계는 언제나 보인다.
        assert "curve.sort_unique" in ids


class Test미리보기:
    def test_아무것도_저장하지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str, db: Session
    ) -> None:
        before = db.scalar(
            select(ProcessingResult).where(ProcessingResult.test_run_id == run_id)
        )
        assert before is None

        response = client.post(
            "/api/processing/preview?x=strain_engineering&y=stress_engineering",
            json={"test_run_id": run_id, "steps": STEPS},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["row_count"] > 0
        assert body["points"], "차트가 그릴 점이 없습니다"
        assert {"strain_engineering", "stress_engineering"} <= set(body["columns"])

        db.expire_all()
        after = db.scalar(
            select(ProcessingResult).where(ProcessingResult.test_run_id == run_id)
        )
        assert after is None, "미리보기가 결과를 저장했습니다"

    def test_근거가_값과_함께_온다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str
    ) -> None:
        # "무슨 방법으로 어느 구간에서 몇 점을 써서 구했는가" 가 없으면, 반년 뒤
        # 그 값을 설명할 수 없다.
        body = client.post(
            "/api/processing/preview",
            json={"test_run_id": run_id, "steps": STEPS},
            headers=admin_headers,
        ).json()
        assert body["notes"], "근거가 비어 있습니다"
        assert any("게이지 길이" in note for note in body["notes"])
        assert all(stage["version"] for stage in body["stages"])

    def test_실패는_422_이고_어느_단계인지_말한다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str
    ) -> None:
        # 500 으로 내면 로그를 뒤져야 안다. 메시지에는 이미 이유가 적혀 있다.
        response = client.post(
            "/api/processing/preview",
            json={
                "test_run_id": run_id,
                "steps": [
                    *STEPS,
                    {
                        "plugin": "tensile.elastic_modulus",
                        "options": {"minimum_strain": 9.0, "maximum_strain": 10.0},
                    },
                ],
            },
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text
        assert "4단계" in response.json()["error"]["message"]

    def test_시편_치수가_없으면_추측하지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str
    ) -> None:
        """**0 이나 기본값으로 채우면 응력이 조용히 틀린다.**

        단면적이 잘못되면 자릿수가 통째로 어긋나는데 숫자는 그럴듯해 보인다.
        일괄 등록으로 만든 시편은 치수가 비어 있는 것이 정상이라 실제로 자주 걸린다.
        """
        response = client.post(
            "/api/processing/preview",
            json={
                "test_run_id": run_id,
                "steps": [
                    {
                        "plugin": "tensile.engineering",
                        "options": {
                            "gauge_length": "@specimen_gauge_length",
                            "area": "@specimen_area",
                        },
                    }
                ],
            },
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text
        assert "시편 기록에 그 값이 있는지" in response.json()["error"]["message"]

    def test_시편_치수가_있으면_참조로_돈다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        run_id: str,
        db: Session,
    ) -> None:
        run = db.get(TestRun, uuid.UUID(run_id))
        assert run is not None
        specimen = db.get(Specimen, run.specimen_id)
        assert specimen is not None
        specimen.gauge_length_m = 0.05
        specimen.width_m = 12.12e-3
        specimen.thickness_m = 1.0e-3
        db.commit()

        body = client.post(
            "/api/processing/preview",
            json={
                "test_run_id": run_id,
                "steps": [
                    {
                        "plugin": "tensile.engineering",
                        "options": {
                            "gauge_length": "@specimen_gauge_length",
                            "area": "@specimen_area",
                        },
                    }
                ],
            },
            headers=admin_headers,
        )
        assert body.status_code == 200, body.text
        # **실제로 쓴 숫자가 근거에 남아야 한다** — "이 응력이 왜 이렇지" 는
        # 대개 면적 문제다.
        assert "12.12 mm²" in body.json()["notes"][0]


class Test결과는불변:
    def _save(self, client: TestClient, headers: dict[str, str], run_id: str) -> Any:
        response = client.post(
            "/api/processing/results",
            json={"test_run_id": run_id, "steps": STEPS, "recipe_key": "proc_check"},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        return response.json()

    @pytest.fixture
    def recipe(self, client: TestClient, admin_headers: dict[str, str], run_id: str) -> Any:
        response = client.post(
            "/api/processing/recipes",
            json={
                "key": "proc_check",
                "label": "확인용",
                "description": None,
                "test_type_key": "tensile",
                "steps": STEPS,
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        return response.json()

    def test_레시피를_고쳐도_저장된_결과는_안_바뀐다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str, recipe: Any
    ) -> None:
        """**이것이 스냅샷을 두는 이유 전부다.**

        `recipe_id` 만 남기면, 탄성 구간을 옮기고 저장한 순간 어제 뽑은 값이
        어느 구간에서 나온 것인지 추적이 끊긴다. 그 값은 이미 보고서에 있다.
        """
        saved = self._save(client, admin_headers, run_id)
        assert len(saved["steps"]) == len(STEPS)

        changed = [*STEPS, {"plugin": "tensile.necking_candidate", "options": {}}]
        updated = client.put(
            "/api/processing/recipes/proc_check",
            json={
                "label": "확인용(수정)",
                "description": None,
                "test_type_key": "tensile",
                "steps": changed,
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert updated.status_code == 200, updated.text
        assert len(updated.json()["steps"]) == len(changed)

        again = client.get(
            f"/api/processing/results?test_run_id={run_id}", headers=admin_headers
        ).json()
        assert len(again) == 1
        assert len(again[0]["steps"]) == len(STEPS), "저장된 결과가 레시피를 따라 바뀌었습니다"

    def test_레시피를_지워도_결과는_남는다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str, recipe: Any
    ) -> None:
        saved = self._save(client, admin_headers, run_id)
        assert saved["recipe_label"] == "확인용"

        removed = client.delete("/api/processing/recipes/proc_check", headers=admin_headers)
        assert removed.status_code == 204, removed.text

        remaining = client.get(
            f"/api/processing/results?test_run_id={run_id}", headers=admin_headers
        ).json()
        assert len(remaining) == 1
        # 이름과 단계는 결과가 자기 안에 갖고 있다.
        assert remaining[0]["recipe_label"] == "확인용"
        assert remaining[0]["steps"]

    def test_다시_돌리면_새_행이_생긴다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str, recipe: Any
    ) -> None:
        # 덮어쓰기가 없으면 "예전 결과를 열었더니 값이 달라졌다" 가 구조적으로
        # 불가능하다.
        first = self._save(client, admin_headers, run_id)
        second = self._save(client, admin_headers, run_id)
        assert first["id"] != second["id"]
        listed = client.get(
            f"/api/processing/results?test_run_id={run_id}", headers=admin_headers
        ).json()
        assert len(listed) == 2


class Test레시피:
    def test_등록되지_않은_단계는_저장_시점에_거절한다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str
    ) -> None:
        # 저장하게 두면 그 레시피는 **쓸 때마다** 실패한다. 저장 시점에 아는
        # 것을 저장 시점에 말한다.
        response = client.post(
            "/api/processing/recipes",
            json={
                "key": "bogus",
                "label": "없는 단계",
                "description": None,
                "test_type_key": "tensile",
                "steps": [{"plugin": "tensile.made_up", "options": {}}],
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text
        assert "등록되지 않은 처리" in response.json()["error"]["message"]

    def test_전역_레시피는_시스템_관리자만(
        self, client: TestClient, db: Session, run_id: str
    ) -> None:
        from app.modules.accounts.models import User
        from app.modules.auth import security
        from app.modules.workspaces.models import Workspace, WorkspaceMember

        workspace = db.scalar(select(Workspace))
        assert workspace is not None
        user = User(
            email="recipe-lead",
            password_hash=security.hash_password("member-password-1"),
            display_name="사업부 관리자",
            status="active",
        )
        db.add(user)
        db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="manager"))
        db.commit()
        token = client.post(
            "/api/auth/login", json={"email": "recipe-lead", "password": "member-password-1"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "key": "dept_recipe",
            "label": "부서 레시피",
            "description": None,
            "test_type_key": "tensile",
            "steps": STEPS,
            "is_active": True,
        }
        blocked = client.post("/api/processing/recipes", json=payload, headers=headers)
        assert blocked.status_code == 403, blocked.text

        allowed = client.post(
            "/api/processing/recipes",
            json={**payload, "owner_workspace_slug": workspace.slug},
            headers=headers,
        )
        assert allowed.status_code == 201, allowed.text
        assert allowed.json()["is_global"] is False


class Test채택:
    """**"이 시험의 항복강도는?" 에 답이 하나여야 한다**(ADR 0007).

    저장된 결과가 전부 동등하면 통계·비교·내보내기가 무엇을 써야 할지 모른다.
    그렇다고 저장을 곧 확정으로 하면 시행착오를 남길 수 없어 방법 간 비교가
    불가능해진다. 그래서 시도는 자유롭게 쌓이고 대표는 사람이 한 번 정한다.
    """

    def _save(self, client: TestClient, headers: dict[str, str], run_id: str) -> Any:
        response = client.post(
            "/api/processing/results",
            json={"test_run_id": run_id, "steps": STEPS},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        return response.json()

    def test_채택하면_요약값_표에_장비_값과_나란히_선다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str
    ) -> None:
        """**이 투영이 없어서 값이 두 곳에 따로 있었다.**

        `TestSummary.source` 를 장비/MatNexus 로 나눈 이유가 이 비교인데, 처리가
        자기 JSONB 에만 값을 두고 있었다. 화면 아래 요약값 표에는 장비가 계산한
        항복강도가, 처리 패널에는 우리가 계산한 항복강도가 있고 둘이 서로를
        몰랐다. 나란히 두면 검증도 된다 — 크게 다르면 뭔가 잘못된 것이다.
        """
        detail = client.get(f"/api/test-runs/{run_id}", headers=admin_headers).json()
        assert {s["source"] for s in detail["summary"]} == {"instrument"}

        saved = self._save(client, admin_headers, run_id)
        adopted = client.post(
            f"/api/processing/results/{saved['id']}/adopt", headers=admin_headers
        )
        assert adopted.status_code == 200, adopted.text
        assert adopted.json()["is_adopted"] is True

        detail = client.get(f"/api/test-runs/{run_id}", headers=admin_headers).json()
        ours = [s for s in detail["summary"] if s["source"] == "matnexus"]
        assert ours, "채택했는데 요약값 표에 우리 값이 없습니다"
        assert {s["key"] for s in ours} >= {"tensile_strength"}
        # 장비 값은 그대로 남는다 — 지우면 비교가 성립하지 않는다.
        assert [s for s in detail["summary"] if s["source"] == "instrument"]

    def test_다른_것을_채택하면_앞의_값이_남지_않는다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str
    ) -> None:
        # 갱신이 아니라 삭제 후 삽입인 이유: 예전 채택에만 있던 키가 남으면
        # 두 계산이 섞인 표가 된다 — 그 표는 그럴듯해 보인다.
        first = self._save(client, admin_headers, run_id)
        client.post(f"/api/processing/results/{first['id']}/adopt", headers=admin_headers)

        second = client.post(
            "/api/processing/results",
            json={
                "test_run_id": run_id,
                "steps": [*STEPS, {"plugin": "tensile.necking_candidate", "options": {}}],
            },
            headers=admin_headers,
        ).json()
        client.post(f"/api/processing/results/{second['id']}/adopt", headers=admin_headers)

        detail = client.get(f"/api/test-runs/{run_id}", headers=admin_headers).json()
        keys = [s["key"] for s in detail["summary"] if s["source"] == "matnexus"]
        assert len(keys) == len(set(keys)), f"같은 키가 두 번 있습니다: {keys}"
        assert "necking_candidate_index" in keys

        # **앞의 결과는 지워지지 않는다.** 시도 목록에 그대로 남는다.
        results = client.get(
            f"/api/processing/results?test_run_id={run_id}", headers=admin_headers
        ).json()
        assert len(results) == 2
        assert [r["is_adopted"] for r in results].count(True) == 1

    def test_채택을_거둬도_결과는_남는다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str
    ) -> None:
        saved = self._save(client, admin_headers, run_id)
        client.post(f"/api/processing/results/{saved['id']}/adopt", headers=admin_headers)
        removed = client.delete(
            f"/api/processing/results/{saved['id']}/adopt", headers=admin_headers
        )
        assert removed.status_code == 204, removed.text

        detail = client.get(f"/api/test-runs/{run_id}", headers=admin_headers).json()
        assert not [s for s in detail["summary"] if s["source"] == "matnexus"]
        results = client.get(
            f"/api/processing/results?test_run_id={run_id}", headers=admin_headers
        ).json()
        assert len(results) == 1, "채택을 거뒀는데 결과가 지워졌습니다"
        assert results[0]["is_adopted"] is False

    def test_목록에서_진행이_보인다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str
    ) -> None:
        # 시편 20개짜리 배치에서 무엇이 아직 안 됐는지를 하나씩 열어 봐야 아는
        # 것은 일이 아니다.
        def row() -> Any:
            page = client.get("/api/test-runs", headers=admin_headers).json()
            return next(r for r in page["items"] if r["id"] == run_id)

        assert row()["result_count"] == 0
        assert row()["adopted_result_id"] is None

        saved = self._save(client, admin_headers, run_id)
        assert row()["result_count"] == 1
        assert row()["adopted_result_id"] is None  # 돌려는 봤지만 아직 안 정함

        client.post(f"/api/processing/results/{saved['id']}/adopt", headers=admin_headers)
        assert row()["adopted_result_id"] == saved["id"]


class Test배치:
    """**시편 20개를 하나씩 처리하는 것은 일이 아니다.**

    한 건으로 단계를 맞춘 뒤 나머지에 같은 것을 거는 것이 실제 작업 흐름이고,
    그것이 안 되면 실데이터를 넣어 볼 수가 없다.

    여기서 지키는 것은 **부분 실패**다. 20건 중 하나가 시편 치수 때문에 막혔다고
    전체를 되돌리면 19건을 다시 해야 하고, 조용히 건너뛰면 사람은 다 된 줄 안다.
    """

    @pytest.fixture
    def three_runs(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> list[str]:
        """시편 3개, 각각 시험 1건씩. 셋 다 같은 재료다."""
        ensure_builtin_test_types(db)
        db.commit()
        material = client.post(
            "/api/materials",
            json={
                "family": "Metal",
                "category": "Steel",
                "grade": "BATCH",
                "details": "MDOI",
                "spec_thickness": 1.0,
            },
            headers=admin_headers,
        ).json()
        sample = client.post(
            f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
        ).json()
        ids: list[str] = []
        for _ in range(3):
            specimen = client.post(
                f"/api/samples/{sample['id']}/specimens",
                json={"orientation": "MD"},
                headers=admin_headers,
            ).json()
            created = client.post(
                "/api/test-runs",
                data={
                    "specimen_id": specimen["id"],
                    "test_type": "tensile",
                    "conditions": "{}",
                },
                files={"file": ("Example.tra", TRA.read_bytes())},
                headers=admin_headers,
            ).json()
            assert services.parse_run(db, uuid.UUID(created["id"])) == "parsed"
            ids.append(str(created["id"]))
        return ids

    def test_한_번에_돌리고_채택까지_한다(
        self, client: TestClient, admin_headers: dict[str, str], three_runs: list[str]
    ) -> None:
        response = client.post(
            "/api/processing/batch",
            json={"test_run_ids": three_runs, "steps": STEPS, "adopt": True},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["requested"], body["succeeded"], body["failed"]) == (3, 3, 0)
        assert all(item["adopted"] for item in body["items"])

        # 채택이 실제로 걸렸는지는 목록이 안다.
        page = client.get("/api/test-runs", headers=admin_headers).json()
        rows = {r["id"]: r for r in page["items"]}
        for run_id in three_runs:
            assert rows[run_id]["adopted_result_id"] is not None
            assert rows[run_id]["result_count"] == 1

    def test_하나가_막혀도_나머지는_저장된다(
        self, client: TestClient, admin_headers: dict[str, str], three_runs: list[str]
    ) -> None:
        """**이것이 이 기능의 핵심이다.**

        실패 이유는 건마다 다르다 — 시편 치수가 없는 것, 탄성 구간에 점이 없는
        것이 한 배치에 섞여 온다. 여기서는 없는 시험 id 를 하나 섞어 같은 것을
        본다.
        """
        bogus = str(uuid.uuid4())
        response = client.post(
            "/api/processing/batch",
            json={"test_run_ids": [three_runs[0], bogus, three_runs[1]], "steps": STEPS},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["succeeded"], body["failed"]) == (2, 1)

        failed = [item for item in body["items"] if item["status"] == "failed"]
        assert len(failed) == 1
        assert failed[0]["test_run_id"] == bogus
        # **왜 막혔는지가 건별로 있어야** 무엇을 고칠지 안다.
        assert failed[0]["error"]

        # 앞의 성공이 살아 있어야 한다 — 롤백되면 19건을 다시 해야 한다.
        listed = client.get(
            f"/api/processing/results?test_run_id={three_runs[0]}", headers=admin_headers
        ).json()
        assert len(listed) == 1

    def test_처리_실패도_건별로_남는다(
        self, client: TestClient, admin_headers: dict[str, str], three_runs: list[str]
    ) -> None:
        # 시편 치수가 없는 시험이 섞이는 것이 실제로 가장 흔하다.
        response = client.post(
            "/api/processing/batch",
            json={
                "test_run_ids": three_runs,
                "steps": [
                    {
                        "plugin": "tensile.engineering",
                        "options": {
                            "gauge_length": "@specimen_gauge_length",
                            "area": "@specimen_area",
                        },
                    }
                ],
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["failed"] == 3
        assert all("시편 기록에" in item["error"] for item in body["items"])
        # 이름이 있어야 어느 시험인지 안다.
        assert all(item["record_name"] != "?" for item in body["items"])

    def test_상한을_서버가_강제한다(
        self, client: TestClient, admin_headers: dict[str, str], run_id: str
    ) -> None:
        response = client.post(
            "/api/processing/batch",
            json={"test_run_ids": [run_id] * 101, "steps": STEPS},
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text
        assert "나눠서" in response.json()["error"]["message"]

    def test_한_건_저장과_배치가_같은_값을_낸다(
        self, client: TestClient, admin_headers: dict[str, str], three_runs: list[str]
    ) -> None:
        """경로가 갈리면 "화면에서는 되는데 배치에서는 다른 값" 이 가능해진다."""
        single = client.post(
            "/api/processing/results",
            json={"test_run_id": three_runs[0], "steps": STEPS},
            headers=admin_headers,
        ).json()
        batch = client.post(
            "/api/processing/batch",
            json={"test_run_ids": [three_runs[1]], "steps": STEPS, "adopt": False},
            headers=admin_headers,
        ).json()

        one = {s["key"]: s["value"] for s in single["scalars"]}
        many = {s["key"]: s["value"] for s in batch["items"][0]["scalars"]}
        assert one == many


class Test저장된_결과의_곡선:
    """**결과 탭이 그림을 못 그렸다.**

    값과 근거는 있는데 곡선은 파일에만 있었다. 채택은 "이 곡선을 이 시험의 물성으로
    삼는다" 는 결정인데, 정작 그 곡선을 안 보고 눌러야 했다.
    """

    def test_저장된_결과의_곡선을_읽는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        run_id: str,
    ) -> None:
        stored = client.post(
            "/api/processing/results",
            json={"test_run_id": run_id, "steps": STEPS},
            headers=admin_headers,
        ).json()

        body = client.get(
            f"/api/processing/results/{stored['id']}/curve", headers=admin_headers
        ).json()

        # 공칭이 먼저다 — 사람이 시험기에서 보던 곡선이다.
        assert (body["x"], body["y"]) == ("strain_engineering", "stress_engineering")
        assert body["points"], "저장된 결과에 곡선이 있어야 한다"
        # **단위를 함께 준다.** Pa 인지 MPa 인지 모르는 축은 읽을 수 없다.
        assert body["units"]["stress_engineering"] == "Pa"
        assert body["units"]["strain_engineering"] == "1"

    def test_진응력_단계가_없으면_그_축이_아예_없다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        run_id: str,
    ) -> None:
        """**없는 것이 답이다.**

        "왜 진응력 곡선이 안 보이나" 의 답은 언제나 같다 — 레시피에 그 단계가
        없으면 그 열은 만들어진 적이 없다. 결과는 불변이라 나중에 덧붙지도 않는다.
        """
        stored = client.post(
            "/api/processing/results",
            json={"test_run_id": run_id, "steps": STEPS},
            headers=admin_headers,
        ).json()

        body = client.get(
            f"/api/processing/results/{stored['id']}/curve",
            params={"x": "strain_true_plastic", "y": "stress_true"},
            headers=admin_headers,
        ).json()
        assert "stress_true" not in body["columns"]
        assert body["points"] == []

    def test_진응력_단계를_넣으면_그_축으로_그릴_수_있다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        run_id: str,
    ) -> None:
        steps = [
            *STEPS,
            {"plugin": "tensile.elastic_modulus", "options": {"maximum_strain": 0.05}},
            {
                "plugin": "tensile.true_plastic",
                "options": {"youngs_modulus": "@youngs_modulus"},
            },
        ]
        stored = client.post(
            "/api/processing/results",
            json={"test_run_id": run_id, "steps": steps},
            headers=admin_headers,
        ).json()

        body = client.get(
            f"/api/processing/results/{stored['id']}/curve",
            params={"x": "strain_true_plastic", "y": "stress_true"},
            headers=admin_headers,
        ).json()
        assert body["points"], "진응력 단계를 넣었으면 그 축으로 그려져야 한다"
        assert body["units"]["stress_true"] == "Pa"
