import sys
from datetime import date
from typing import List

from app import app, db
from models import User, Module, Certificate, Course


def get_course_modules(course_code: str) -> List[Module]:
    course = Course.query.filter(Course.code.ilike(course_code)).first()
    if not course:
        return []
    return list(course.modules)


def has_cert_for_course(user_id: int, modules: List[Module]) -> bool:
    if not modules:
        return False
    module_ids = [m.module_id for m in modules]
    # any certificate for any module in this course counts
    existing = (
        Certificate.query
        .filter(Certificate.user_id == user_id)
        .filter(Certificate.module_id.in_(module_ids))
        .first()
    )
    return existing is not None


def ensure_pending_cert(user: User, course_code: str, modules: List[Module]) -> bool:
    """If user completed all modules and has no cert for this course, create a pending certificate.
    Returns True if created, False otherwise."""
    # EligibleForCertificate expects a course_type string that matches Module.module_type/course code
    if not user.EligibleForCertificate(course_code):
        return False
    if has_cert_for_course(user.User_id, modules):
        return False
    # Pick a representative module for certificate association (first by series or id)
    try:
        modules_sorted = sorted(modules, key=lambda m: (m.series_number or '', m.module_id))
        mod = modules_sorted[0]
    except Exception:
        if not modules:
            return False
        mod = modules[0]
    cert = Certificate(
        user_id=user.User_id,
        module_type=course_code,
        module_id=mod.module_id,
        issue_date=date.today(),
        status='pending'
    )
    db.session.add(cert)
    return True


def main(argv):
    if len(argv) < 2:
        print('Usage: python backfill_pending_certificates.py <COURSE_CODE>')
        sys.exit(1)
    course_code = argv[1].strip()
    created = 0
    with app.app_context():
        modules = get_course_modules(course_code)
        if not modules:
            print(f"No course found for code '{course_code}' or course has no modules.")
            sys.exit(2)
        # Iterate all users to find eligible ones
        for user in User.query.all():
            if ensure_pending_cert(user, course_code, modules):
                created += 1
        if created:
            db.session.commit()
        print(f"Backfill complete. Created {created} pending certificate(s) for course {course_code}.")


if __name__ == '__main__':
    main(sys.argv)

