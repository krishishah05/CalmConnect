from flask import Flask, request, jsonify
from app.storage import get_user_entries, save_entry
from app.analysis import analyze_sentiment
from app.journal import create_entry
from app.auth import authenticate
from app.stats import get_weekly_summary, get_streak

app = Flask(__name__)


def _check_auth(user_id, token):
    if not authenticate(user_id, token):
        return jsonify({"error": "Unauthorized"}), 401
    return None


@app.route("/submit", methods=["POST"])
def submit_entry():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    user_id = data.get("user_id")
    token = data.get("token")
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"error": "Entry text is required"}), 400

    denied = _check_auth(user_id, token)
    if denied:
        return denied

    entry = create_entry(text, user_id)
    result = analyze_sentiment(text)
    entry.update(result)

    save_entry({**entry, "emotions": ",".join(entry["emotions"])})
    return jsonify(entry), 201


@app.route("/logs/<user_id>", methods=["GET"])
def get_logs(user_id):
    denied = _check_auth(user_id, request.args.get("token"))
    if denied:
        return denied

    limit = request.args.get("limit", type=int)
    entries = get_user_entries(user_id, limit=limit)
    return jsonify(entries)


@app.route("/stats/<user_id>", methods=["GET"])
def get_stats(user_id):
    denied = _check_auth(user_id, request.args.get("token"))
    if denied:
        return denied

    return jsonify({
        "weekly": get_weekly_summary(user_id),
        "streak": get_streak(user_id),
    })


if __name__ == "__main__":
    app.run(debug=True)
