"""지운 이름을 다시 쓸 수 있게 — 유니크를 부분 인덱스로.

삭제는 소프트(`deleted_at`)라 행이 남는다. 그런데 유니크 제약이 **지워진 행까지
세고 있었다.** 목록에서는 사라지는데 이름은 잡혀 있으니, 지운 이름으로 다시
만들면 이렇게 된다.

    DELETE /api/materials/{id}   → 204
    POST   /api/materials        → 409 같은 이름의 재료가 이미 있습니다: SPCC_-_1.2
    GET    /api/materials?q=SPCC → []          ← 화면 어디에도 없다

복구 기능이 없어 빠져나갈 길이 아예 없었다. 같은 파일의 `find_by_name` 은 지운
것을 걸렀으므로 **둘이 어긋나 있었다** — 찾을 때는 없고 만들 때는 있는 이름.

## 왜 지금 고치나

이관에서 그대로 터졌다(2026-08-28). 이관은 한 번에 안 끝나고 이름 규칙을 고쳐
다시 돌리는 일인데, 잘못 들어간 것을 지우고 다시 돌리면 **그 재료 아래가 통째로
안 들어간다.** 로그가 `재료 실패 ... 같은 이름의 재료가 이미 있습니다` 로 가득
찼고 금속 계열 전부가 그렇게 막혔다.

## 삭제의 뜻이 바뀐다

**지운 이름을 다시 쓸 수 있게 된다.** 그러므로 지운 것을 되살리는 기능을 나중에
만든다면, 되살릴 때 이름이 이미 남에게 가 있을 수 있다. 그것을 감수하고 고른
길이다 — 지금은 복구 기능이 아예 없고, 이름이 영영 타는 쪽의 손해가 훨씬 크다.

**채번은 안 건드린다.** `next_sample_seq`·`next_specimen_seq` 는 지운 번호를
여전히 재사용하지 않는다 — 자동으로 붙는 이름이 옛 문서·엑셀에 적힌 것과 다른
것을 가리키면 안 된다. 여기서 푸는 것은 **사람이나 파일이 번호를 지정했을
때**뿐이다.

## 셋 다 같은 모양이었다

    materials   (owner_workspace_id, record_name)
    samples     (material_id, seq_no)
    specimens   (sample_id, orientation, seq_no)

Revision ID: c3d7b21f9a04
Revises: 985f5610be6e
Create Date: 2026-08-28 02:15:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c3d7b21f9a04"
down_revision: Union[str, Sequence[str], None] = "985f5610be6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # **이름을 그대로 물려받는다.** PG 에서 유니크 제약은 같은 이름의 인덱스를
    # 만들므로, 제약을 지우면 그 인덱스도 함께 사라진다 — 그 뒤에 같은 이름으로
    # 부분 인덱스를 만들 수 있다. 이름이 바뀌면 모델과 대조하는 검사가 걸린다.
    op.drop_constraint("uq_materials_scope_record_name", "materials", type_="unique")
    op.create_index(
        "uq_materials_scope_record_name",
        "materials",
        ["owner_workspace_id", "record_name"],
        unique=True,
        # PG15+. 없으면 NULL != NULL 이라 전역 재료끼리 같은 이름이 허용된다.
        postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.drop_constraint("uq_samples_material_seq_no", "samples", type_="unique")
    op.create_index(
        "uq_samples_material_seq_no",
        "samples",
        ["material_id", "seq_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.drop_constraint("uq_specimens_sample_dir_seq_no", "specimens", type_="unique")
    op.create_index(
        "uq_specimens_sample_dir_seq_no",
        "specimens",
        ["sample_id", "orientation", "seq_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Downgrade schema.

    **되돌리면 실패할 수 있다.** 부분 인덱스로 사는 동안 지운 이름을 다시 쓴
    행이 생겼다면, 전체 유니크로 되돌릴 때 그 짝이 중복이 된다. 그때는 되돌리기
    전에 어느 쪽을 남길지 사람이 정해야 한다 — 조용히 지우지 않는다.
    """
    op.drop_index("uq_specimens_sample_dir_seq_no", table_name="specimens")
    op.create_unique_constraint(
        "uq_specimens_sample_dir_seq_no",
        "specimens",
        ["sample_id", "orientation", "seq_no"],
    )

    op.drop_index("uq_samples_material_seq_no", table_name="samples")
    op.create_unique_constraint(
        "uq_samples_material_seq_no", "samples", ["material_id", "seq_no"]
    )

    op.drop_index("uq_materials_scope_record_name", table_name="materials")
    op.create_unique_constraint(
        "uq_materials_scope_record_name",
        "materials",
        ["owner_workspace_id", "record_name"],
        postgresql_nulls_not_distinct=True,
    )
