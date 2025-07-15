from models import db, Module
from app import app
import os

TNG_MODULES = [
    'INTRODUCTION TO SECURITY INDUSTRY',
    'ROLE AND RESPONSIBILITIES',
    'ETHICS AND TURNOUT',
    'MALAYSIAN CULTURE & CUSTOMS',
    'PATROLLING & ACCESS CONTROL',
    'REPORT WRITING',
    'CUSTOMER SERVICE',
    'COMMUNICATION',
    'LAWS OF ARREST, SEARCH & USE OF FORCE',
    'FIRE CONTROL & PREVENTION',
    'FIRST AID & CPR',
    'SAFETY AT WORK PLACE',
    'SECURITY DRILL'
]

CSG_MODULES = [
    'PENGENALAN KEPADA INDUSTRI KESELAMATAN',
    'PERANAN, PENAMPILAN & TANGGUNGJAWAB PENGAWAL KESELAMATAN',
    'ARAHAN TUGAS',
    'KAWALAN KELUAR MASUK',
    'PEMERIKSAAN & PEMERIKSAAN KENDERAAN',
    'RONDAAN',
    'MENULIS LAPORAN',
    'PENGENALAN ALAT KOMUNIKASI',
    'KHIDMAT PELANGGAN',
    'MELAKSANAKAN TUGAS MENGIKUT BATASAN UNDANG-UNDANG',
    'PERTOLONGAN CEMAS DAN CPR',
    'PENCEGAHAN KEBAKARAN DAN BENCANA',
    'LATIHAN SENI MEMPERTAHANKAN DIRI',
    'LATIHAN T-BATON',
    'KAWAD',
    'PENGENALAN DADAH DAN PENYALAHGUNAAN DADAH',
    'PENGENALAN & PERANAN ANGGOTA BERSENJATA & CIT'
]

# Use absolute path for SQLite DB
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'security_training.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'

def reset_modules():
    with app.app_context():
        print('Database file:', app.config['SQLALCHEMY_DATABASE_URI'])
        try:
            before = Module.query.count()
            print(f'Modules before delete: {before}')
            Module.query.delete()
            db.session.commit()
            after_delete = Module.query.count()
            print(f'Modules after delete: {after_delete}')
            # Add TNG modules
            for idx, name in enumerate(TNG_MODULES, 1):
                m = Module(module_name=name, module_type='TNG', series_number=f'TNG{idx:03d}', content='')
                db.session.add(m)
            # Add CSG modules
            for idx, name in enumerate(CSG_MODULES, 1):
                m = Module(module_name=name, module_type='CSG', series_number=f'CSG{idx:03d}', content='')
                db.session.add(m)
            db.session.commit()
            after_insert = Module.query.count()
            print(f'Modules after insert: {after_insert}')
            print('Modules reset: 13 TNG and 17 CSG modules added.')
        except Exception as e:
            print('Error:', e)

if __name__ == '__main__':
    reset_modules()
