"""시험 업로드 → 파싱 → 곡선.

실제 Zwick 파일(`tests/fixtures/Example.tra`)로 끝에서 끝까지 돌린다. 합성 데이터로
만들면 "우리가 만든 형식을 우리가 읽는" 순환이 되어, 장비가 실제로 뱉는 것과
어긋나도 초록으로 남는다.

지키려는 것:
  - 업로드는 파일만 받고 끝난다(202). 파싱은 워커가 한다
  - 파싱 실패는 재시도하지 않고 이유를 남긴다 — 같은 바이트는 다시 읽어도 같다
  - 정의(TestChannel)에 없는 필수 채널이 빠지면 조용히 반쪽 곡선을 만들지 않는다
  - 저장은 SI, 원본은 그대로 보관
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs import kinds
from app.jobs.models import Job
from app.modules.tests import services
from app.modules.tests.definitions import ensure_builtin_test_types
from app.modules.tests.models import Curve, TestRun, TestSummary

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"


@pytest.fixture
def tensile(db: Session) -> None:
    ensure_builtin_test_types(db)
    db.commit()


@pytest.fixture
def specimen(client: TestClient, admin_headers: dict[str, str]) -> dict[str, Any]:
    material = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": "SECC",
            "details": "MDOI",
            "spec_thickness": 1.0,
        },
        headers=admin_headers,
    ).json()
    sample = client.post(
        f"/api/materials/{material['id']}/samples", json={}, headers=admin_headers
    ).json()
    created: dict[str, Any] = client.post(
        f"/api/samples/{sample['id']}/specimens",
        json={"orientation": "MD"},
        headers=admin_headers,
    ).json()
    return created


def _upload(
    client: TestClient,
    headers: dict[str, str],
    specimen_id: str,
    *,
    content: bytes | None = None,
    filename: str = "Example.tra",
    conditions: str = "{}",
    division: str | None = None,
) -> Any:
    data = {
        "specimen_id": specimen_id,
        "test_type": "tensile",
        "conditions": conditions,
    }
    if division is not None:
        data["division"] = division
    return client.post(
        "/api/test-runs",
        data=data,
        files={"file": (filename, content if content is not None else TRA.read_bytes())},
        headers=headers,
    )


class TestDefinitions:
    def test_정의가_채널과_조건을_함께_준다(
        self, client: TestClient, admin_headers: dict[str, str], tensile: None
    ) -> None:
        """화면이 이 응답만으로 업로드 폼을 그릴 수 있어야 한다(수준 2)."""
        response = client.get("/api/test-types", headers=admin_headers)
        assert response.status_code == 200, response.text
        types = response.json()

        # **읽을 수 있는 것만 넣는다.** 처음 규율은 "파서가 있는 것만" 이었는데,
        # 형식 프로파일이 생기면서 넓어졌다 — DMA 는 전용 파서 없이 프로파일로
        # 읽힌다(ADR 0005). 정의만 있고 못 읽는 종류가 목록에 보이면 사용자가
        # 올렸다가 실패하므로, 그 선은 그대로다.
        assert [t["key"] for t in types] == ["tensile", "dma_sweep"]
        dma_type = next(t for t in types if t["key"] == "dma_sweep")
        assert dma_type["parser_key"] is None  # 프로파일이 읽는다
        assert {"storage_modulus", "loss_modulus"} <= {c["key"] for c in dma_type["channels"]}

        tensile_type = types[0]
        assert tensile_type["parser_key"] == "zwick_tra"
        assert [c["key"] for c in tensile_type["channels"]] == [
            "displacement",
            "force",
            "specimen_width",
        ]
        assert {c["si_unit"] for c in tensile_type["channels"]} == {"m", "N"}
        assert "temperature" in {c["key"] for c in tensile_type["conditions"]}
        # 정의가 비면 **저장된 값은 비고** 실효값에만 전역값이 채워진다. 한 칸에
        # 섞어 두면 화면이 되돌려 보낼 값을 잃는다 — §11 참조.
        assert tensile_type["max_upload_bytes"] is None
        assert tensile_type["max_upload_bytes_effective"] > 0


class TestUpload:
    def test_업로드는_파일만_받고_끝난다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        response = _upload(client, admin_headers, specimen["id"])
        assert response.status_code == 202, response.text
        run = response.json()

        assert run["record_name"] == "SECC_MDOI_1.0__01__MD_01__TEN_01"
        assert run["status"] == "uploaded"  # 아직 파싱 전이다
        assert run["source_filename"] == "Example.tra"
        assert run["source_bytes"] == TRA.stat().st_size
        assert run["row_count"] is None

        job = db.scalar(select(Job).where(Job.kind == kinds.TESTS_PARSE_UPLOAD))
        assert job is not None
        assert job.payload["test_run_id"] == run["id"]

    def test_정의에_없는_조건은_거절한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """조용히 버리면 오타로 넣은 조건이 사라진 줄 모르고 저장된다."""
        response = _upload(
            client, admin_headers, specimen["id"], conditions='{"temprature": 25}'
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "MNX-TESTS-0004"

    def test_조건_숫자는_SI_로_저장된다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        response = _upload(
            client, admin_headers, specimen["id"], conditions='{"temperature": 25}'
        )
        assert response.status_code == 202, response.text
        run = db.get(TestRun, uuid.UUID(response.json()["id"]))
        assert run is not None
        # 정의상 온도의 SI 단위는 K 다. 25 를 그대로 두면 25K(-248℃)가 된다.
        assert run.conditions["temperature"] == pytest.approx(25.0)
        assert run.input_units["temperature"] == "K"

    def test_화면이_쓴_단위로_환산한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """**실제로 6만 배 어긋났던 자리다.**

        `speed_elastic` 의 정의상 SI 단위는 `m/s` 인데, 화면은 사람이 쓰는
        `mm/min` 으로 라벨을 붙여 놓고 값은 그대로 보냈다. 서버가 그것을 m/s 로
        해석해 10 을 10 m/s 로 저장했지만 사용자가 뜻한 것은 10 mm/min 이었다.
        숫자가 그럴듯해서 화면 어디에도 티가 나지 않는다.
        """
        response = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "tensile",
                "conditions": '{"speed_elastic": 10}',
                "condition_units": '{"speed_elastic": "mm/min"}',
            },
            files={"file": ("Example.tra", TRA.read_bytes())},
            headers=admin_headers,
        )
        assert response.status_code == 202, response.text

        run = db.get(TestRun, uuid.UUID(response.json()["id"]))
        assert run is not None
        assert run.conditions["speed_elastic"] == pytest.approx(10 / 60000)
        assert run.input_units["speed_elastic"] == "mm/min"  # 무엇으로 받았는지 남는다

    def test_차원이_다른_단위는_거절한다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """계수만 맞으면 통과시키는 변환은 위험하다 — `mm` 과 `ms` 는 둘 다 0.001 이다."""
        response = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen["id"],
                "test_type": "tensile",
                "conditions": '{"temperature": 25}',
                "condition_units": '{"temperature": "mm"}',
            },
            files={"file": ("Example.tra", TRA.read_bytes())},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "MNX-TESTS-0014"

    def test_단위를_안_보내면_정의의_SI_로_본다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        response = _upload(
            client, admin_headers, specimen["id"], conditions='{"temperature": 298.15}'
        )
        assert response.status_code == 202, response.text
        run = db.get(TestRun, uuid.UUID(response.json()["id"]))
        assert run is not None
        assert run.conditions["temperature"] == pytest.approx(298.15)

    def test_중복_파일_안내가_응답에_실린다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """서버는 sha256 으로 알고 있었는데 응답에 실을 곳이 없어 사용자는 몰랐다."""
        first = _upload(client, admin_headers, specimen["id"])
        assert first.json()["note"] is None

        second = _upload(client, admin_headers, specimen["id"])
        assert "이미" in (second.json()["note"] or "")

    def test_한도를_넘으면_받는_도중에_멈춘다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        from app.modules.tests.models import TestType

        test_type = db.scalar(select(TestType).where(TestType.key == "tensile"))
        assert test_type is not None
        test_type.max_upload_bytes = 100
        db.commit()

        response = _upload(client, admin_headers, specimen["id"], content=b"x" * 5000)
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "MNX-FILES-0001"


class TestWorkspaceScope:
    def test_부서로_좁힌다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """사이드바가 `/w/:slug/tests` 라고 말하는 화면이므로 그 부서 것만
        보여야 한다. 가시 범위(볼 권한)와 기본 필터(무엇을 먼저 보여줄까)는
        다른 축이다 — 둘을 섞으면 '부서' 라는 말이 거짓이 된다."""
        _upload(client, admin_headers, specimen["id"])

        from app.modules.workspaces.models import Workspace

        other = Workspace(slug="polymer", name="고분자팀")
        db.add(other)
        db.commit()

        assert client.get("/api/test-runs", headers=admin_headers).json()["total"] == 1
        mine = client.get("/api/test-runs?workspace=metal", headers=admin_headers)
        assert mine.json()["total"] == 1
        theirs = client.get("/api/test-runs?workspace=polymer", headers=admin_headers)
        assert theirs.json()["total"] == 0

    def test_없는_부서는_알려_준다(
        self, client: TestClient, admin_headers: dict[str, str], tensile: None
    ) -> None:
        response = client.get("/api/test-runs?workspace=nowhere", headers=admin_headers)
        assert response.status_code == 404


class TestAdoptedFilter:
    """**"올렸는데 아직 아무것도 안 한 것"** 을 서버가 센다.

    부서 홈이 "처리 대기 N건" 을 말한다. 목록을 받아 화면이 세면 상한(`limit`)에
    걸린 순간 숫자가 조용히 틀린다 — 100건까지만 세고 101건째부터는 없는 셈이
    되는데, 화면에는 그냥 "100" 이라고 적힌다.
    """

    def test_채택_여부로_가른다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        runs = [_upload(client, admin_headers, specimen["id"]).json() for _ in range(2)]
        assert services.parse_run(db, uuid.UUID(runs[0]["id"])) == "parsed"
        stored = client.post(
            "/api/processing/results",
            json={
                "test_run_id": runs[0]["id"],
                "steps": [
                    {
                        "plugin": "tensile.engineering",
                        "options": {"gauge_length": 0.05, "area": 12.12e-6},
                    }
                ],
            },
            headers=admin_headers,
        ).json()
        client.post(f"/api/processing/results/{stored['id']}/adopt", headers=admin_headers)

        def total(query: str) -> int:
            body = client.get(f"/api/test-runs{query}", headers=admin_headers).json()
            return int(body["total"])

        assert total("") == 2
        assert total("?adopted=true") == 1
        assert total("?adopted=false") == 1

    def test_안_주면_안_거른다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """**빠뜨린 값이 필터가 되면 안 된다.** 기존 화면들이 이 인자를 안 준다."""
        _upload(client, admin_headers, specimen["id"])
        body = client.get("/api/test-runs", headers=admin_headers).json()
        assert body["total"] == 1


class TestParsing:
    def _parse(self, db: Session, run_id: str) -> TestRun:
        assert services.parse_run(db, uuid.UUID(run_id)) == "parsed"
        run = db.get(TestRun, uuid.UUID(run_id))
        assert run is not None
        db.refresh(run)
        return run

    def test_실제_장비파일을_읽어_곡선과_요약값을_만든다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        created = _upload(client, admin_headers, specimen["id"]).json()
        run = self._parse(db, created["id"])

        assert run.status == "parsed"
        assert run.parse_error is None
        # 무엇으로 읽었는지 남는다 — 프로파일과 플러그인 중 어느 쪽인지가
        # 나중에 "이 곡선을 왜 이렇게 읽었나" 를 답하는 유일한 단서다.
        assert run.parser_version == "zwick_tra:1"
        # 장비가 준 시편 치수는 결과가 아니라 입력이라 metadata 로 간다
        assert run.source_metadata["specimen_thickness_a0"] == "0.986"

        curve = db.scalar(select(Curve).where(Curve.test_run_id == run.id))
        assert curve is not None
        assert curve.row_count == 18
        assert curve.channels == ["displacement", "force", "specimen_width"]
        assert curve.byte_size > 0

        summary = {
            s.key: s
            for s in db.scalars(select(TestSummary).where(TestSummary.test_run_id == run.id))
        }
        assert all(s.source == "instrument" for s in summary.values())
        # 282.128 MPa -> Pa. 파일의 이름은 'Force maximum' 이지만 단위가 MPa 이고
        # 실제로 Fmax/A0 와 0.1% 안에서 맞는다 — 힘이 아니라 인장강도다.
        assert summary["tensile_strength"].value_num == pytest.approx(282_128_000.0)
        # 장비가 못 구한 값은 숫자 칸을 비우고 사실만 남긴다
        assert summary["yield_strain"].value_num is None
        assert summary["yield_strain"].value_text == "Unknown"

    def test_센서가_놓친_구간을_경고로_남긴다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """실측: 마지막 두 행의 Specimen width 가 0 이다(파단 후 센서 상실).

        진응력은 폭으로 나눈다. 경고 없이 계산하면 마지막 두 점이 무한대가 된다.
        """
        created = _upload(client, admin_headers, specimen["id"]).json()
        run = self._parse(db, created["id"])
        assert "specimen_width" in run.source_metadata["_warnings"]

        detail = client.get(f"/api/test-runs/{run.id}", headers=admin_headers).json()
        assert len(detail["warnings"]) == 1
        assert "_warnings" not in detail["source_metadata"]  # 경고는 따로 보여 준다

    def test_읽을_수_없는_파일은_이유를_남기고_재시도하지_않는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        created = _upload(
            client, admin_headers, specimen["id"], content=b"this is not a tra file\n"
        ).json()

        # 예외를 던지지 않는다 — 던지면 워커가 같은 바이트로 재시도만 반복한다.
        assert services.parse_run(db, uuid.UUID(created["id"])) == "failed"
        run = db.get(TestRun, uuid.UUID(created["id"]))
        assert run is not None
        assert run.status == "failed"
        assert "Zwick" in (run.parse_error or "")
        assert db.scalar(select(Curve).where(Curve.test_run_id == run.id)) is None

    def test_필수_채널이_빠지면_실패한다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """정의를 데이터로 둔 값이 여기서 나온다 — 장비 설정이 바뀌어 채널이
        빠지면 곡선이 조용히 반쪽이 되는 대신 등록이 실패한다."""
        without_force = b""""Standard extensometer","Specimen width"
"mm","mm"
0.1,12.4
0.2,12.3
0.3,12.2
"""
        created = _upload(client, admin_headers, specimen["id"], content=without_force).json()
        assert services.parse_run(db, uuid.UUID(created["id"])) == "failed"
        run = db.get(TestRun, uuid.UUID(created["id"]))
        assert run is not None
        assert "force" in (run.parse_error or "")

    def test_지워진_시험은_조용히_넘어간다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        created = _upload(client, admin_headers, specimen["id"]).json()
        client.delete(f"/api/test-runs/{created['id']}", headers=admin_headers)
        assert services.parse_run(db, uuid.UUID(created["id"])) == "gone"


class TestCurve:
    def test_축약해서_준다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        created = _upload(client, admin_headers, specimen["id"]).json()
        services.parse_run(db, uuid.UUID(created["id"]))

        response = client.get(
            f"/api/test-runs/{created['id']}/curve?max_points=10", headers=admin_headers
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["x"] == "displacement" and body["y"] == "force"  # 정의 순서
        assert body["row_count"] == 18  # 원본 행 수는 축약과 무관하게 그대로 알려 준다
        # `max_points` 는 상한이지 목표가 아니다. 빈 버킷이 생기면 그만큼 적게
        # 준다 — 같은 점을 두 번 넣어 개수를 맞추면 실제 점은 하나 적어진다.
        assert body["returned"] == len(body["points"]) <= 10
        assert len({tuple(p) for p in body["points"]}) == len(body["points"])

    def test_없는_채널을_달라고_하면_알려_준다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        created = _upload(client, admin_headers, specimen["id"]).json()
        services.parse_run(db, uuid.UUID(created["id"]))
        response = client.get(
            f"/api/test-runs/{created['id']}/curve?x=displacement&y=stress",
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "stress" in response.json()["error"]["message"]

    def test_원본을_그대로_내려받는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """파서가 못 읽었을 때 사람이 열어 봐야 한다."""
        created = _upload(client, admin_headers, specimen["id"]).json()
        response = client.get(f"/api/test-runs/{created['id']}/source", headers=admin_headers)
        assert response.status_code == 200
        assert response.content == TRA.read_bytes()


class TestStorageCleanup:
    """치울 것이 **세 종류**다. 하나만 다루면 나머지가 영원히 쌓인다."""

    def test_DB_에_없는_폴더를_찾는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """**방향이 중요하다.** DB 를 훑어서는 오펀을 찾을 수 없다 — 오펀은
        정의상 DB 에 없다.

        기준선을 먼저 재는 이유: 앞선 테스트들이 남긴 파일이 이미 오펀이다.
        테스트는 테이블을 비우지만 파일은 지우지 않으므로, 이 잡이 실제로 필요한
        상황이 매 실행마다 재현된다.
        """
        from app.shared import filestore

        def orphan_paths() -> set[str]:
            return {str(item["path"]) for item in services.storage_report(db)["orphans"]}

        baseline = orphan_paths()

        created = _upload(client, admin_headers, specimen["id"]).json()
        run = db.get(TestRun, uuid.UUID(created["id"]))
        assert run is not None
        directory = filestore.run_dir(run.id, run.created_at)

        assert directory not in orphan_paths()  # 행이 살아 있으면 오펀이 아니다

        db.delete(run)
        db.commit()
        assert orphan_paths() - baseline == {directory}

        removed = services.cleanup_storage(db, dry_run=False)
        assert directory in removed["removed"]
        assert directory not in orphan_paths()

    def test_소프트_삭제는_보존기간이_지나야_지운다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """**셋 중 가장 큰 구멍이었다.** 소프트 삭제는 행을 남기므로 그 파일은
        오펀 탐색으로 영원히 안 잡힌다. 실측(2026-08-15): 지운 시험 2건의 파일이
        그대로 남아 있었고 치울 경로가 아예 없었다.
        """
        from app.shared import filestore

        created = _upload(client, admin_headers, specimen["id"]).json()
        services.parse_run(db, uuid.UUID(created["id"]))
        run = db.get(TestRun, uuid.UUID(created["id"]))
        assert run is not None
        directory = filestore.run_dir(run.id, run.created_at)

        client.delete(f"/api/test-runs/{created['id']}", headers=admin_headers)
        db.expire_all()

        # 방금 지운 것은 아직 보존기간 안이라 건드리지 않는다
        report = services.storage_report(db)
        assert directory not in {str(item["path"]) for item in report["expired"]}
        assert directory not in {str(item["path"]) for item in report["orphans"]}

        # 보존기간이 0 이면 대상이 된다
        expired = services.storage_report(db, retention_days=0)
        assert directory in {str(item["path"]) for item in expired["expired"]}

        result = services.cleanup_storage(db, dry_run=False, retention_days=0)
        assert directory in result["removed"]

        # **행은 남는다.** 옛 보고서에 적힌 이름이 무엇이었는지 답할 수 있어야 한다.
        db.expire_all()
        survivor = db.get(TestRun, uuid.UUID(created["id"]))
        assert survivor is not None
        assert survivor.record_name
        assert survivor.source_path is None  # 가리키던 파일이 없어졌다
        assert "보존기간" in (survivor.note or "")
        assert db.scalar(select(Curve).where(Curve.test_run_id == survivor.id)) is None

    def test_미리보기는_아무것도_지우지_않는다(
        self,
        client: TestClient,
        db: Session,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """되돌릴 수 없는 작업이라 기본이 안전한 쪽이다."""
        from app.shared import filestore

        created = _upload(client, admin_headers, specimen["id"]).json()
        run = db.get(TestRun, uuid.UUID(created["id"]))
        assert run is not None
        directory = filestore.run_dir(run.id, run.created_at)
        db.delete(run)
        db.commit()

        preview = services.cleanup_storage(db, dry_run=True)
        assert preview["removed"] == []
        assert preview["reclaimable_bytes"] > 0
        assert filestore.resolve(directory).is_dir()  # 아직 있다

    def test_정리를_큐에_넣는_경로가_있다(
        self, client: TestClient, db: Session, admin_headers: dict[str, str], tensile: None
    ) -> None:
        """**실행 경로가 없으면 만들어 둔 잡은 없는 것과 같다.** 핸들러만 등록해
        두고 큐에 넣는 곳을 안 만들어서, 한 번도 돌지 않은 채 파일이 쌓였다."""
        report = client.get("/api/maintenance/storage", headers=admin_headers)
        assert report.status_code == 200, report.text
        assert report.json()["retention_days"] > 0

        queued = client.post(
            "/api/maintenance/cleanup", json={"dry_run": True}, headers=admin_headers
        )
        assert queued.status_code == 202
        assert queued.json()["dry_run"] is True

        job = db.scalar(select(Job).where(Job.kind == kinds.TESTS_CLEANUP_STORAGE))
        assert job is not None
        assert job.payload["dry_run"] is True

    def test_일반_사용자는_저장소를_볼_수_없다(
        self, client: TestClient, db: Session, tensile: None
    ) -> None:
        """파일 경로는 서버 내부 구조다. 관리자만 본다."""
        from app.modules.accounts.models import User
        from app.modules.auth import security
        from app.modules.workspaces.models import Workspace

        workspace = db.scalar(select(Workspace))
        member = User(
            email="member",
            password_hash=security.hash_password("member-password-1"),
            display_name="일반 사용자",
            status="active",
            is_system_admin=False,
            home_workspace_id=workspace.id if workspace else None,
        )
        db.add(member)
        db.commit()

        token = client.post(
            "/api/auth/login", json={"email": "member", "password": "member-password-1"}
        ).json()["access_token"]
        response = client.get(
            "/api/maintenance/storage", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403


class Test목록_거르기와_여러_건_삭제:
    """실사용에서 나온 셋.

    *"등록한 사람도 나오게 해줘"* · *"각 열에 필터"* · *"체크박스로 고른 것을
    한꺼번에 삭제"*.
    """

    @pytest.fixture
    def parsed(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        db: Session,
        tensile: None,
        specimen: dict[str, Any],
    ) -> dict[str, Any]:
        """올려서 읽힌 시험 하나."""
        del tensile
        made = _upload(client, admin_headers, specimen["id"])
        assert made.status_code == 202, made.text
        run: dict[str, Any] = made.json()
        assert services.parse_run(db, uuid.UUID(run["id"])) == "parsed"
        return run

    def test_등록한_사람이_목록에_실린다(
        self, client: TestClient, admin_headers: dict[str, str], parsed: dict[str, Any]
    ) -> None:
        """**파일이 이상할 때 물어볼 데가 거기다.** 전에는 상세를 열어야 알 수
        있었고, 20건이 이상하면 20번 열어야 했다."""
        assert parsed
        body = client.get("/api/test-runs", headers=admin_headers).json()
        assert body["items"], body
        assert body["items"][0]["registered_by"]

    def test_열로_거른다(
        self, client: TestClient, admin_headers: dict[str, str], parsed: dict[str, Any]
    ) -> None:
        """**거르는 일은 서버가 한다.** 한 쪽만 받아 화면에서 거르면 뒤엣것이
        없는 시험이 된다."""
        assert parsed
        got = client.get("/api/test-runs?test_type_key=tensile", headers=admin_headers).json()
        assert got["total"] >= 1
        none = client.get(
            "/api/test-runs?test_type_key=없는종류", headers=admin_headers
        ).json()
        # **필터를 무시하고 전부 주면 안 된다.** 그러면 화면이 「이 종류에
        # 이만큼 있다」고 말하게 된다.
        assert none["total"] == 0

    def test_거를_수_있는_것과_그_수를_준다(
        self, client: TestClient, admin_headers: dict[str, str], parsed: dict[str, Any]
    ) -> None:
        assert parsed
        found = client.get("/api/test-runs/facets", headers=admin_headers)
        assert found.status_code == 200, found.text
        body = found.json()
        assert any(row["key"] == "tensile" for row in body["test_types"])
        assert body["registrants"], body
        assert body["statuses"], body

    def test_개수는_한_쪽이_아니라_전체를_센다(
        self, client: TestClient, admin_headers: dict[str, str], parsed: dict[str, Any]
    ) -> None:
        """화면이 한 쪽에서 세면 「인장시험 1」이라고 적히는데 실제로는 여러
        건이다 — **필터 옆의 숫자가 거짓말을 하면 필터 자체를 못 믿는다.**"""
        assert parsed
        page = client.get("/api/test-runs?limit=1", headers=admin_headers).json()
        assert len(page["items"]) == 1
        body = client.get("/api/test-runs/facets", headers=admin_headers).json()
        counted = {row["key"]: row["count"] for row in body["test_types"]}
        assert counted["tensile"] == page["total"]

    def test_여러_건을_한_번에_지운다(
        self, client: TestClient, admin_headers: dict[str, str], parsed: dict[str, Any]
    ) -> None:
        listed = client.get("/api/test-runs", headers=admin_headers).json()
        ids = [row["id"] for row in listed["items"]]
        assert ids

        done = client.post(
            "/api/test-runs/delete", json={"run_ids": ids}, headers=admin_headers
        )
        assert done.status_code == 200, done.text
        assert done.json()["deleted"] == len(ids)
        assert done.json()["blocked"] == []

        after = client.get("/api/test-runs", headers=admin_headers).json()
        assert after["total"] == 0

    def test_못_지운_것을_이름으로_돌려준다(
        self, client: TestClient, admin_headers: dict[str, str], parsed: dict[str, Any]
    ) -> None:
        """**한 건이 막혔다고 나머지를 되돌리지 않는다.** 20건을 골라 지우는데
        하나가 권한 밖이라 전부 실패하면, 사람은 어느 것이 문제인지 모른 채
        다시 골라야 한다."""
        listed = client.get("/api/test-runs", headers=admin_headers).json()
        ids = [row["id"] for row in listed["items"]]
        assert ids
        ghost = "00000000-0000-0000-0000-000000000000"

        done = client.post(
            "/api/test-runs/delete", json={"run_ids": [*ids, ghost]}, headers=admin_headers
        ).json()
        assert done["deleted"] == len(ids)
        assert done["blocked"] == [ghost]


class Test사업부:
    """어느 사업부가 낸 시험인가 — **부서와 다른 축이다.**

    부서(`workspace`)는 누가 볼 수 있는가를 정하는 권한의 축이고, 사업부는
    누가 낸 데이터인가를 적는 이름표다. 한 부서 계정으로 여러 사업부의 판을
    올리는 일이 있고, 그때 부서로는 그 둘을 못 가른다.
    """

    def test_기준정보에_축이_있다(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        """**목록을 기준정보가 관리한다.** 자유 문자열이면 `전장`·`전장사업부`·
        `전장 사업부` 가 갈려서 「사업부별로 몇 건」에 답이 셋 나온다."""
        axes = {
            item["slug"]: item
            for item in client.get("/api/vocabularies", headers=admin_headers).json()
        }
        assert "division" in axes, "사업부 축이 없다"
        assert axes["division"]["label"] == "사업부"
        # 부서가 스스로 늘린다 — 관리자가 미리 다 적어 둘 수 있는 목록이 아니고,
        # 못 고르면 사람은 비워 두거나 메모에 적는다.
        assert axes["division"]["entry_policy"] == "open"

    def test_올릴_때_적고_목록에서_읽는다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        del tensile
        made = _upload(client, admin_headers, specimen["id"], division="전장  ")
        assert made.status_code == 202, made.text
        # 가운데·양끝 공백이 정리된 값이 들어간다(기준정보를 거친다).
        assert made.json()["division"] == "전장"

        listed = client.get("/api/test-runs", headers=admin_headers).json()
        assert listed["items"][0]["division"] == "전장"

    def test_표기가_갈려도_한_값이다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """이 축을 둔 이유 전부다."""
        del tensile
        for spelling in ("전장", "전장 ", " 전장"):
            assert (
                _upload(client, admin_headers, specimen["id"], division=spelling).status_code
                == 202
            )

        found = client.get(
            "/api/vocabularies/division/terms", params={"q": "전장"}, headers=admin_headers
        ).json()["items"]
        assert len(found) == 1, f"표기가 갈려 값이 여러 개 생겼다: {found}"
        assert found[0]["usage_count"] == 3

    def test_사업부로_거른다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """**거르는 일은 서버가 한다.** 한 쪽만 받아 화면에서 거르면 뒤엣것이
        없는 시험이 된다."""
        del tensile
        _upload(client, admin_headers, specimen["id"], division="전장")
        _upload(client, admin_headers, specimen["id"], division="차체")

        got = client.get("/api/test-runs?division=전장", headers=admin_headers).json()
        assert got["total"] == 1
        assert got["items"][0]["division"] == "전장"

        none = client.get("/api/test-runs?division=없는사업부", headers=admin_headers).json()
        assert none["total"] == 0

    def test_거를_수_있는_것과_그_수를_준다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """화면이 한 쪽에서 세면 필터 옆의 숫자가 거짓말을 한다."""
        del tensile
        _upload(client, admin_headers, specimen["id"], division="전장")
        _upload(client, admin_headers, specimen["id"], division="전장")
        _upload(client, admin_headers, specimen["id"])  # 안 적은 것

        body = client.get("/api/test-runs/facets", headers=admin_headers).json()
        divisions = {row["key"]: row["count"] for row in body["divisions"]}
        assert divisions == {"전장": 2}, "안 적은 것이 빈 이름으로 실렸다"

    def test_안_적어도_올라간다(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> None:
        """**모르는 것을 지어내지 않는다.** 전에 올린 시험은 사업부가 비어 있고
        그것이 맞다 — 필수로 만들면 그 시험들을 아무도 못 고친다."""
        del tensile
        made = _upload(client, admin_headers, specimen["id"])
        assert made.status_code == 202, made.text
        assert made.json()["division"] is None


class Test여러_건_한꺼번에_고치기:
    """*"선택한 시험에 속성 하나를 한 번에 적용"* — 실사용에서 나왔다.

    올릴 때 사업부를 빠뜨리면 지금까지는 **다시 올리는 수밖에** 없었다.
    """

    @pytest.fixture
    def three(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        tensile: None,
        specimen: dict[str, Any],
    ) -> list[str]:
        del tensile
        made = []
        for _ in range(3):
            response = _upload(client, admin_headers, specimen["id"])
            assert response.status_code == 202, response.text
            made.append(response.json()["id"])
        return made

    def _apply(
        self,
        client: TestClient,
        headers: dict[str, str],
        ids: list[str],
        field: str,
        value: str | None,
    ) -> Any:
        return client.post(
            "/api/test-runs/bulk-update",
            json={"run_ids": ids, "field": field, "value": value},
            headers=headers,
        )

    def test_사업부를_한_번에_맞춘다(
        self, client: TestClient, admin_headers: dict[str, str], three: list[str]
    ) -> None:
        done = self._apply(client, admin_headers, three, "division", "전장")
        assert done.status_code == 200, done.text
        assert done.json() == {"updated": 3, "unchanged": 0, "blocked": []}

        listed = client.get("/api/test-runs", headers=admin_headers).json()
        assert {row["division"] for row in listed["items"]} == {"전장"}

    def test_기준정보를_거친다(
        self, client: TestClient, admin_headers: dict[str, str], three: list[str]
    ) -> None:
        """**표기가 갈리면 안 된다.** 한 번에 스무 건을 바꾸는 자리라 오타의
        파급이 크다 — 자유 문자열이면 여기서 한 글자 틀릴 때 스무 건이 새 값을
        가리킨다."""
        self._apply(client, admin_headers, three, "division", "전장  ")

        found = client.get(
            "/api/vocabularies/division/terms", params={"q": "전장"}, headers=admin_headers
        ).json()["items"]
        assert [item["value"] for item in found] == ["전장"]
        assert found[0]["usage_count"] == 3

    def test_옮겨_가면_옛_값의_쓰는_곳이_준다(
        self, client: TestClient, admin_headers: dict[str, str], three: list[str]
    ) -> None:
        """안 줄이면 피커에 「쓰이지 않는 값」 이 남고 관리 화면이 거짓말을 한다."""
        self._apply(client, admin_headers, three, "division", "전장")
        self._apply(client, admin_headers, three, "division", "차체")

        counts = {
            item["value"]: item["usage_count"]
            for item in client.get(
                "/api/vocabularies/division/terms",
                params={"include_hidden": "true"},
                headers=admin_headers,
            ).json()["items"]
        }
        assert counts["전장"] == 0
        assert counts["차체"] == 3

    def test_비우면_지운다(
        self, client: TestClient, admin_headers: dict[str, str], three: list[str]
    ) -> None:
        self._apply(client, admin_headers, three, "division", "전장")
        done = self._apply(client, admin_headers, three, "division", "")
        assert done.json()["updated"] == 3

        listed = client.get("/api/test-runs", headers=admin_headers).json()
        assert {row["division"] for row in listed["items"]} == {None}

    def test_이미_그_값이면_안_센다(
        self, client: TestClient, admin_headers: dict[str, str], three: list[str]
    ) -> None:
        """**조용히 성공으로 세지 않는다.** 20건을 골랐는데 「17건 바꿨습니다」
        가 나오면 나머지 셋이 왜 빠졌는지 알 수 있어야 한다."""
        self._apply(client, admin_headers, three, "operator", "박")
        again = self._apply(client, admin_headers, three, "operator", "박").json()
        assert again == {"updated": 0, "unchanged": 3, "blocked": []}

    def test_못_고친_것을_이름으로_돌려준다(
        self, client: TestClient, admin_headers: dict[str, str], three: list[str]
    ) -> None:
        ghost = "00000000-0000-0000-0000-000000000000"
        done = self._apply(client, admin_headers, [*three, ghost], "operator", "박").json()
        assert done["updated"] == 3
        assert done["blocked"] == [ghost]

    def test_날짜는_손대기_전에_판정한다(
        self, client: TestClient, admin_headers: dict[str, str], three: list[str]
    ) -> None:
        """**열 건을 고치다 열한 번째에서 멈추면** 앞의 열 건만 바뀐 상태가
        남는다. 값이 하나뿐인 요청이니 손대기 전에 걸러야 맞다."""
        bad = self._apply(client, admin_headers, three, "tested_at", "어제")
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "MNX-TESTS-0021"

        listed = client.get("/api/test-runs", headers=admin_headers).json()
        assert all(row["tested_at"] is None for row in listed["items"]), "일부만 바뀌었다"

        good = self._apply(client, admin_headers, three, "tested_at", "2026-08-20")
        assert good.status_code == 200, good.text
        assert good.json()["updated"] == 3

    def test_위험한_칸은_아예_못_받는다(
        self, client: TestClient, admin_headers: dict[str, str], three: list[str]
    ) -> None:
        """이름을 만드는 값과 파이프라인이 쓰는 값. **막는 것이 아니라 받지
        않는다** — 스키마에서 걸러야 새 칸이 실수로 열리지 않는다."""
        for field in ("status", "specimen_id", "test_type_id", "record_name", "conditions"):
            response = self._apply(client, admin_headers, three, field, "아무거나")
            assert response.status_code == 422, f"{field} 가 통과했다"

    def test_바꾼_것을_기록에_남긴다(
        self, client: TestClient, admin_headers: dict[str, str], three: list[str]
    ) -> None:
        """한 번에 스무 건을 바꾸는 일이라, 남지 않으면 나중에 「이 값이 왜
        이래」 에 답할 수 없다."""
        self._apply(client, admin_headers, three, "division", "전장")

        entries = client.get(
            "/api/audit", params={"action": "test_run.updated"}, headers=admin_headers
        ).json()
        assert len(entries) == 3
        assert entries[0]["changes"]["division"]["after"] == "전장"
