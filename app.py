import sys
import json
from flask import Flask, request, jsonify

app = Flask(__name__)

# Force unbuffered output so prints show in Coolify logs
sys.stdout.reconfigure(line_buffering=True)

def parse_multipart_boundary(content_type):
    """Извлекает boundary из Content-Type."""
    if 'boundary=' in content_type:
        return content_type.split('boundary=')[1].rstrip('; ').strip('"')
    return None

def log_request(route_name):
    """Расширенный лог с поддержкой multipart/x-mixed-replace и изображений."""
    print(f"\n{'='*50}")
    print(f"Route: /{route_name}")
    print(f"Method: {request.method}")
    print(f"Content-Type: {request.content_type}")
    print(f"Content-Encoding: {request.content_encoding}")
    print(f"Headers: {dict(request.headers)}")
    print(f"Args (query params): {dict(request.args)}")
    
    image_detected = False
    data = None
    content_type = request.headers.get("Content-Type", "")
    
    try:
        if "multipart/x-mixed-replace" in content_type:
            print("🔄 Обработка multipart/x-mixed-replace")
            boundary = parse_multipart_boundary(content_type)
            if boundary:
                print(f"  Boundary: --{boundary}")
                # Flask не парсит mixed-replace автоматически, логируем raw
                print(f"  Raw multipart data: {len(request.data)} байт")
                print("  Для полного парсинга используй python-multipart или Quart")
            image_detected = "image" in content_type.lower()
            
        else:
            # Обычная обработка
            if request.files:
                print(f"📁 Files: {len(request.files)} файлов")
                for key, file in request.files.items():
                    print(f"  - {key}: {file.filename or 'no-name'} ({file.content_length} байт, {file.mimetype})")
                image_detected = True
                
            elif request.is_json or "application/json" in content_type:
                data = request.get_json()
                print(f"📄 JSON Body: {json.dumps(data, indent=2, ensure_ascii=False)[:1000]}...")
                
            elif "text/plain" in content_type:
                raw_text = request.data.decode('utf-8', errors='replace')
                try:
                    data = json.loads(raw_text)
                    print(f"📄 Text JSON: {json.dumps(data, indent=2, ensure_ascii=False)[:1000]}...")
                except json.JSONDecodeError:
                    print(f"📄 Raw Text ({len(raw_text)} chars): {raw_text[:500]}...")
                    
            elif "image/jpeg" in content_type or "image/" in content_type:
                image_data = request.get_data()
                image_detected = True
                print(f"🖼️  Изображение пришло: {len(image_data)} байт ({content_type})")
                
            elif request.data:
                print(f"📦 Raw Data ({len(request.data)} байт): {request.data[:200]}...")
        
        if image_detected:
            print("🚨 *** ИЗОБРАЖЕНИЕ ПРИШЛО! *** 🚨")
            
    except Exception as e:
        print(f"❌ Ошибка логирования: {e}")
        print(f"Raw request.data: {request.data[:300]}...")
    
    print(f"{'='*50}\n")

@app.route("/test1", methods=["GET", "POST"])
def test1():
    log_request("test1")
    return jsonify({"status": "ok", "route": "test1"})

@app.route("/test2", methods=["GET", "POST"])
def test2():
    log_request("test2")
    return jsonify({"status": "ok", "route": "test2"})

@app.route("/test3", methods=["GET", "POST"])
def test3():
    log_request("test3")
    return jsonify({"status": "ok", "route": "test3"})

@app.route("/testpost1", methods=["POST"])
def testpost1():
    log_request("testpost1")
    return jsonify({"status": "ok", "route": "testpost1"})

@app.route("/testpost2", methods=["POST"])
def testpost2():
    log_request("testpost2")
    return jsonify({"status": "ok", "route": "testpost2"})

@app.route("/testpost3", methods=["POST"])
def testpost3():
    log_request("testpost3")
    return jsonify({"status": "ok", "route": "testpost3"})

@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "running", 
        "routes": ["/test1", "/test2", "/test3", "/testpost1", "/testpost2", "/testpost3"],
        "features": ["multipart detection", "image logging", "deflate support"]
    })

if __name__ == "__main__":
    print("🚀 Starting enhanced server on port 5000...")
    print("Поддержка: JSON, multipart/form-data, image/jpeg, multipart/x-mixed-replace")
    app.run(host="0.0.0.0", port=5000, debug=False)
