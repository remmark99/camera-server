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

@app.route("/imageupload", methods=["POST"])
def imageupload():
    print(f"🖼️ /imageupload received. Content-Type: {request.content_type} Length: {request.content_length}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique_id = uuid.uuid4().hex[:6]
    saved_files = []
    
    # Keep track of current event context for subsequent image parts
    current_event_code = None
    current_event_id = None
    
    # 1. Handle multipart/x-mixed-replace (Dahua style)
    if request.content_type and "multipart/x-mixed-replace" in request.content_type:
        try:
            boundary = request.content_type.split("boundary=")[-1].strip()
            # Handle quotes around boundary if present
            if boundary.startswith('"') and boundary.endswith('"'):
                boundary = boundary[1:-1]
            
            # Flask's get_data() returns the full raw body
            raw_data = request.get_data()
            
            # Split by boundary
            delimiter = f"--{boundary}".encode()
            parts = raw_data.split(delimiter)
            
            for part in parts:
                if not part or part.strip() == b"--": continue
                
                # Split headers and body
                head_body_sep = b"\r\n\r\n"
                if head_body_sep not in part:
                    head_body_sep = b"\n\n"
                
                if head_body_sep in part:
                    headers_raw, body = part.split(head_body_sep, 1)
                    headers_text = headers_raw.decode('utf-8', errors='ignore')
                    
                    # Check for JSON metadata first
                    if "application/json" in headers_text or "text/plain" in headers_text:
                        try:
                            # Trim potential trailing whitespace
                            text_content = body.decode('utf-8', errors='ignore').strip()
                            json_data = json.loads(text_content)
                            
                            # Extract event info
                            events = json_data.get("Events", [])
                            if events:
                                current_event_code = events[0].get("Code")
                                current_event_id = events[0].get("EventID")
                                print(f"   � Event Detected: {current_event_code} (ID: {current_event_id})")
                                
                                # Log detection
                                if current_event_code == "CrossLineDetection":
                                    print("   ✅ Valid Event: CrossLineDetection")
                                else:
                                    print(f"   ⚠️ Ignoring Event: {current_event_code}")

                        except Exception as e:
                            print(f"   ⚠️ Could not parse text part as JSON: {e}")

                    # Check for Image
                    elif "Content-Type: image/jpeg" in headers_text or "image/jpeg" in headers_text:
                         # Only process if it matches our criteria
                         if current_event_code == "CrossLineDetection":
                             filename = f"{timestamp}_{unique_id}_{current_event_code}.jpg"
                             filepath = os.path.join(IMAGES_DIR, filename)
                             
                             # Simple trim check: usually body ends with \r\n
                             if body.endswith(b"\r\n"): body = body[:-2]
                             
                             with open(filepath, 'wb') as f:
                                 f.write(body)
                             saved_files.append(filename)
                             print(f"   📸 Saved Image: {filename}")
                             
                             # Upload to Supabase
                             if supabase:
                                 try:
                                     with open(filepath, 'rb') as f:
                                         supabase.storage.from_("alert_images").upload(filename, f)
                                     print(f"   ☁️ Uploaded to Supabase: {filename}")
                                 except Exception as e:
                                     print(f"   ❌ Supabase upload failed: {e}")
                         else:
                             print(f"   ⛔ Skipping image for event: {current_event_code}")

        except Exception as e:
            print(f"   ❌ Error parsing multipart: {e}")
            import traceback
            traceback.print_exc()

    return jsonify({"status": "ok", "saved": saved_files})

@app.route("/", methods=["GET"])
def health(): return jsonify({"status": "running"})

if __name__ == "__main__":
    print("🚀 Логирую ВСЕ запросы. Ищу image/ и multipart/")
    print(f"📂 Saving data to: {DATA_DIR}")
    app.run(host="0.0.0.0", port=5000, debug=False)
