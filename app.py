#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Drive Downloader Pro - Tải file Google Drive vượt mọi rào cản
# Tác giả: palofsc

import os
import re
import time
import json
import tempfile
from flask import Flask, render_template, request, send_file, after_this_request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
from drive_api import DriveAPI

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-please")
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(BASE_DIR, 'cookies.txt')
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, 'service_account.json')
TEMP_DIR = tempfile.gettempdir()

drive_api = DriveAPI(
    cookie_file=COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
    service_account_file=SERVICE_ACCOUNT_FILE if os.path.exists(SERVICE_ACCOUNT_FILE) else None
)

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

@app.route('/')
def index():
    return render_template('index.html',
                           cookie_exists=os.path.exists(COOKIE_FILE),
                           service_exists=os.path.exists(SERVICE_ACCOUNT_FILE))

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
        flash('Chỉ chấp nhận file .txt', 'error')
        return redirect(url_for('index'))
    file.save(COOKIE_FILE)
    drive_api.reload_cookie(COOKIE_FILE)
    flash('Upload cookies.txt thành công!', 'success')
    return redirect(url_for('index'))

@app.route('/upload_service_account', methods=['POST'])
def upload_service_account():
    if 'sa_file' not in request.files:
        flash('Không có file được chọn', 'error')
        return redirect(url_for('index'))
    file = request.files['sa_file']
    if not file.filename or not file.filename.lower().endswith('.json'):
        flash('Chỉ chấp nhận file .json', 'error')
        return redirect(url_for('index'))
    try:
        data = json.load(file)
        if 'client_email' not in data:
            flash('File JSON không hợp lệ (thiếu client_email)', 'error')
            return redirect(url_for('index'))
        file.seek(0)
        file.save(SERVICE_ACCOUNT_FILE)
        drive_api.reload_service_account(SERVICE_ACCOUNT_FILE)
        flash(f'Upload Service Account thành công ({data["client_email"]})', 'success')
    except Exception as e:
        flash(f'Lỗi đọc JSON: {e}', 'error')
    return redirect(url_for('index'))

@app.route('/api/info', methods=['POST'])
def api_info():
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
            except:
                pass
            return response

        return send_file(filepath, as_attachment=True, download_name=real_name)
    except Exception as e:
        return f"Lỗi hệ thống: {str(e)}", 500

@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'cookie': os.path.exists(COOKIE_FILE),
        'service_account': os.path.exists(SERVICE_ACCOUNT_FILE)
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
