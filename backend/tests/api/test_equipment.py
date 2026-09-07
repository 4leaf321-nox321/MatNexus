"""보유 장비 — **개체·부속·교정, 그리고 붙여넣기 등록.**

무는 것이 다섯이다.

    자산번호는 어떻게 쳐도 닿는다   `A-2019-0142` · `a20190142` 가 같은 장비
    비워 둘 수 있되 겹치면 안 된다   스티커 없는 장비가 여럿, 같은 번호는 하나
    사업부는 부모를 타고 나온다     장비에 사업부를 안 적는다
    붙여넣기는 드라이런이 기본       오타 하나가 새 조직을 만든다
    가리키는 것이 있으면 못 지운다   폐기는 상태이지 삭제가 아니다
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.equipment.models import EquipmentUnit
from app.modules.vocabulary.models import Vocabulary, VocabularyTerm

UNITS = "/api/equipment/units"


def term(
    db: Session, slug: str, value: str, parent: VocabularyTerm | None = None
) -> VocabularyTerm:
    axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == slug))
    assert axis is not None, f"'{slug}' 축이 없습니다 — 기본 축 시딩을 보세요."
    row = VocabularyTerm(
        vocabulary_id=axis.id,
        value=value,
        normalized=value.lower(),
        parent_term_id=parent.id if parent else None,
    )
    db.add(row)
    db.commit()
    return row


def make(client: TestClient, headers: dict[str, str], **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"name": "생기연 DMA"}
    body.update(over)
    made = client.post(UNITS, json=body, headers=headers)
    assert made.status_code == 201, made.text
    got: dict[str, Any] = made.json()
    return got


class Test자산번호:
    def test_어떻게_쳐도_같은_장비에_닿는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**스티커를 보고 치는 것이라 표기가 갈린다.**

        하이픈·공백·대소문자가 사람마다 다르다. 정규화 열에 등호로 붙이므로
        유니크 색인을 그대로 탄다 — `ILIKE` 로 훑지 않는다.
        """
        made = make(client, admin_headers, asset_no="A-2019-0142")
        for typed in ("A-2019-0142", "a20190142", "A 2019 0142", "a-2019-0142"):
            found = client.get(UNITS, params={"q": typed}, headers=admin_headers)
            assert found.status_code == 200
            ids = [item["id"] for item in found.json()["items"]]
            assert ids == [made["id"]], f"'{typed}' 로 못 찾았습니다."

    def test_비워_둘_수_있다(self, client: TestClient, admin_headers: dict[str, str]) -> None:
        """**스티커 없는 장비를 못 넣게 하면 가짜 번호를 지어낸다.**

        NULL 은 유일 제약에서 빠지므로 여럿이어도 된다.
        """
        make(client, admin_headers, name="대형 챔버")
        make(client, admin_headers, name="소형 챔버")
        got = client.get(UNITS, headers=admin_headers).json()
        assert got["total"] == 2

    def test_같은_번호는_거절한다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        make(client, admin_headers, asset_no="A-1")
        again = client.post(
            UNITS, json={"name": "다른 장비", "asset_no": "a1"}, headers=admin_headers
        )
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "MNX-EQUIPMENT-0003"


class Test이름으로_찾기:
    def test_부분_일치로_찾힌다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**사람은 「DMA」 를 치고 「생기연 DMA」 를 찾는다.**"""
        make(client, admin_headers, name="생기연 DMA")
        make(client, admin_headers, name="대형 챔버")
        found = client.get(UNITS, params={"q": "DMA"}, headers=admin_headers).json()
        assert [item["name"] for item in found["items"]] == ["생기연 DMA"]


class Test조직은_부서에서_온다:
    """**기준정보에 조직 축을 두지 않는다.**

    부서가 이미 조직 트리다(`Workspace.parent_id`: *"본부 아래 팀이 있고, 같은
    이름의 팀이 본부마다 있을 수 있다"*). 축을 하나 더 두면 같은 조직이 두 목록에
    쌓이고 합칠 방법이 없다 — 실제로 한 번 그렇게 만들었다가 걷어냈다.
    """

    def test_상위_조직은_부서_트리를_타고_나온다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session, workspace: Any
    ) -> None:
        """**장비에 상위 조직을 안 적는다.** 부모를 타고 올라가서 낸다."""
        from app.modules.workspaces.models import Workspace

        team = Workspace(slug="lab-eng", name="생기연", parent_id=workspace.id)
        db.add(team)
        db.commit()
        made = make(client, admin_headers, workspace=team.slug)
        assert made["org"]["label"] == "생기연"
        assert made["org"]["root_label"] == "금속재료팀", "꼭대기가 함께 와야 한다"

    def test_현황이_두_층으로_나온다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session, workspace: Any
    ) -> None:
        from app.modules.workspaces.models import Workspace

        first = Workspace(slug="lab-a", name="생기연", parent_id=workspace.id)
        second = Workspace(slug="lab-b", name="재료연구팀", parent_id=workspace.id)
        db.add_all([first, second])
        db.commit()
        make(client, admin_headers, name="DMA", workspace=first.slug)
        make(client, admin_headers, name="UTM", workspace=second.slug)

        got = client.get("/api/equipment/summary", headers=admin_headers).json()
        by_root = {row["label"]: row["total"] for row in got["by_root_org"]}
        by_org = {row["label"]: row["total"] for row in got["by_org"]}
        assert by_root["금속재료팀"] == 2, "상위 조직에서는 둘이 합쳐진다"
        assert by_org["생기연"] == 1 and by_org["재료연구팀"] == 1

    def test_붙여넣기는_부서를_만들지_않는다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """기준정보는 없으면 만들지만 **부서는 권한이 붙는 자리다.**"""
        got = client.post(
            f"{UNITS}/bulk",
            json={"dry_run": False, "rows": [{"name": "새 DMA", "workspace": "없는팀"}]},
            headers=admin_headers,
        ).json()
        assert got["errors"] == 1
        assert "부서가 없습니다" in got["rows"][0]["reason"]


class Test상태:
    def test_폐기는_목록에서_빠지되_행은_산다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """**폐기는 삭제가 아니다** — 지난 시험이 그 장비를 가리킨다."""
        made = make(client, admin_headers, name="옛 UTM")
        client.patch(
            f"{UNITS}/{made['id']}", json={"status": "retired"}, headers=admin_headers
        )

        listed = client.get(UNITS, headers=admin_headers).json()
        assert listed["total"] == 0, "기본 목록에서는 빠진다"
        only = client.get(UNITS, params={"status": "retired"}, headers=admin_headers).json()
        assert only["total"] == 1, "골라 보면 나온다"
        assert db.get(EquipmentUnit, made["id"]) is not None


class Test부분_수정:
    def test_안_보낸_칸은_그대로다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**안 구별하면 이름만 고쳐 저장할 때마다 나머지가 지워진다**(AGENTS.md)."""
        made = make(client, admin_headers, owner_name="김OO", location_detail="3번 벤치")
        after = client.patch(
            f"{UNITS}/{made['id']}", json={"name": "생기연 DMA 2호"}, headers=admin_headers
        ).json()
        assert after["owner_name"] == "김OO"
        assert after["location_detail"] == "3번 벤치"

    def test_null_을_보내면_지운다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        made = make(client, admin_headers, owner_name="김OO")
        after = client.patch(
            f"{UNITS}/{made['id']}", json={"owner_name": None}, headers=admin_headers
        ).json()
        assert after["owner_name"] is None


class Test교정:
    def test_이력이_쌓이고_최근_것이_목록에_실린다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**목록에서 만료를 보려면 최근 교정이 함께 와야 한다** — 장비마다 따로
        부르면 목록 한 장에 N+1 이 난다."""
        made = make(client, admin_headers)
        for done, until in (("2025-03-10", "2026-03-09"), ("2026-03-15", "2027-03-14")):
            added = client.post(
                f"{UNITS}/{made['id']}/calibrations",
                json={"performed_on": done, "valid_until": until, "agency": "KOLAS"},
                headers=admin_headers,
            )
            assert added.status_code == 201, added.text

        got = client.get(f"{UNITS}/{made['id']}", headers=admin_headers).json()
        assert got["last_calibrated_on"] == "2026-03-15", "최근 것이 실린다"
        assert got["calibration_valid_until"] == "2027-03-14"

        history = client.get(
            f"{UNITS}/{made['id']}/calibrations", headers=admin_headers
        ).json()
        assert len(history) == 2, "이력이라 덮이지 않는다"

    def test_유효기간이_교정일보다_앞설_수_없다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        made = make(client, admin_headers)
        bad = client.post(
            f"{UNITS}/{made['id']}/calibrations",
            json={"performed_on": "2026-03-15", "valid_until": "2026-03-14"},
            headers=admin_headers,
        )
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "MNX-EQUIPMENT-0006"

    def test_만료_임박만_골라_본다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**기간이 없는 것은 여기 안 넣는다** — 「모른다」 를 「만료」 로 읽으면
        멀쩡한 장비가 목록을 채운다."""
        soon = make(client, admin_headers, name="곧 만료")
        later = make(client, admin_headers, name="한참 남음")
        unknown = make(client, admin_headers, name="기간 모름")
        today = date.today()
        client.post(
            f"{UNITS}/{soon['id']}/calibrations",
            json={"performed_on": str(today), "valid_until": str(today + timedelta(days=5))},
            headers=admin_headers,
        )
        client.post(
            f"{UNITS}/{later['id']}/calibrations",
            json={"performed_on": str(today), "valid_until": str(today + timedelta(days=300))},
            headers=admin_headers,
        )
        client.post(
            f"{UNITS}/{unknown['id']}/calibrations",
            json={"performed_on": str(today)},
            headers=admin_headers,
        )
        got = client.get(UNITS, params={"calibration_due": True}, headers=admin_headers).json()
        assert [item["name"] for item in got["items"]] == ["곧 만료"]


class Test부속:
    def test_장비를_지우면_함께_지워진다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """부속은 장비를 떠나 따로 살지 않는다."""
        made = make(client, admin_headers)
        added = client.post(
            f"{UNITS}/{made['id']}/parts",
            json={"kind": "load_cell", "label": "50kN 로드셀", "capacity": "50 kN"},
            headers=admin_headers,
        )
        assert added.status_code == 201, added.text
        assert (
            client.get(f"{UNITS}/{made['id']}", headers=admin_headers).json()["part_count"]
            == 1
        )

        gone = client.delete(f"{UNITS}/{made['id']}", headers=admin_headers)
        assert gone.status_code == 204
        assert client.get(f"{UNITS}/{made['id']}", headers=admin_headers).status_code == 404


class Test붙여넣기:
    def test_드라이런이_기본이고_새_기준정보를_미리_말한다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        """**오타 하나가 새 조직을 만든다.** 그것이 이 화면에서 가장 흔한 사고다."""
        got = client.post(
            f"{UNITS}/bulk",
            json={
                "rows": [
                    {"name": "생기연 DMA", "asset_no": "A-1", "instrument_type": "DMA"},
                    {"name": "대형 챔버", "asset_no": "A-2", "lab": "2공장 3층"},
                ]
            },
            headers=admin_headers,
        ).json()
        assert got["dry_run"] is True
        assert got["created"] == 2
        made = {one for row in got["rows"] for one in row["new_terms"]}
        assert made == {"장비 유형: DMA", "시험실: 2공장 3층"}
        assert db.scalar(select(EquipmentUnit)) is None, "드라이런은 아무것도 안 쓴다"

    def test_적용하면_기준정보까지_만들어진다(
        self, client: TestClient, admin_headers: dict[str, str], db: Session
    ) -> None:
        got = client.post(
            f"{UNITS}/bulk",
            json={
                "dry_run": False,
                "rows": [{"name": "생기연 DMA", "asset_no": "A-1", "lab": "2공장 3층"}],
            },
            headers=admin_headers,
        ).json()
        assert got["created"] == 1 and got["dry_run"] is False
        unit = db.scalar(select(EquipmentUnit))
        assert unit is not None
        assert unit.lab == "2공장 3층", "문자열 짝이 채워진다"
        assert unit.lab_term_id is not None, "FK 도 함께 — apply_bindings 가 한다"

    def test_이미_있는_자산번호는_건너뛴다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        make(client, admin_headers, asset_no="A-1")
        got = client.post(
            f"{UNITS}/bulk",
            json={"dry_run": False, "rows": [{"name": "또 그 장비", "asset_no": "a1"}]},
            headers=admin_headers,
        ).json()
        assert got["skipped"] == 1 and got["created"] == 0


class Test권한:
    def test_읽기는_모두가_쓰기는_관리자가(
        self, client: TestClient, db: Session, workspace: Any, admin_headers: dict[str, str]
    ) -> None:
        """**장비 목록은 실험하는 사람이 매일 본다** — 관리 메뉴에 숨으면 못 찾는다.

        고치는 것은 부서 관리자다(데이터 체계 그룹의 다른 화면들과 같은 모양).
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

        assert client.get(UNITS, headers=headers).status_code == 200
        blocked = client.post(UNITS, json={"name": "새 장비"}, headers=headers)
        assert blocked.status_code == 403, blocked.text
        assert blocked.json()["error"]["code"] == "MNX-EQUIPMENT-0001"
