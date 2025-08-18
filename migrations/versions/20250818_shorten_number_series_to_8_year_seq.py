"""
Migration: change number_series to 8 chars (YYYYNNNN) with per-year sequence.
Assumes previous migration may have set 12-char numeric values.
Conversion rules:
- If value already 8 digits and first 4 between 2000 and 2099 => keep.
- Else generate new using current year + zero-padded sequence (per-year sequence created if needed).
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

def upgrade():
    # 1. Alter column length to 8 (shrink if previously 12)
    with op.batch_alter_table('user') as batch_op:
        batch_op.alter_column('number_series', type_=sa.String(8))

    # 2. Create per-year sequence for current year if not exists
    year = datetime.utcnow().strftime('%Y')
    seq_name = f'user_number_series_{year}_seq'
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}")

    # 3. Update invalid / old values
    # Keep those already matching pattern ^(20\d{2})\d{4}$
    op.execute(
        f"""
        UPDATE "user"
        SET number_series = (
            SELECT CASE
                WHEN number_series ~ '^(20\\d{{2}})\\d{{4}}$' THEN number_series
                ELSE '{year}' || LPAD(nextval('{seq_name}')::text, 4, '0')
            END
        )
        """
    )

    # 4. Resolve duplicates after reassignment (rare but safeguard)
    op.execute(
        f"""
        WITH d AS (
          SELECT "User_id", number_series,
                 ROW_NUMBER() OVER (PARTITION BY number_series ORDER BY "User_id") rn
          FROM "user"
        )
        UPDATE "user" u
        SET number_series = '{year}' || LPAD(nextval('{seq_name}')::text,4,'0')
        FROM d
        WHERE u."User_id" = d."User_id" AND d.rn > 1;
        """
    )

    # 5. (Unique constraint likely already exists.) Attempt to (re)create to ensure.
    try:
        op.create_unique_constraint('uq_user_number_series', 'user', ['number_series'])
    except Exception:
        pass


def downgrade():
    # Revert size back to 12 (data will keep 8 values)
    with op.batch_alter_table('user') as batch_op:
        batch_op.alter_column('number_series', type_=sa.String(12))
    # leave constraint intact

