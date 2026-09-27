# app.py
# Web tool tải file Google Drive qua link - Hỗ trợ upload cookies.txt
# Tác giả: palofsc
# Yêu cầu: pip install flask gdown requests gunicorn werkzeug

from flask import Flask, render_template, request, send_file, after_this_request, redirect, url_for, flash
import gdown
import os
import tempfile
import re
import time
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'  # Thay bằng chuỗi ngẫu nhiên
TEMP_DIR = tempfile.gettempdir()
COOKIE_FILE = os.path.join(os.path.dirname(__file__), 'cookies.txt')
ALLOWED_EXTENSIONS = {'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_file_id(url):
    """Trích xuất file ID từ link Google Drive."""
    patterns = [
        r'/file/d/([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)',
        r'/open\?id=([a-zA-Z0-9_-]+)'
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

@app.route('/')
def index():
    cookie_exists = os.path.exists(COOKIE_FILE)
    return render_template('index.html', cookie_exists=cookie_exists)

@app.route('/upload_cookie', methods=['POST'])
def upload_cookie():
    if 'cookie_file' not in request.files:
        flash('Không có file được chọn')
        return redirect(url_for('index'))
    file = request.files['cookie_file']
    if file.filename == '':
        flash('Chưa chọn file')
        return redirect(url_for('index'))
    if file and allowed_file(file.filename):
        # Lưu file cookies.txt vào thư mục gốc
        file.save(COOKIE_FILE)
        flash('Upload cookies thành công!')
    else:
        flash('Chỉ chấp nhận file .txt')
    return redirect(url_for('index'))

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url', '').strip()
    if not url:
        return "Thiếu URL", 400
    file_id = extract_file_id(url)
    if not file_id:
        return "Link Google Drive không hợp lệ", 400

    filename = f"drive_{file_id}_{int(time.time())}.bin"
    filepath = os.path.join(TEMP_DIR, filename)

    try:
        # Sử dụng cookie nếu có
        cookies_arg = COOKIE_FILE if os.path.exists(COOKIE_FILE) else None
        gdown.download(id=file_id, output=filepath, quiet=False, cookies=cookies_arg)
        
        if not os.path.exists(filepath):
            return "Tải file thất bại. File bị giới hạn quyền hoặc đã hết lượt tải (quota).", 500

        @after_this_request
        def remove_file(response):
            try:
                os.remove(filepath)
            except:
                pass
            return response

        return send_file(filepath, as_attachment=True, download_name=f"{file_id}.bin")
    except Exception as e:
        return f"Lỗi hệ thống: {str(e)}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
