#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# DriveAPI - Tầng xử lý tải file Google Drive
# Hỗ trợ: Cookie (gdown) + Service Account (Google Drive API v3)
# Tác giả: palofsc

import os
import io
import re
import time
import json
import logging
import requests
import gdown

# Google API client
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
log = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


class DriveAPI:
    """Tầng API tải file Google Drive với nhiều cơ chế fallback."""

    def __init__(self, cookie_file=None, service_account_file=None):
        self.cookie_file = cookie_file
        self.service_account_file = service_account_file
        self.service = None
        self._init_service()

    # ---------- KHỞI TẠO ----------
    def _init_service(self):
        """Khởi tạo Google Drive API service từ service account."""
        if not GOOGLE_API_AVAILABLE:
            log.warning("google-api-python-client chưa cài. Chỉ dùng cookie.")
            self.service = None
            return

        if self.service_account_file and os.path.exists(self.service_account_file):
            try:
                creds = service_account.Credentials.from_service_account_file(
                    self.service_account_file, scopes=SCOPES
                )
                self.service = build('drive', 'v3', credentials=creds, cache_discovery=False)
                log.info("Đã khởi tạo Drive API service bằng Service Account.")
            except Exception as e:
                log.error(f"Lỗi khởi tạo service account: {e}")
                self.service = None
        else:
            self.service = None

    def reload_cookie(self, cookie_file):
        """Cập nhật lại đường dẫn cookie (sau khi upload mới)."""
        self.cookie_file = cookie_file if os.path.exists(cookie_file) else None
        log.info(f"Đã reload cookie: {self.cookie_file}")

    def reload_service_account(self, sa_file):
        """Cập nhật lại service account (sau khi upload mới)."""
        self.service_account_file = sa_file if os.path.exists(sa_file) else None
        self._init_service()
        log.info(f"Đã reload service account: {self.service_account_file}")

    # ---------- LẤY THÔNG TIN FILE ----------
    def get_file_info(self, file_id):
        """
        Lấy thông tin file: name, size, mimeType.
        Ưu tiên service account (nếu có), fallback sang cookie.
        """
        # Cách 1: Service Account
        if self.service:
            try:
                meta = self.service.files().get(
                    fileId=file_id,
                    fields='id, name, size, mimeType, md5Checksum'
                ).execute()
                return {
                    'id': meta.get('id'),
                    'name': meta.get('name', f'{file_id}.bin'),
                    'size': int(meta.get('size', 0)) if meta.get('size') else None,
                    'mimeType': meta.get('mimeType'),
                    'source': 'service_account'
                }
            except Exception as e:
                log.warning(f"Service Account không lấy được info: {e}")

        # Cách 2: Cookie + gdown
        if self.cookie_file:
            try:
                url = f"https://drive.google.com/uc?id={file_id}&export=download"
                # Dùng gdown để lấy metadata qua filename
                tmp = gdown.download(id=file_id, output=None, quiet=True,
                                     cookies=self.cookie_file)
                # gdown không trả metadata trực tiếp; fallback name mặc định
                return {
                    'id': file_id,
                    'name': f'{file_id}.bin',
                    'size': None,
                    'mimeType': None,
                    'source': 'cookie'
                }
            except Exception as e:
                log.warning(f"Cookie không lấy được info: {e}")

        # Cách 3: Không có gì
        return {
            'id': file_id,
            'name': f'{file_id}.bin',
            'size': None,
            'mimeType': None,
            'source': 'none'
        }

    # ---------- TẢI FILE ----------
    def download(self, file_id, output_path):
        """
        Tải file từ Google Drive.
        Trả về (True/False, thông báo).
        Thứ tự: Service Account → Cookie → Không xác thực.
        """
        # 1. Thử Service Account
        if self.service:
            ok, msg = self._download_via_api(file_id, output_path)
            if ok:
                return True, 'Tải thành công bằng Service Account'
            log.warning(f"Service Account thất bại: {msg}")

        # 2. Thử Cookie
        if self.cookie_file:
            ok, msg = self._download_via_gdown(file_id, output_path, self.cookie_file)
            if ok:
                return True, f'Tải thành công bằng Cookie ({self.cookie_file})'
            log.warning(f"Cookie thất bại: {msg}")

        # 3. Thử ẩn danh
        ok, msg = self._download_via_gdown(file_id, output_path, None)
        if ok:
            return True, 'Tải thành công ẩn danh'

        return False, msg

    def _download_via_api(self, file_id, output_path):
        """Tải file qua Google Drive API v3 (Service Account)."""
        try:
            # Kiểm tra file có phải Google Docs (cần export)
            meta = self.service.files().get(
                fileId=file_id,
                fields='id, name, mimeType, size'
            ).execute()

            mime = meta.get('mimeType', '')
            export_map = {
                'application/vnd.google-apps.document':
                    ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx'),
                'application/vnd.google-apps.spreadsheet':
                    ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx'),
                'application/vnd.google-apps.presentation':
                    ('application/vnd.openxmlformats-officedocument.presentationml.presentation', '.pptx'),
                'application/vnd.google-apps.drawing':
                    ('application/pdf', '.pdf'),
            }

            if mime in export_map:
                export_mime, ext = export_map[mime]
                request = self.service.files().export_media(fileId=file_id, mimeType=export_mime)
                # Đổi đường dẫn output thành file có đuôi phù hợp
                output_path = output_path + ext
            else:
                request = self.service.files().get_media(fileId=file_id)

            fh = io.FileIO(output_path, 'wb')
            downloader = MediaIoBaseDownload(fh, request, chunksize=50 * 1024 * 1024)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    log.info(f"Tiến độ tải: {int(status.progress() * 100)}%")
            fh.close()
            return True, output_path
        except Exception as e:
            return False, str(e)

    def _download_via_gdown(self, file_id, output_path, cookie_file):
        """Tải file qua gdown với cookie tùy chọn."""
        try:
            # Tạo thư mục chứa output nếu chưa có
            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

            kwargs = dict(id=file_id, output=output_path, quiet=False, fuzzy=True)
            if cookie_file:
                kwargs['cookies'] = cookie_file

            result = gdown.download(**kwargs)
            if result and os.path.exists(result):
                return True, result
            return False, "gdown không trả về file"
        except Exception as e:
            return False, str(e)

    # ---------- LIỆT KÊ FOLDER ----------
    def list_folder(self, folder_id, max_items=1000):
        """Liệt kê file trong folder Google Drive (cần Service Account)."""
        if not self.service:
            return None
        try:
            items = []
            page_token = None
            while len(items) < max_items:
                resp = self.service.files().list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    fields='nextPageToken, files(id, name, size, mimeType)',
                    pageSize=min(1000, max_items - len(items)),
                    pageToken=page_token
                ).execute()
                items.extend(resp.get('files', []))
                page_token = resp.get('nextPageToken')
                if not page_token:
                    break
            return items
        except Exception as e:
            log.error(f"Lỗi list_folder: {e}")
            return None
