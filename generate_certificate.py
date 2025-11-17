import os
from datetime import datetime
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
from models import User, Certificate, Module
from app import db  # Assuming you use SQLAlchemy

def generate_certificate(user_id, course_type, overall_percentage, cert_id=None, module_id=None):
    # Fetch user info from database
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    name = user.full_name or f"User {user_id}"
    date_str = datetime.now().strftime('%B %d, %Y')
    cert_id = cert_id or f"CERT-{user_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Paths
    template_path = os.path.join('static', 'cert_templates', 'Training_cert.pdf')
    output_dir = os.path.join('static', 'certificates')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"certificate_{user_id}_{course_type}.pdf")

    # Get module either by ID (preferred) or by looking up module_type
    if module_id:
        module = db.session.get(Module, module_id)
        if not module:
            raise ValueError(f"No module found with ID {module_id}")
    else:
        # Fallback: Find the module name for the certificate (first module of this type)
        module = Module.query.filter_by(module_type=course_type.upper()).first()
        if not module:
            # Try without uppercase conversion
            module = Module.query.filter_by(module_type=course_type).first()
        if not module:
            raise ValueError(f"No module found for course type {course_type}")
    module_name = module.module_name

    # Get active certificate template settings
    from models import CertificateTemplate
    template_settings = CertificateTemplate.query.filter_by(is_active=True).first()
    if not template_settings:
        # Create default template if none exists
        template_settings = CertificateTemplate(name='Default Template')
        db.session.add(template_settings)
        db.session.commit()

    # Create overlay PDF with user info
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)

    # Attempt-based Course Grade from user progress
    try:
        course_grade = user.get_overall_grade_for_course(course_type)
    except Exception:
        course_grade = 'N/A'

    # Try to fetch existing certificate for this user/module
    cert = Certificate.query.filter_by(user_id=user_id, module_id=module.module_id).order_by(Certificate.issue_date.desc()).first()
    passport_ic = getattr(user, 'passport_number', None) or getattr(user, 'ic_number', None) or getattr(user, 'number_series', None) or 'N/A'

    # Place Name using template settings (only if visible)
    if getattr(template_settings, 'name_visible', True):
        can.setFont("Times-Roman", template_settings.name_font_size)
        can.setFillColorRGB(0, 0, 0)
        can.drawCentredString(template_settings.name_x, template_settings.name_y, name)

    # Passport/IC using template settings (only if visible)
    if getattr(template_settings, 'ic_visible', True):
        can.setFont("Times-Roman", template_settings.ic_font_size)
        can.drawCentredString(template_settings.ic_x, template_settings.ic_y, f"Passport/IC: {passport_ic}")

    # Course type using template settings (only if visible)
    if getattr(template_settings, 'course_type_visible', True):
        can.setFont("Times-Roman", template_settings.course_type_font_size)
        can.drawCentredString(template_settings.course_type_x, template_settings.course_type_y, course_type.upper())

    # Display overall percentage using template settings (only if visible)
    if getattr(template_settings, 'percentage_visible', True):
        can.setFont("Times-Roman", template_settings.percentage_font_size)
        can.drawCentredString(template_settings.percentage_x, template_settings.percentage_y, f"Overall Percentage: {overall_percentage}%")

    # Display Course Grade using template settings (only if visible)
    if getattr(template_settings, 'grade_visible', True):
        can.setFont("Times-Roman", template_settings.grade_font_size)
        can.drawCentredString(template_settings.grade_x, template_settings.grade_y, f"Course Grade: {course_grade}")

    # Text using template settings (only if visible)
    if getattr(template_settings, 'text_visible', True):
        can.setFont("Times-Roman", template_settings.text_font_size)
        can.drawCentredString(template_settings.text_x, template_settings.text_y, "received training and fulfilled the requirements on")

    # Date using template settings (only if visible)
    if getattr(template_settings, 'date_visible', True):
        can.setFont("Times-Roman", template_settings.date_font_size)
        can.drawCentredString(template_settings.date_x, template_settings.date_y, date_str)

    can.save()
    packet.seek(0)

    # Merge overlay with template
    template_pdf = PdfReader(template_path)
    overlay_pdf = PdfReader(packet)
    output_pdf = PdfWriter()
    page = template_pdf.pages[0]
    page.merge_page(overlay_pdf.pages[0])
    output_pdf.add_page(page)
    with open(output_path, "wb") as f:
        output_pdf.write(f)

    # After generating the certificate, save it in the Certificate table (star_rating column exists; not set here)
    if not cert:
        cert = Certificate(
            user_id=user_id,
            module_type=course_type,
            module_id=module.module_id,
            issue_date=datetime.now().date(),
            score=overall_percentage,
            certificate_url=output_path.replace('static/', '/static/')
        )
        db.session.add(cert)
        db.session.commit()
    else:
        # Update existing cert's score/url if needed
        cert.score = overall_percentage
        cert.certificate_url = output_path.replace('static/', '/static/')
        db.session.commit()
    return output_path

if __name__ == "__main__":
    from app import app
    with app.app_context():
        try:
            cert_path = generate_certificate(1, 'TNG', 75)
            print(f"Certificate generated at: {cert_path}")
        except Exception as e:
            print(f"Error generating certificate: {e}")
