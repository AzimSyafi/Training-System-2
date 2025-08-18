"""
Migration: Add prefixed number_series formats.
- Users: change number_series from 8 to 10 chars and prefix existing values with 'SG'. (Old format YYYYNNNN -> SGYYYYNNNN)
- Trainers: add number_series (10 chars) and populate as TRYYYYNNNN using per-year sequence.
Admins: unchanged (no series).
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

def upgrade():
    # 1. Alter user.number_series length to 10
    with op.batch_alter_table('user') as batch_op:
        batch_op.alter_column('number_series', type_=sa.String(10))

    # 2. Prefix existing user series values with 'SG' if not already
    op.execute("""
        UPDATE "user"
        SET number_series = 'SG' || number_series
        WHERE number_series IS NOT NULL AND number_series <> ''
          AND number_series NOT LIKE 'SG%'
    """)

    # 2a. Backfill NULL/empty user series
    year = datetime.utcnow().strftime('%Y')
    seq_name = f'user_number_series_{year}_seq'
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}")
    op.execute(f"""
        UPDATE "user"
        SET number_series = 'SG{year}' || LPAD(nextval('{seq_name}')::text,4,'0')
        WHERE (number_series IS NULL OR number_series='')
    """)

    # 3. Add trainer.number_series column
    with op.batch_alter_table('trainer') as batch_op:
        batch_op.add_column(sa.Column('number_series', sa.String(10), unique=True))

    # 4. Populate trainer number_series
    t_seq_name = f'trainer_number_series_{year}_seq'
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {t_seq_name}")
    op.execute(f"""
        UPDATE trainer
        SET number_series = 'TR{year}' || LPAD(nextval('{t_seq_name}')::text,4,'0')
        WHERE number_series IS NULL OR number_series=''
    """)

    # 5. Ensure unique constraints exist (ignore if already)
    try:
        op.create_unique_constraint('uq_user_number_series', 'user', ['number_series'])
    except Exception:
        pass
    try:
        op.create_unique_constraint('uq_trainer_number_series', 'trainer', ['number_series'])
    except Exception:
        pass


def downgrade():
    # Remove trainer number_series column
    with op.batch_alter_table('trainer') as batch_op:
        batch_op.drop_column('number_series')
    # Revert user.number_series back to 8 (strip SG prefix if present)
    op.execute("""
        UPDATE "user"
        SET number_series = SUBSTRING(number_series FROM 3)
        WHERE number_series LIKE 'SG%'
    """)
    with op.batch_alter_table('user') as batch_op:
        batch_op.alter_column('number_series', type_=sa.String(8))
