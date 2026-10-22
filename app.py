import os, re
from datetime import date, datetime
from decimal import Decimal
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import check_password_hash
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'change-this-before-use')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')

# Only these schema-backed tables/columns are exposed through generic management screens.
MODULES = {
 'stations': {'table':'charging_stations','title':'Stations','icon':'⌖','pk':'station_id','fields':[('station_name','Station name','text',True),('address','Address','text',True),('city','City','text',True)]},
 'slots': {'table':'charging_slots','title':'Charging slots','icon':'ϟ','pk':'slot_id','fields':[('station_id','Station','station',True),('charger_type','Charger type','text',True),('speed','Speed (kW)','number',True),('status','Status','enum:AVAILABLE,OCCUPIED,MAINTENANCE',True)]},
 'tariffs': {'table':'tariff_plans','title':'Tariff plans','icon':'₹','pk':'tariff_id','fields':[('charger_type','Charger type','text',True),('rate_per_kwh','Rate per kWh','number',True),('service_fee','Service fee','number',True),('is_active','Active','bool',True)]},
 'sessions': {'table':'charging_sessions','title':'Charging sessions','icon':'↗','pk':'session_id','fields':[('station_id','Station','station',True),('slot_id','Slot','slot',True),('user_id','User','user',True),('vehicle_id','Vehicle','vehicle',True),('tariff_id','Tariff','tariff',True),('duration','Duration (minutes)','number',True),('start_time','Start time','datetime',False),('end_time','End time','datetime',False),('energy_kwh','Energy (kWh)','number',True),('status','Status','enum:BOOKED,ACTIVE,COMPLETED,CANCELLED',True)]},
 'technicians': {'table':'technicians','title':'Technicians','icon':'⚒','pk':'technician_id','fields':[('name','Name','text',True),('experience','Experience (years)','number',True),('phone','Phone','text',False)]},
 'maintenance': {'table':'maintenance','title':'Maintenance','icon':'⚒','pk':'maintenance_id','fields':[('technician_id','Technician','technician',True),('station_id','Station','station',True),('issue','Issue','text',True),('maintenance_date','Maintenance date','date',True),('status','Status','enum:PENDING,IN_PROGRESS,COMPLETED',True)]},
 'bills': {'table':'bills','title':'Bills','icon':'▤','pk':'bill_id','fields':[('session_id','Session','session',True),('amount','Amount before GST','number',True),('gst','GST (%)','number',True),('status','Status','enum:ESTIMATED,FINAL,PAID',True)]},
 'payments': {'table':'payments','title':'Payments','icon':'₹','pk':'payment_id','fields':[('user_id','User','user',True),('bill_id','Bill','bill',True),('amount','Amount','number',True),('mode','Mode','enum:UPI,CARD,CASH,SIMULATED',True),('payment_status','Payment status','enum:PENDING,SUCCESS,FAILED',True),('transaction_reference','Transaction reference','text',False)]},
 'users': {'table':'users','title':'Users','icon':'◎','pk':'user_id','fields':[('name','Name','text',True),('email_id','Email','email',True),('phone','Phone','text',False),('address','Address','text',False),('role','Role','enum:USER,ADMIN',True)]},
 'vehicles': {'table':'vehicles','title':'Vehicles','icon':'▰','pk':'vehicle_id','fields':[('user_id','User','user',True),('vehicle_no','Vehicle number','text',True),('model','Model','text',True),('battery_capacity','Battery capacity (kWh)','number',True)]}
}
FK_LOOKUPS = {'station':('charging_stations','station_id','station_name'),'slot':('charging_slots','slot_id','slot_id'),'user':('users','user_id','name'),'vehicle':('vehicles','vehicle_id','vehicle_no'),'tariff':('tariff_plans','tariff_id','charger_type'),'technician':('technicians','technician_id','name'),'session':('charging_sessions','session_id','session_id'),'bill':('bills','bill_id','bill_id')}

def db():
    return mysql.connector.connect(host=os.getenv('DB_HOST','localhost'), port=int(os.getenv('DB_PORT','3306')), user=os.getenv('DB_USER','root'), password=os.getenv('DB_PASSWORD',''), database=os.getenv('DB_NAME','ev_charging_management'), autocommit=False)

def rows(sql, params=()):
    conn=db(); cur=conn.cursor(dictionary=True)
    try:
        cur.execute(sql,params); result=cur.fetchall(); conn.commit(); return result
    finally: cur.close(); conn.close()

def one(sql, params=()):
    result=rows(sql,params); return result[0] if result else None

def execute(sql, params=()):
    conn=db(); cur=conn.cursor()
    try: cur.execute(sql,params); conn.commit(); return cur.lastrowid,cur.rowcount
    except: conn.rollback(); raise
    finally: cur.close(); conn.close()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        if not session.get('manager_id'): return redirect(url_for('login', next=request.path))
        return fn(*args,**kwargs)
    return wrapped

@app.context_processor
def global_context(): return {'modules':MODULES}

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
        except Exception as e: flash('Could not connect to MySQL. Check .env and make sure MySQL is running.','error'); return render_template('login.html')
        if user and user['role']=='ADMIN' and user['password_hash'] and user['password_hash'].startswith(('scrypt:','pbkdf2:')) and check_password_hash(user['password_hash'],password):
            session.clear(); session['manager_id']=user['user_id']; session['manager_name']=user['name']; return redirect(request.args.get('next') or url_for('dashboard'))
        flash('Invalid manager credentials. Set a real password using setup_admin.py.','error')
    return render_template('login.html')

@app.route('/logout',methods=['POST'])
def logout(): session.clear(); return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    try:
        metrics={
          'stations':one('SELECT COUNT(*) n FROM charging_stations')['n'],
          'slots':one('SELECT COUNT(*) n FROM charging_slots')['n'],
          'available':one("SELECT COUNT(*) n FROM charging_slots WHERE status='AVAILABLE'")['n'],
          'occupied':one("SELECT COUNT(*) n FROM charging_slots WHERE status='OCCUPIED'")['n'],
          'sessions':one('SELECT COUNT(*) n FROM charging_sessions')['n'],
          'active':one("SELECT COUNT(*) n FROM charging_sessions WHERE status='ACTIVE'")['n'],
          'revenue':one("SELECT COALESCE(SUM(amount),0) n FROM payments WHERE payment_status='SUCCESS'")['n'],
          'maintenance':one("SELECT COUNT(*) n FROM maintenance WHERE status IN ('PENDING','IN_PROGRESS')")['n']}
        recent=rows('''SELECT cs.session_id, s.station_name, cs.status, cs.energy_kwh, cs.booking_time
          FROM charging_sessions cs JOIN charging_stations s ON s.station_id=cs.station_id ORDER BY cs.booking_time DESC LIMIT 6''')
        city=rows('SELECT city,COUNT(*) AS total FROM charging_stations GROUP BY city ORDER BY total DESC')
        statuses=rows('SELECT status,COUNT(*) AS total FROM charging_sessions GROUP BY status')
        return render_template('dashboard.html',metrics=metrics,recent=recent,city=city,statuses=statuses)
    except Exception as e: return render_template('error.html',message='Dashboard could not load from MySQL: '+str(e))

@app.route('/<module>')
@login_required
def list_module(module):
    if module not in MODULES: return redirect(url_for('dashboard'))
    cfg=MODULES[module]; search=request.args.get('q','').strip()
    try:
        sql=f"SELECT * FROM {cfg['table']}"; params=[]
        if search:
            searchable=[f[0] for f in cfg['fields'] if f[2] in ('text','email')]
            if searchable: sql+=' WHERE '+' OR '.join(f"CAST({c} AS CHAR) LIKE %s" for c in searchable); params=['%'+search+'%']*len(searchable)
        sql+=f" ORDER BY {cfg['pk']} DESC LIMIT 300"
        data=rows(sql,params)
        lookups={}
        for field,label,kind,required in cfg['fields']:
            if kind in FK_LOOKUPS:
                table,key,display=FK_LOOKUPS[kind]; lookups[field]=rows(f'SELECT {key} AS id, {display} AS label FROM {table} ORDER BY {key} DESC LIMIT 500')
        return render_template('module.html',cfg=cfg,module=module,data=data,search=search,lookups=lookups)
    except Exception as e: return render_template('error.html',message='Could not load '+cfg['title']+': '+str(e))

@app.route('/<module>/new',methods=['GET','POST'])
@app.route('/<module>/<int:record_id>/edit',methods=['GET','POST'])
@login_required
def edit_module(module,record_id=None):
    if module not in MODULES: return redirect(url_for('dashboard'))
    cfg=MODULES[module]; editing=record_id is not None; record=None
    try:
        if editing: record=one(f"SELECT * FROM {cfg['table']} WHERE {cfg['pk']}=%s",(record_id,));
        if editing and not record: flash('Record not found.','error'); return redirect(url_for('list_module',module=module))
        lookups={}
        for field,label,kind,required in cfg['fields']:
            if kind in FK_LOOKUPS:
                table,key,display=FK_LOOKUPS[kind]; lookups[field]=rows(f'SELECT {key} AS id, {display} AS label FROM {table} ORDER BY {key} DESC LIMIT 500')
        if request.method=='POST':
            values=[]
            for field,label,kind,required in cfg['fields']:
                raw=request.form.get(field,'').strip()
                if required and raw=='': flash(label+' is required.','error'); return render_template('form.html',cfg=cfg,module=module,record=record,editing=editing,lookups=lookups)
                if kind=='bool': raw=1 if raw in ('1','true','on') else 0
                elif raw=='' and kind in ('date','datetime'): raw=None
                elif raw=='': raw=None
                if kind=='number' and raw is not None:
                    try:
                        if float(raw)<0: raise ValueError()
                    except ValueError: flash(label+' must be a valid non-negative number.','error'); return render_template('form.html',cfg=cfg,module=module,record=record,editing=editing,lookups=lookups)
                values.append(raw)
            if module=='sessions':
                station_id=int(request.form['station_id']); slot_id=int(request.form['slot_id']); status=request.form['status']
                slot=one('SELECT station_id,status FROM charging_slots WHERE slot_id=%s',(slot_id,))
                if not slot or int(slot['station_id'])!=station_id: flash('Choose a slot belonging to the selected station.','error'); return render_template('form.html',cfg=cfg,module=module,record=record,editing=editing,lookups=lookups)
                if status in ('BOOKED','ACTIVE') and slot['status']=='MAINTENANCE': flash('A slot under maintenance cannot be booked or activated.','error'); return render_template('form.html',cfg=cfg,module=module,record=record,editing=editing,lookups=lookups)
                vehicle=one('SELECT user_id FROM vehicles WHERE vehicle_id=%s',(int(request.form['vehicle_id']),))
                if not vehicle or int(vehicle['user_id'])!=int(request.form['user_id']): flash('Selected vehicle does not belong to selected user.','error'); return render_template('form.html',cfg=cfg,module=module,record=record,editing=editing,lookups=lookups)
                if status in ('BOOKED','ACTIVE'):
                    occupied=one("SELECT COUNT(*) n FROM charging_sessions WHERE slot_id=%s AND status IN ('BOOKED','ACTIVE') AND session_id<>%s",(slot_id,record_id or 0))['n']
                    if occupied: flash('That slot already has a booked or active session.','error'); return render_template('form.html',cfg=cfg,module=module,record=record,editing=editing,lookups=lookups)
            if editing:
                cols=[f[0] for f in cfg['fields']]; sql=f"UPDATE {cfg['table']} SET "+', '.join(c+'=%s' for c in cols)+f" WHERE {cfg['pk']}=%s"; execute(sql,values+[record_id])
            else:
                cols=[f[0] for f in cfg['fields']]; execute(f"INSERT INTO {cfg['table']} ("+', '.join(cols)+') VALUES ('+', '.join(['%s']*len(cols))+')',values)
            if module=='sessions': sync_slot_status(int(request.form['slot_id']))
            flash(cfg['title']+' saved to MySQL.','success'); return redirect(url_for('list_module',module=module))
        return render_template('form.html',cfg=cfg,module=module,record=record,editing=editing,lookups=lookups)
    except Exception as e:
        flash(db_error(e),'error'); return render_template('form.html',cfg=cfg,module=module,record=record,editing=editing,lookups=locals().get('lookups',{}))

def sync_slot_status(slot_id):
    active=one("SELECT COUNT(*) n FROM charging_sessions WHERE slot_id=%s AND status IN ('BOOKED','ACTIVE')",(slot_id,))['n']
    slot=one('SELECT status FROM charging_slots WHERE slot_id=%s',(slot_id,))
    if slot and slot['status']!='MAINTENANCE': execute('UPDATE charging_slots SET status=%s WHERE slot_id=%s',('OCCUPIED' if active else 'AVAILABLE',slot_id))

def db_error(e):
    msg=str(e)
    if 'foreign key constraint fails' in msg.lower(): return 'This record is linked to other records. Remove or update its dependent records first.'
    if 'duplicate entry' in msg.lower(): return 'That value already exists. Check unique fields such as email, vehicle number, or transaction reference.'
    if 'cannot be null' in msg.lower() or 'check constraint' in msg.lower(): return 'One or more values violate a database requirement. Check the fields and try again.'
    return 'Database operation failed: '+msg

@app.route('/<module>/<int:record_id>/delete',methods=['POST'])
@login_required
def delete_module(module,record_id):
    if module not in MODULES: return redirect(url_for('dashboard'))
    cfg=MODULES[module]
    try:
        if module=='users' and one('SELECT user_id FROM users WHERE user_id=%s',(record_id,))['user_id']==session.get('manager_id'): flash('You cannot delete the manager account currently signed in.','error')
        else:
            execute(f"DELETE FROM {cfg['table']} WHERE {cfg['pk']}=%s",(record_id,)); flash('Record deleted.','success')
    except Exception as e: flash(db_error(e),'error')
    return redirect(url_for('list_module',module=module))

@app.route('/reports')
@login_required
def reports():
    try:
        revenue=rows("SELECT DATE(payment_date) AS day, SUM(amount) AS revenue FROM payments WHERE payment_status='SUCCESS' GROUP BY DATE(payment_date) ORDER BY day DESC LIMIT 14")
        by_station=rows('''SELECT s.station_name, COUNT(cs.session_id) sessions, COALESCE(SUM(cs.energy_kwh),0) energy_kwh
            FROM charging_stations s LEFT JOIN charging_sessions cs ON cs.station_id=s.station_id GROUP BY s.station_id,s.station_name ORDER BY sessions DESC''')
        maint=rows('SELECT status,COUNT(*) total FROM maintenance GROUP BY status')
        return render_template('reports.html',revenue=revenue,by_station=by_station,maint=maint)
    except Exception as e: return render_template('error.html',message='Reports could not load: '+str(e))

EXAMPLES=[
 ('SELECT + WHERE','Find completed charging sessions.',"SELECT session_id, station_id, energy_kwh, status FROM charging_sessions WHERE status = 'COMPLETED' LIMIT 100"),
 ('ORDER BY','Sort stations alphabetically.',"SELECT station_id, station_name, city FROM charging_stations ORDER BY station_name ASC"),
 ('Aggregates','COUNT, SUM, AVG, MIN and MAX of energy.',"SELECT COUNT(*) AS sessions, SUM(energy_kwh) AS total_kwh, AVG(energy_kwh) AS avg_kwh, MIN(energy_kwh) AS min_kwh, MAX(energy_kwh) AS max_kwh FROM charging_sessions"),
 ('GROUP BY','Count sessions by status.',"SELECT status, COUNT(*) AS total_sessions FROM charging_sessions GROUP BY status"),
 ('HAVING','Find users with more than one session.',"SELECT u.name, COUNT(cs.session_id) AS total_sessions FROM users u JOIN charging_sessions cs ON u.user_id=cs.user_id GROUP BY u.user_id,u.name HAVING COUNT(cs.session_id)>1"),
 ('INNER JOIN','Sessions with station, user and vehicle details.',"SELECT cs.session_id,s.station_name,u.name AS user_name,v.vehicle_no,cs.status,cs.energy_kwh FROM charging_sessions cs JOIN charging_stations s ON s.station_id=cs.station_id JOIN users u ON u.user_id=cs.user_id JOIN vehicles v ON v.vehicle_id=cs.vehicle_id LIMIT 100"),
 ('LEFT JOIN','Show every station including those with no sessions.',"SELECT s.station_name,COUNT(cs.session_id) AS sessions FROM charging_stations s LEFT JOIN charging_sessions cs ON cs.station_id=s.station_id GROUP BY s.station_id,s.station_name"),
 ('Subquery','Users with at least one completed session.',"SELECT name FROM users WHERE user_id IN (SELECT user_id FROM charging_sessions WHERE status='COMPLETED')"),
 ('Successful payment revenue','Total successful payments by mode.',"SELECT mode,COUNT(*) AS payments,SUM(amount) AS revenue FROM payments WHERE payment_status='SUCCESS' GROUP BY mode"),
 ('Slot availability','Slot counts by station and status.',"SELECT s.station_name,sl.status,COUNT(*) AS slots FROM charging_slots sl JOIN charging_stations s ON s.station_id=sl.station_id GROUP BY s.station_id,s.station_name,sl.status ORDER BY s.station_name"),
 ('Maintenance summary','Maintenance count by status and station.',"SELECT s.station_name,m.status,COUNT(*) AS records FROM maintenance m JOIN charging_stations s ON s.station_id=m.station_id GROUP BY s.station_id,s.station_name,m.status"),
 ('Tariff and energy','Estimate session energy charges using the applied tariff.',"SELECT cs.session_id,s.station_name,cs.energy_kwh,tp.rate_per_kwh,(cs.energy_kwh*tp.rate_per_kwh+tp.service_fee) AS estimated_before_gst FROM charging_sessions cs JOIN charging_stations s ON s.station_id=cs.station_id JOIN tariff_plans tp ON tp.tariff_id=cs.tariff_id LIMIT 100"),
 ('Bills with payments','Compare bill status and payment status.',"SELECT b.bill_id,b.amount,b.gst,b.status AS bill_status,p.amount AS paid_amount,p.mode,p.payment_status FROM bills b LEFT JOIN payments p ON p.bill_id=b.bill_id LIMIT 100")]
@app.route('/sql-playground',methods=['GET','POST'])
@login_required
def sql_playground():
    query=request.form.get('query',EXAMPLES[0][2]); selected=request.form.get('example','')
    result=None; columns=[]; error=None; affected=None; destructive=bool(re.match(r'\s*(DELETE|DROP|TRUNCATE|ALTER|UPDATE)\b',query,re.I))
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
                    conn.commit()
                else:
                    affected=cur.rowcount; conn.commit()
            except: conn.rollback(); raise
            finally: cur.close(); conn.close()
        except Exception as e: error=str(e)
    return render_template('sql.html',examples=EXAMPLES,query=query,result=result,columns=columns,error=error,affected=affected,destructive=destructive)

@app.errorhandler(404)
def not_found(e): return redirect(url_for('dashboard') if session.get('manager_id') else url_for('login'))
if __name__=='__main__': app.run(host='127.0.0.1',port=int(os.getenv('PORT','5000')),debug=os.getenv('FLASK_DEBUG','false').lower()=='true')
