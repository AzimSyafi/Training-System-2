"""
Migration script to add emergency contact fields to user table
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('user', sa.Column('emergency_contact', sa.String(20)))
    op.add_column('user', sa.Column('emergency_name', sa.String(100)))
    op.add_column('user', sa.Column('emergency_relationship', sa.String(100)))

def downgrade():
    op.drop_column('user', 'emergency_contact')
    op.drop_column('user', 'emergency_name')
    op.drop_column('user', 'emergency_relationship')

