import sqlite3

db_path = "instance/security_training.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE user_new RENAME TO user;")
    print("Table 'user_new' renamed to 'user' successfully.")
except Exception as e:
    print("Error:", e)

conn.commit()
conn.close()
