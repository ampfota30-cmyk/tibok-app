from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from functools import wraps
import pymongo
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# --- FIX FOR APPLE & ANDROID ICONS ---
@app.route('/favicon.ico')
@app.route('/apple-touch-icon.png')
@app.route('/apple-touch-icon-precomposed.png')
@app.route('/apple-touch-icon-120x120.png')
@app.route('/apple-touch-icon-120x120-precomposed.png')
def serve_apple_icons():
    return app.send_static_file('logo.png')

app.secret_key = "secure_ncd_secret_key_2026"
app.permanent_session_lifetime = timedelta(days=365) # STAY LOGGED IN FOR 1 YEAR

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r

# --- MONGODB CLOUD CONNECTION ---
MONGO_URI = "mongodb+srv://namoroc:bhw2026@hypertension.tzs1dpj.mongodb.net/?appName=Hypertension"

try:
    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client["ncd_database"]
    patients_col = db["patients"]
    visits_col = db["visits"]
    users_col = db["users"] 
    
    if users_col.count_documents({"username": "admin"}) == 0:
        users_col.insert_one({
            "username": "admin", "password": "password123", "role": "admin", "name": "System Admin"
        })
except Exception as e:
    print(f"Database connection failed: {e}")

# ==========================================
# 🔒 AUTHENTICATION
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = request.args.get('next') or request.form.get('next') or '/'
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = users_col.find_one({"username": username, "password": password})
        if user:
            session.permanent = True 
            session['logged_in'] = True
            session['username'] = user['username']
            session['role'] = user['role']
            session['name'] = user.get('name', 'BHW')
            return redirect(next_url)
        else:
            return render_template('login.html', error="Invalid username or password.", next_url=next_url)
    return render_template('login.html', next_url=next_url)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ==========================================
# 📱 APP CORE API
# ==========================================
@app.route('/')
@app.route('/mobile')
@login_required
def home():
    return render_template('index.html')

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def serve_sw():
    return send_from_directory('static', 'sw.js')

@app.route('/api/me', methods=['GET'])
@login_required
def get_me():
    return jsonify({
        "username": session.get('username'),
        "role": session.get('role'),
        "name": session.get('name')
    })

@app.route('/api/data', methods=['GET'])
@login_required
def get_data():
    db_patients = list(patients_col.find())
    db_visits = list(visits_col.find())
    js_patients = []
    
    for p in db_patients:
        p_id = str(p.get("patient_id", ""))
        p_visits = [v for v in db_visits if str(v.get("patient_id")) == p_id]
        p_visits.sort(key=lambda x: x.get("visit_date", ""), reverse=True)
        
        bp_list = []
        visit_list = []
        
        for v in reversed(p_visits):
            bp = v.get("blood_pressure") or {}
            if bp.get("sys_1"):
                bp_list.append({ "date": str(v.get("visit_date", "Unknown")), "sys": bp.get("sys_1", 0), "dia": bp.get("dia_1", 0) })
                
        for v in p_visits:
            bp = v.get("blood_pressure") or {}
            sys_val, dia_val = bp.get("sys_1", ""), bp.get("dia_1", "")
            avg_val = bp.get("avg_bp") or (f"{sys_val}/{dia_val}" if sys_val else "N/A")
            visit_note = str(v.get("notes", v.get("details", "")))
            
            visit_list.append({
                "date": str(v.get("visit_date", "Unknown")), 
                "title": v.get("visit_type", "Visit"),
                "avg": avg_val, 
                "notes": visit_note, 
                "assessed_by": str(v.get("assessed_by", "Unknown"))
            })
            
        js_patients.append({
            "id": p_id, 
            "firstName": p.get("first_name", p.get("name", "").split(" ")[0] if p.get("name") else "Unknown"),
            "middleName": p.get("middle_name", ""),
            "lastName": p.get("last_name", " ".join(p.get("name", "").split(" ")[1:]) if p.get("name") else ""),
            "age": p.get("age", 0), 
            "sex": p.get("sex", "Unknown"),
            "civil": p.get("civil_status", "Unknown"), 
            "homeAddress": p.get("home_address", p.get("address", "Unknown")),
            "purok": p.get("purok", ""),
            "height": p.get("height", 0),
            "weight": p.get("weight", 0),
            "contact": p.get("contact_number", ""), 
            "status": p.get("status", "Active"),
            "notes": p.get("notes", ""), 
            "bp": bp_list, 
            "visits": visit_list,
            "lastUpdated": p.get("last_updated", (p_visits[0].get("visit_date", "New") if p_visits else "New"))
        })
    return jsonify(js_patients)

@app.route('/api/add_patient', methods=['POST'])
@login_required
def add_patient():
    data = request.json
    pid = data.get("patientId")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    notes = data.get("notes", "")

    new_doc = {
        "patient_id": pid, 
        "first_name": data.get("firstName", ""),
        "middle_name": data.get("middleName", ""),
        "last_name": data.get("lastName", ""),
        "name": f"{data.get('firstName', '')} {data.get('lastName', '')}".strip(),
        "age": int(data.get("age", 0) or 0), 
        "sex": data.get("sex"), 
        "civil_status": data.get("civil"),
        "status": data.get("status"), 
        "home_address": data.get("homeAddress", ""),
        "purok": data.get("purok", ""),
        "height": float(data.get("height", 0) or 0),
        "weight": float(data.get("weight", 0) or 0),
        "contact_number": data.get("contact"), 
        "notes": notes, 
        "last_updated": timestamp
    }
    patients_col.update_one({"patient_id": pid}, {"$set": new_doc}, upsert=True)

    sys_val, dia_val = data.get("sys"), data.get("dia")
    if sys_val and dia_val:
        visits_col.insert_one({
            "patient_id": pid, 
            "visit_date": timestamp, 
            "visit_type": "Initial Registration",
            "blood_pressure": { "sys_1": int(sys_val), "dia_1": int(dia_val), "avg_bp": f"{sys_val}/{dia_val}" },
            "notes": notes if notes.strip() else "Baseline BP taken during registration.",
            "assessed_by": data.get("assessedBy") or "System Admin"
        })
    return jsonify({"status": "success"})

@app.route('/api/log_visit', methods=['POST'])
@login_required
def log_visit():
    data = request.json
    pid = data.get("patientId")
    sys_val, dia_val = data.get("sys"), data.get("dia")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    new_visit = {
        "patient_id": pid, 
        "visit_date": timestamp, 
        "visit_type": data.get("visitType"),
        "blood_pressure": { "sys_1": int(sys_val) if sys_val else 0, "dia_1": int(dia_val) if dia_val else 0, "avg_bp": f"{sys_val}/{dia_val}" if sys_val else "N/A" },
        "notes": data.get("notes", ""), 
        "assessed_by": data.get("assessedBy") or "Unknown BHW"
    }
    visits_col.insert_one(new_visit)
    
    update_fields = {"last_updated": timestamp}
    if data.get("height"): update_fields["height"] = float(data.get("height"))
    if data.get("weight"): update_fields["weight"] = float(data.get("weight"))
        
    patients_col.update_one({"patient_id": pid}, {"$set": update_fields})
    return jsonify({"status": "success"})

@app.route('/api/delete_visit', methods=['POST'])
@login_required
def delete_visit():
    pid = request.json.get("patientId")
    vdate = request.json.get("visitDate")
    visits_col.delete_one({"patient_id": pid, "visit_date": vdate})
    return jsonify({"status": "success"})

@app.route('/api/delete_patient', methods=['POST'])
@login_required
def delete_patient():
    pid = request.json.get("patientId")
    patients_col.delete_one({"patient_id": pid})
    visits_col.delete_many({"patient_id": pid})
    return jsonify({"status": "success"})

# --- USER API ENDPOINTS ---
@app.route('/api/users', methods=['GET'])
@login_required
def get_users():
    if session.get('role') != 'admin': return jsonify([]), 403
    return jsonify(list(users_col.find({}, {"_id": 0, "password": 0})))

@app.route('/api/add_user', methods=['POST'])
@login_required
def add_user():
    if session.get('role') != 'admin': return jsonify({"error": "Unauthorized"}), 403
    data = request.json
    if users_col.find_one({"username": data.get("username")}):
        return jsonify({"status": "error", "message": "Username already exists!"})
    
    # 🟢 FIX: Explicity assign role to "bhw" on creation
    users_col.insert_one({
        "name": data.get("name"),
        "username": data.get("username"),
        "password": data.get("password"),
        "role": "bhw"
    })
    return jsonify({"status": "success"})

@app.route('/api/delete_user', methods=['POST'])
@login_required
def delete_user():
    if session.get('role') != 'admin': return jsonify({"error": "Unauthorized"}), 403
    if request.json.get("username") == 'admin': return jsonify({"status": "error", "message": "Cannot delete master admin."})
    users_col.delete_one({"username": request.json.get("username")})
    return jsonify({"status": "success"})

@app.route('/api/reset_password', methods=['POST'])
@login_required
def reset_password():
    if session.get('role') != 'admin': return jsonify({"error": "Unauthorized"}), 403
    users_col.update_one({"username": request.json.get("username")}, {"$set": {"password": request.json.get("newPassword")}})
    return jsonify({"status": "success"})

if __name__ == '__main__':
    if not os.path.exists('static'):
        os.makedirs('static')
    app.run(debug=True, port=5000)
