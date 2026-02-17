import sys
from flask import Flask, request, jsonify

app = Flask(__name__)

# Force unbuffered output so prints show in Coolify logs
sys.stdout.reconfigure(line_buffering=True)


def log_request(route_name):
    """Log all incoming request details to console."""
    print(f"\n{'='*50}")
    print(f"Route: /{route_name}")
    print(f"Method: {request.method}")
    print(f"Headers: {dict(request.headers)}")
    print(f"Args (query params): {dict(request.args)}")

    if request.is_json:
        print(f"JSON Body: {request.get_json()}")
    elif request.form:
        print(f"Form Data: {dict(request.form)}")
    elif request.data:
        print(f"Raw Data: {request.data.decode('utf-8', errors='replace')}")

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


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "running", "routes": ["/test1", "/test2", "/test3"]})


if __name__ == "__main__":
    print("Starting server on port 5000...")
    app.run(host="0.0.0.0", port=5000)
