#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# DriveAPI - Tầng xử lý tải file Google Drive
# Hỗ trợ: Cookie (gdown) + Service Account (Google Drive API v3)
# Tác giả: palofsc

import os
import io
import json
import logging
import traceback
import gdown

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

log = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


class DriveAPI:
    """Tầng API tải file Google Drive với nhiều cơ chế fallback."""

    def __init__(self, cookie_file=None, service_account_file=None):
        self.cookie_file = cookie_file if cookie_file and os.path.exists(cookie_file) else None
        self.service_account_file = service_account_file if service_account_file and os.path.exists(service_account_file) else None
        self.service = None
        self._init_service()

    def _init_service(self):
        if not GOOGLE_API_AVAILABLE:
            log.warning("google-api-python-client chưa cài. Chỉ dùng cookie.")
            self.service = None
            return

        if not self.service_account_file or not os.path.exists(self.service_account_file):
            self.service = None
            return

        try:
            # Đọc file JSON và log client_email để debug
            with open(self.service_account_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            log.info(f"Service account email: {data.get('client_email')}")

            creds = service_account.Credentials.from_service_account_file(
                self.service_account_file, scopes=SCOPES
            )
            self.service = build('drive', 'v3', credentials=creds, cache_discovery=False)
            log.info("✅ Khởi tạo Drive API service thành công")
        except Exception as e:
            log.error(f"❌ Lỗi khởi tạo service account: {e}")
            log.error(traceback.format_exc())
            self.service = None

    def reload_cookie(self, cookie_file):
        """Cập nhật lại đường dẫn cookie."""
        self.cookie_file = cookie_file if cookie_file and os.path.exists(cookie_file) else None
        log.info(f"Đã reload cookie: {self.cookie_file}")

    def reload_service_account(self, sa_file):
        """Cập nhật lại service account."""
        self.service_account_file = sa_file if sa_file and os.path.exists(sa_file) else None
        self._init_service()
        log.info(f"Đã reload service account: {self.service_account_file}")

    def get_file_info(self, file_id):
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

        if self.cookie_file:
            try:
                return {
                    'id': file_id,
                    'name': f'{file_id}.bin',
                    'size': None,
                    'mimeType': None,
                    'source': 'cookie'
                }
            except Exception as e:
                log.warning(f"Cookie không lấy được info: {e}")

        return {
            'id': file_id,
            'name': f'{file_id}.bin',
            'size': None,
            'mimeType': None,
            'source': 'none'
        }

    def download(self, file_id, output_path):
        if self.service:
            ok, msg = self._download_via_api(file_id, output_path)
            if ok:
                return True, 'Tải thành công bằng Service Account'
            log.warning(f"Service Account thất bại: {msg}")

        if self.cookie_file:
            ok, msg = self._download_via_gdown(file_id, output_path, self.cookie_file)
            if ok:
                return True, 'Tải thành công bằng Cookie'
            log.warning(f"Cookie thất bại: {msg}")

        ok, msg = self._download_via_gdown(file_id, output_path, None)
        if ok:
            return True, 'Tải thành công ẩn danh'
        return False, msg

    def _download_via_api(self, file_id, output_path):
        try:
            meta = self.service.files().get(
                fileId=file_id, fields='id, name, mimeType, size'
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
                output_path = output_path + ext
            else:
                request = self.service.files().get_media(fileId=file_id)

            fh = io.FileIO(output_path, 'wb')
            downloader = MediaIoBaseDownload(fh, request, chunksize=50 * 1024 * 1024)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    log.info(f"Tiến độ: {int(status.progress() * 100)}%")
            fh.close()
            return True, output_path
        except Exception as e:
            log.error(traceback.format_exc())
            return False, str(e)

    def _download_via_gdown(self, file_id, output_path, cookie_file):
        try:
            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
            kwargs = dict(id=file_id, output=output_path, quiet=False, fuzzy=True)
            if cookie_file:
                kwargs['cookies'] = cookie_file
            result = gdown.download(**kwargs)
            if result and os.path.exists(result):
                return True, result
            return False, "gdown không trả về file"
        except Exception as e:
            log.error(traceback.format_exc())
            return False, str(e)

    def list_folder(self, folder_id, max_items=1000):
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
