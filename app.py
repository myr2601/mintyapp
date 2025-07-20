from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
import os
import sys
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import joinedload
import pandas as pd

app = Flask(__name__)

database_url = os.environ.get('DATABASE_URL')
if database_url:
    database_url = database_url.replace("postgres://", "postgresql://", 1)

if getattr(sys, 'frozen', False):
    basedir = os.path.dirname(sys.executable)
else:
    basedir = os.path.abspath(os.path.dirname(__file__))

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///' + os.path.join(basedir, 'gudang.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'kunci-rahasia-lokal-yang-super-aman')

db = SQLAlchemy(app)

# --- Model Database (Tidak ada perubahan) ---
user_material_permissions = db.Table('user_material_permissions',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('material_id', db.Integer, db.ForeignKey('material.id'), primary_key=True)
)

class Kantor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama_kantor = db.Column(db.String(100), unique=True, nullable=False)
    kode_kantor = db.Column(db.String(20), unique=True, nullable=False)
    users = db.relationship('User', backref='kantor', lazy=True)
    materials = db.relationship('Material', backref='kantor', lazy=True)
    transactions = db.relationship('Transaction', backref='kantor', lazy=True)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')
    kantor_id = db.Column(db.Integer, db.ForeignKey('kantor.id'), nullable=False)
    permitted_materials = db.relationship('Material', secondary=user_material_permissions, lazy='subquery',
        backref=db.backref('permitted_users', lazy=True))

class Satuan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(10), unique=True, nullable=False)
    materials = db.relationship('Material', backref='satuan', lazy=True)

class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    id_barang = db.Column(db.String(50), nullable=False) 
    nama_material = db.Column(db.String(200), nullable=False)
    jumlah = db.Column(db.Integer, nullable=False)
    kantor_id = db.Column(db.Integer, db.ForeignKey('kantor.id'), nullable=False)
    satuan_id = db.Column(db.Integer, db.ForeignKey('satuan.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('id_barang', 'kantor_id', name='_id_barang_kantor_uc'),)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('material.id'), nullable=False)
    tipe_transaksi = db.Column(db.String(10), nullable=False)
    jumlah = db.Column(db.Integer, nullable=False)
    sumber = db.Column(db.String(100), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    kantor_id = db.Column(db.Integer, db.ForeignKey('kantor.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('transactions', lazy=True))
    material = db.relationship('Material', backref=db.backref('transactions', lazy=True))

# --- Rute Aplikasi (Tidak ada perubahan signifikan) ---
# ... (Semua @app.route kamu tetap sama di sini) ...
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['kantor_id'] = user.kantor_id
            kantor = Kantor.query.get(user.kantor_id)
            session['nama_kantor'] = kantor.nama_kantor
            flash('Login berhasil!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau Password salah.', 'danger')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    user_kantor_id = session.get('kantor_id')
    total_material_types = Material.query.filter_by(kantor_id=user_kantor_id).count()
    total_stock = db.session.query(db.func.sum(Material.jumlah)).filter(Material.kantor_id == user_kantor_id).scalar() or 0
    latest_transaction = Transaction.query.filter_by(kantor_id=user_kantor_id).order_by(Transaction.timestamp.desc()).first()
    LOW_STOCK_THRESHOLD = 50 
    low_stock_materials = Material.query.filter(Material.kantor_id == user_kantor_id, Material.jumlah < LOW_STOCK_THRESHOLD).order_by(Material.jumlah).all()
    search_query = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    query = Material.query.filter_by(kantor_id=user_kantor_id)
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(db.or_(Material.nama_material.ilike(search_term), Material.id_barang.ilike(search_term)))
    pagination = query.order_by(Material.nama_material).paginate(page=page, per_page=10, error_out=False)
    return render_template('dashboard.html', pagination=pagination, search_query=search_query, total_material_types=total_material_types, total_stock=total_stock, latest_transaction=latest_transaction, low_stock_materials=low_stock_materials)

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('Kamu berhasil logout.', 'info')
    return redirect(url_for('login'))

@app.route('/history')
@login_required
def history():
    user_kantor_id = session.get('kantor_id')
    all_transactions = (Transaction.query.options(joinedload(Transaction.material), joinedload(Transaction.user)).filter_by(kantor_id=user_kantor_id).order_by(Transaction.timestamp.desc()).all())
    return render_template('history.html', transactions=all_transactions)

@app.route('/history/clear', methods=['POST'])
@login_required
@admin_required
def clear_history():
    try:
        user_kantor_id = session.get('kantor_id')
        Transaction.query.filter_by(kantor_id=user_kantor_id).delete()
        db.session.commit()
        flash('Semua riwayat transaksi untuk kantor ini berhasil dihapus!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Terjadi error saat menghapus riwayat: {e}', 'danger')
    return redirect(url_for('history'))

@app.route('/transaction/new', methods=['GET', 'POST'])
@login_required
def new_transaction():
    user_kantor_id = session.get('kantor_id')
    if request.method == 'POST':
        try:
            tipe_transaksi = request.form.get('tipe_transaksi')
            material_ids = request.form.getlist('material_id')
            jumlahs = request.form.getlist('jumlah')
            if tipe_transaksi == 'IN':
                sumber = request.form.get('sumber_in')
                for i in range(len(material_ids)):
                    material_id = material_ids[i]
                    jumlah = int(jumlahs[i])
                    if not material_id or jumlah <= 0: continue
                    material = Material.query.filter_by(id=material_id, kantor_id=user_kantor_id).first()
                    if material:
                        material.jumlah += jumlah
                        db.session.add(Transaction(material_id=material.id, tipe_transaksi='IN', jumlah=jumlah, sumber=sumber, user_id=session['user_id'], kantor_id=user_kantor_id))
            elif tipe_transaksi == 'OUT':
                metode = request.form.get('metode_out')
                sumber_tujuan = request.form.get('online_option') or request.form.get('manual_option')
                for i in range(len(material_ids)):
                    material_id = material_ids[i]
                    jumlah_keluar = int(jumlahs[i])
                    if not material_id or jumlah_keluar <= 0: continue
                    material = Material.query.filter_by(id=material_id, kantor_id=user_kantor_id).first()
                    if material:
                        if material.jumlah < jumlah_keluar:
                            flash(f"Gagal! Stok {material.nama_material} tidak cukup.", 'danger')
                            db.session.rollback()
                            return redirect(url_for('new_transaction'))
                        material.jumlah -= jumlah_keluar
                        db.session.add(Transaction(material_id=material.id, tipe_transaksi='OUT', jumlah=jumlah_keluar, sumber=f"{metode} - {sumber_tujuan}", user_id=session['user_id'], kantor_id=user_kantor_id))
            db.session.commit()
            flash("Transaksi berhasil diproses!", "success")
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f"Terjadi error: {e}", 'danger')
            return redirect(url_for('new_transaction'))

    if session.get('role') == 'admin':
        available_materials = Material.query.filter_by(kantor_id=user_kantor_id).order_by(Material.nama_material).all()
    else:
        current_user = User.query.get(session['user_id'])
        available_materials = current_user.permitted_materials
        available_materials.sort(key=lambda x: x.nama_material)

    materials_list = [{'id': m.id, 'nama_material': m.nama_material, 'jumlah': m.jumlah} for m in available_materials]
    return render_template('form_transaksi.html', materials=materials_list)

# --- Rute Admin ---
@app.route('/admin/materials')
@login_required
@admin_required
def manage_materials():
    materials = Material.query.filter_by(kantor_id=session.get('kantor_id')).order_by(Material.nama_material).all()
    return render_template('admin_materials.html', materials=materials)

@app.route('/admin/materials/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_material():
    user_kantor_id = session.get('kantor_id')
    if request.method == 'POST':
        id_brg = request.form.get('id_barang')
        if Material.query.filter_by(id_barang=id_brg, kantor_id=user_kantor_id).first():
            flash(f'Gagal! ID Barang "{id_brg}" sudah ada di kantor ini.', 'danger')
            return redirect(url_for('add_material'))
        new_material = Material(id_barang=id_brg, nama_material=request.form.get('nama_material'), jumlah=request.form.get('jumlah'), satuan_id=request.form.get('satuan_id'), kantor_id=user_kantor_id)
        db.session.add(new_material)
        db.session.commit()
        flash('Material baru berhasil ditambahkan!', 'success')
        return redirect(url_for('manage_materials'))
    satuans = Satuan.query.all()
    return render_template('add_material.html', satuans=satuans)

@app.route('/admin/materials/edit/<int:material_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_material(material_id):
    material = Material.query.filter_by(id=material_id, kantor_id=session.get('kantor_id')).first_or_404()
    if request.method == 'POST':
        material.nama_material = request.form.get('nama_material')
        material.jumlah = request.form.get('jumlah')
        material.satuan_id = request.form.get('satuan_id')
        db.session.commit()
        flash('Data material berhasil diperbarui!', 'success')
        return redirect(url_for('manage_materials'))
    satuans = Satuan.query.all()
    return render_template('edit_material.html', material=material, satuans=satuans)

@app.route('/admin/materials/delete/<int:material_id>', methods=['POST'])
@login_required
@admin_required
def delete_material(material_id):
    material = Material.query.filter_by(id=material_id, kantor_id=session.get('kantor_id')).first_or_404()
    if material.transactions:
        flash('Material tidak bisa dihapus karena sudah memiliki riwayat transaksi.', 'danger')
        return redirect(url_for('manage_materials'))
    db.session.delete(material)
    db.session.commit()
    flash('Material berhasil dihapus.', 'success')
    return redirect(url_for('manage_materials'))

@app.route('/admin/materials/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_materials():
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash('Tidak ada file yang dipilih.', 'danger')
            return redirect(request.url)
        file = request.files['excel_file']
        if file.filename == '':
            flash('Tidak ada file yang dipilih.', 'danger')
            return redirect(request.url)
        if file and file.filename.endswith('.xlsx'):
            try:
                user_kantor_id = session.get('kantor_id')
                df = pd.read_excel(file)
                df.columns = df.columns.str.lower().str.replace(' ', '_')
                required_columns = ['id_barang', 'nama_material', 'jumlah', 'satuan']
                if not all(col in df.columns for col in required_columns):
                    flash('File Excel tidak memiliki semua kolom yang dibutuhkan (id_barang, nama_material, jumlah, satuan).', 'danger')
                    return redirect(request.url)
                for index, row in df.iterrows():
                    id_brg = str(row['id_barang'])
                    nama = str(row['nama_material'])
                    jumlah = int(row['jumlah'])
                    nama_satuan = str(row['satuan'])
                    existing = Material.query.filter_by(id_barang=id_brg, kantor_id=user_kantor_id).first()
                    if existing:
                        existing.jumlah += jumlah
                        continue
                    satuan_obj = Satuan.query.filter_by(nama=nama_satuan).first()
                    if not satuan_obj:
                        flash(f"Peringatan: Satuan '{nama_satuan}' untuk ID Barang '{id_brg}' tidak ditemukan. Baris ini dilewati.", 'warning')
                        continue
                    new_material = Material(id_barang=id_brg, nama_material=nama, jumlah=jumlah, satuan_id=satuan_obj.id, kantor_id=user_kantor_id)
                    db.session.add(new_material)
                db.session.commit()
                flash('Data dari Excel berhasil diimpor!', 'success')
                return redirect(url_for('manage_materials'))
            except Exception as e:
                db.session.rollback()
                flash(f'Terjadi error saat memproses file: {e}', 'danger')
                return redirect(request.url)
        else:
            flash('Format file harus .xlsx (Excel)', 'danger')
            return redirect(request.url)
    return render_template('import_excel.html')

@app.route('/admin/users')
@login_required
@admin_required
def manage_users():
    users = User.query.order_by(User.kantor_id, User.username).all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        kantor_id = request.form.get('kantor_id')
        if not kantor_id:
            flash('Kamu harus memilih kantor untuk user baru.', 'danger')
            return redirect(url_for('add_user'))
        if User.query.filter_by(username=username).first():
            flash(f'Username "{username}" sudah digunakan.', 'danger')
            return redirect(url_for('add_user'))
        hashed_password = generate_password_hash(request.form.get('password'), method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_password, role=request.form.get('role'), kantor_id=kantor_id)
        db.session.add(new_user)
        db.session.commit()
        flash(f'User "{username}" berhasil ditambahkan.', 'success')
        return redirect(url_for('manage_users'))
    offices = Kantor.query.order_by(Kantor.nama_kantor).all()
    return render_template('add_user.html', offices=offices)

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == session['user_id']:
        flash('Kamu tidak bisa menghapus akunmu sendiri!', 'danger')
        return redirect(url_for('manage_users'))
    user = User.query.get_or_404(user_id)
    if user.transactions:
        flash(f'User "{user.username}" tidak bisa dihapus karena memiliki riwayat transaksi.', 'danger')
        return redirect(url_for('manage_users'))
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{user.username}" telah dihapus.', 'success')
    return redirect(url_for('manage_users'))

@app.route('/admin/users/permissions/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def assign_permissions(user_id):
    user_to_edit = User.query.get_or_404(user_id)
    materials_in_office = Material.query.filter_by(kantor_id=user_to_edit.kantor_id).order_by(Material.nama_material).all()
    if request.method == 'POST':
        permitted_ids = request.form.getlist('material_ids')
        user_to_edit.permitted_materials.clear()
        for mat_id in permitted_ids:
            material = Material.query.get(mat_id)
            if material:
                user_to_edit.permitted_materials.append(material)
        db.session.commit()
        flash(f'Izin material untuk user "{user_to_edit.username}" telah diperbarui.', 'success')
        return redirect(url_for('manage_users'))
    current_permissions = [mat.id for mat in user_to_edit.permitted_materials]
    return render_template('admin_user_permissions.html', user=user_to_edit, materials=materials_in_office, current_permissions=current_permissions)

@app.route('/admin/offices')
@login_required
@admin_required
def manage_offices():
    offices = Kantor.query.order_by(Kantor.nama_kantor).all()
    return render_template('admin_offices.html', offices=offices)

@app.route('/admin/offices/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_office():
    if request.method == 'POST':
        nama = request.form.get('nama_kantor')
        kode = request.form.get('kode_kantor')
        if Kantor.query.filter_by(nama_kantor=nama).first() or Kantor.query.filter_by(kode_kantor=kode).first():
            flash('Nama atau Kode Kantor sudah ada.', 'danger')
            return redirect(url_for('add_office'))
        new_office = Kantor(nama_kantor=nama, kode_kantor=kode)
        db.session.add(new_office)
        db.session.commit()
        flash('Kantor baru berhasil ditambahkan!', 'success')
        return redirect(url_for('manage_offices'))
    return render_template('add_office.html')

@app.route('/admin/offices/edit/<int:office_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_office(office_id):
    office = Kantor.query.get_or_404(office_id)
    if request.method == 'POST':
        office.nama_kantor = request.form.get('nama_kantor')
        office.kode_kantor = request.form.get('kode_kantor')
        db.session.commit()
        flash('Data kantor berhasil diperbarui.', 'success')
        return redirect(url_for('manage_offices'))
    return render_template('edit_office.html', office=office)

@app.route('/admin/offices/delete/<int:office_id>', methods=['POST'])
@login_required
@admin_required
def delete_office(office_id):
    office = Kantor.query.get_or_404(office_id)
    if office.users or office.materials or office.transactions:
        flash(f'Gagal! Kantor "{office.nama_kantor}" tidak bisa dihapus karena masih memiliki data terkait.', 'danger')
        return redirect(url_for('manage_offices'))
    db.session.delete(office)
    db.session.commit()
    flash(f'Kantor "{office.nama_kantor}" berhasil dihapus.', 'success')
    return redirect(url_for('manage_offices'))
