import sys
import os
import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)
sys.stdout.reconfigure(line_buffering=True)

# Create directories for capturing data
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "captured_data")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
JSON_DIR = os.path.join(DATA_DIR, "json")

os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)

def log_all_requests():
    """Логирует ВСЕ запросы с Content-Type. Ничего лишнего."""
    print(f"\n🔍 [{request.method}] {request.path}")
    print(f"   Content-Type: {request.content_type or 'none'}")
    print(f"   Content-Length: {request.content_length or 0}")
    
    # Ищем изображения
    if 'image/' in (request.content_type or ''):
        print("🖼️  *** ИЗОБРАЖЕНИЕ ОБНАРУЖЕНО! ***")
    elif 'multipart/' in (request.content_type or ''):
        print("📁 *** MULTIPART ОБНАРУЖЕН! ***")
    elif request.content_length and request.content_length > 10000:
        print("📦 *** БОЛЬШОЙ ФАЙЛ! ***")
    
    print()

# Логируем ВСЕ запросы через before_request
@app.before_request
def log_requests():
    log_all_requests()

@app.route("/autoupload", methods=["POST"])
def autoupload():
    data = request.get_json(silent=True)
    print(f"🚨 /autoupload JSON: {data}")
    
    if data:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{timestamp}_{uuid.uuid4().hex[:6]}.json"
        filepath = os.path.join(JSON_DIR, filename)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"   💾 Saved JSON to {filename}")

    return jsonify({"status": "ok"})

    return jsonify({"status": "ok", "saved": saved_files})

# Supabase Configuration
SUPABASE_URL = "https://urgwxfryomiertsyuwco.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVyZ3d4ZnJ5b21pZXJ0c3l1d2NvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njk0MjkwOTIsImV4cCI6MjA4NTAwNTA5Mn0.IDuetEPZQl-DaFwGqGM2-psoOXoyUsSdUrNUwhDjxYk"
try:
    from supabase import create_client, Client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except ImportError:
    print("⚠️ Supabase library not found. Uploads will be skipped.")
    supabase = None

@app.route("/imageupload", methods=["POST"])
def imageupload():
    print(f"🖼️ /imageupload received. Content-Type: {request.content_type} Length: {request.content_length}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique_id = uuid.uuid4().hex[:6]
    saved_files = []
    
    # Try standard Flask file storage
    if request.files:
        for key, file in request.files.items():
            if file and file.filename:
                # Clean filename
                safe_name = "".join([c for c in file.filename if c.isalnum() or c in "._-"])
                filename = f"{timestamp}_{unique_id}_{safe_name}"
                filepath = os.path.join(IMAGES_DIR, filename)
                file.save(filepath)
                saved_files.append(filename)
                print(f"   💾 Saved file: {filename}")
                
                # Upload to Supabase
                if supabase:
                    try:
                        with open(filepath, 'rb') as f:
                            supabase.storage.from_("alert_images").upload(filename, f)
                        print(f"   ☁️ Uploaded to Supabase: {filename}")
                    except Exception as e:
                        print(f"   ❌ Supabase upload failed: {e}")

    # If no files found via standard parsing, save raw body
    if not saved_files and request.data:
        # Detect extension or default to .bin
        ext = ".bin"
        if "image/jpeg" in (request.content_type or ""): ext = ".jpg"
        elif "image/png" in (request.content_type or ""): ext = ".png"
        
        filename = f"{timestamp}_{unique_id}_raw{ext}"
        filepath = os.path.join(IMAGES_DIR, filename)
        with open(filepath, 'wb') as f:
            f.write(request.data)
        saved_files.append(filename)
        print(f"   💾 Saved raw body: {filename}")
        
        # Upload to Supabase
        if supabase:
            try:
                with open(filepath, 'rb') as f:
                    supabase.storage.from_("alert_images").upload(filename, f)
                print(f"   ☁️ Uploaded to Supabase: {filename}")
            except Exception as e:
                print(f"   ❌ Supabase upload failed: {e}")

    return jsonify({"status": "ok", "saved": saved_files})

@app.route("/", methods=["GET"])
def health(): return jsonify({"status": "running"})

if __name__ == "__main__":
    print("🚀 Логирую ВСЕ запросы. Ищу image/ и multipart/")
    print(f"📂 Saving data to: {DATA_DIR}")
    app.run(host="0.0.0.0", port=5000, debug=False)
