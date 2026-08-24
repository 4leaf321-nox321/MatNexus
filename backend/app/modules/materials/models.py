"""재료 계층 — 재료 → 시료 → 시편.

**참조는 UUID, 이름은 사람용.** 기존 앱(MaterialAppVer2)은 조합한 문자열이 곧
키였다. 그래서 Grade 오타 하나를 고치면 그 재료를 가리키던 하위 데이터가 전부
끊어졌고, 값이 하나 비면 이름 칸이 사라져 다른 재료와 같은 이름이 될 수 있었다.
여기서는 `record_name` 이 표시와 중복 방지만 맡으므로, 언제든 고쳐도 안전하다.

계층을 나눈 기준:

- **재료**는 규격이다. Grade·Details·스펙두께까지. 0.45t 와 1.0t 는 실무에서
  별도 자재로 구매·관리되고 압연 이력이 달라, 섞으면 편차 통계가 오염된다.
- **시료**는 실물 한 덩이다. 로트·벤더·생산일이 여기 붙는다. 시료 편차 분석의
  단위이기도 하다.
- **시편**은 시료에서 잘라낸 조각이다. **방향(MD/TD/DD)이 여기 있다** — 방향은
  자를 때 정해지는 시편의 속성이지 재료의 속성이 아니다. 재료에 두면 한 재료의
  r값이나 Hill48 파라미터를 구할 때 서로 다른 재료 셋을 묶어야 한다.

수치는 전부 **SI 기본단위**로 저장한다(m·kg·s·Pa·K). 사람이 입력할 때 쓴 단위는
`input_units` 에 남겨 역추적할 수 있게 한다 — 컬럼마다 단위 컬럼을 두면 스키마가
두 배가 되므로 한 칸에 모은다.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 시편 방향. 등방성 재료(수지 등)는 `NA`.
ORIENTATIONS = ("MD", "TD", "DD", "NA")


class Material(Base):
    """재료 규격.

    `owner_workspace_id` 가 NULL 이면 **전역 재료**다. 승격은 이 컬럼을 NULL 로
    바꾸는 UPDATE 한 줄이고, 하위(시료·시편·시험)는 항상 워크스페이스 소속이라
    손댈 것이 없다. 전역 재료 밑에 여러 부서의 시료가 공존해야 하기 때문이다.

    이 컬럼을 처음부터 nullable 로 두는 이유가 전부 여기 있다. 나중에 NOT NULL
    에서 바꾸려면 마이그레이션에 더해 모든 조회 코드를 고쳐야 한다.
    """

    __tablename__ = "materials"
    __table_args__ = (
        UniqueConstraint(
            "owner_workspace_id",
            "record_name",
            name="uq_materials_scope_record_name",
            # PG15+. 없으면 NULL != NULL 이라 **전역 재료끼리 같은 이름이 허용된다**
            # — 유니크 제약을 두는 이유가 바로 사라진다. 서버는 17.5.
            postgresql_nulls_not_distinct=True,
        ),
        # **검색용 trigram 인덱스.** `ILIKE '%낱말%'` 은 B-tree 를 못 탄다 —
        # 앞의 와일드카드 때문에 어느 접두사부터 볼지 정할 수가 없다.
        #
        # 여기 있는 컬럼과 `routes._SEARCH_COLUMNS` 는 **정확히 같아야 한다.**
        # `OR` 가지 하나가 색인이 없으면 그것 때문에 전 행을 훑게 되어 나머지
        # 인덱스가 통째로 무의미해진다(실측: 6개 OR 118ms vs 4개 OR 4.6ms).
        Index(
            "ix_materials_record_name_trgm",
            "record_name",
            postgresql_using="gin",
            postgresql_ops={"record_name": "gin_trgm_ops"},
        ),
        Index(
            "ix_materials_alias_trgm",
            "alias",
            postgresql_using="gin",
            postgresql_ops={"alias": "gin_trgm_ops"},
        ),
        Index(
            "ix_materials_family_trgm",
            "family",
            postgresql_using="gin",
            postgresql_ops={"family": "gin_trgm_ops"},
        ),
        Index(
            "ix_materials_category_trgm",
            "category",
            postgresql_using="gin",
            postgresql_ops={"category": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id"), index=True, nullable=True
    )
    """NULL = 전역. 삭제는 막는다(NO ACTION) — 부서를 지운다고 시험 데이터가
    사라지면 안 된다. 어떤 것이 걸려 있는지는 `shared/dependents.py` 가 알려준다."""

    record_name: Mapped[str] = mapped_column(String(200), index=True)
    """`SECC_MDOI_1.0`. `matcore.naming.material_name` 이 만든다. 사람용이다."""
    alias: Mapped[str | None] = mapped_column(String(200), nullable=True)
    """'도어 이너 강판' 처럼 부르기 쉬운 이름. 유니크가 아니고 언제든 바뀐다.

    record_name 에 자유 문자열을 덧붙이지 않고 따로 두는 이유: 덧붙일 수 있으면
    `SECC_MDOI_1.0` 과 `SECC_MDOI_1.0_재시험용` 이 둘 다 통과해 같은 재료가 두 개
    생긴다. 유니크 제약이 무력화된다."""

    family: Mapped[str] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(50))
    grade: Mapped[str] = mapped_column(String(100))
    details: Mapped[str | None] = mapped_column(String(100), nullable=True)
    """같은 규격인데 구분해야 할 때 쓴다(개발 A안/B안 등). 이름의 한 칸을
    차지하므로, 비어 있으면 `-` 가 들어가고 칸 수는 유지된다."""
    family_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabulary_terms.id"), index=True, nullable=True
    )
    category_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabulary_terms.id"), index=True, nullable=True
    )
    grade_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabulary_terms.id"), index=True, nullable=True
    )
    """Grade 기준정보(ADR 0010). **이 값이 재료 이름을 만든다**(ADR 0004) —
    기준정보 값 이름을 고치면 재료 이름과 그 아래 시료·시편·시험 이름이 전부
    따라 바뀐다."""

    spec_thickness_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    """SI(m). 입력은 mm 로 받는다. **규격 두께이고 이름의 한 칸이다** — 계산에
    쓰는 것은 시편의 실측 두께(`Specimen.thickness_m`)다. 1.0t 판재를 재면
    0.98 이 나오는데, 둘을 합치면 규격이 흔들리거나 계산이 틀린다."""

    applied_product: Mapped[str | None] = mapped_column(String(100), nullable=True)
    applied_part: Mapped[str | None] = mapped_column(String(100), nullable=True)
    """이 재료를 어디에 쓰는가. **재료의 용도이지 로트의 행선지가 아니다.**

    전에는 시료에 있었다. 그러면 "도어 이너용 재료가 뭐가 있나" 를 물을 때 로트를
    전부 뒤져야 하고, 같은 재료의 로트 다섯 개에 같은 용도를 다섯 번 적게 된다 —
    푸아송비를 시료에서 올린 것과 같은 이유다.

    로트가 실제로 어디로 갔는지는 생산관리의 일이고 이 시스템의 질문이 아니다.
    """

    applied_product_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabulary_terms.id"), index=True, nullable=True
    )
    applied_part_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabulary_terms.id"), index=True, nullable=True
    )
    """용도 기준정보(ADR 0010). **이름에는 안 들어간다** — Grade 와 달리 값을 고쳐도
    재료 이름이 안 바뀐다. 그래서 연쇄 변경 훅이 필요 없다."""

    density_si: Mapped[float | None] = mapped_column(Float, nullable=True)
    """공칭 밀도 SI(kg/m³). 문헌값·등급값이다.

    **로트마다 재는 값은 시료에 있다**(`Sample.density_si`). 강판은 로트가
    달라도 7850 이지만 복합재·발포재·소결재는 실제로 다르다 — 그래서 두 층을
    둔다. 카드는 시료 실측을 먼저 보고 없으면 이 값을 쓴다."""

    poisson_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    """**재료의 성질이다. 시료가 아니다.**

    같은 Grade 의 다른 로트가 푸아송비가 다르지 않다. 게다가 인장시험은 이 값을
    주지 않는다 — 횡변형을 따로 재야 한다. 들어오는 값은 대개 문헌값이고,
    그것은 재료 등급에 붙는다.

    전에는 시료에 있었다. 로트 5개에 0.3 을 다섯 번 적어야 했고, 그중 하나를
    0.28 로 고치면 같은 재료가 두 값을 갖게 됐다."""

    declared_properties: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    """**시험이 주지 않는 물성.** 사람이 문헌·규격·밀시트를 보고 적는다.

    탄성계수는 처리 결과에서만 왔고 열팽창계수·비열·열전도도는 자리가 아예
    없었다 — 그런데 그것들은 인장시험이 안 준다. 시험을 안 한 재료가 대부분인데
    그 재료로는 해석용 카드를 만들 수 없었다.

    한 줄의 모양:

        item        물성 항목(기준정보 `property_item`)의 값. `"탄성계수"`
        value_si    **언제나 정본 SI.** 사람이 GPa 로 적어도 저장은 Pa 다
        input_unit  사람이 적은 단위. 화면이 그대로 되돌려 보여 준다
        source      `literature` · `datasheet` · `standard` · `estimate`
        reference   **어느 문서인가.** "KS D 3512 표 3", "MTC-2024-0812"
        temperature_k  잰 온도. 비면 상온으로 본다

    **출처가 필수다.** 이 저장소는 카드가 자기 근거를 들고 있어야 한다는 원칙
    위에 서 있다(ADR 0009·0012). 값만 있고 어디서 왔는지 모르면, 그 값으로 돌린
    해석의 근거를 나중에 되짚을 수 없다.

    **왜 컬럼이 아니라 JSONB 인가:** 항목 목록을 부서가 정한다(D7). 컬럼으로
    두면 물성 하나를 더할 때마다 마이그레이션이고, 재료 표가 물성 창고가 된다.

    **왜 재료인가:** Grade 가 같으면 같은 값이다 — 푸아송비를 시료에서 재료로
    옮긴 것과 같은 판단이다. 롯마다 다른 밀시트 값(항복강도 등)은 시료 층의
    일이고 아직 안 만들었다."""

    input_units: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    """기존 앱의 `Technical Data ID`. '이 데이터가 예전 앱의 어느 레코드였나'를
    나중에 답할 수 있게 보관만 한다."""

    registered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=True
    )
    """소유 컬럼 이름 규약(개발계획 Phase 1-3). 이 이름을 쓰면 계정 삭제 시
    자료 승계가 자동으로 편입된다."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )


class Sample(Base):
    """실물 한 덩이. 시료 편차 분석의 단위.

    이름은 **일련번호**로 짓고 로트번호는 속성으로 둔다. 시료를 먼저 등록하고
    로트를 나중에 확인하는 일이 흔한데, 로트가 이름에 들어가 있으면 그때 이름이
    바뀐다. 로트를 관리하지 않는 재료도 있어서, 이름을 로트에 맡기면 그쪽은
    이름을 지을 수 없다.
    """

    __tablename__ = "samples"
    __table_args__ = (
        # 재료 안에서 채번한다. 워크스페이스별로 채번하면 전역 재료 밑에서
        # 서로 다른 부서의 시료가 같은 이름을 갖는다.
        UniqueConstraint("material_id", "seq_no", name="uq_samples_material_seq_no"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id"), index=True
    )
    material_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("materials.id"), index=True
    )

    seq_no: Mapped[int] = mapped_column(Integer)
    record_name: Mapped[str] = mapped_column(String(300), index=True)
    alias: Mapped[str | None] = mapped_column(String(200), nullable=True)

    lot_no: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    """관리하는 팀도, 안 하는 팀도 있다. 있으면 표시·검색·통계 축으로 쓴다.
    한 로트에서 시료를 여러 개 뜨는 것이 정상이므로 유니크가 아니다."""

    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manufacturer_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("vocabulary_terms.id"),
        index=True,
        nullable=True,
    )
    """제조사 기준정보(ADR 0010). **문자열과 나란히 둔다 — 아직 옮기는 중이다.**

    한 번에 바꾸면 롤백할 데가 없고, 백필 도중에 반쯤 옮겨진 상태로 서비스가
    돈다. 그래서 세 번에 나눈다:

        Expand   지금. FK 를 더하고 쓰기는 양쪽에. 읽기는 아직 문자열
        Backfill 문자열에서 값을 만들고 FK 를 채운다
        Contract 읽기를 FK 로 옮기고, 한 릴리스 검증한 뒤 문자열을 지운다
    """
    distributor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    primary_vendor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sales_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 기준정보(ADR 0010). 유통사와 주 벤더는 **같은 축**을 가리킨다 — 같은 회사가
    # 로트에 따라 둘 중 어느 쪽도 될 수 있다.
    distributor_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabulary_terms.id"), index=True, nullable=True
    )
    primary_vendor_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabulary_terms.id"), index=True, nullable=True
    )
    sales_type_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabulary_terms.id"), index=True, nullable=True
    )
    production_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    """용도(적용 제품·부위)는 여기 없다. 재료로 올렸다 — 로트마다 달라지는 값이
    아니고, 시료에 두면 재료 단위로 물어볼 수가 없다."""

    density_si: Mapped[float | None] = mapped_column(Float, nullable=True)
    """**이 로트에서 실제로 잰 밀도** SI(kg/m³). 공칭은 재료에 있다.

    기존 앱은 `tonne/mm³` 로 저장했다 — Abaqus 단위계다. 저장을 특정 솔버에
    맞추면 다른 솔버를 붙일 때 어디서 변환됐는지 추적이 안 된다.

    푸아송비는 여기 없다. 재료로 올렸다 — 로트마다 달라지는 값이 아니고,
    같은 값을 로트 수만큼 적게 하면 그중 하나만 고쳐지는 일이 생긴다."""

    input_units: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)

    registered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )


class Specimen(Base):
    """시료에서 잘라낸 조각. 방향이 여기서 정해진다.

    실측 치수(두께·폭·게이지길이)를 시편에 두는 이유: 시험 조건이 아니라 시편의
    물리적 성질이다. 같은 시편으로 두 번 시험하면 치수는 같다.
    """

    __tablename__ = "specimens"
    __table_args__ = (
        UniqueConstraint(
            "sample_id", "orientation", "seq_no", name="uq_specimens_sample_dir_seq_no"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("workspaces.id"), index=True
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("samples.id"), index=True
    )

    seq_no: Mapped[int] = mapped_column(Integer)
    orientation: Mapped[str] = mapped_column(String(10), index=True)
    """MD/TD/DD/NA. 이름의 한 칸이므로 비울 수 없다 — 모르면 `NA`."""
    record_name: Mapped[str] = mapped_column(String(300), index=True)

    standard: Mapped[str | None] = mapped_column(String(100), nullable=True)
    standard_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("vocabulary_terms.id"), index=True, nullable=True
    )
    """시편 규격(ASTM E8 subsize, JIS 5호 …). **시편을 어떻게 잘랐는가다.**

    전에는 시험 조건에 있었다. 그런데 규격은 시험할 때 정하는 것이 아니라 자를
    때 정해지고, **아래 게이지 길이·폭을 정하는 쪽**이다 — 정해지는 값은 시편에,
    정하는 값은 시험에 있어 인과가 반대로 놓여 있었다.

    장비 파일에도 없다. Zwick `.tra` 가 주는 시편 정보는 번호·두께 a0·폭 b0
    셋뿐이고(실측 112건 전수 확인), 규격은 사람이 아는 값이다 — 게이지 길이가
    원본에 없는 것과 같은 이유다.

    시험마다 넣게 하면 같은 시편의 시험 두 건에 다른 규격이 적히는 것을 막을
    방법이 없었다.
    """

    thickness_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    width_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    gauge_length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    """**평판을 전제한 옛 컬럼 셋.** 환봉에는 직경이 필요한데 여기 자리가 없다.

    `dimensions` 로 옮기는 중이다(ADR 0010 Expand). 둘 다 채워 두고, 읽는 쪽은
    `dimensions` 를 먼저 본다 — 문자열 컬럼과 기준정보를 나란히 들고 있는 것과
    같은 단계다."""

    dimensions: Mapped[dict[str, float]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    """실측 치수. 키는 **그 시편의 규격이 정한 칸 이름**이고 값은 SI 다.

    고정 컬럼 셋으로는 모양마다 다른 치수를 담을 수 없다 — 환봉은 직경 하나이고
    관은 외경·내경이다. 규격이 칸을 정하고 시편은 그 칸을 채운다.

    **규격의 공칭 치수를 여기 복사해 두지 않는다.** 빈 칸은 규격에서 물려받아
    읽고, 여기 적힌 것은 **사람이 실제로 잰 값**뿐이다 — 둘을 섞으면 "이 값이
    잰 것인가 규격에서 온 것인가" 를 나중에 답할 수 없다."""

    input_units: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    registered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
