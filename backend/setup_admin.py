"""Create or reset the manager login using the existing users table."""
import os, getpass
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
import mysql.connector
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
email=input('Manager email (existing ADMIN email or new email): ').strip().lower()
name=input('Manager display name: ').strip() or 'Network Manager'
password=getpass.getpass('Choose manager password (minimum 10 characters): ')
if len(password)<10: raise SystemExit('Password must contain at least 10 characters.')
conn=mysql.connector.connect(host=os.getenv('DB_HOST','localhost'),port=int(os.getenv('DB_PORT','3306')),user=os.getenv('DB_USER','root'),password=os.getenv('DB_PASSWORD',''),database=os.getenv('DB_NAME','ev_charging_management'))
cur=conn.cursor()
try:
 cur.execute('SELECT user_id, role FROM users WHERE LOWER(email_id)=%s',(email,)); row=cur.fetchone()
 if row:
  if row[1] != 'ADMIN': raise SystemExit('That email belongs to a USER, not an ADMIN. Use an existing ADMIN email.')
  cur.execute('UPDATE users SET name=%s,password_hash=%s WHERE user_id=%s',(name,generate_password_hash(password),row[0]))
 else:
  cur.execute("INSERT INTO users (name,email_id,password_hash,role) VALUES (%s,%s,%s,'ADMIN')",(name,email,generate_password_hash(password)))
 conn.commit(); print('Manager account is ready. Keep your password private.')
except:
 conn.rollback(); raise
finally: cur.close(); conn.close()
