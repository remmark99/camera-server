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

# Логируем ВСЕ запросы через before_request - REMOVED to reduce spam
# @app.before_request
# def log_requests():
#     log_all_requests()

@app.route("/imageupload", methods=["POST"])
def imageupload():
    # Only print internal details if it looks interesting or on errors, to avoid spam
    # print(f"🖼️ /imageupload received. Content-Type: {request.content_type} Length: {request.content_length}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique_id = uuid.uuid4().hex[:6]
    saved_files = []
    
    # Keep track of current event context for subsequent image parts
    current_event_code = None
    
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
                                code = events[0].get("Code")
                                
                                # Only process valid events
                                if code == "CrossLineDetection":
                                    current_event_code = code
                                    print(f"🚨 CrossLineDetection EVENT! ID: {events[0].get('EventID')}")
                                    
                                    # Save and Upload JSON
                                    json_filename = f"{timestamp}_{unique_id}_{code}.json"
                                    json_filepath = os.path.join(JSON_DIR, json_filename)
                                    with open(json_filepath, 'w') as f:
                                        json.dump(json_data, f, indent=2, ensure_ascii=False)
                                    
                                    if supabase:
                                        try:
                                            # Upload JSON to Supabase
                                            with open(json_filepath, 'rb') as f:
                                                supabase.storage.from_("alert_images").upload(json_filename, f)
                                            print(f"   📋 JSON Uploaded: {json_filename}")
                                        except Exception as e:
                                            print(f"   ❌ JSON Upload failed: {e}")
                                else:
                                    current_event_code = None # Reset if new part is a different/ignored event

                        except Exception as e:
                            pass # Silent fail on text parsing to avoid spam

                    # Check for Image
                    elif "Content-Type: image/jpeg" in headers_text or "image/jpeg" in headers_text:
                         # Only process if we are currently in a valid event context
                         if current_event_code == "CrossLineDetection":
                             filename = f"{timestamp}_{unique_id}_{current_event_code}.jpg"
                             filepath = os.path.join(IMAGES_DIR, filename)
                             
                             # Simple trim check: usually body ends with \r\n
                             if body.endswith(b"\r\n"): body = body[:-2]
                             
                             with open(filepath, 'wb') as f:
                                 f.write(body)
                             saved_files.append(filename)
                             print(f"   📸 Image Saved: {filename}")
                             
                             # Upload to Supabase
                             if supabase:
                                 try:
                                     with open(filepath, 'rb') as f:
                                         supabase.storage.from_("alert_images").upload(filename, f)
                                     print(f"   ☁️ Image Uploaded: {filename}")
                                 except Exception as e:
                                     print(f"   ❌ Image Upload failed: {e}")

        except Exception as e:
            print(f"❌ Error: {e}")

    return jsonify({"status": "ok", "saved": saved_files})

@app.route("/", methods=["GET"])
def health(): return jsonify({"status": "running"})

if __name__ == "__main__":
    print("🚀 Логирую ВСЕ запросы. Ищу image/ и multipart/")
    print(f"📂 Saving data to: {DATA_DIR}")
    app.run(host="0.0.0.0", port=5000, debug=False)
