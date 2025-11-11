from flask import Flask, request, jsonify
import requests

# Flask app बनाओ
app = Flask(__name__)

# Vercel के लिए entrypoint
application = app

@app.route('/api')
def osint():
    key = request.args.get('key')
    number = request.args.get('term', '').strip()

    if key != "ANUJ123":
        return jsonify({"success": False, "error": "Invalid key"}), 401

    if not number.isdigit() or len(number) != 10:
        return jsonify({"success": False, "error": "Invalid number"}), 400

    try:
        r = requests.get(f"https://zionix-x-osint.vercel.app/api?key=VALD7&type=mobile&term={number}")
        return jsonify(r.json())
    except:
        return jsonify({"success": False, "error": "API down"}), 500

@app.route('/')
def home():
    return "<h1 style='color: #00ffaa; text-align: center; margin-top: 100px;'>AnujWebs OSINT API LIVE है! 🚀</h1><p style='text-align: center;'>Use: /api?key=ANUJ123&term=7701803770</p>"

# Vercel के लिए जरूरी
if __name__ == "__main__":
    app.run()
