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

# Supabase Configuration
SUPABASE_URL = "https://urgwxfryomiertsyuwco.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVyZ3d4ZnJ5b21pZXJ0c3l1d2NvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njk0MjkwOTIsImV4cCI6MjA4NTAwNTA5Mn0.IDuetEPZQl-DaFwGqGM2-psoOXoyUsSdUrNUwhDjxYk"
try:
    from supabase import create_client, Client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except ImportError:
    print("⚠️ Supabase library not found. Uploads will be skipped.")
    supabase = None

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

@app.route("/imageupload", methods=["POST"])
def imageupload():
    print(f"🖼️ /imageupload received. Content-Type: {request.content_type} Length: {request.content_length}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique_id = uuid.uuid4().hex[:6]
    saved_files = []
    
    # 1. Handle multipart/x-mixed-replace (Dahua style)
    if request.content_type and "multipart/x-mixed-replace" in request.content_type:
        print("🔄 Detected multipart/x-mixed-replace")
        try:
            boundary = request.content_type.split("boundary=")[-1].strip()
            # Handle quotes around boundary if present
            if boundary.startswith('"') and boundary.endswith('"'):
                boundary = boundary[1:-1]
            
            # Flask's get_data() returns the full raw body
            raw_data = request.get_data()
            
            # Split by boundary
            # The boundary in the body is prefixed with "--"
            delimiter = f"--{boundary}".encode()
            parts = raw_data.split(delimiter)
            
            for part in parts:
                if not part or part.strip() == b"--": continue
                
                # Split headers and body
                # Layout is: CRLF headers CRLF CRLF body CRLF
                # But sometimes just LF. Let's look for double newline.
                # Common pattern: \r\n\r\n or \n\n
                
                head_body_sep = b"\r\n\r\n"
                if head_body_sep not in part:
                    head_body_sep = b"\n\n"
                
                if head_body_sep in part:
                    headers_raw, body = part.split(head_body_sep, 1)
                    # Trim trailing newline from body if it exists (often just before next boundary)
                    # But be careful not to corrupt binary data. Usually split result is safe.
                    # Actually split() might leave the CRLF at the start of the part?
                    # The split(delimiter) eats the delimiter.
                    # The part usually starts with \r\n (from the previous boundary's end)
                    
                    headers_text = headers_raw.decode('utf-8', errors='ignore')
                    
                    if "Content-Type: image/jpeg" in headers_text or "image/jpeg" in headers_text:
                         # Extract image
                         filename = f"{timestamp}_{unique_id}.jpg"
                         filepath = os.path.join(IMAGES_DIR, filename)
                         # Simple trim check: usually body ends with \r\n
                         if body.endswith(b"\r\n"): body = body[:-2]
                         
                         with open(filepath, 'wb') as f:
                             f.write(body)
                         saved_files.append(filename)
                         print(f"   📸 Extracted Multipart Image: {filename}")
                         
                         # Upload to Supabase
                         if supabase:
                             try:
                                 with open(filepath, 'rb') as f:
                                     supabase.storage.from_("alert_images").upload(filename, f)
                                 print(f"   ☁️ Uploaded to Supabase: {filename}")
                             except Exception as e:
                                 print(f"   ❌ Supabase upload failed: {e}")

                    elif "application/json" in headers_text or "text/plain" in headers_text:
                        # Extract JSON/Text
                        # The user snippet suggests text/plain might contain JSON
                        try:
                            # Trim potential trailing whitespace
                            text_content = body.decode('utf-8', errors='ignore').strip()
                            json_data = json.loads(text_content)
                            
                            json_filename = f"{timestamp}_{unique_id}.json"
                            json_filepath = os.path.join(JSON_DIR, json_filename)
                            with open(json_filepath, 'w') as f:
                                json.dump(json_data, f, indent=2, ensure_ascii=False)
                            print(f"   📋 Extracted Multipart JSON: {json_filename}")
                        except Exception as e:
                            print(f"   ⚠️ Could not parse text part as JSON: {e}")

        except Exception as e:
            print(f"   ❌ Error parsing multipart: {e}")
            import traceback
            traceback.print_exc()

    # 2. Try standard Flask file storage (for normal uploads)
    elif request.files:
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
    
    # 3. Fallback: Save raw body with magic byte detection
    if not saved_files and request.data:
        # Check if we already handled it in multipart
        # If saved_files is empty, maybe multipart failed or it wasn't multipart
        
        # Detect extension
        ext = ".bin"
        header = request.data[:4]
        
        if header.startswith(b'\xff\xd8\xff'):
            ext = ".jpg"
        elif header.startswith(b'\x89PNG'):
            ext = ".png"
        elif "image/jpeg" in (request.content_type or ""): 
            ext = ".jpg"
        elif "image/png" in (request.content_type or ""): 
            ext = ".png"
        
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
