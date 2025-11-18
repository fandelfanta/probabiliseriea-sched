from __future__ import annotations
import os, re, glob, mimetypes
from typing import List
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]

def _resolve_folder_id(url_or_id: str) -> str:
    if not url_or_id: return ""
    s = url_or_id.strip()
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", s) or re.search(r"[?&]id=([A-Za-z0-9_-]+)", s)
    return m.group(1) if m else s

def _mime_for(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if mime: return mime
    p = path.lower()
    if p.endswith(".png"): return "image/png"
    if p.endswith(".jpg") or p.endswith(".jpeg"): return "image/jpeg"
    return "application/octet-stream"

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    print("🔑 Service Account: {}".format(getattr(creds, "service_account_email", "n/a")))
    return build("drive", "v3", credentials=creds)

def _find_by_name_in_folder(drive, folder_id: str, filename: str) -> str | None:
    escaped = filename.replace("'", "\\'")
    q = "'{folder}' in parents and name = '{name}' and trashed = false".format(
        folder=folder_id, name=escaped
    )
    res = drive.files().list(
        q=q, fields="files(id,name)", includeItemsFromAllDrives=True,
        supportsAllDrives=True, spaces="drive", corpora="allDrives", pageSize=10
    ).execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None

def upload_or_replace(drive, folder_id: str, file_path: str):
    filename = os.path.basename(file_path)
    media = MediaFileUpload(file_path, mimetype=_mime_for(file_path), resumable=True)
    meta = {"name": filename, "parents": [folder_id]}
    try:
        existing_id = _find_by_name_in_folder(drive, folder_id, filename)
        if existing_id:
            upd = drive.files().update(
                fileId=existing_id, media_body=media,
                fields="id,name,size,modifiedTime", supportsAllDrives=True
            ).execute()
            print("♻️  Aggiornato: {} (id: {})".format(upd["name"], upd["id"]))
        else:
            created = drive.files().create(
                body=meta, media_body=media,
                fields="id,name,size,createdTime", supportsAllDrives=True
            ).execute()
            print("⬆️  Caricato:  {} (id: {})".format(created["name"], created["id"]))
    except HttpError as e:
        print("❌ Errore Drive su {}: {}".format(filename, e))

def main():
    image_glob = os.environ.get("IMAGE_GLOB", "output/**/*.png").strip()
    print("🔎 IMAGE_GLOB: {}".format(image_glob))

    drive_folder_raw = os.environ.get("DRIVE_FOLDER_URL", "").strip()
    stars = "*" * len(drive_folder_raw) if drive_folder_raw else ""
    print("User DRIVE_FOLDER: '{}'".format(stars))
    folder_id = _resolve_folder_id(drive_folder_raw)
    print("➜ ID risolto: {}".format(folder_id or "(vuoto)"))
    if not folder_id:
        print("❌ DRIVE_FOLDER_URL/ID mancante."); raise SystemExit(1)

    files = sorted(glob.glob(image_glob, recursive=True))
    if not files:
        print("⚠️  Nessun file immagine trovato. Imposta IMAGE_GLOB o verifica i percorsi.")
        return

    drive = get_drive_service()
    try:
        meta = drive.files().get(
            fileId=folder_id, fields="id,name,mimeType", supportsAllDrives=True
        ).execute()
        if meta.get("mimeType") != "application/vnd.google-apps.folder":
            print("❌ L'ID fornito non è una cartella Drive."); return
        print("📁 Drive OK. Cartella: {}".format(meta["name"]))
    except HttpError as e:
        print("❌ Errore sul target della cartella: {}".format(e)); return

    for p in files:
        if not os.path.isfile(p):
            print("⚠️  Salto (non esiste): {}".format(p)); continue
        upload_or_replace(drive, folder_id, p)

if __name__ == "__main__":
    main()
