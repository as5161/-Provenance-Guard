from signals import groq_signal, stylometric_signal, combine_scores, generate_label
from flask import Flask, request, jsonify
import sqlite3
import uuid
from datetime import datetime, timezone
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from signals import groq_signal

app = Flask(__name__)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)
DB_FILE = "provenance.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            content_id       TEXT PRIMARY KEY,
            creator_id       TEXT,
            text             TEXT,
            llm_score        REAL,
            stylo_score      REAL,
            confidence       REAL,
            attribution      TEXT,
            label            TEXT,
            status           TEXT,
            timestamp        TEXT,
            appeal_reasoning TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    ...
    data = request.get_json()
    text = data.get("text")
    creator_id = data.get("creator_id")

    # Basic input validation
    if not text or not creator_id:
        return jsonify({"error": "Both 'text' and 'creator_id' are required."}), 400

    # Generate a unique ID for this submission
    content_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    # Run both signals
    llm_score = groq_signal(text)
    stylo_score = stylometric_signal(text)

    # Combine into a single confidence score + attribution
    confidence, attribution = combine_scores(llm_score, stylo_score)

    label =  generate_label(attribution)
    status = "classified"

    # Write to the database
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO submissions
        (content_id, creator_id, text, llm_score, stylo_score,
         confidence, attribution, label, status, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (content_id, creator_id, text, llm_score, stylo_score,
          confidence, attribution, label, status, timestamp))
    conn.commit()
    conn.close()

    # Return the result
    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": label
    })

@app.route("/log", methods=["GET"])
def log():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row   # lets us read rows as dictionaries
    cur = conn.cursor()
    cur.execute("""
        SELECT content_id, creator_id, llm_score, stylo_score,
               confidence, attribution, status, timestamp, appeal_reasoning
        FROM submissions
        ORDER BY timestamp DESC
        LIMIT 20
    """)
    rows = cur.fetchall()
    conn.close()

    entries = [dict(row) for row in rows]
    return jsonify({"entries": entries})

@app.route("/dashboard", methods=["GET"])
def dashboard():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # Total submissions
    cur.execute("SELECT COUNT(*) FROM submissions")
    total = cur.fetchone()[0]

    # Breakdown by attribution
    cur.execute("SELECT attribution, COUNT(*) FROM submissions GROUP BY attribution")
    breakdown = dict(cur.fetchall())  # e.g. {"likely_ai": 1, "uncertain": 1, ...}

    # Appeals (status = under_review)
    cur.execute("SELECT COUNT(*) FROM submissions WHERE status = 'under_review'")
    appeals = cur.fetchone()[0]

    # Average confidence
    cur.execute("SELECT AVG(confidence) FROM submissions")
    avg_conf = cur.fetchone()[0]

    conn.close()

    # Handle the empty-database case gracefully
    if total == 0:
        return "<h1>Provenance Guard Dashboard</h1><p>No submissions yet.</p>"

    # Compute derived metrics
    appeal_rate = round((appeals / total) * 100, 1)
    avg_conf = round(avg_conf, 3)

    ai_count = breakdown.get("likely_ai", 0)
    uncertain_count = breakdown.get("uncertain", 0)
    human_count = breakdown.get("likely_human", 0)

    # Bar widths as percentages of total (for the visual bars)
    ai_pct = round((ai_count / total) * 100, 1)
    uncertain_pct = round((uncertain_count / total) * 100, 1)
    human_pct = round((human_count / total) * 100, 1)

    # Build the HTML page
    html = f"""
    <html>
    <head>
        <title>Provenance Guard Dashboard</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 700px;
                    margin: 40px auto; padding: 0 20px; color: #222; }}
            h1 {{ border-bottom: 2px solid #444; padding-bottom: 8px; }}
            .stat {{ font-size: 1.4em; margin: 16px 0; }}
            .stat b {{ font-size: 1.6em; }}
            .bar-label {{ margin-top: 18px; font-weight: bold; }}
            .bar-track {{ background: #eee; border-radius: 4px; overflow: hidden;
                          height: 28px; margin: 4px 0 12px; }}
            .bar-fill {{ height: 100%; color: white; text-align: right;
                         padding-right: 8px; line-height: 28px; box-sizing: border-box; }}
            .ai {{ background: #c0392b; }}
            .uncertain {{ background: #d4920a; }}
            .human {{ background: #27ae60; }}
        </style>
    </head>
    <body>
        <h1>Provenance Guard Dashboard</h1>

        <div class="stat">Total submissions: <b>{total}</b></div>
        <div class="stat">Appeal rate: <b>{appeal_rate}%</b> ({appeals} of {total})</div>
        <div class="stat">Average confidence: <b>{avg_conf}</b></div>

        <h2>Attribution breakdown</h2>

        <div class="bar-label">Likely AI ({ai_count})</div>
        <div class="bar-track"><div class="bar-fill ai" style="width:{ai_pct}%">{ai_pct}%</div></div>

        <div class="bar-label">Uncertain ({uncertain_count})</div>
        <div class="bar-track"><div class="bar-fill uncertain" style="width:{uncertain_pct}%">{uncertain_pct}%</div></div>

        <div class="bar-label">Likely Human ({human_count})</div>
        <div class="bar-track"><div class="bar-fill human" style="width:{human_pct}%">{human_pct}%</div></div>
    </body>
    </html>
    """
    return html

@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json()
    content_id = data.get("content_id")
    creator_reasoning = data.get("creator_reasoning")

    # Validate input
    if not content_id or not creator_reasoning:
        return jsonify({
            "error": "Both 'content_id' and 'creator_reasoning' are required."
        }), 400

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # Check the submission exists
    cur.execute("SELECT content_id FROM submissions WHERE content_id = ?",
                (content_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        return jsonify({"error": "No submission found with that content_id."}), 404

    # Update status to under_review and attach the reasoning
    cur.execute("""
        UPDATE submissions
        SET status = ?, appeal_reasoning = ?
        WHERE content_id = ?
    """, ("under_review", creator_reasoning, content_id))
    conn.commit()
    conn.close()

    return jsonify({
        "message": "Appeal received. Status updated to under_review.",
        "content_id": content_id,
        "status": "under_review"
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000)