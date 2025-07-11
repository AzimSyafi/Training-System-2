 from app import app, db, User, Trainer, Admin, Registration, UserModule, Certificate

def cleanup_database():
    with app.app_context():
        print("Starting database cleanup...")

        # --- Clean Users ---
        user_to_keep = User.query.filter_by(username='john').first()
        if user_to_keep:
            print(f"Keeping user: {user_to_keep.username}")
            # Delete associated records first
            users_to_delete = User.query.filter(User.username != 'john').all()
            for user in users_to_delete:
                print(f"Deleting user: {user.username}")
                UserModule.query.filter_by(user_id=user.User_id).delete()
                Certificate.query.filter_by(user_id=user.User_id).delete()
                db.session.delete(user)
        else:
            print("User 'john' not found.")

        # --- Clean Trainers ---
        trainer_to_keep = Trainer.query.filter_by(username='sarah').first()
        if trainer_to_keep:
            print(f"Keeping trainer: {trainer_to_keep.username}")
            trainers_to_delete = Trainer.query.filter(Trainer.username != 'sarah').all()
            for trainer in trainers_to_delete:
                print(f"Deleting trainer: {trainer.username}")
                db.session.delete(trainer)
        else:
            print("Trainer 'sarah' not found.")

        # --- Clean Admins ---
        admin_to_keep = Admin.query.filter_by(username='admin').first()
        if admin_to_keep:
            print(f"Keeping admin: {admin_to_keep.username}")
            admins_to_delete = Admin.query.filter(Admin.username != 'admin').all()
            for admin in admins_to_delete:
                print(f"Deleting admin: {admin.username}")
                db.session.delete(admin)
        else:
            print("Admin 'admin' not found.")

        try:
            db.session.commit()
            print("Database cleanup successful. Only 'john', 'sarah', and 'admin' should remain.")
        except Exception as e:
            db.session.rollback()
            print(f"An error occurred: {e}")

if __name__ == '__main__':
    cleanup_database()

