import psycopg2
from config.settings import DATABASE_URL

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'skill_inventory';")
for row in cur.fetchall():
    print(row[0])
