# Drive Downloader Pro

Tool tải file Google Drive vượt mọi rào cản với 3 lớp xác thực:
1. **Service Account** (khuyến nghị – không bị quota)
2. **Cookies.txt** (cho file riêng tư)
3. **Ẩn danh** (cho file công khai)

## Deploy lên Render (miễn phí)
1. Push code lên GitHub.
2. Vào render.com → New Web Service → kết nối repo.
3. Cấu hình:
   - Environment: Python 3
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app --timeout 600 --workers 2 --threads 4`
4. Env: `SECRET_KEY` = chuỗi ngẫu nhiên 32 ký tự.
5. Deploy → truy cập domain.

## Lấy Service Account (khuyến nghị)
1. Vào console.cloud.google.com → tạo Project → bật Drive API.
2. IAM & Admin → Service Accounts → Create.
3. Tạo key JSON → tải về.
4. Share file/folder Drive cho email `xxx@xxx.iam.gserviceaccount.com` (quyền Viewer).
5. Upload file JSON lên tool.

## Lấy cookies.txt
1. Cài extension "Get cookies.txt LOCALLY" trên Chrome.
2. Đăng nhập drive.google.com.
3. Export cookies cho domain google.com → upload lên tool.

## Tính năng
- Tải file/folder (folder tự nén zip)
- Lấy metadata (name, size, mimeType)
- Fallback 3 lớp: SA → Cookie → Ẩn danh
- Hỗ trợ Google Docs/Sheets/Slides (tự export)
- Endpoint /health để kiểm tra trạng thái
