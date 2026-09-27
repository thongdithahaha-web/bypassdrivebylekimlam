#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Drive Downloader Pro - Tải file Google Drive vượt mọi rào cản
# FIX: Upload JSON service account, xử lý lỗi rõ ràng, hỗ trợ env base64
# Tác giả: palofsc

import os
import re
import io
import time
import json
import base64
import tempfile
import logging
import traceback
from flask import (Flask, render_template, request, send_file,
                   after_this_request, redirect, url_for, flash, jsonify)
from werkzeug.utils import secure_filename

try:
    from drive_api import DriveAPI
except ImportError:
    DriveAPI = None

# ---------- LOGGING ----------
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
log = logging.getLogger(__name__)

# ---------- APP ----------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-please-please-please")
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, 'cookies.txt')
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, 'service_account.json')
TEMP_DIR = tempfile.gettempdir()

# ---------- NẠP SERVICE ACCOUNT TỪ ENV (base64) ----------
def load_sa_from_env():
    """Nếu có biến SA_B64 thì giải mã và ghi ra file."""
    sa_b64 = os.getenv("SA_B64", "").strip()
    if sa_b64 and not os.path.exists(SERVICE_ACCOUNT_FILE):
        try:
            decoded = base64.b64decode(sa_b64)
            with open(SERVICE_ACCOUNT_FILE, 'wb') as f:
                f.write(decoded)
            log.info("Đã nạp service_account.json từ biến môi trường SA_B64")
        except Exception as e:
            log.error(f"Lỗi giải mã SA_B64: {e}")

load_sa_from_env()

# ---------- KHỞI TẠO DRIVE API ----------
if DriveAPI:
    drive_api = DriveAPI(
        cookie_file=COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
        service_account_file=SERVICE_ACCOUNT_FILE if os.path.exists(SERVICE_ACCOUNT_FILE) else None
    )
else:
    drive_api = None
    log.error("Không import được drive_api.py – kiểm tra file tồn tại")


# ---------- UTILS ----------
def extract_file_id(url):
    if not url:
        return None
    patterns = [
        r'/file/d/([a-zA-Z0-9_-]{10,})',
        r'[?&]id=([a-zA-Z0-9_-]{10,})',
        r'/open\?id=([a-zA-Z0-9_-]{10,})',
        r'/uc\?id=([a-zA-Z0-9_-]{10,})',
        r'/folders/([a-zA-Z0-9_-]{10,})',
        r'/document/d/([a-zA-Z0-9_-]{10,})',
        r'/spreadsheets/d/([a-zA-Z0-9_-]{10,})',
        r'/presentation/d/([a-zA-Z0-9_-]{10,})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def human_size(num_bytes):
    if not num_bytes:
        return "?"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


def validate_service_account_json(raw_bytes):
    """
    Kiểm tra nội dung file JSON có phải service account hợp lệ không.
    Trả về (ok, data hoặc thông báo lỗi).
    """
    try:
        text = raw_bytes.decode('utf-8', errors='strict')
    except UnicodeDecodeError as e:
        return False, f"File không phải UTF-8 ({e})"

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return False, f"File không phải JSON hợp lệ ({e})"

    if not isinstance(data, dict):
        return False, "JSON không phải object"

    if data.get('type') != 'service_account':
        return False, f"Trường 'type' phải là 'service_account' (hiện tại: {data.get('type')})"

    required = ['client_email', 'private_key', 'token_uri']
    missing = [k for k in required if k not in data]
    if missing:
        return False, f"Thiếu trường: {', '.join(missing)}"

    if 'iam.gserviceaccount.com' not in data['client_email']:
        return False, f"client_email không phải service account ({data['client_email']})"

    return True, data


# ---------- ROUTES ----------
@app.route('/')
def index():
    cookie_exists = os.path.exists(COOKIE_FILE)
    service_exists = os.path.exists(SERVICE_ACCOUNT_FILE)
    sa_email = None
    if service_exists:
        try:
            with open(SERVICE_ACCOUNT_FILE, 'r', encoding='utf-8') as f:
                sa_email = json.load(f).get('client_email')
        except Exception:
            pass
    return render_template('index.html',
                           cookie_exists=cookie_exists,
                           service_exists=service_exists,
                           sa_email=sa_email)


@app.route('/upload_cookie', methods=['POST'])
def upload_cookie():
    if 'cookie_file' not in request.files:
        flash('Không có file được chọn', 'error')
        return redirect(url_for('index'))
    file = request.files['cookie_file']
    if not file.filename:
        flash('Chưa chọn file', 'error')
        return redirect(url_for('index'))
    if not file.filename.lower().endswith('.txt'):
        flash(f'Chỉ chấp nhận file .txt (nhận: {file.filename})', 'error')
        return redirect(url_for('index'))

    try:
        raw = file.read()
        if not raw or len(raw) < 10:
            flash('File cookies.txt rỗng hoặc quá nhỏ', 'error')
            return redirect(url_for('index'))
        with open(COOKIE_FILE, 'wb') as f:
            f.write(raw)
        if drive_api:
            drive_api.reload_cookie(COOKIE_FILE)
        log.info(f"Đã upload cookies.txt ({len(raw)} bytes)")
        flash('Upload cookies.txt thành công!', 'success')
    except Exception as e:
        log.error(traceback.format_exc())
        flash(f'Lỗi ghi file: {e}', 'error')
    return redirect(url_for('index'))


@app.route('/upload_service_account', methods=['POST'])
def upload_service_account():
    """Upload file JSON – có validate chặt chẽ và log chi tiết."""
    log.info("=== BẮT ĐẦU UPLOAD SERVICE ACCOUNT ===")

    # 1. Kiểm tra form
    if 'sa_file' not in request.files:
        log.warning("Không có file trong request.files")
        flash('Không có file được chọn', 'error')
        return redirect(url_for('index'))

    file = request.files['sa_file']
    log.info(f"Filename: {file.filename!r}")

    # 2. Kiểm tra tên file
    if not file.filename:
        flash('Chưa chọn file', 'error')
        return redirect(url_for('index'))

    if not file.filename.lower().endswith('.json'):
        flash(f'Chỉ chấp nhận file .json (nhận: {file.filename})', 'error')
        return redirect(url_for('index'))

    # 3. Đọc nội dung
    try:
        raw = file.read()
        log.info(f"Đã đọc {len(raw)} bytes")
    except Exception as e:
        flash(f'Không đọc được file: {e}', 'error')
        return redirect(url_for('index'))

    if not raw or len(raw) < 50:
        flash('File JSON rỗng hoặc quá nhỏ (phải > 50 bytes)', 'error')
        return redirect(url_for('index'))

    if len(raw) > 1 * 1024 * 1024:
        flash('File JSON quá lớn (> 1 MB). Có thể nhầm file?', 'error')
        return redirect(url_for('index'))

    # 4. Validate nội dung
    ok, result = validate_service_account_json(raw)
    if not ok:
        log.error(f"Validate thất bại: {result}")
        flash(f'File JSON không hợp lệ: {result}', 'error')
        return redirect(url_for('index'))

    data = result
    log.info(f"Validate thành công: {data.get('client_email')}")

    # 5. Ghi file
    try:
        with open(SERVICE_ACCOUNT_FILE, 'wb') as f:
            f.write(raw)
        log.info(f"Đã ghi {SERVICE_ACCOUNT_FILE}")
    except Exception as e:
        log.error(traceback.format_exc())
        flash(f'Lỗi ghi file: {e}', 'error')
        return redirect(url_for('index'))

    # 6. Reload Drive API
    if drive_api:
        try:
            drive_api.reload_service_account(SERVICE_ACCOUNT_FILE)
            log.info("Reload drive_api thành công")
        except Exception as e:
            log.error(f"Reload drive_api lỗi: {e}")
            flash(f'Upload thành công nhưng reload API lỗi: {e}', 'error')
            return redirect(url_for('index'))

    flash(f'✅ Upload thành công! Email: {data["client_email"]}', 'success')
    log.info("=== UPLOAD SERVICE ACCOUNT THÀNH CÔNG ===")
    return redirect(url_for('index'))


@app.route('/delete_cookie', methods=['POST'])
def delete_cookie():
    try:
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
            if drive_api:
                drive_api.reload_cookie(None)
            flash('Đã xóa cookies.txt', 'success')
        else:
            flash('Không có cookies.txt để xóa', 'error')
    except Exception as e:
        flash(f'Lỗi: {e}', 'error')
    return redirect(url_for('index'))


@app.route('/delete_service_account', methods=['POST'])
def delete_service_account():
    try:
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            os.remove(SERVICE_ACCOUNT_FILE)
            if drive_api:
                drive_api.reload_service_account(None)
            flash('Đã xóa service_account.json', 'success')
        else:
            flash('Không có service_account.json để xóa', 'error')
    except Exception as e:
        flash(f'Lỗi: {e}', 'error')
    return redirect(url_for('index'))


@app.route('/api/info', methods=['POST'])
def api_info():
    if not drive_api:
        return jsonify({'error': 'Drive API chưa khởi tạo'}), 500
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'Thiếu URL'}), 400
    file_id = extract_file_id(url)
    if not file_id:
        return jsonify({'error': 'Link không hợp lệ'}), 400
    info = drive_api.get_file_info(file_id)
    if not info:
        return jsonify({'error': 'Không lấy được thông tin file'}), 500
    info['size_human'] = human_size(info.get('size'))
    return jsonify(info)


@app.route('/download', methods=['POST'])
def download():
    if not drive_api:
        return "Drive API chưa khởi tạo. Kiểm tra log server.", 500

    url = request.form.get('url', '').strip()
    if not url:
        return "Thiếu URL", 400
    file_id = extract_file_id(url)
    if not file_id:
        return "Link Google Drive không hợp lệ", 400

    filename = f"drive_{file_id}_{int(time.time())}"
    filepath = os.path.join(TEMP_DIR, filename)

    info = drive_api.get_file_info(file_id)
    real_name = info.get('name') if info else f"{file_id}.bin"

    try:
        ok, msg = drive_api.download(file_id, filepath)
        if not ok or not os.path.exists(filepath):
            return f"Tải thất bại: {msg}", 500

        @after_this_request
        def remove_file(response):
            try:
                os.remove(filepath)
            except Exception:
                pass
            return response

        return send_file(filepath, as_attachment=True, download_name=real_name)
    except Exception as e:
        log.error(traceback.format_exc())
        return f"Lỗi hệ thống: {str(e)}", 500


@app.route('/health')
def health():
    """Endpoint kiểm tra trạng thái."""
    sa_email = None
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        try:
            with open(SERVICE_ACCOUNT_FILE, 'r', encoding='utf-8') as f:
                sa_email = json.load(f).get('client_email')
        except Exception:
            pass
    return jsonify({
        'status': 'ok',
        'cookie_exists': os.path.exists(COOKIE_FILE),
        'service_account_exists': os.path.exists(SERVICE_ACCOUNT_FILE),
        'service_account_email': sa_email,
        'drive_api_ready': drive_api is not None,
        'drive_api_service': bool(drive_api.service) if drive_api else False,
    })


# ---------- ERROR HANDLERS ----------
@app.errorhandler(413)
def too_large(e):
    flash('File upload quá lớn (> 10 MB)', 'error')
    return redirect(url_for('index'))


@app.errorhandler(500)
def server_error(e):
    log.error(f"Server error: {e}")
    return f"Lỗi server: {e}", 500


# ---------- MAIN ----------
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    log.info(f"Khởi động server trên cổng {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
