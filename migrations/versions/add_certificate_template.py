"""Create certificate_template table

Revision ID: 20251014_add_certificate_template
Revises: 20250923_add_authority_and_cert_approval
Create Date: 2025-10-14 11:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251014_add_certificate_template'
down_revision = '20250923_add_authority_and_cert_approval'
branch_labels = None
depends_on = None


def upgrade():
    # Create certificate_template table
    op.create_table(
        'certificate_template',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False, server_default='Default Template'),
        sa.Column('name_x', sa.Integer(), nullable=True, server_default='425'),
        sa.Column('name_y', sa.Integer(), nullable=True, server_default='290'),
        sa.Column('name_font_size', sa.Integer(), nullable=True, server_default='28'),
        sa.Column('ic_x', sa.Integer(), nullable=True, server_default='425'),
        sa.Column('ic_y', sa.Integer(), nullable=True, server_default='260'),
        sa.Column('ic_font_size', sa.Integer(), nullable=True, server_default='14'),
        sa.Column('course_type_x', sa.Integer(), nullable=True, server_default='425'),
        sa.Column('course_type_y', sa.Integer(), nullable=True, server_default='230'),
        sa.Column('course_type_font_size', sa.Integer(), nullable=True, server_default='14'),
        sa.Column('percentage_x', sa.Integer(), nullable=True, server_default='425'),
        sa.Column('percentage_y', sa.Integer(), nullable=True, server_default='200'),
        sa.Column('percentage_font_size', sa.Integer(), nullable=True, server_default='14'),
        sa.Column('grade_x', sa.Integer(), nullable=True, server_default='425'),
        sa.Column('grade_y', sa.Integer(), nullable=True, server_default='185'),
        sa.Column('grade_font_size', sa.Integer(), nullable=True, server_default='14'),
        sa.Column('text_x', sa.Integer(), nullable=True, server_default='425'),
        sa.Column('text_y', sa.Integer(), nullable=True, server_default='170'),
        sa.Column('text_font_size', sa.Integer(), nullable=True, server_default='12'),
        sa.Column('date_x', sa.Integer(), nullable=True, server_default='425'),
        sa.Column('date_y', sa.Integer(), nullable=True, server_default='150'),
        sa.Column('date_font_size', sa.Integer(), nullable=True, server_default='12'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )

    # Insert default template
    op.execute("""
        INSERT INTO certificate_template (name, is_active) 
        VALUES ('Default Template', true)
    """)


def downgrade():
    op.drop_table('certificate_template')
