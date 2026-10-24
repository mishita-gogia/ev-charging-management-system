import os, re
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import check_password_hash
from dotenv import load_dotenv
import mysql.connector

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
app = Flask(__name__, template_folder='../frontend/templates', static_folder='../frontend/static')
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'change-this-before-use')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')

MODULES = {
 'stations': {'table':'charging_stations','title':'Stations','icon':'⌖','pk':'station_id','fields':[('station_name','Station name','text',True),('address','Address','text',True),('city','City','text',True)]},
 'slots': {'table':'charging_slots','title':'Charging slots','icon':'ϟ','pk':'slot_id','fields':[('station_id','Station','station',True),('charger_type','Charger type','text',True),('speed','Speed (kW)','number',True),('status','Status','enum:AVAILABLE,OCCUPIED,MAINTENANCE',True)]},
 'tariffs': {'table':'tariff_plans','title':'Tariff plans','icon':'₹','pk':'tariff_id','fields':[('charger_type','Charger type','text',True),('rate_per_kwh','Rate per kWh','number',True),('service_fee','Service fee','number',True),('is_active','Active','bool',True)]},
 'sessions': {'table':'charging_sessions','title':'Charging sessions','icon':'↗','pk':'session_id','fields':[('vehicle_id','Vehicle','vehicle',True),('slot_id','Slot','slot',True),('tariff_id','Tariff','tariff',True),('duration','Duration (minutes)','number',True),('energy_kwh','Energy (kWh)','number',True),('status','Status','enum:BOOKED,ACTIVE,COMPLETED,CANCELLED',True)]},
 'technicians': {'table':'technicians','title':'Technicians','icon':'⚒','pk':'technician_id','fields':[('name','Name','text',True),('experience','Experience (years)','number',True),('phone','Phone','text',False)]},
 'maintenance': {'table':'maintenance','title':'Maintenance','icon':'⚒','pk':'maintenance_id','fields':[('technician_id','Technician','technician',True),('station_id','Station','station',True),('issue','Issue','text',True),('maintenance_date','Maintenance date','date',True),('status','Status','enum:PENDING,IN_PROGRESS,COMPLETED',True)]},
 'bills': {'table':'bills','title':'Bills','icon':'▤','pk':'bill_id','fields':[('session_id','Session','session',True),('amount','Amount before GST','number',True),('gst','GST (%)','number',True),('status','Status','enum:ESTIMATED,FINAL,PAID',True)]},
 'payments': {'table':'payments','title':'Payments','icon':'₹','pk':'payment_id','fields':[('user_id','User','user',True),('bill_id','Bill','bill',True),('amount','Amount','number',True),('mode','Mode','enum:UPI,CARD,CASH,SIMULATED',True),('payment_status','Payment status','enum:PENDING,SUCCESS,FAILED',True),('transaction_reference','Transaction reference','text',False)]},
 'users': {'table':'users','title':'Users','icon':'◎','pk':'user_id','fields':[('name','Name','text',True),('email_id','Email','email',True),('phone','Phone','text',False),('address','Address','text',False),('role','Role','enum:USER,ADMIN',True)]},
 'vehicles': {'table':'vehicles','title':'Vehicles','icon':'▰','pk':'vehicle_id','fields':[('user_id','User','user',True),('vehicle_no','Vehicle number','text',True),('model','Model','text',True),('battery_capacity','Battery capacity (kWh)','number',True)]}
}
FK_LOOKUPS = {'station':('charging_stations','station_id','station_name'),'slot':('charging_slots','slot_id','slot_id'),'user':('users','user_id','name'),'vehicle':('vehicles','vehicle_id','vehicle_no'),'tariff':('tariff_plans','tariff_id','charger_type'),'technician':('technicians','technician_id','name'),'session':('charging_sessions','session_id','session_id'),'bill':('bills','bill_id','bill_id')}

LIST_QUERIES = {
 'slots': ("SELECT sl.*, st.station_name FROM charging_slots sl JOIN charging_stations st ON st.station_id=sl.station_id", ["CAST(sl.slot_id AS CHAR)","st.station_name","sl.charger_type","CAST(sl.speed AS CHAR)","sl.status"]),
 'vehicles': ("SELECT v.*, u.name AS owner_name FROM vehicles v JOIN users u ON u.user_id=v.user_id", ["v.vehicle_no","v.model","u.name","CAST(v.battery_capacity AS CHAR)"]),
 'sessions': ("SELECT sd.*, tp.charger_type AS tariff_charger_type, tp.rate_per_kwh, b.bill_id FROM session_details sd JOIN tariff_plans tp ON tp.tariff_id=sd.tariff_id LEFT JOIN bills b ON b.session_id=sd.session_id", ["CAST(sd.session_id AS CHAR)","sd.station_name","CAST(sd.slot_id AS CHAR)","sd.slot_charger_type","sd.user_name","sd.vehicle_no","tp.charger_type","CAST(tp.rate_per_kwh AS CHAR)","sd.status"]),
 'bills': ("SELECT b.*, sd.session_id, sd.user_name, sd.station_name FROM bills b JOIN session_details sd ON sd.session_id=b.session_id", ["CAST(b.bill_id AS CHAR)","CAST(b.session_id AS CHAR)","sd.user_name","sd.station_name","CAST(b.amount AS CHAR)","CAST(b.gst AS CHAR)","b.status"]),
 'payments': ("SELECT p.*, u.name AS user_name, b.amount AS bill_amount FROM payments p JOIN users u ON u.user_id=p.user_id JOIN bills b ON b.bill_id=p.bill_id", ["CAST(p.payment_id AS CHAR)","u.name","CAST(p.bill_id AS CHAR)","CAST(b.amount AS CHAR)","CAST(p.amount AS CHAR)","p.mode","p.payment_status","p.transaction_reference"]),
 'maintenance': ("SELECT m.*, t.name AS technician_name, st.station_name FROM maintenance m JOIN technicians t ON t.technician_id=m.technician_id JOIN charging_stations st ON st.station_id=m.station_id", ["CAST(m.maintenance_id AS CHAR)","t.name","st.station_name","m.issue","CAST(m.maintenance_date AS CHAR)","m.status"])
}

def db():
    return mysql.connector.connect(host=os.getenv('DB_HOST','localhost'), port=int(os.getenv('DB_PORT','3306')), user=os.getenv('DB_USER','root'), password=os.getenv('DB_PASSWORD',''), database=os.getenv('DB_NAME','ev_charging_management'), autocommit=False)

def rows(sql, params=()):
    conn=db(); cur=conn.cursor(dictionary=True)
    try:
        cur.execute(sql,params); result=cur.fetchall(); conn.commit(); return result
    finally:
        cur.close(); conn.close()

def one(sql, params=()):
    result=rows(sql,params); return result[0] if result else None

def execute(sql, params=()):
    conn=db(); cur=conn.cursor()
    try:
        cur.execute(sql,params); conn.commit(); return cur.lastrowid,cur.rowcount
    except:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        if not session.get('manager_id'): return redirect(url_for('login', next=request.path))
        return fn(*args,**kwargs)
    return wrapped

@app.context_processor
def global_context(): return {'modules':MODULES}

def db_error(e):
    msg=str(e)
    if getattr(e,'errno',None)==1644 or '45000' in msg or 'signal sqlstate' in msg.lower(): return msg.split(': ',1)[-1] if ': ' in msg else msg
    if 'foreign key constraint fails' in msg.lower(): return 'This record is linked to other records. Remove or update its dependent records first.'
    if 'duplicate entry' in msg.lower():
        if 'transaction_reference' in msg.lower() or 'transaction reference' in msg.lower(): return 'That transaction reference already exists. Use a unique transaction reference.'
        return 'That value already exists. Check the unique fields and try again.'
    if 'cannot be null' in msg.lower() or 'check constraint' in msg.lower(): return 'One or more values violate a database requirement. Check the fields and try again.'
    return 'Database operation failed: '+msg

@app.route('/health')
def health():
    try:
        r=one('SELECT DATABASE() AS database_name, VERSION() AS mysql_version')
        return jsonify({'ok':True,'database':r['database_name'],'mysql_version':r['mysql_version']})
    except Exception as e: return jsonify({'ok':False,'error':str(e)}),503

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        try: user=one("SELECT user_id,name,email_id,password_hash,role FROM users WHERE LOWER(email_id)=%s",(email,))
        except Exception: flash('Could not connect to MySQL. Check .env and make sure MySQL is running.','error'); return render_template('login.html')
        if user and user['role']=='ADMIN' and user['password_hash'] and user['password_hash'].startswith(('scrypt:','pbkdf2:')) and check_password_hash(user['password_hash'],password):
            session.clear(); session['manager_id']=user['user_id']; session['manager_name']=user['name']; return redirect(request.args.get('next') or url_for('dashboard'))
        flash('Invalid manager credentials. Set a real password using python backend/setup_admin.py.','error')
    return render_template('login.html')

@app.route('/logout',methods=['POST'])
def logout(): session.clear(); return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    try:
        metrics={'stations':one('SELECT COUNT(*) n FROM charging_stations')['n'],'slots':one('SELECT COUNT(*) n FROM charging_slots')['n'],'available':one("SELECT COUNT(*) n FROM charging_slots WHERE status='AVAILABLE'")['n'],'occupied':one("SELECT COUNT(*) n FROM charging_slots WHERE status='OCCUPIED'")['n'],'sessions':one('SELECT COUNT(*) n FROM charging_sessions')['n'],'active':one("SELECT COUNT(*) n FROM charging_sessions WHERE status='ACTIVE'")['n'],'revenue':one("SELECT COALESCE(SUM(amount),0) n FROM payments WHERE payment_status='SUCCESS'")['n'],'maintenance':one("SELECT COUNT(*) n FROM maintenance WHERE status IN ('PENDING','IN_PROGRESS')")['n']}
        recent=rows('SELECT session_id,station_name,status,energy_kwh,booking_time FROM session_details ORDER BY booking_time DESC LIMIT 6')
        statuses=rows('SELECT status,COUNT(*) AS total FROM charging_sessions GROUP BY status')
        return render_template('dashboard.html',metrics=metrics,recent=recent,statuses=statuses)
    except Exception as e: return render_template('error.html',message='Dashboard could not load from MySQL: '+db_error(e))

def get_lookups(fields):
    lookups={}
    for field,label,kind,required in fields:
        if kind in FK_LOOKUPS:
            table,key,display=FK_LOOKUPS[kind]
            if kind=='vehicle': lookups[field]=rows("SELECT v.vehicle_id AS id, CONCAT(v.vehicle_no,' - ',u.name) AS label FROM vehicles v JOIN users u ON u.user_id=v.user_id ORDER BY v.vehicle_id DESC LIMIT 500")
            elif kind=='slot': lookups[field]=rows("SELECT sl.slot_id AS id, CONCAT(st.station_name,' - ',sl.slot_id,' - ',sl.charger_type) AS label FROM charging_slots sl JOIN charging_stations st ON st.station_id=sl.station_id ORDER BY sl.slot_id DESC LIMIT 500")
            elif kind=='tariff': lookups[field]=rows("SELECT tariff_id AS id, CONCAT(charger_type,' - ',rate_per_kwh) AS label FROM tariff_plans WHERE is_active=1 ORDER BY tariff_id DESC LIMIT 500")
            else: lookups[field]=rows(f'SELECT {key} AS id, {display} AS label FROM {table} ORDER BY {key} DESC LIMIT 500')
    return lookups

@app.route('/<module>')
@login_required
def list_module(module):
    if module not in MODULES: return redirect(url_for('dashboard'))
    cfg=MODULES[module]; search=request.args.get('q','').strip()
    try:
        if module in LIST_QUERIES:
            base_sql, searchable=LIST_QUERIES[module]
            sql=base_sql; params=[]
            if search:
                sql+=' WHERE '+' OR '.join(f"{col} LIKE %s" for col in searchable); params=['%'+search+'%']*len(searchable)
        else:
            sql=f"SELECT * FROM {cfg['table']}"; params=[]
            searchable=[f[0] for f in cfg['fields'] if f[2] in ('text','email')]
            if search and searchable: sql+=' WHERE '+' OR '.join(f"CAST({c} AS CHAR) LIKE %s" for c in searchable); params=['%'+search+'%']*len(searchable)
        sql+=f" ORDER BY {cfg['pk']} DESC LIMIT 300"
        data=rows(sql,params); lookups=get_lookups(cfg['fields'])
        display_fields = cfg['fields']
        if module == 'slots': display_fields = [('slot_id','Slot ID','text',True),('station_name','Station','text',True),('charger_type','Charger type','text',True),('speed','Speed (kW)','number',True),('status','Status','text',True)]
        elif module == 'vehicles': display_fields = [('vehicle_id','Vehicle ID','text',True),('vehicle_no','Vehicle number','text',True),('owner_name','Owner','text',True),('model','Model','text',True),('battery_capacity','Battery capacity (kWh)','number',True)]
        elif module == 'sessions': display_fields = [('session_id','Session','text',True),('station_name','Station','text',True),('slot_id','Slot','text',True),('slot_charger_type','Slot charger','text',True),('user_name','User','text',True),('vehicle_no','Vehicle','text',True),('tariff_charger_type','Tariff charger','text',True),('rate_per_kwh','Rate/kWh','number',True),('status','Status','text',True)]
        elif module == 'bills': display_fields = [('bill_id','Bill','text',True),('session_id','Session','text',True),('user_name','User','text',True),('station_name','Station','text',True),('amount','Amount','number',True),('gst','GST','number',True),('status','Status','text',True)]
        elif module == 'payments': display_fields = [('payment_id','Payment','text',True),('user_name','User','text',True),('bill_id','Bill','text',True),('bill_amount','Bill amount','number',True),('amount','Payment amount','number',True),('mode','Mode','text',True),('payment_status','Payment status','text',True),('transaction_reference','Transaction reference','text',False)]
        elif module == 'maintenance': display_fields = [('maintenance_id','Maintenance','text',True),('technician_name','Technician','text',True),('station_name','Station','text',True),('issue','Issue','text',True),('maintenance_date','Date','text',True),('status','Status','text',True)]
        return render_template('module.html',cfg=cfg,module=module,data=data,search=search,lookups=lookups,display_fields=display_fields)
    except Exception as e: return render_template('error.html',message='Could not load '+cfg['title']+': '+db_error(e))

@app.route('/<module>/new',methods=['GET','POST'])
@app.route('/<module>/<int:record_id>/edit',methods=['GET','POST'])
@login_required
def edit_module(module,record_id=None):
    if module not in MODULES: return redirect(url_for('dashboard'))
    cfg=MODULES[module]; editing=record_id is not None; record=None
    try:
        if editing: record=one(f"SELECT * FROM {cfg['table']} WHERE {cfg['pk']}=%s",(record_id,))
        if editing and not record: flash('Record not found.','error'); return redirect(url_for('list_module',module=module))
        lookups=get_lookups(cfg['fields'])
        if request.method=='POST':
            values=[]
            for field,label,kind,required in cfg['fields']:
                raw=request.form.get(field,'').strip()
                if required and raw=='': flash(label+' is required.','error'); return render_template('form.html',cfg=cfg,module=module,record=record,editing=editing,lookups=lookups)
                if kind=='bool': raw=1 if raw in ('1','true','on') else 0
                elif raw=='': raw=None
                if kind=='number' and raw is not None:
                    try:
                        if float(raw)<0: raise ValueError()
                    except ValueError: flash(label+' must be a valid non-negative number.','error'); return render_template('form.html',cfg=cfg,module=module,record=record,editing=editing,lookups=lookups)
                values.append(raw)
            if module=='sessions':
                slot_id=int(request.form['slot_id']); status=request.form['status']
                conn=db(); cur=conn.cursor(dictionary=True)
                try:
                    cur.execute('SELECT status FROM charging_slots WHERE slot_id=%s FOR UPDATE',(slot_id,))
                    slot=cur.fetchone()
                    if not slot: raise ValueError('Choose a valid charging slot.')
                    if status in ('BOOKED','ACTIVE'):
                        cur.execute("SELECT session_id FROM charging_sessions WHERE slot_id=%s AND status IN ('BOOKED','ACTIVE') AND session_id<>%s LIMIT 1",(slot_id,record_id or 0))
                        if cur.fetchone(): raise ValueError('That slot already has a booked or active session.')
                    cols=[f[0] for f in cfg['fields']]
                    if editing:
                        cur.execute(f"UPDATE charging_sessions SET "+', '.join(c+'=%s' for c in cols)+ " WHERE session_id=%s",tuple(values+[record_id]))
                    else:
                        cur.execute("INSERT INTO charging_sessions ("+', '.join(cols)+") VALUES ("+', '.join(['%s']*len(cols))+")",tuple(values))
                    conn.commit()
                except Exception:
                    conn.rollback(); raise
                finally:
                    cur.close(); conn.close()
            elif editing:
                cols=[f[0] for f in cfg['fields']]; execute(f"UPDATE {cfg['table']} SET "+', '.join(c+'=%s' for c in cols)+f" WHERE {cfg['pk']}=%s",values+[record_id])
            else:
                cols=[f[0] for f in cfg['fields']]; execute(f"INSERT INTO {cfg['table']} ("+', '.join(cols)+') VALUES ('+', '.join(['%s']*len(cols))+')',values)
            flash(cfg['title']+' saved to MySQL.','success'); return redirect(url_for('list_module',module=module))
        return render_template('form.html',cfg=cfg,module=module,record=record,editing=editing,lookups=lookups)
    except Exception as e:
        flash(db_error(e),'error'); return render_template('form.html',cfg=cfg,module=module,record=record,editing=editing,lookups=locals().get('lookups',{}))

@app.route('/<module>/<int:record_id>/delete',methods=['POST'])
@login_required
def delete_module(module,record_id):
    if module not in MODULES: return redirect(url_for('dashboard'))
    cfg=MODULES[module]
    try:
        if module=='users':
            current=one('SELECT user_id FROM users WHERE user_id=%s',(record_id,))
            if current and current['user_id']==session.get('manager_id'): flash('You cannot delete the manager account currently signed in.','error')
            else: execute(f"DELETE FROM {cfg['table']} WHERE {cfg['pk']}=%s",(record_id,)); flash('Record deleted.','success')
        else: execute(f"DELETE FROM {cfg['table']} WHERE {cfg['pk']}=%s",(record_id,)); flash('Record deleted.','success')
    except Exception as e: flash(db_error(e),'error')
    return redirect(url_for('list_module',module=module))

@app.route('/bills/generate/<int:session_id>',methods=['POST'])
@login_required
def generate_bill(session_id):
    try:
        conn=db(); cur=conn.cursor()
        try: cur.execute('CALL sp_generate_bill(%s)',(session_id,)); conn.commit()
        except Exception: conn.rollback(); raise
        finally: cur.close(); conn.close()
        flash(f'Bill generated for session #{session_id}.','success')
    except Exception as e: flash(db_error(e),'error')
    return redirect(url_for('list_module',module='bills'))

@app.route('/reports')
@login_required
def reports():
    try:
        revenue=rows("SELECT DATE(payment_date) AS day,SUM(amount) AS revenue FROM payments WHERE payment_status='SUCCESS' GROUP BY DATE(payment_date) ORDER BY day DESC LIMIT 14")
        by_station=rows("SELECT st.station_name,COUNT(cs.session_id) sessions,COALESCE(SUM(cs.energy_kwh),0) energy_kwh FROM charging_stations st LEFT JOIN charging_slots sl ON sl.station_id=st.station_id LEFT JOIN charging_sessions cs ON cs.slot_id=sl.slot_id GROUP BY st.station_id,st.station_name ORDER BY sessions DESC")
        maint=rows('SELECT status,COUNT(*) total FROM maintenance GROUP BY status')
        return render_template('reports.html',revenue=revenue,by_station=by_station,maint=maint)
    except Exception as e: return render_template('error.html',message='Reports could not load: '+db_error(e))

EXAMPLES = [
('Relational algebra','Selection + projection',"SELECT session_id, energy_kwh FROM charging_sessions WHERE status='COMPLETED'"),
('Relational algebra','DISTINCT',"SELECT DISTINCT city FROM charging_stations"),
('Relational algebra','UNION',"SELECT user_id FROM vehicles UNION SELECT user_id FROM payments"),
('Relational algebra','INTERSECT',"SELECT user_id FROM vehicles INTERSECT SELECT user_id FROM payments"),
('Relational algebra','EXCEPT',"SELECT user_id FROM vehicles EXCEPT SELECT user_id FROM payments"),
('Relational algebra','Cartesian product (CROSS JOIN)',"SELECT u.name, st.station_name FROM users u CROSS JOIN charging_stations st"),
('Relational algebra','Division: users who charged at every station',"SELECT u.user_id,u.name FROM users u WHERE NOT EXISTS (SELECT 1 FROM charging_stations st WHERE NOT EXISTS (SELECT 1 FROM charging_sessions cs JOIN charging_slots sl ON sl.slot_id=cs.slot_id JOIN vehicles v ON v.vehicle_id=cs.vehicle_id WHERE v.user_id=u.user_id AND sl.station_id=st.station_id))"),
('ER relationship joins','Station — slots',"SELECT st.station_name, sl.slot_id, sl.charger_type, sl.status FROM charging_stations st JOIN charging_slots sl ON sl.station_id=st.station_id"),
('ER relationship joins','User — vehicles',"SELECT u.name, v.vehicle_no, v.model FROM users u JOIN vehicles v ON v.user_id=u.user_id"),
('ER relationship joins','Slot — sessions',"SELECT sl.slot_id, cs.session_id, cs.status FROM charging_slots sl JOIN charging_sessions cs ON cs.slot_id=sl.slot_id"),
('ER relationship joins','Vehicle — sessions',"SELECT v.vehicle_no, cs.session_id, cs.status FROM vehicles v JOIN charging_sessions cs ON cs.vehicle_id=v.vehicle_id"),
('ER relationship joins','Tariff — sessions',"SELECT tp.charger_type, tp.rate_per_kwh, cs.session_id FROM tariff_plans tp JOIN charging_sessions cs ON cs.tariff_id=tp.tariff_id"),
('ER relationship joins','Session — bill',"SELECT cs.session_id, b.bill_id, b.amount FROM charging_sessions cs LEFT JOIN bills b ON b.session_id=cs.session_id"),
('ER relationship joins','Bill — payments',"SELECT b.bill_id, p.payment_id, p.amount FROM bills b LEFT JOIN payments p ON p.bill_id=b.bill_id"),
('ER relationship joins','User — payments',"SELECT u.name, p.payment_id, p.amount FROM users u JOIN payments p ON p.user_id=u.user_id"),
('ER relationship joins','Station — maintenance',"SELECT st.station_name, m.issue, m.status FROM charging_stations st JOIN maintenance m ON m.station_id=st.station_id"),
('ER relationship joins','Maintenance — technician',"SELECT t.name, m.issue, m.status FROM technicians t JOIN maintenance m ON m.technician_id=t.technician_id"),
('Join types','INNER JOIN',"SELECT st.station_name, sl.slot_id FROM charging_stations st INNER JOIN charging_slots sl ON sl.station_id=st.station_id"),
('Join types','LEFT JOIN',"SELECT st.station_name, sl.slot_id FROM charging_stations st LEFT JOIN charging_slots sl ON sl.station_id=st.station_id"),
('Join types','RIGHT JOIN',"SELECT st.station_name, sl.slot_id FROM charging_slots sl RIGHT JOIN charging_stations st ON st.station_id=sl.station_id"),
('Join types','FULL OUTER JOIN (LEFT UNION RIGHT)',"SELECT st.station_id, st.station_name, sl.slot_id FROM charging_stations st LEFT JOIN charging_slots sl ON sl.station_id=st.station_id UNION SELECT st.station_id, st.station_name, sl.slot_id FROM charging_stations st RIGHT JOIN charging_slots sl ON sl.station_id=st.station_id"),
('Join types','SELF JOIN: two vehicles owned by the same user',"SELECT a.vehicle_no AS vehicle_one, b.vehicle_no AS vehicle_two, u.name FROM vehicles a JOIN vehicles b ON a.user_id=b.user_id AND a.vehicle_id<b.vehicle_id JOIN users u ON u.user_id=a.user_id"),
('Join types','JOIN ... USING',"SELECT b.bill_id, b.amount, p.payment_id, p.amount AS payment_amount FROM bills b JOIN payments p USING (bill_id)"),
('Join types','Full relationship chain',"SELECT st.station_name, sl.slot_id, cs.session_id, v.vehicle_no, u.name AS user_name, tp.charger_type, b.bill_id, p.payment_id FROM charging_sessions cs JOIN charging_slots sl ON sl.slot_id=cs.slot_id JOIN charging_stations st ON st.station_id=sl.station_id JOIN vehicles v ON v.vehicle_id=cs.vehicle_id JOIN users u ON u.user_id=v.user_id JOIN tariff_plans tp ON tp.tariff_id=cs.tariff_id LEFT JOIN bills b ON b.session_id=cs.session_id LEFT JOIN payments p ON p.bill_id=b.bill_id"),
('Subqueries','IN',"SELECT name FROM users WHERE user_id IN (SELECT user_id FROM vehicles)"),
('Subqueries','NOT IN',"SELECT name FROM users WHERE user_id NOT IN (SELECT user_id FROM vehicles)"),
('Subqueries','Scalar',"SELECT session_id, energy_kwh FROM charging_sessions WHERE energy_kwh>(SELECT AVG(energy_kwh) FROM charging_sessions)"),
('Subqueries','Correlated',"SELECT v.vehicle_no FROM vehicles v WHERE v.battery_capacity>(SELECT AVG(v2.battery_capacity) FROM vehicles v2 WHERE v2.user_id=v.user_id)"),
('Subqueries','EXISTS',"SELECT st.station_name FROM charging_stations st WHERE EXISTS (SELECT 1 FROM maintenance m WHERE m.station_id=st.station_id)"),
('Subqueries','NOT EXISTS',"SELECT sl.slot_id FROM charging_slots sl WHERE NOT EXISTS (SELECT 1 FROM charging_sessions cs WHERE cs.slot_id=sl.slot_id)"),
('Subqueries','ANY',"SELECT session_id FROM charging_sessions WHERE energy_kwh>ANY (SELECT energy_kwh FROM charging_sessions WHERE status='COMPLETED')"),
('Subqueries','ALL',"SELECT session_id FROM charging_sessions WHERE energy_kwh>=ALL (SELECT energy_kwh FROM charging_sessions)"),
('Subqueries','Derived table in FROM',"SELECT status, avg_kwh FROM (SELECT status, AVG(energy_kwh) AS avg_kwh FROM charging_sessions GROUP BY status) AS status_energy"),
('Aggregates','COUNT / SUM / AVG / MIN / MAX',"SELECT COUNT(*) AS sessions, SUM(energy_kwh) AS total_kwh, AVG(energy_kwh) AS avg_kwh, MIN(energy_kwh) AS min_kwh, MAX(energy_kwh) AS max_kwh FROM charging_sessions"),
('Aggregates','GROUP BY',"SELECT status, COUNT(*) AS total FROM charging_sessions GROUP BY status"),
('Aggregates','HAVING',"SELECT user_id, COUNT(*) AS vehicles FROM vehicles GROUP BY user_id HAVING COUNT(*)>1"),
('Miscellaneous','LIKE',"SELECT name FROM users WHERE name LIKE 'A%'"),
('Miscellaneous','BETWEEN',"SELECT session_id, booking_time FROM charging_sessions WHERE booking_time BETWEEN NOW()-INTERVAL 7 DAY AND NOW()"),
('Miscellaneous','IS NULL',"SELECT session_id FROM charging_sessions WHERE start_time IS NULL"),
('Miscellaneous','CASE',"SELECT session_id, CASE WHEN energy_kwh>=20 THEN 'HIGH' WHEN energy_kwh>0 THEN 'LOW' ELSE 'NONE' END AS usage_band FROM charging_sessions"),
('Miscellaneous','ORDER BY',"SELECT station_name, city FROM charging_stations ORDER BY station_name"),
('Miscellaneous','LIMIT',"SELECT session_id, booking_time FROM charging_sessions ORDER BY booking_time DESC LIMIT 5"),
('Views and indexes','session_details view',"SELECT session_id, station_name, user_name, vehicle_no, status FROM session_details"),
('Views and indexes','charging_history view',"SELECT * FROM charging_history"),
('Views and indexes','EXPLAIN status filter',"EXPLAIN SELECT session_id, slot_id, status FROM charging_sessions WHERE status='COMPLETED'")
]

EXAMPLE_GROUPS = {}
for group, title, sql in EXAMPLES:
    EXAMPLE_GROUPS.setdefault(group, []).append((title, sql))

@app.route('/sql-playground',methods=['GET','POST'])
@login_required
def sql_playground():
    query=request.form.get('query',EXAMPLES[0][2]); result=None; columns=[]; error=None; affected=None
    destructive=bool(re.match(r'\s*(DELETE|DROP|TRUNCATE|ALTER|UPDATE)\b',query,re.I))
    if request.method=='POST' and request.form.get('run')=='1':
        try:
            if ';' in query.strip().rstrip(';'): raise ValueError('Only one SQL statement can be run at a time.')
            if not query.strip(): raise ValueError('Enter a SQL statement first.')
            if destructive and request.form.get('confirm')!='yes': raise ValueError('For safety, confirm this data-changing query using the checkbox, then run it again.')
            conn=db(); cur=conn.cursor(dictionary=True)
            try:
                cur.execute(query)
                if cur.with_rows:
                    result=cur.fetchmany(500); columns=list(result[0].keys()) if result else [d[0] for d in cur.description]
                else: affected=cur.rowcount
                conn.commit()
            except: conn.rollback(); raise
            finally: cur.close(); conn.close()
        except Exception as e: error=db_error(e)
    return render_template('sql.html',examples=EXAMPLES,example_groups=EXAMPLE_GROUPS,query=query,result=result,columns=columns,error=error,affected=affected,destructive=destructive)

@app.errorhandler(404)
def not_found(e): return redirect(url_for('dashboard') if session.get('manager_id') else url_for('login'))

if __name__=='__main__':
    app.run(host='127.0.0.1',port=int(os.getenv('PORT','5000')),debug=os.getenv('FLASK_DEBUG','false').lower()=='true')
