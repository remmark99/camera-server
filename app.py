import sys
from flask import Flask, request, jsonify

app = Flask(__name__)
sys.stdout.reconfigure(line_buffering=True)

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

# Простые эндпоинты без лишних логов
@app.route("/test1", methods=["GET", "POST"])
def test1(): return jsonify({"ok": True})

@app.route("/test2", methods=["GET", "POST"])
def test2(): return jsonify({"ok": True})

@app.route("/test3", methods=["GET", "POST"])
def test3(): return jsonify({"ok": True})

@app.route("/testpost1", methods=["POST"])
def testpost1(): return jsonify({"ok": True})

@app.route("/testpost2", methods=["POST"])
def testpost2(): return jsonify({"ok": True})

@app.route("/testpost3", methods=["POST"])
def testpost3(): return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def health(): return jsonify({"status": "running"})

if __name__ == "__main__":
    print("🚀 Логирую ВСЕ запросы. Ищу image/ и multipart/")
    app.run(host="0.0.0.0", port=5000, debug=False)
