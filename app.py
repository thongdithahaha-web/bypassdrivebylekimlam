from flask import Flask, render_template, request, send_file, after_this_request
import gdown, os, tempfile, re, time

app = Flask(__name__)
TEMP_DIR = tempfile.gettempdir()

def extract_file_id(url):
    patterns = [r'/file/d/([a-zA-Z0-9_-]+)', r'id=([a-zA-Z0-9_-]+)', r'/open\?id=([a-zA-Z0-9_-]+)']
    for p in patterns:
        m = re.search(p, url)
        if m: return m.group(1)
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url', '').strip()
    if not url: return "Thiếu URL", 400
    file_id = extract_file_id(url)
    if not file_id: return "Link không hợp lệ", 400
    filename = f"drive_{file_id}_{int(time.time())}.bin"
    filepath = os.path.join(TEMP_DIR, filename)
    try:
        gdown.download(id=file_id, output=filepath, quiet=False)
        if not os.path.exists(filepath): return "Tải thất bại", 500
        @after_this_request
        def remove_file(response):
            try: os.remove(filepath)
            except: pass
            return response
        return send_file(filepath, as_attachment=True, download_name=f"{file_id}.bin")
    except Exception as e:
        return f"Lỗi: {str(e)}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
