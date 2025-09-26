"""
Add user.role, certificate approval fields, and approval_audit table
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    # Add role to user with default 'agency'
    try:
        op.add_column('user', sa.Column('role', sa.String(length=50), nullable=False, server_default='agency'))
        # Remove server_default after setting default so new rows use app-side default
        op.alter_column('user', 'role', server_default=None)
    except Exception:
        pass
    # Add fields to certificate
    try:
        op.add_column('certificate', sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'))
        op.add_column('certificate', sa.Column('approved_by_id', sa.Integer(), nullable=True))
        op.add_column('certificate', sa.Column('approved_at', sa.DateTime(), nullable=True))
        # Drop server_default on status after backfill
        op.alter_column('certificate', 'status', server_default=None)
        # FK to user
        op.create_foreign_key('fk_certificate_approved_by_user', 'certificate', 'user', ['approved_by_id'], ['User_id'], ondelete='SET NULL')
    except Exception:
        pass
    # Create approval_audit table
    try:
        op.create_table(
            'approval_audit',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('certificate_id', sa.Integer(), nullable=False),
            sa.Column('approved_by_id', sa.Integer(), nullable=False),
            sa.Column('approved_at', sa.DateTime(), nullable=False),
            sa.Column('status_before', sa.String(length=20), nullable=False),
            sa.Column('status_after', sa.String(length=20), nullable=False),
            sa.Column('note', sa.String(length=255), nullable=True),
            sa.ForeignKeyConstraint(['certificate_id'], ['certificate.certificate_id'], name='fk_audit_certificate'),
            sa.ForeignKeyConstraint(['approved_by_id'], ['user.User_id'], name='fk_audit_approver')
        )
    except Exception:
        pass


def downgrade():
    try:
        op.drop_table('approval_audit')
    except Exception:
        pass
    try:
        op.drop_constraint('fk_certificate_approved_by_user', 'certificate', type_='foreignkey')
    except Exception:
        pass
    try:
        op.drop_column('certificate', 'approved_at')
    except Exception:
        pass
    try:
        op.drop_column('certificate', 'approved_by_id')
    except Exception:
        pass
    try:
        op.drop_column('certificate', 'status')
    except Exception:
        pass
    try:
        op.drop_column('user', 'role')
    except Exception:
        pass

