-- Create certificate_template table
CREATE TABLE IF NOT EXISTS certificate_template (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL DEFAULT 'Default Template',
    name_x INTEGER DEFAULT 425,
    name_y INTEGER DEFAULT 290,
    name_font_size INTEGER DEFAULT 28,
    ic_x INTEGER DEFAULT 425,
    ic_y INTEGER DEFAULT 260,
    ic_font_size INTEGER DEFAULT 14,
    course_type_x INTEGER DEFAULT 425,
    course_type_y INTEGER DEFAULT 230,
    course_type_font_size INTEGER DEFAULT 14,
    percentage_x INTEGER DEFAULT 425,
    percentage_y INTEGER DEFAULT 200,
    percentage_font_size INTEGER DEFAULT 14,
    grade_x INTEGER DEFAULT 425,
    grade_y INTEGER DEFAULT 185,
    grade_font_size INTEGER DEFAULT 14,
    text_x INTEGER DEFAULT 425,
    text_y INTEGER DEFAULT 170,
    text_font_size INTEGER DEFAULT 12,
    date_x INTEGER DEFAULT 425,
    date_y INTEGER DEFAULT 150,
    date_font_size INTEGER DEFAULT 12,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default template
INSERT INTO certificate_template (name, is_active)
VALUES ('Default Template', true);

