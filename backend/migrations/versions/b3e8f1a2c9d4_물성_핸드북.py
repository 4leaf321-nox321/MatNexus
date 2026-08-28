"""물성 핸드북 — 문서·절·리비전·그림.

## 왜 절이 단위인가

원본 문서는 하나에 절이 열 개다. 문서째 두면 찾기도 고치기도 문서 단위가 된다.
절 단위면 검색 결과가 절로 떨어지고, 편집이 절 하나로 끝나고, 앱의 자리가 절을
가리킬 수 있다.

## 정본은 편집기 문서(JSONB), 검색은 평문(trigram)

`body` 는 리치 텍스트 편집기가 내는 문서. `body_text` 는 거기서 글자만 뽑은 것으로
`pg_trgm` GIN 을 건다 — 한국어는 띄어쓰기가 단어 경계가 아니라 `tsvector` 로는
가운데 일치가 안 된다. 재료 이름 검색과 같은 선택(154c0d5508af).

## 초안 → 승인

절의 `body` 는 승인된 것. 고치려면 리비전(누구나) → 검토자 승인. 검토 없이 정본이
바뀌는 길은 없다.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b3e8f1a2c9d4"
down_revision: Union[str, Sequence[str], None] = "a7c2e9d41b58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "guide_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("topic", sa.String(length=50), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_guide_documents_created_by_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guide_documents")),
    )
    op.create_index(op.f("ix_guide_documents_key"), "guide_documents", ["key"], unique=True)
    op.create_index(op.f("ix_guide_documents_kind"), "guide_documents", ["kind"], unique=False)
    op.create_index(
        op.f("ix_guide_documents_topic"), "guide_documents", ["topic"], unique=False
    )

    op.create_table(
        "guide_sections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "body",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("body_text", sa.Text(), server_default="", nullable=False),
        sa.Column("revision_no", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["guide_documents.id"],
            name=op.f("fk_guide_sections_document_id_guide_documents"),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"], ["users.id"], name=op.f("fk_guide_sections_updated_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guide_sections")),
        sa.UniqueConstraint("document_id", "key", name="uq_guide_sections_doc_key"),
    )
    op.create_index(
        op.f("ix_guide_sections_document_id"), "guide_sections", ["document_id"], unique=False
    )
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX ix_guide_sections_body_text_trgm ON guide_sections"
        " USING gin (body_text gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_guide_sections_title_trgm ON guide_sections"
        " USING gin (title gin_trgm_ops)"
    )

    op.create_table(
        "guide_revisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("section_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "body",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("body_text", sa.Text(), server_default="", nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reviewed_by_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_guide_revisions_author_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"],
            ["users.id"],
            name=op.f("fk_guide_revisions_reviewed_by_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["guide_sections.id"],
            name=op.f("fk_guide_revisions_section_id_guide_sections"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guide_revisions")),
    )
    op.create_index(
        op.f("ix_guide_revisions_created_at"), "guide_revisions", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_guide_revisions_section_id"), "guide_revisions", ["section_id"], unique=False
    )
    op.create_index(
        op.f("ix_guide_revisions_status"), "guide_revisions", ["status"], unique=False
    )

    op.create_table(
        "guide_assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_guide_assets_created_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["guide_documents.id"],
            name=op.f("fk_guide_assets_document_id_guide_documents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guide_assets")),
    )
    op.create_index(
        op.f("ix_guide_assets_document_id"), "guide_assets", ["document_id"], unique=False
    )
    op.create_index(op.f("ix_guide_assets_sha256"), "guide_assets", ["sha256"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_guide_assets_sha256"), table_name="guide_assets")
    op.drop_index(op.f("ix_guide_assets_document_id"), table_name="guide_assets")
    op.drop_table("guide_assets")
    op.drop_index(op.f("ix_guide_revisions_status"), table_name="guide_revisions")
    op.drop_index(op.f("ix_guide_revisions_section_id"), table_name="guide_revisions")
    op.drop_index(op.f("ix_guide_revisions_created_at"), table_name="guide_revisions")
    op.drop_table("guide_revisions")
    op.execute("DROP INDEX IF EXISTS ix_guide_sections_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_guide_sections_body_text_trgm")
    op.drop_index(op.f("ix_guide_sections_document_id"), table_name="guide_sections")
    op.drop_table("guide_sections")
    op.drop_index(op.f("ix_guide_documents_topic"), table_name="guide_documents")
    op.drop_index(op.f("ix_guide_documents_kind"), table_name="guide_documents")
    op.drop_index(op.f("ix_guide_documents_key"), table_name="guide_documents")
    op.drop_table("guide_documents")
