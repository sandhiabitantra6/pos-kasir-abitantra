from datetime import datetime
import hashlib
import json
import os
import pandas as pd
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

# --- KONFIGURASI HALAMAN STREAMLIT ---
st.set_page_config(
    page_title="POS Kasir Abitantra",
    page_icon="🛒",
    layout="wide"
)

# --- INISIALISASI FIREBASE ---
db = None
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    pass

NAMA_TOKO = "TOKO PALING DASAR PEMROGRAMAN"
ALAMAT_TOKO1 = "Institut Media Digital Emtek"

# --- HELPER: PASSWORD HASHING ---
def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# --- LOCAL BACKUP HELPER ---
def save_local_backup(product_db):
    try:
        backup_data = {code: {"name": p['name'], "price": p['price'], "stock": p['stock']} for code, p in product_db.items()}
        with open("local_products_backup.json", "w") as f:
            json.dump(backup_data, f)
    except:
        pass

def load_product_database():
    product_db = {}
    try:
        if db is not None:
            docs = db.collection("products").stream()
            for doc in docs:
                data = doc.to_dict()
                product_db[doc.id] = data
            save_local_backup(product_db)
            return product_db
    except:
        pass
    
    # Fallback lokal
    try:
        if os.path.exists("local_products_backup.json"):
            with open("local_products_backup.json", "r") as f:
                product_db = json.load(f)
    except:
        pass
    return product_db

def load_cashier_accounts():
    accounts = {"kasir1": hash_password("1234")}
    try:
        if db is not None:
            doc = db.collection("settings").document("cashiers").get()
            if doc.exists:
                accounts = doc.to_dict().get("accounts", accounts)
    except:
        pass
    return accounts

# --- STATE MANAGEMENT (SESSION STATE) ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.session_state.cart = {}

# --- HALAMAN LOGIN ---
if not st.session_state.logged_in:
    st.title("🔐 Login - POS Kasir Abitantra")
    
    with st.form("login_form"):
        username_input = st.text_input("Username")
        password_input = st.text_input("Password", type="password")
        submit_login = st.form_submit_button("Masuk Aplikasi")
        
        if submit_login:
            cashier_accounts = load_cashier_accounts()
            hashed_pwd = hash_password(password_input)
            
            if username_input == "Abitantra" and password_input == "SuperAdmin":
                st.session_state.logged_in = True
                st.session_state.username = username_input
                st.session_state.role = "admin"
                st.rerun()
            elif username_input in cashier_accounts and cashier_accounts[username_input] == hashed_pwd:
                st.session_state.logged_in = True
                st.session_state.username = username_input
                st.session_state.role = "kasir"
                st.rerun()
            else:
                st.error("Username atau Password salah!")

else:
    # --- HALAMAN UTAMA SETELAH LOGIN ---
    st.sidebar.title(f"Halo, {st.session_state.username}!")
    st.sidebar.info("Role: `{st.session_state.role.upper()}`")
    
    menu = st.sidebar.radio("Navigasi Menu", ["Belanja & Transaksi", "Daftar Produk & Stok", "Kelola Produk (Admin)", "Kelola Kasir (Admin)", "Rekap Sales Excel"])
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = ""
        st.session_state.cart = {}
        st.rerun()

    product_db = load_product_database()

    # 1. MENU BELANJA & TRANSAKSI
    if menu == "Belanja & Transaksi":
        st.header(f"🛒 {NAMA_TOKO} - Kasir")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("Pilih Produk")
            if not product_db:
                st.warning("Belum ada produk di database.")
            else:
                for code, prod in product_db.items():
                    with st.container():
                        c1, c2, c3 = st.columns([3, 2, 1])
                        c1.write(f"**{prod['name']}** ([{code}])")
                        c2.write(f"Rp{prod['price']:,.0f} | Stok: {prod['stock']}")
                        qty = c3.number_input("Qty", min_value=1, max_value=max(1, prod['stock']), value=1, key=f"qty_{code}")
                        if c3.button("Tambah", key=f"add_{code}"):
                            if code in st.session_state.cart:
                                st.session_state.cart[code] += qty
                            else:
                                st.session_state.cart[code] = qty
                            st.success(f"Berhasil ditambahkan!")

        with col2:
            st.subheader("Keranjang Belanja")
            if not st.session_state.cart:
                st.info("Keranjang masih kosong.")
            else:
                subtotal = 0
                for code, qty in list(st.session_state.cart.items()):
                    if code in product_db:
                        p = product_db[code]
                        item_total = p['price'] * qty
                        subtotal += item_total
                        st.write(f"- {p['name']} ({qty}x) : Rp{item_total:,.0f}")
                        if st.button("Hapus", key=f"del_{code}"):
                            del st.session_state.cart[code]
                            st.rerun()
                
                st.markdown("---")
                st.write(f"### Total: Rp{subtotal:,.0f}")
                
                if st.button("Bayar & Selesaikan Transaksi", type="primary"):
                    # Kurangi stok dan simpan transaksi
                    for code, qty in st.session_state.cart.items():
                        product_db[code]['stock'] -= qty
                        if db is not None:
                            db.collection("products").document(code).set(product_db[code])
                    save_local_backup(product_db)
                    
                    tx_data = {
                        "invoice": f"INV/{datetime.now().strftime('%Y%m%d/%H%M%S')}",
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "cashier": st.session_state.username,
                        "method": "TUNAI",
                        "items": st.session_state.cart,
                        "total": subtotal
                    }
                    if db is not None:
                        db.collection("transactions").add(tx_data)
                    else:
                        # Simpan lokal
                        tx_backup = []
                        if os.path.exists("local_transactions_backup.json"):
                            with open("local_transactions_backup.json", "r") as fb:
                                tx_backup = json.load(fb)
                        tx_backup.append(tx_data)
                        with open("local_transactions_backup.json", "w") as fb:
                            json.dump(tx_backup, fb)

                    st.success("Transaksi Berhasil!")
                    st.session_state.cart = {}
                    st.rerun()

    # 2. MENU LIHAT PRODUK
    elif menu == "Daftar Produk & Stok":
        st.header("📦 Daftar Produk & Sisa Stok")
        if product_db:
            df_prod = pd.DataFrame([
                {"Kode": k, "Nama Produk": v['name'], "Harga (Rp)": v['price'], "Stok": v['stock']} 
                for k, v in product_db.items()
            ])
            st.dataframe(df_prod, use_container_width=True)
        else:
            st.info("Belum ada produk.")

    # 3. KELOLA PRODUK (ADMIN)
    elif menu == "Kelola Produk (Admin)":
        if st.session_state.role != 'admin':
            st.error("Akses khusus Admin!")
        else:
            st.header("🛠️ Kelola Produk & Stok")
            with st.form("add_prod"):
                p_name = st.text_input("Nama Produk Baru")
                p_price = st.number_input("Harga Satuan (Rp)", min_value=0, value=1000)
                p_stock = st.number_input("Stok Awal", min_value=0, value=10)
                submitted = st.form_submit_button("Simpan Produk Baru")
                
                if submitted and p_name:
                    code = p_name[:4].upper()
                    product_db[code] = {"name": p_name, "price": p_price, "stock": p_stock}
                    if db is not None:
                        db.collection("products").document(code).set(product_db[code])
                    save_local_backup(product_db)
                    st.success(f"Produk {p_name} berhasil ditambahkan!")

    # 4. KELOLA KASIR (ADMIN)
    elif menu == "Kelola Kasir (Admin)":
        if st.session_state.role != 'admin':
            st.error("Akses khusus Admin!")
        else:
            st.header("👥 Kelola Akun Kasir")
            accounts = load_cashier_accounts()
            st.write("Akun Kasir Saat Ini:", list(accounts.keys()))
            
            new_c_user = st.text_input("Username Kasir Baru")
            new_c_pwd = st.text_input("Password Kasir Baru", type="password")
            if st.button("Tambah Akun Kasir"):
                if new_c_user:
                    accounts[new_c_user] = hash_password(new_c_pwd)
                    if db is not None:
                        db.collection("settings").document("cashiers").set({"accounts": accounts})
                    st.success(f"Kasir {new_c_user} berhasil ditambahkan!")

    # 5. REKAP EXCEL
    elif menu == "Rekap Sales Excel":
        st.header("📊 Rekap Sales & Export Excel")
        st.info("Fitur rekap penjualan otomatis tersedia lewat sistem backend Python sebelumnya.")