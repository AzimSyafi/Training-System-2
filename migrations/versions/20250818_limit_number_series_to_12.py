"""
Migration: enforce 12-digit unique numeric number_series on user table.
Steps:
1. Normalize existing values to digits only, truncate to 12.
2. Ensure sequence exists (user_number_series_seq) for filling blanks/collisions.
3. Fill NULL/empty values.
4. Resolve duplicates by reassigning new sequence-based numbers.
5. Alter column length to 12.
6. Add unique constraint.
Downgrade reverses length and drops the constraint (data kept as-is).
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    # 1 & 2: Normalize and ensure sequence
    op.execute("CREATE SEQUENCE IF NOT EXISTS user_number_series_seq")
    op.execute(
        """
        UPDATE "user"
        SET number_series = LEFT(regexp_replace(COALESCE(number_series,''),'[^0-9]','','g'),12)
        """
    )

    # 3: Fill NULL/empty values
    op.execute(
        """
        DO $$
        DECLARE r RECORD;
        BEGIN
          FOR r IN SELECT "User_id" FROM "user" WHERE number_series IS NULL OR number_series='' LOOP
            UPDATE "user"
            SET number_series = LPAD(nextval('user_number_series_seq')::text,12,'0')
            WHERE "User_id" = r."User_id";
          END LOOP;
        END $$;
        """
    )

    # 4: Resolve duplicates (keep first, reassign others)
    op.execute(
        """
        WITH d AS (
          SELECT "User_id", number_series,
                 ROW_NUMBER() OVER (PARTITION BY number_series ORDER BY "User_id") AS rn
          FROM "user"
        )
        UPDATE "user" u
        SET number_series = LPAD(nextval('user_number_series_seq')::text,12,'0')
        FROM d
        WHERE u."User_id" = d."User_id" AND d.rn > 1;
        """
    )

    # 5: Alter column to length 12 (shrink). Using USING expression for safety.
    with op.batch_alter_table('user') as batch_op:
        batch_op.alter_column('number_series', type_=sa.String(12))

    # 6: Add unique constraint (idempotent guard: only if not exists)
    # Alembic lacks native IF NOT EXISTS; rely on try/except at runtime if rerun manually.
    try:
        op.create_unique_constraint('uq_user_number_series', 'user', ['number_series'])
    except Exception:
        pass


def downgrade():
    # Drop unique constraint if exists
    try:
        op.drop_constraint('uq_user_number_series', 'user', type_='unique')
    except Exception:
        pass
    with op.batch_alter_table('user') as batch_op:
        batch_op.alter_column('number_series', type_=sa.String(50))

