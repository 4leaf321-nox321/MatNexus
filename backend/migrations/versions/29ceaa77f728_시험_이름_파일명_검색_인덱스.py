"""시험 이름·파일명 검색 인덱스

**`ILIKE '%낱말%'` 은 B-tree 를 못 탄다.** 앞의 와일드카드 때문에 어느 접두사부터
볼지 정할 수가 없다. `record_name` 에 이미 B-tree 가 있지만 그것은 정렬·정확일치용
이고 부분일치에는 안 쓰인다.

재료 목록이 같은 자리에서 실측으로 걸렸다: 색인 없는 `OR` 가지 하나가 전 행 훑기를
부르면서 나머지 인덱스까지 무의미해졌다(6개 OR 118ms vs 4개 OR 4.6ms, 합성 5만 건).
그래서 찾는 칸 둘에 다 건다.

## autogenerate 가 지우려 한 것을 빼 두었다

이 마이그레이션을 autogenerate 로 만들었더니 `ix_guide_sections_title_trgm` 과
`ix_guide_sections_body_text_trgm` 을 **지우는 줄**이 함께 나왔다. 그 둘은
`b3e8f1a2c9d4` 가 raw SQL 로 만들었고 모델에 선언이 없어서, autogenerate 눈에는
「DB 에만 있는 것」 으로 보인다. 그대로 올렸으면 가이드 검색이 조용히 전 행 훑기가
됐을 것이다.

지우는 줄을 뺐고, 다시 나지 않도록 **모델에 그 인덱스를 선언했다**
(`GuideSection.__table_args__`). 그래서 이 마이그레이션은 만들기만 한다.

Revision ID: 29ceaa77f728
Revises: 674ee685adee
Create Date: 2026-09-01 09:16:03.454553

"""

from collections.abc import Sequence

from alembic import op

revision: str = "29ceaa77f728"
down_revision: str | Sequence[str] | None = "674ee685adee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_test_runs_record_name_trgm",
        "test_runs",
        ["record_name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"record_name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_test_runs_source_filename_trgm",
        "test_runs",
        ["source_filename"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"source_filename": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_test_runs_source_filename_trgm",
        table_name="test_runs",
        postgresql_using="gin",
        postgresql_ops={"source_filename": "gin_trgm_ops"},
    )
    op.drop_index(
        "ix_test_runs_record_name_trgm",
        table_name="test_runs",
        postgresql_using="gin",
        postgresql_ops={"record_name": "gin_trgm_ops"},
    )
