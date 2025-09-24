from flask import Flask, request, jsonify, send_file
import requests
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
import os

app = Flask(__name__)
DB_FILE = "weather.db"

# ----------------- Database Initialization -----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS weather_data (
            timestamp TEXT PRIMARY KEY,
            temperature REAL,
            humidity REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ----------------- Fetch Weather Data -----------------
@app.route("/weather-report")
def weather_report():
    print("Inside weather report")
    lat = request.args.get("lat")
    lon = request.args.get("lon")

    if not lat or not lon:
        return jsonify({"error": "Missing lat or lon"}), 400

    try:
        url = (
    f"https://api.open-meteo.com/v1/forecast"
    f"?latitude={lat}&longitude={lon}"
    f"&hourly=temperature_2m,relative_humidity_2m&past_days=2&timezone=UTC"
)
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        timestamps = data["hourly"]["time"]
        temperatures = data["hourly"]["temperature_2m"]
        humidities = data["hourly"]["relative_humidity_2m"]

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # insert or replace to avoid duplicate primary key errors
        for ts, temp, hum in zip(timestamps, temperatures, humidities):
            c.execute(
                """
                INSERT OR REPLACE INTO weather_data (timestamp, temperature, humidity)
                VALUES (?, ?, ?)
                """,
                (ts, temp, hum),
            )
        conn.commit()
        conn.close()
        print("Weather data saved successfully")
        return jsonify({"message": "Weather data saved successfully", "records": len(timestamps)})

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Request failed: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"Other error: {e}"}), 500


# ----------------- Export Excel -----------------
@app.route("/export/excel", methods=["GET"])
def export_excel():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM weather_data ORDER BY timestamp DESC LIMIT 48", conn)
    conn.close()

    excel_file = "weather_data_last_48h.xlsx"
    df.to_excel(excel_file, index=False)
    return send_file(excel_file, as_attachment=True)

# ----------------- Export PDF -----------------
@app.route("/export/pdf", methods=["GET"])
def export_pdf():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query(
        "SELECT * FROM weather_data ORDER BY timestamp ASC", conn
    )
    conn.close()

    if df.empty:
        return jsonify({"error": "No data available for the last 48 hours"}), 404

    # Ensure timestamp is datetime for plotting and range display
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Plot chart
    chart_file = "chart.png"
    plt.figure(figsize=(10, 5))
    plt.plot(df["timestamp"], df["temperature"], label="Temperature (°C)", color="red")
    plt.plot(df["timestamp"], df["humidity"], label="Humidity (%)", color="blue")
    plt.xticks(rotation=45, ha="right")
    plt.xlabel("Timestamp (UTC)")
    plt.ylabel("Values")
    plt.legend()
    plt.tight_layout()
    plt.savefig(chart_file)
    plt.close()

    # Generate PDF
    pdf_file = "weather_report_last_48h.pdf"
    doc = SimpleDocTemplate(pdf_file, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(Paragraph("Weather Report", styles["Title"]))
    story.append(Spacer(1, 12))

    # Metadata
    lat = request.args.get("lat", "N/A")
    lon = request.args.get("lon", "N/A")
    date_range = f"{df['timestamp'].min().strftime('%Y-%m-%d %H:%M')} → {df['timestamp'].max().strftime('%Y-%m-%d %H:%M')}"
    story.append(Paragraph(f"<b>Location:</b> ({lat}, {lon})", styles["Normal"]))
    story.append(Paragraph(f"<b>Date Range:</b> {date_range}", styles["Normal"]))
    story.append(Spacer(1, 12))

    # Insert chart
    if os.path.exists(chart_file):
        story.append(Image(chart_file, width=500, height=250))
        story.append(Spacer(1, 12))

    # Add a sample table (first 10 rows)
    sample = df.head(10)
    table_data = [["Timestamp", "Temperature (°C)", "Humidity (%)"]]
    for _, row in sample.iterrows():
        table_data.append([
            row["timestamp"].strftime("%Y-%m-%d %H:%M"),
            f"{row['temperature']:.1f}",
            f"{row['humidity']:.1f}"
        ])
    from reportlab.platypus import Table
    story.append(Table(table_data, hAlign="LEFT"))

    doc.build(story)
    return send_file(pdf_file, as_attachment=True)

# ----------------- Optional Homepage -----------------
@app.route("/")
def home():
    return """
    <h2>Weather Service</h2>
    <ul>
        <li>GET /weather-report?lat=&lt;lat&gt;&lon=&lt;lon&gt; → Fetch & save data</li>
        <li>GET /export/excel → Download Excel</li>
        <li>GET /export/pdf → Download PDF report</li>
    </ul>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)