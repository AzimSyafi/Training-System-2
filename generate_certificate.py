import os
from datetime import datetime
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from io import BytesIO
from models import User, Certificate, Module, UserModule  # Assuming you have a User and Certificate model
from app import db  # Assuming you use SQLAlchemy
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

def generate_certificate(user_id, course_type, overall_percentage, cert_id=None):
    # Fetch user info from database
    user = User.query.get(user_id)
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

    # Find the module name for the certificate (first module of this type)
    module = Module.query.filter_by(module_type=course_type.upper()).first()
    if not module:
        raise ValueError(f"No module found for course type {course_type}")
    module_name = module.module_name
    # Create overlay PDF with user info
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    # Use overall_percentage for stars
    percent = overall_percentage
    if percent < 20:
        stars = 1
    elif percent < 40:
        stars = 2
    elif percent < 60:
        stars = 3
    elif percent < 70:
        stars = 4
    else:
        stars = 5

    # Attempt-based Course Grade from user progress
    try:
        course_grade = user.get_overall_grade_for_course(course_type)
    except Exception:
        course_grade = 'N/A'

    # Try to fetch existing certificate for this user/module
    cert = Certificate.query.filter_by(user_id=user_id, module_id=module.module_id).order_by(Certificate.issue_date.desc()).first()
    passport_ic = getattr(user, 'passport_number', None) or getattr(user, 'ic_number', None) or getattr(user, 'number_series', None) or 'N/A'
    # Place Name (centered at 425, 290), Times New Roman, 28pt, Black
    can.setFont("Times-Roman", 28)
    can.setFillColorRGB(0, 0, 0)
    can.drawCentredString(425, 290, name)
    # Passport/IC, Module, Stars, Date text, Date all Times New Roman, 14pt, Black
    can.setFont("Times-Roman", 14)
    can.drawCentredString(425, 260, f"Passport/IC: {passport_ic}")
    can.drawCentredString(425, 230, course_type.upper())
    # Register DejaVuSans font for star rendering (use correct path)
    font_path = os.path.join('static', 'cert_templates', 'dejavu-fonts-ttf-2.37', 'ttf', 'DejaVuSans.ttf')
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
        star_font = 'DejaVuSans'
    else:
        star_font = 'Helvetica'
    # Place Stars (centered at 425, 200) with star font
    can.setFont(star_font, 20)
    can.setFillColorRGB(0, 0, 0)
    can.drawCentredString(425, 200, '\u2605' * stars)
    # Display overall percentage under the stars
    can.setFont("Times-Roman", 14)
    can.drawCentredString(425, 185, f"Overall Percentage: {percent}%")
    # Display Course Grade (attempt-based) under the overall percentage
    can.drawCentredString(425, 170, f"Course Grade: {course_grade}")
    # Set font size for text and date to 12
    can.setFont("Times-Roman", 12)
    can.drawCentredString(425, 155, "received training and fulfilled the requirements on")
    can.drawCentredString(425, 135, date_str)
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

    # After generating the certificate, save it in the Certificate table
    if not cert:
        cert = Certificate(
            user_id=user_id,
            module_type=course_type,
            module_id=module.module_id,
            issue_date=datetime.now().date(),
            star_rating=stars,
            score=overall_percentage,  # Save overall_percentage as score for reference
            certificate_url=output_path.replace('static/', '/static/')
        )
        db.session.add(cert)
        db.session.commit()
    return output_path

if __name__ == "__main__":
    from app import app
    with app.app_context():
        try:
            # Example standalone generation with a placeholder overall percentage
            cert_path = generate_certificate(1, 'TNG', 75)
            print(f"Certificate generated at: {cert_path}")
        except Exception as e:
            print(f"Error generating certificate: {e}")
