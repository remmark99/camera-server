import sys
import os
import json
import uuid
import io
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify
import cv2
import numpy as np
import requests as http_requests
from requests.auth import HTTPDigestAuth

app = Flask(__name__)
sys.stdout.reconfigure(line_buffering=True)

# Create directories for capturing data
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "captured_data")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

os.makedirs(IMAGES_DIR, exist_ok=True)

# Supabase Configuration
SUPABASE_URL = "https://urgwxfryomiertsyuwco.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVyZ3d4ZnJ5b21pZXJ0c3l1d2NvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njk0MjkwOTIsImV4cCI6MjA4NTAwNTA5Mn0.IDuetEPZQl-DaFwGqGM2-psoOXoyUsSdUrNUwhDjxYk"
try:
    from supabase import create_client, Client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except ImportError:
    print("⚠️ Supabase library not found. Uploads will be skipped.")
    supabase = None

# Camera Configuration
CAMERA_IP = "192.168.2.30"
CAMERA_USER = "admin"
CAMERA_PASS = "qwe12345"
CAMERA_CHANNEL = 1

# Target event filter
TARGET_LINE_NAME = "Дорога пересечена"
TARGET_OBJECT_TYPE = "Human"

# Helper to normalize coordinates (Dahua uses 8192x8192 coordinate system)
def normalize_coords(point, img_width, img_height):
    x = int((point[0] / 8192.0) * img_width)
    y = int((point[1] / 8192.0) * img_height)
    return (x, y)


def download_clip_from_camera(event_utc, clip_filename):
    """Download a clip from the Dahua camera via HTTP playback, convert to mp4, and return bytes."""
    try:
        # Calculate time window: 10 seconds before, 5 seconds after
        event_time = datetime.fromtimestamp(event_utc, tz=timezone(timedelta(hours=5)))
        start_time = event_time - timedelta(seconds=10)
        end_time = event_time + timedelta(seconds=5)

        start_str = start_time.strftime("%Y-%m-%d%%20%H:%M:%S")
        end_str = end_time.strftime("%Y-%m-%d%%20%H:%M:%S")

        playback_url = (
            f"http://{CAMERA_IP}/cgi-bin/playBack.cgi?action=getStream"
            f"&channel={CAMERA_CHANNEL}&subtype=0"
            f"&startTime={start_str}&endTime={end_str}"
        )

        print(f"   🎬 Downloading clip: {start_time.strftime('%H:%M:%S')} - {end_time.strftime('%H:%M:%S')}")

        # Download raw DAV stream
        resp = http_requests.get(
            playback_url,
            auth=HTTPDigestAuth(CAMERA_USER, CAMERA_PASS),
            stream=True,
            timeout=30
        )
        resp.raise_for_status()

        # Write raw stream to temp file, then convert to mp4 with ffmpeg
        with tempfile.NamedTemporaryFile(suffix=".dav", delete=False) as tmp_dav:
            tmp_dav_path = tmp_dav.name
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    tmp_dav.write(chunk)

        tmp_mp4_path = tmp_dav_path.replace(".dav", ".mp4")

        # Convert DAV to MP4 using ffmpeg
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", tmp_dav_path,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-movflags", "+faststart",
            tmp_mp4_path
        ]

        result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=60)
        if result.returncode != 0:
            print(f"   ❌ ffmpeg error: {result.stderr.decode('utf-8', errors='ignore')[-200:]}")
            # Cleanup
            os.unlink(tmp_dav_path)
            return None

        # Read the mp4 bytes
        with open(tmp_mp4_path, "rb") as f:
            mp4_bytes = f.read()

        # Cleanup temp files
        os.unlink(tmp_dav_path)
        os.unlink(tmp_mp4_path)

        print(f"   🎬 Clip converted: {len(mp4_bytes)} bytes")
        return mp4_bytes

    except Exception as e:
        print(f"   ❌ Clip download failed: {e}")
        return None


@app.route("/imageupload", methods=["POST"])
def imageupload():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique_id = uuid.uuid4().hex[:6]
    saved_files = []

    # Keep track of current event context for subsequent image parts
    current_event_code = None
    current_event_data = None

    # Handle multipart/x-mixed-replace (Dahua style)
    if request.content_type and "multipart/x-mixed-replace" in request.content_type:
        try:
            boundary = request.content_type.split("boundary=")[-1].strip()
            if boundary.startswith('"') and boundary.endswith('"'):
                boundary = boundary[1:-1]

            raw_data = request.get_data()
            delimiter = f"--{boundary}".encode()
            parts = raw_data.split(delimiter)

            for part in parts:
                if not part or part.strip() == b"--": continue

                head_body_sep = b"\r\n\r\n"
                if head_body_sep not in part:
                    head_body_sep = b"\n\n"

                if head_body_sep in part:
                    headers_raw, body = part.split(head_body_sep, 1)
                    headers_text = headers_raw.decode('utf-8', errors='ignore')

                    # Check for JSON metadata
                    if "application/json" in headers_text or "text/plain" in headers_text:
                        try:
                            text_content = body.decode('utf-8', errors='ignore').strip()
                            json_data = json.loads(text_content)

                            events = json_data.get("Events", [])
                            if events:
                                event = events[0]
                                code = event.get("Code")
                                data = event.get("Data", {})

                                line_name = data.get("Name", "")
                                obj_type = data.get("Object", {}).get("ObjectType", "")

                                # Only process: CrossLineDetection + "Дорога пересечена" + Human
                                if (code == "CrossLineDetection"
                                        and line_name == TARGET_LINE_NAME
                                        and obj_type == TARGET_OBJECT_TYPE):
                                    current_event_code = code
                                    current_event_data = data
                                    print(f"🚨 {TARGET_LINE_NAME} crossed by {obj_type}! ID: {event.get('EventID')}")
                                else:
                                    current_event_code = None
                                    current_event_data = None

                        except Exception:
                            pass

                    # Check for Image
                    elif "image/jpeg" in headers_text:
                        if current_event_code == "CrossLineDetection" and current_event_data:
                            filename = f"{timestamp}_{unique_id}_CrossLineDetection.jpg"
                            filepath = os.path.join(IMAGES_DIR, filename)

                            if body.endswith(b"\r\n"): body = body[:-2]

                            # Annotate Image
                            try:
                                nparr = np.frombuffer(body, np.uint8)
                                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                                if img is not None:
                                    height, width = img.shape[:2]

                                    # Draw Detect Line
                                    detect_line = current_event_data.get("DetectLine")
                                    if detect_line:
                                        pt1 = normalize_coords(detect_line[0], width, height)
                                        pt2 = normalize_coords(detect_line[1], width, height)
                                        cv2.line(img, pt1, pt2, (0, 0, 255), 3)

                                    # Draw Bounding Box
                                    obj = current_event_data.get("Object")
                                    if obj:
                                        bbox = obj.get("BoundingBox")
                                        if bbox and len(bbox) == 4:
                                            x1, y1 = normalize_coords((bbox[0], bbox[1]), width, height)
                                            x2, y2 = normalize_coords((bbox[2], bbox[3]), width, height)
                                            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 3)

                                    _, img_encoded = cv2.imencode('.jpg', img)
                                    body = img_encoded.tobytes()
                                    print("   ✏️ Annotated")

                            except Exception as e:
                                print(f"   ❌ Annotation failed: {e}")

                            # Save image locally
                            with open(filepath, 'wb') as f:
                                f.write(body)
                            saved_files.append(filename)
                            print(f"   📸 Image Saved: {filename}")

                            # Upload image to alert_images bucket
                            clip_url = ""
                            if supabase:
                                try:
                                    with open(filepath, 'rb') as f:
                                        supabase.storage.from_("alert_images").upload(filename, f)
                                    print(f"   ☁️ Image Uploaded: {filename}")
                                except Exception as e:
                                    print(f"   ❌ Image Upload failed: {e}")

                                # Download and upload clip
                                event_utc = current_event_data.get("UTC")
                                if event_utc:
                                    clip_filename = f"{timestamp}_{unique_id}_CrossLineDetection.mp4"
                                    mp4_bytes = download_clip_from_camera(event_utc, clip_filename)
                                    if mp4_bytes:
                                        try:
                                            supabase.storage.from_("clips").upload(
                                                clip_filename,
                                                mp4_bytes,
                                                {"content-type": "video/mp4"}
                                            )
                                            clip_url = f"{SUPABASE_URL}/storage/v1/object/public/clips/{clip_filename}"
                                            print(f"   🎬 Clip Uploaded: {clip_filename}")
                                        except Exception as e:
                                            print(f"   ❌ Clip Upload failed: {e}")

                                # Insert alert
                                try:
                                    line_name = current_event_data.get("Name", "Unknown")
                                    if event_utc:
                                        ts = datetime.fromtimestamp(event_utc).isoformat()
                                    else:
                                        ts = datetime.now().isoformat()

                                    alert_payload = {
                                        "module_name": "dahua_detection",
                                        "alert_type": "tripwire",
                                        "severity": 0.5,
                                        "message": f"Пересечение линии {line_name}",
                                        "timestamp": ts,
                                        "video_timestamp": 1,
                                        "source_video": "dahua_stream",
                                        "clip_path": clip_url or f"{SUPABASE_URL}/storage/v1/object/public/alert_images/{filename}",
                                        "camera_index": 322,
                                    }

                                    supabase.table("alerts").insert(alert_payload).execute()
                                    print(f"   🔔 Alert inserted")
                                except Exception as e:
                                    print(f"   ❌ Alert insertion failed: {e}")

        except Exception as e:
            print(f"❌ Error: {e}")

    return jsonify({"status": "ok", "saved": saved_files})

@app.route("/", methods=["GET"])
def health(): return jsonify({"status": "running"})

if __name__ == "__main__":
    print(f"📂 Saving data to: {DATA_DIR}")
    app.run(host="0.0.0.0", port=5000, debug=False)
