from flask import Flask
import json
import time
import datetime
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

app = Flask(__name__)

# Load WHOOP secrets from environment variables
CLIENT_ID = os.getenv("WHOOP_CLIENT_ID")
CLIENT_SECRET = os.getenv("WHOOP_CLIENT_SECRET")
TOKEN_FILE = "whoop_tokens.json"

# Google Sheets Setup
SHEET_NAME = "WHOOP Log"
GOOGLE_CRED_FILE = "credentials.json"
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CRED_FILE, SCOPE)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

def refresh_token():
    with open(TOKEN_FILE, "r") as f:
        tokens = json.load(f)

    if tokens["expires_at"] > int(time.time()) + 60:
        return tokens["access_token"]

    r = requests.post("https://api.prod.whoop.com/oauth/oauth2/token", data={
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": tokens["refresh_token"]
    })

    r.raise_for_status()
    tokens = r.json()
    tokens["expires_at"] = int(time.time()) + tokens.get("expires_in", 7200)

    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)

    return tokens["access_token"]

def fetch_whoop_data(token):
    today = datetime.date.today()
    start = today.isoformat()
    end = (today + datetime.timedelta(days=1)).isoformat()
    headers = {"Authorization": f"Bearer {token}"}

    def get(endpoint):
        url = f"https://api.prod.whoop.com{endpoint}"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        return r.json().get("records", [])

    return {
        "Recovery": get(f"/v1/recovery?start={start}&end={end}"),
        "Sleep": get(f"/v1/sleep?start={start}&end={end}"),
        "Strain": get(f"/v1/strain?start={start}&end={end}")
    }

def log_to_sheet(data):
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    rec = data['Recovery'][0] if data['Recovery'] else {}
    slp = data['Sleep'][0] if data['Sleep'] else {}
    strn = data['Strain'][0] if data['Strain'] else {}

    row = [
        now,
        slp.get('time_in_bed', 'N/A') / 3600 if slp else 'N/A',
        rec.get('recovery_score', 'N/A'),
        strn.get('score', 'N/A'),
        rec.get('heart_rate_variability_rmssd', 'N/A'),
        rec.get('resting_heart_rate', 'N/A'),
        rec.get('skin_temp_celsius', 'N/A'),
        rec.get('respiratory_rate', 'N/A'),
        '', '', '', ''
    ]
    sheet.append_row(row)

@app.route('/')
def sync():
    try:
        token = refresh_token()
        data = fetch_whoop_data(token)
        log_to_sheet(data)
        return "✅ WHOOP data synced."
    except Exception as e:
        return f"❌ Sync error: {str(e)}"

if __name__ == "__main__":
    app.run(debug=True)
