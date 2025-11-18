# smoke.py
from google.oauth2 import service_account
from googleapiclient.discovery import build
import gspread

SHEET_ID = "1l8v3uDyzk1A9sMUwoV2L_rhOns-vJRV7iOTRfLK4ZvU"
DRIVE_FOLDER_ID = "1Oy6nEebc7hE0OOyD3DKnqb3PaGSLk2eO"
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

def main():
    creds = service_account.Credentials.from_service_account_file(
        "credentials.json", scopes=SCOPES
    )
    print("🔑 Service Account:", creds.service_account_email)

    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    print("📄 Sheets OK. Titolo:", sh.title)

    drive = build("drive", "v3", credentials=creds)
    folder = drive.files().get(
        fileId=DRIVE_FOLDER_ID,
        fields="id, name, mimeType, parents",
        supportsAllDrives=True
    ).execute()
    print("📁 Drive OK. Cartella:", folder["name"])

if __name__ == "__main__":
    main()
