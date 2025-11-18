# probabili.py
from __future__ import annotations
import os
import re
import glob
import mimetypes
from typing import List

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]


def _resolve_folder_id(url_or_id: str) -> str:
    """Accetta un URL di cartella Drive o un ID e ritorna l'ID."""
    if not url_or_id:
        return ""
    s = url_or_id.strip()

    # Se è un URL di tipo /folders/<ID>
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1)

    # Se è un URL con open?id=<ID>
    m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1)

    # Altrimenti assumiamo sia già un ID
    return s


def _mime_for(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if mime:
        return mime
    lp = path.lower()
    if lp.endswith(".png"):
        return "image/png"
    if lp.endswith(".jpg") or lp.endswith(".jpeg"):
        return "image/jpeg"
    return "application/octet-stream"


def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        "credentials.json", scopes=SCOPES
    )
    print(f"🔑 Service Account: {getattr(creds, 'service_account_email', 'n/a')}")
    return build("drive", "v3", credentials=creds)


def _find_by_name_in_folder(drive, folder_id: str, filename: str) -> str | None:
    """Cerca un file con lo stesso nome nella cartella target. Ritorna l'ID se esiste."""
    from googleapiclient.discovery import Resource  # type: ignore
    assert isinstance(drive, Resource)
    q = (
        f"'{folder_id}' in parents and name = '{filename.replace(\"'\", \"\\'\")}' "
        f"and trashed = false"
    )
    res = drive.files().list(
        q=q,
        fields="files(id,name)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        spaces="drive",
        corpora="allDrives",
        pageSize=10,
    ).execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None


def upload_or_replace(drive, folder_id: str, file_path: str):
    filename = os.path.basename(file_path)
    media = MediaFileUpload(file_path, mimetype=_mime_for(file_path), resumable=True)
    file_metadata = {"name": filename, "parents": [folder_id]}

    try:
        existing_id = _find_by_name_in_folder(drive, folder_id, filename)
        if existing_id:
            updated = drive.files().update(
                fileId=existing_id,
                media_body=media,
                fields="id,name,size,modifiedTime",
                supportsAllDrives=True,
            ).execute()
            print(f"♻️  Aggiornato: {updated['name']} (id: {updated['id']})")
        else:
            created = drive.files().create(
                body=file_metadata,
                media_body=media,
                fields="id,name,size,createdTime",
                supportsAllDrives=True,
            ).execute()
            print(f"⬆️  Caricato:  {created['name']} (id: {created['id']})")
    except HttpError as e:
        print(f"❌ Errore Drive su {filename}: {e}")


def main():
    # 1) Legge dove prendere i PNG (pattern)
    image_glob = os.environ.get("IMAGE_GLOB", "output/**/*.png").strip()
    print(f"🔎 IMAGE_GLOB: {image_glob}")

    # 2) Legge URL/ID della cartella Drive dai secrets/vars
    drive_folder_raw = os.environ.get("DRIVE_FOLDER_URL", "").strip()
    print(f"User DRIVE_FOLDER: '{'*'*len(drive_folder_raw) if drive_folder_raw else ''}'")
    folder_id = _resolve_folder_id(drive_folder_raw)
    print(f"➜ ID risolto: {folder_id or '(vuoto)'}")
    if not folder_id:
        print("❌ DRIVE_FOLDER_URL/ID mancante. Imposta il secret/variabile 'DRIVE_FOLDER_URL'.")
        raise SystemExit(1)

    # 3) Scansiona i file locali
    files = sorted(glob.glob(image_glob, recursive=True))
    if not files:
        print("⚠️  Nessun file immagine trovato. Imposta IMAGE_GLOB o verifica i percorsi.")
        return  # non fallisco il job

    # 4) Verifica cartella e prepara Drive
    drive = get_drive_service()
    try:
        meta = drive.files().get(
            fileId=folder_id,
            fields="id,name,mimeType",
            supportsAllDrives=True,
        ).execute()
        if meta.get("mimeType") != "application/vnd.google-apps.folder":
            print("❌ L'ID fornito non è una cartella Drive.")
            return
        print(f"📁 Drive OK. Cartella: {meta['name']}")
    except HttpError as e:
        print(f"❌ Errore sul target della cartella: {e}")
        return

    # 5) Upload (o update se esiste già lo stesso filename)
    for p in files:
        if not os.path.isfile(p):
            print(f"⚠️  Salto (non esiste): {p}")
            continue
        upload_or_replace(drive, folder_id, p)


if __name__ == "__main__":
    main()
