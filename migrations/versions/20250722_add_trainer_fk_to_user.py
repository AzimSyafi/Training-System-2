"""
Migration script to update the User table:
- Remove the old 'trainer' string column
- Add a new 'trainer_id' integer column as a foreign key to Trainer
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Remove the old string-based trainer column if it exists
    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_column('trainer')
        batch_op.add_column(sa.Column('trainer_id', sa.Integer(), sa.ForeignKey('trainer.trainer_id'), nullable=True))

def downgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_column('trainer_id')
        batch_op.add_column(sa.Column('trainer', sa.String(255)))

