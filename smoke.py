# smoke.py – verifica credenziali + accesso cartella Drive
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

DRIVE_FOLDER_ID = "1Oy6nEebc7hE0OOyD3DKnqb3PaGSLk2eO"
SCOPES = ["https://www.googleapis.com/auth/drive"]

def main():
    creds = service_account.Credentials.from_service_account_file(
        "credentials.json", scopes=SCOPES
    )
    print("🔑 Service Account:", getattr(creds, "service_account_email", "n/a"))

    drive = build("drive", "v3", credentials=creds)

    # 1) leggo i metadati della cartella
    try:
        folder = drive.files().get(
            fileId=DRIVE_FOLDER_ID,
            fields="id, name, mimeType, parents",
            supportsAllDrives=True,
        ).execute()
    except HttpError as e:
        print("❌ Errore nell'accesso alla cartella:", e)
        return

    if folder.get("mimeType") != "application/vnd.google-apps.folder":
        print("❌ L'ID fornito NON è una cartella Drive.")
        return

    print("📁 Drive OK. Cartella:", folder["name"])

    # 2) elenco i primi 5 file nella cartella (opzionale ma utile)
    res = drive.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and trashed = false",
        fields="files(id,name,mimeType) , nextPageToken",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        pageSize=5,
    ).execute()
    files = res.get("files", [])
    if not files:
        print("ℹ️  La cartella è vuota (o non ho permessi sui file).")
    else:
        print("📄 Esempi contenuti:")
        for f in files:
            print(f"  - {f['name']}  ({f['mimeType']})")

if __name__ == "__main__":
    main()
