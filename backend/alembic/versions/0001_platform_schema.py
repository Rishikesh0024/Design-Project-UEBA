"""Create UEBA platform tables."""

from alembic import op

from app.db.session import Base
from app.models_db import models  # noqa: F401

revision = "0001_platform_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
