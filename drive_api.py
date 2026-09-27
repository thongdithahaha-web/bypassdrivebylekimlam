#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# DriveAPI - Tải file Google Drive qua 3 phương pháp: Service Account -> Cookie -> gdown ẩn danh
# Tác giả: palofsc

import os
import re
import time
import requests
import gdown

# Thử import google api client (nếu có)
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    import io
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


class DriveAPI:
    def __init__(self, cookie_file=None, service_account_file=None):
        self.cookie_file = cookie_file
        self.service_account_file = service_account_file
        self.drive_service = None
        self.cookies = {}
        self._load_cookie()
        self._load_service_account()

    # ---------- COOKIE ----------
    def reload_cookie(self, path):
        self.cookie_file = path
        self._load_cookie()

    def _load_cookie(self):
        self.cookies = {}
        if self.cookie_file and os.path.exists(self.cookie_file):
            try:
                with open(self.cookie_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        parts = line.split('\t')
                        if len(parts) >= 7:
                            domain, _, path, secure, expires, name, value = parts[:7]
                            if 'google.com' in domain:
                                self.cookies[name] = value
            except Exception as e:
                print(f"[DriveAPI] Lỗi đọc cookie: {e}")

    # ---------- SERVICE ACCOUNT ----------
    def reload_service_account(self, path):
        self.service_account_file = path
        self._load_service_account()

    def _load_service_account(self):
        if not GOOGLE_API_AVAILABLE:
            return
        if self.service_account_file and os.path.exists(self.service_account_file):
            try:
                creds = service_account.Credentials.from_service_account_file(
                    self.service_account_file, scopes=SCOPES
                )
                self.drive_service = build('drive', 'v3', credentials=creds, cache_discovery=False)
            except Exception as e:
                print(f"[DriveAPI] Lỗi Service Account: {e}")
                self.drive_service = None

    # ---------- INFO ----------
    def get_file_info(self, file_id):
        """Lấy metadata file (name, size, mimeType)."""
        # Ưu tiên Service Account
        if self.drive_service:
            try:
                meta = self.drive_service.files().get(
                    fileId=file_id,
                    fields='id,name,size,mimeType,createdTime'
                ).execute()
                return {
                    'id': meta.get('id'),
                    'name': meta.get('name'),
                    'size': int(meta.get('size', 0)) if meta.get('size') else 0,
                    'mimeType': meta.get('mimeType'),
                    'createdTime': meta.get('createdTime'),
                    'source': 'service_account'
                }
            except Exception as e:
                print(f"[DriveAPI] SA info error: {e}")
        # Fallback: HEAD request
        try:
            r = requests.get(
                f"https://drive.google.com/uc?id={file_id}&export=download",
                cookies=self.cookies, stream=True, timeout=15, allow_redirects=True
            )
            name = None
            disp = r.headers.get('Content-Disposition', '')
            m = re.search(r'filename="([^"]+)"', disp)
            if m:
                name = m.group(1)
            size = int(r.headers.get('Content-Length', 0))
            return {
                'id': file_id,
                'name': name or f"{file_id}.bin",
                'size': size,
                'mimeType': r.headers.get('Content-Type'),
                'source': 'cookie' if self.cookies else 'anonymous'
            }
        except Exception as e:
            print(f"[DriveAPI] Fallback info error: {e}")
            return {'id': file_id, 'name': f"{file_id}.bin", 'size': 0, 'source': 'unknown'}

    # ---------- DOWNLOAD ----------
    def download(self, file_id, output_path):
        """Thử 3 phương pháp theo thứ tự ưu tiên."""
        # 1. Service Account (nhanh, ổn định nhất, không quota)
        if self.drive_service:
            ok, msg = self._download_via_api(file_id, output_path)
            if ok:
                return True, "service_account"

        # 2. Cookie (vượt quota nếu có tài khoản)
        if self.cookies:
            ok, msg = self._download_via_cookie(file_id, output_path)
            if ok:
                return True, "cookie"

        # 3. gdown ẩn danh (fallback cuối)
        ok, msg = self._download_via_gdown(file_id, output_path)
        if ok:
            return True, "gdown"
        return False, msg

    def _download_via_api(self, file_id, output_path):
        try:
            request = self.drive_service.files().get_media(fileId=file_id)
            with io.FileIO(output_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request, chunksize=10 * 1024 * 1024)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            return True, "OK"
        except Exception as e:
            return False, f"API error: {e}"

    def _download_via_cookie(self, file_id, output_path):
        try:
            session = requests.Session()
            session.cookies.update(self.cookies)
            url = f"https://drive.google.com/uc?id={file_id}&export=download"
            r = session.get(url, stream=True, timeout=30)
            # Xử lý trang xác nhận virus cho file lớn
            if 'confirm' in r.text[:1000] or 'Xác nhận' in r.text[:2000]:
                # Trích token
                m = re.search(r'confirm=([a-zA-Z0-9_-]+)', r.text)
                if m:
                    url = f"{url}&confirm={m.group(1)}"
                    r = session.get(url, stream=True, timeout=30)
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
            return True, "OK"
        except Exception as e:
            return False, f"Cookie error: {e}"

    def _download_via_gdown(self, file_id, output_path):
        try:
            cookies_arg = self.cookie_file if self.cookie_file and os.path.exists(self.cookie_file) else None
            gdown.download(id=file_id, output=output_path, quiet=True, cookies=cookies_arg)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True, "OK"
            return False, "File rỗng hoặc không tải được"
        except Exception as e:
            return False, f"gdown error: {e}"
