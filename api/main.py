from flask import Flask, request, jsonify
from app.storage import get_user_entries, save_entry
from app.analysis import analyze_sentiment
from app.journal import create_entry
from app.auth import authenticate

app = Flask(__name__)

@app.route("/submit", methods=["POST"])
def submit_entry():
    data = request.get_json()
    user_id = data.get("user_id")
    token = data.get("token")
    text = data.get("text")
    if not authenticate(user_id, token):
        return jsonify({"error": "Unauthorized"}), 401
    entry = create_entry(text, user_id)
    sentiment = analyze_sentiment(text)
    entry.update(sentiment)
    save_entry(entry)
    return jsonify(entry), 201

@app.route("/logs/<user_id>", methods=["GET"])
def get_logs(user_id):
    token = request.args.get("token")
    if not authenticate(user_id, token):
        return jsonify({"error": "Unauthorized"}), 401
    entries = get_user_entries(user_id)
    return jsonify(entries)

if __name__ == "__main__":
    app.run(debug=True)
