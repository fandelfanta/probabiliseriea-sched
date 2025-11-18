# smoke.py – verifica credenziali + accesso cartella Drive (robusto)
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

DRIVE_FOLDER_ID = "1Oy6nEebc7hE0OOyD3DKnqb3PaGSLk2eO"  # <-- ID CORRETTO (1O..., non 10...)
SCOPES = ["https://www.googleapis.com/auth/drive"]

def err(msg: str):
    print(f"❌ {msg}")
    sys.exit(1)

def main():
    print("🔎 DRIVE_FOLDER_ID usato:", DRIVE_FOLDER_ID)
    creds = service_account.Credentials.from_service_account_file(
        "credentials.json", scopes=SCOPES
    )
    print("🔑 Service Account:", getattr(creds, "service_account_email", "n/a"))

    drive = build("drive", "v3", credentials=creds)

    # Provo a leggere i metadati dell'ID passato
    try:
        file_meta = drive.files().get(
            fileId=DRIVE_FOLDER_ID,
            fields="id,name,mimeType,shortcutDetails",
            supportsAllDrives=True,
        ).execute()
    except HttpError as e:
        # Drive restituisce 404 anche per oggetti non condivisi con l'utente/SA
        err(f"Errore nell'accesso alla cartella: {e}")

    # Se è una scorciatoia, seguo il target
    if file_meta.get("mimeType") == "application/vnd.google-apps.shortcut":
        target = file_meta["shortcutDetails"]["targetId"]
        print("↪️  L'ID è una scorciatoia. targetId:", target)
        try:
            file_meta = drive.files().get(
                fileId=target,
                fields="id,name,mimeType",
                supportsAllDrives=True,
            ).execute()
        except HttpError as e:
            err(f"Errore sul target della scorciatoia: {e}")

    if file_meta.get("mimeType") != "application/vnd.google-apps.folder":
        err("L'ID indicato non è una cartella Drive.")

    print("📁 Drive OK. Cartella:", file_meta["name"])

    # elenco primi file (facoltativo)
    res = drive.files().list(
        q=f"'{file_meta['id']}' in parents and trashed = false",
        fields="files(id,name,mimeType)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        pageSize=5,
    ).execute()
    files = res.get("files", [])
    if not files:
        print("ℹ️  La cartella è vuota (o non ho visibilità sui contenuti).")
    else:
        print("📄 Esempi contenuti:")
        for f in files:
            print(f"  - {f['name']} ({f['mimeType']})")

if __name__ == "__main__":
    main()
