import os, re, sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/drive"]

def die(msg: str):
    print(f"❌ {msg}")
    sys.exit(1)

def extract_id_from_input(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    # Se è una URL Google Drive stile .../folders/<ID>
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", raw)
    if m:
        return m.group(1)
    # Altrimenti assumiamo sia già un ID
    return raw

def main():
    raw = os.getenv("DRIVE_FOLDER", "").strip()
    if not raw:
        die("DRIVE_FOLDER non impostato (metti la URL completa o l'ID).")

    folder_id = extract_id_from_input(raw)
    print("🔎 DRIVE_FOLDER input :", raw)
    print("🔎 ID estratto         :", folder_id)

    if not folder_id:
        die("Impossibile estrarre un ID valido da DRIVE_FOLDER.")

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

    # Se è una scorciatoia, risolviamo il target
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
