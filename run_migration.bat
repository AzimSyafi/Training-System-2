@echo off
echo Running database migration to add module disclaimer column...
cd /d "C:\Users\USER\PycharmProjects\Training-System-2"
python add_module_disclaimer_column.py
pause

