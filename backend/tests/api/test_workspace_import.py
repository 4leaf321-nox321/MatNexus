"""ReportArchive 부서 트리 가져오기 — **조직도를 두 번 치지 않는다.**

무는 것이 다섯이다. 전부 「조용히 잘못 들어가는」 부류다 — 조직도는 한 번 잘못
들어가면 부서마다 재료·시험이 매달리기 시작해 지우기 어렵다.

    트리가 트리로 들어온다        부모-자식이 평면으로 풀리면 안 된다
    이미 있는 부서는 안 덮는다     MatNexus 에서 고친 이름이 조용히 되돌면 안 된다
    TF 는 안 들어온다            한시 조직은 조직도가 아니다
    깨진 부모는 오류로 남는다      루트로 슬쩍 붙이면 트리가 거짓말을 한다
    미리보기와 적용이 같은 답이다   「미리보기엔 된다더니」 가 없어야 한다
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.workspaces.models import Workspace

#: RA `workspaces/export.csv` 그대로 — UTF-8 BOM, 열 14개, 깊이우선.
HEADER = (
    "slug,name,parent_slug,parent_name,depth,path,kind,status,description,"
    "sort_order,external_view_default,member_count,managers,created_at"
)


def csv_bytes(*rows: str) -> bytes:
    return ("﻿" + HEADER + "\n" + "\n".join(rows) + "\n").encode("utf-8")


def send(
    client: TestClient, headers: dict[str, str], body: bytes, *, preview: bool
) -> dict[str, Any]:
    made = client.post(
        f"/api/workspaces/import{'/preview' if preview else ''}",
        files={"file": ("부서정보.csv", body, "text/csv")},
        headers=headers,
    )
    assert made.status_code == 200, made.text
    result: dict[str, Any] = made.json()
    return result


TREE = csv_bytes(
    'rnd,연구소,,,0,연구소,org,active,,0,false,12,"김소장",2024-01-01',
    "rnd-metal,금속재료팀,rnd,연구소,1,연구소 > 금속팀,org,active,,0,false,5,박팀장,"
    "2024-01-02",
    "rnd-polymer,고분자팀,rnd,연구소,1,연구소 > 고분자팀,org,active,,1,false,4,,2024-01-03",
    "grp-quality,품질그룹,rnd,연구소,1,연구소 > 품질그룹,virtual,active,,2,false,0,,"
    "2024-01-04",
    "tf-crash,충돌TF,,,0,충돌TF,tf,active,,0,false,7,,2024-05-01",
)


class Test트리가_트리로_들어온다:
    def test_부모_자식과_순서가_붙는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        result = send(client, admin_headers, TREE, preview=False)
        assert result["created"] == 4  # org 셋 + virtual 하나

        rows = {one.slug: one for one in db.scalars(select(Workspace))}
        assert rows["rnd-metal"].parent_id == rows["rnd"].id
        assert rows["grp-quality"].parent_id == rows["rnd"].id
        # RA 트리의 형제 순서가 그대로 온다 — 순서는 사람이 정한 것이다.
        assert rows["rnd-polymer"].sort_order == 1
        # virtual 은 org 로 — MatNexus 에는 종류 구분이 없고, 트리의 그 자리는 필요하다.
        assert rows["grp-quality"].kind == "org"

    def test_TF_는_건너뛴다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """한시 조직은 조직도가 아니다 — RA 설계에서도 트리 밖이다."""
        result = send(client, admin_headers, TREE, preview=False)
        skipped = {one["slug"]: one for one in result["rows"]}
        assert skipped["tf-crash"]["action"] == "skip_kind"
        assert db.scalar(select(Workspace).where(Workspace.slug == "tf-crash")) is None


class Test이미_있는_부서는_안_덮는다:
    def test_이름이_달라도_그대로_둔다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """MatNexus 에서 고친 이름을 가져오기가 조용히 되돌리면, 고친 사람은
        영문을 모른다. 갱신은 부서 관리 화면에서 한다."""
        client.post(
            "/api/workspaces",
            json={"slug": "rnd", "name": "우리가 고친 이름"},
            headers=admin_headers,
        )
        result = send(client, admin_headers, TREE, preview=False)
        assert result["created"] == 3
        kept = db.scalar(select(Workspace).where(Workspace.slug == "rnd"))
        assert kept is not None and kept.name == "우리가 고친 이름"
        # 자식은 **기존 부서 아래로** 붙는다 — 겹친다고 트리가 끊기면 안 된다.
        child = db.scalar(select(Workspace).where(Workspace.slug == "rnd-metal"))
        assert child is not None and child.parent_id == kept.id

    def test_두_번_올려도_두_벌이_안_된다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        send(client, admin_headers, TREE, preview=False)
        again = send(client, admin_headers, TREE, preview=False)
        assert again["created"] == 0
        assert db.scalar(select(Workspace).where(Workspace.slug == "rnd-metal")) is not None


class Test깨진_것은_오류로_남는다:
    def test_부모가_없으면_루트로_슬쩍_붙이지_않는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        body = csv_bytes(
            "child,외톨이팀,ghost,유령본부,1,유령본부 > 외톨이팀,org,active,,0,false,0,,"
            "2024-01-01"
        )
        result = send(client, admin_headers, body, preview=False)
        assert result["errors"] == 1
        assert "ghost" in result["rows"][0]["reason"]
        assert db.scalar(select(Workspace).where(Workspace.slug == "child")) is None

    def test_규칙에_안_맞는_주소는_고쳐_쓰지_않는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        """자르거나 바꾸면 두 시스템이 같은 부서를 다른 주소로 부르게 된다 —
        이 기능이 막으려는 바로 그 일이다."""
        body = csv_bytes("Bad_Slug,이상한팀,,,0,이상한팀,org,active,,0,false,0,,2024-01-01")
        result = send(client, admin_headers, body, preview=False)
        assert result["errors"] == 1
        assert db.scalar(select(Workspace).where(Workspace.name == "이상한팀")) is None

    def test_다른_CSV_는_무엇이_없는지_말하고_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        refused = client.post(
            "/api/workspaces/import/preview",
            files={"file": ("아무거나.csv", "이름,값\nA,1\n".encode(), "text/csv")},
            headers=admin_headers,
        )
        assert refused.status_code == 422, refused.text
        assert "slug" in refused.json()["error"]["message"]


class Test미리보기와_적용이_같은_답이다:
    def test_미리보기는_만들지_않는다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str]
    ) -> None:
        shown = send(client, admin_headers, TREE, preview=True)
        assert shown["created"] == 4
        assert db.scalar(select(Workspace).where(Workspace.slug == "rnd")) is None

        done = send(client, admin_headers, TREE, preview=False)
        # **같은 코드로 판정한다.** 「미리보기엔 된다더니」 가 없어야 한다.
        assert [one["action"] for one in done["rows"]] == [
            one["action"] for one in shown["rows"]
        ]
