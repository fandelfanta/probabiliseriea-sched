import os, sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/drive"]

def die(msg: str):
    print(f"❌ {msg}")
    sys.exit(1)

def main():
    folder_id = os.getenv("DRIVE_FOLDER_ID", "").strip()
    if not folder_id:
        die("DRIVE_FOLDER_ID non impostato nell'ambiente.")
    print("🔎 DRIVE_FOLDER_ID usato:", folder_id)

    creds = service_account.Credentials.from_service_account_file(
        "credentials.json", scopes=SCOPES
    )
    print("🔑 Service Account:", getattr(creds, "service_account_email", "n/a"))

    drive = build("drive", "v3", credentials=creds)

    try:
        meta = drive.files().get(
            fileId=folder_id,
            fields="id,name,mimeType,shortcutDetails",
            supportsAllDrives=True,
        ).execute()
    except HttpError as e:
        die(f"Errore nell'accesso all'ID fornito: {e}")

    if meta.get("mimeType") == "application/vnd.google-apps.shortcut":
        target = meta["shortcutDetails"]["targetId"]
        print("↪️  L'ID è una scorciatoia. targetId:", target)
        try:
            meta = drive.files().get(
                fileId=target,
                fields="id,name,mimeType",
                supportsAllDrives=True,
            ).execute()
        except HttpError as e:
            die(f"Errore sul target della scorciatoia: {e}")

    if meta.get("mimeType") != "application/vnd.google-apps.folder":
        die("L'ID indicato non è una cartella Drive.")

    print("📁 Drive OK. Cartella:", meta["name"])

if __name__ == "__main__":
    main()
