import sqlite3

# Path to your SQLite database
DB_PATH = 'instance/security_training.db'

# Connect to the database
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check if the column already exists
cursor.execute("PRAGMA table_info(module);")
columns = [col[1] for col in cursor.fetchall()]

if 'youtube_url' not in columns:
    cursor.execute("ALTER TABLE module ADD COLUMN youtube_url VARCHAR(255);")
    print("youtube_url column added successfully.")
else:
    print("youtube_url column already exists.")

conn.commit()
conn.close()

