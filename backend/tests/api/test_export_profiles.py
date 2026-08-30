"""덱 정의가 **행 하나로** 는다 — ADR 0023 2단계.

1단계가 답한 것은 「템플릿으로 같은 덱이 나오는가」 였다. 여기서 보는 것은 그
템플릿이 **DB 에서 와서 API 까지 닿는가** 다.

무는 자리를 넷에 둔다. 넷 다 조용히 틀리는 종류다:

  1. 행 하나가 목록에 뜨고 덱을 낸다 — 이것이 되면 「배포 없이 새 솔버」 다.
  2. **코드 렌더러를 못 덮는다.** 덮게 두면 코드 쪽 검증을 정의 하나가 우회한다.
  3. **부서 것이 전역을 덮는다.** 같은 솔버라도 사업부마다 덱 관례가 다르다.
  4. **깨진 정의 하나가 목록을 안 죽인다.** 목록이 안 뜨면 고치러 들어갈 화면도
     그 목록 위에 있어서, 사람이 손쓸 길이 사라진다.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.fitting import renderers
from app.modules.fitting.models import ExportProfile
from matcore import export

DEFINITION: dict[str, Any] = {
    "label": "OptiStruct 탄성 (부서)",
    "extension": "fem",
    "describe": "정의로 붙인 솔버.",
    "needs": [{"block": "elastic", "values": ["density"]}],
    "lines": [
        {"text": "$ {name}"},
        {"text": "MAT1"},
        {
            "fields": [
                {"value": "elastic.youngs_modulus", "format": ["fixed", 8, 1]},
                {"value": "elastic.poisson_ratio", "format": ["fixed", 8, 1]},
            ],
            "join": "",
        },
    ],
}


def _profile(
    db: Session,
    key: str = "optistruct",
    *,
    workspace_id: uuid.UUID | None = None,
    definition: dict[str, Any] | None = None,
) -> ExportProfile:
    row = ExportProfile(
        key=key,
        label=str((definition or DEFINITION)["label"]),
        owner_workspace_id=workspace_id,
        definition=definition or DEFINITION,
    )
    db.add(row)
    db.flush()
    return row


def _deck() -> export.Deck:
    return export.Deck(
        name="DP600",
        solver_id=1,
        blocks={"elastic": {"values": {"youngs_modulus": 200e9, "poisson_ratio": 0.3}}},
        provenance=(),
    )


class Test행_하나가_솔버가_된다:
    def test_목록에_뜬다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        _profile(db)
        db.commit()
        body = client.get("/api/fitting/formats", headers=admin_headers).json()
        by_key = {item["key"]: item for item in body}
        assert "optistruct" in by_key, "정의로 붙인 솔버가 목록에 없습니다"
        assert by_key["optistruct"]["extension"] == "fem"
        # **`needs` 가 따라와야** 화면이 「이 형식은 아직 못 낸다」 를 미리 말한다.
        # 안 따라오면 덱을 만들다 터지고, 그때는 사람이 이유를 모른다.
        #
        # 사람이 읽는 이름으로 바뀌었는지는 **여기서 안 본다.** 그 변환은
        # `matcore.cards` 레지스트리가 하는데 등록이 다른 모듈 로드에 딸려 와서,
        # 이 파일만 돌리면 raw 이름이 나온다(기존 시험도 단독으로는 그렇다).
        # 그것은 이 시험의 주제가 아니고, 여기서 물면 「파일 하나만 돌린다」 가
        # 깨진다. 개수만 본다.
        assert len(by_key["optistruct"]["requires"]) == 1
        # 코드 렌더러가 사라지지 않는다.
        assert {"abaqus", "openradioss", "json"} <= set(by_key)

    def test_칸_폭이_지켜진다(self, db: Session, workspace: Any) -> None:
        """**칸이 어긋나면 다른 필드로 읽힌다** — 그리고 솔버는 그것을 오류로
        알려 주지 않는다. 정의가 적은 폭이 실제 덱에 그대로 나와야 한다."""
        _profile(db)
        made = renderers.renderer_for(db, workspace.id, "optistruct")
        line = made.render(_deck()).text.splitlines()[2]
        assert len(line) == 16, f"8칸 둘이어야 하는데 {len(line)}칸입니다: {line!r}"

    def test_지운_정의는_안_온다(self, db: Session, workspace: Any) -> None:
        from datetime import UTC, datetime

        row = _profile(db)
        row.deleted_at = datetime.now(UTC)
        db.flush()
        assert "optistruct" not in {
            item.key for item in renderers.all_renderers(db, workspace.id)
        }


class Test덮어쓰기:
    def test_코드_렌더러를_못_덮는다(self, db: Session, workspace: Any) -> None:
        """덮게 두면 **코드 쪽 검증을 정의 하나가 조용히 우회한다** — 키워드 확인도
        물리적 타당성도 그 코드 안에 있다."""
        _profile(db, "abaqus", definition={**DEFINITION, "label": "가짜 Abaqus"})
        made = renderers.renderer_for(db, workspace.id, "abaqus")
        assert made.label != "가짜 Abaqus"
        assert made.extension == "inp"

        # **목록에도 하나여야 한다.** 고르는 쪽은 먼저 나온 것을 쓰니 둘이어도
        # 덱은 맞게 나오지만, 화면에는 같은 이름이 두 줄 뜬다 — 그리고 사람은
        # 아래쪽을 눌러 보고 왜 같은지 묻는다.
        keys = [item.key for item in renderers.all_renderers(db, workspace.id)]
        assert keys.count("abaqus") == 1, f"목록에 abaqus 가 {keys.count('abaqus')}개"

    def test_부서_것이_전역을_덮는다(self, db: Session, workspace: Any) -> None:
        """같은 솔버라도 사업부마다 덱 관례가 다르다 — 어느 키워드를 쓰는지, 표를
        몇 줄로 자르는지. 그 지식은 해석을 돌리는 사람에게 있다."""
        _profile(db, definition={**DEFINITION, "label": "전역"})
        _profile(
            db,
            workspace_id=workspace.id,
            definition={**DEFINITION, "label": "우리 부서"},
        )
        made = renderers.renderer_for(db, workspace.id, "optistruct")
        assert made.label == "우리 부서"

    def test_남의_부서_것은_안_보인다(self, db: Session, workspace: Any) -> None:
        from app.modules.workspaces.models import Workspace

        other = Workspace(slug="polymer", name="고분자팀")
        db.add(other)
        db.flush()
        _profile(db, workspace_id=other.id, definition={**DEFINITION, "label": "남"})
        assert "optistruct" not in {
            item.key for item in renderers.all_renderers(db, workspace.id)
        }


class Test깨진_정의:
    def test_하나가_깨져도_목록이_산다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """**목록이 안 뜨면 사람이 손쓸 길이 사라진다** — 고치러 들어갈 화면도
        그 목록 위에 있다. 건너뛰고 로그를 남긴다."""
        _profile(db, "broken", definition={"label": "줄이 없다"})
        _profile(db)
        db.commit()
        body = client.get("/api/fitting/formats", headers=admin_headers).json()
        keys = {item["key"] for item in body}
        assert "broken" not in keys
        assert "optistruct" in keys
        assert "abaqus" in keys


VALID: dict[str, Any] = {
    "label": "OptiStruct 탄성",
    "definition": {
        "extension": "fem",
        "describe": "정의로 붙인 솔버.",
        "lines": [{"text": "$ {name}"}, {"text": "MAT1"}],
    },
}


class Test정의를_만들고_고친다:
    """**지금까지는 DB 에 직접 넣어야 썼다.** 그러면 「배포 없이」 가 「DBA 없이」 로
    바뀔 뿐이다 — 현장에서 만들 수 있어야 이 창구가 뜻을 갖는다(ADR 0023 4단계).
    """

    def _create(self, client: TestClient, headers: dict[str, str], **over: Any) -> Any:
        body = {"key": "optistruct", **VALID, **over}
        return client.post("/api/fitting/export-profiles", json=body, headers=headers)

    def test_만들면_바로_형식_목록에_뜬다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        # **재기동이 없다.** 그것이 이 설계의 요점이다.
        assert self._create(client, admin_headers).status_code == 201
        body = client.get("/api/fitting/formats", headers=admin_headers).json()
        assert "optistruct" in {item["key"] for item in body}

    def test_저장하기_전에_실제로_만들어_본다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**「저장은 됐는데 내려받을 때 터지는」 정의를 만들지 않는다.** 그때는
        화면에서 고칠 사람이 그 자리에 없다 — 해석을 돌리려던 사람이 500 을 본다."""
        response = self._create(client, admin_headers, definition={"describe": "줄이 없다"})
        assert response.status_code == 422, response.text
        assert "lines" in response.text

    def test_코드_렌더러의_이름은_못_쓴다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """덮게 두면 코드 쪽 검증(키워드 확인·물리적 타당성)이 통째로 빠진다."""
        response = self._create(client, admin_headers, key="abaqus")
        assert response.status_code == 409, response.text

    def test_같은_key_는_한_번만(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        assert self._create(client, admin_headers).status_code == 201
        assert self._create(client, admin_headers).status_code == 409

    def test_고치면_다음_요청부터_먹는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        self._create(client, admin_headers)
        response = client.put(
            "/api/fitting/export-profiles/optistruct",
            json={**VALID, "label": "OptiStruct 고침"},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = client.get("/api/fitting/formats", headers=admin_headers).json()
        by_key = {item["key"]: item for item in body}
        assert by_key["optistruct"]["label"] == "OptiStruct 고침"

    def test_고칠_때도_만들어_본다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        # 만들 때만 검사하면 **고치면서 깨뜨릴 수 있다.**
        self._create(client, admin_headers)
        response = client.put(
            "/api/fitting/export-profiles/optistruct",
            json={**VALID, "definition": {"describe": "줄이 없다"}},
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text


class Test지우고_되살린다:
    """수집 체계 넷과 같은 규칙이다(2026-08-29) — 부분 유니크 인덱스까지."""

    def _create(self, client: TestClient, headers: dict[str, str]) -> None:
        assert (
            client.post(
                "/api/fitting/export-profiles",
                json={"key": "optistruct", **VALID},
                headers=headers,
            ).status_code
            == 201
        )

    def test_지우면_형식_목록에서_빠진다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        self._create(client, admin_headers)
        assert (
            client.delete(
                "/api/fitting/export-profiles/optistruct", headers=admin_headers
            ).status_code
            == 204
        )
        body = client.get("/api/fitting/formats", headers=admin_headers).json()
        assert "optistruct" not in {item["key"] for item in body}

    def test_지운_key_로_다시_만들_수_있다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**부분 유니크 인덱스가 하는 일이다.** 그냥 유니크면 지운 행이 key 를
        붙들어 「이미 있습니다」 가 나오는데, 화면 어디에도 그것이 없다 — 재료에서
        그대로 터졌다(2026-08-28 이관 사고)."""
        self._create(client, admin_headers)
        client.delete("/api/fitting/export-profiles/optistruct", headers=admin_headers)
        self._create(client, admin_headers)

    def test_휴지통에_들어간다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        self._create(client, admin_headers)
        client.delete("/api/fitting/export-profiles/optistruct", headers=admin_headers)
        body = client.get("/api/trash", headers=admin_headers).json()
        rows = body["items"] if isinstance(body, dict) else body
        mine = [row for row in rows if row.get("kind") == "export_profile"]
        assert mine, f"휴지통에 안 들어갔습니다: {rows}"
        assert mine[0]["name"] == "OptiStruct 탄성"

    def test_되살리면_다시_쓴다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        self._create(client, admin_headers)
        client.delete("/api/fitting/export-profiles/optistruct", headers=admin_headers)
        body = client.get("/api/trash", headers=admin_headers).json()
        rows = body["items"] if isinstance(body, dict) else body
        mine = next(row for row in rows if row.get("kind") == "export_profile")
        restored = client.post(
            f"/api/trash/export_profile/{mine['id']}/restore", headers=admin_headers
        )
        assert restored.status_code in (200, 204), restored.text
        formats = client.get("/api/fitting/formats", headers=admin_headers).json()
        assert "optistruct" in {item["key"] for item in formats}
