# app.py
# Web tool tải file Google Drive qua link - Tích hợp cookie để vượt quota
# Tác giả: palofsc
# Yêu cầu: pip install flask gdown requests gunicorn

from flask import Flask, render_template, request, send_file, after_this_request
import gdown
import os
import tempfile
import re
import time

app = Flask(__name__)
TEMP_DIR = tempfile.gettempdir()
COOKIE_FILE = 'cookies.txt'  # File cookie lưu cùng cấp với app.py

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
    return render_template('index.html')

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
        # Sử dụng cookie để xác thực và vượt qua giới hạn quota của Google Drive
        # Nếu không có file cookies.txt, gdown sẽ chạy ở chế độ ẩn danh (dễ bị chặn)
        cookies_arg = COOKIE_FILE if os.path.exists(COOKIE_FILE) else None
        gdown.download(id=file_id, output=filepath, quiet=False, cookies=cookies_arg)
        
        if not os.path.exists(filepath):
            return "Tải file thất bại. File bị giới hạn quyền hoặc đã hết lượt tải (quota).", 500

        # Xóa file tạm sau khi gửi
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
    app.run(host='0.0.0.0', port=5000)
