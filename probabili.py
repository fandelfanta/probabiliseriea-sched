# probabili.py  — versione senza f-string
from __future__ import annotations

import glob
import mimetypes
import os
import re
from typing import List, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


# ------------------------------------------
# Utility
# ------------------------------------------

def _mime_for(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if mime is None:
        if path.lower().endswith(".png"):
            mime = "image/png"
        elif path.lower().endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        else:
            mime = "application/octet-stream"
    return mime


def _ensure_paths_exist(paths: List[str]) -> List[str]:
    ok = []
    missing = []
    for p in paths:
        if os.path.isfile(p):
            ok.append(p)
        else:
            missing.append(p)
    if missing:
        print("⚠️  Mancano questi file locali, li salto:", missing)
    return ok


def _resolve_folder_id(url_or_id: str) -> Optional[str]:
    """Accetta URL di cartella Drive o ID già pulito e restituisce l'ID."""
    if not url_or_id:
        return None
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", url_or_id)
    if m:
        return m.group(1)
    # se è un id puro, lo accettiamo
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", url_or_id):
        return url_or_id
    return None


def _drive_service():
    # Il workflow setta GOOGLE_APPLICATION_CREDENTIALS -> credentials.json
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    scopes = ["https://www.googleapis.com/auth/drive"]
    creds = service_account.Credentials.from_service_account_file(cred_path, scopes=scopes)
    print("🔑 Service Account:", getattr(creds, "service_account_email", "n/a"))
    return build("drive", "v3", credentials=creds)


def _find_by_name_in_folder(drive, folder_id: str, filename: str) -> Optional[str]:
    query = (
        "'" + folder_id + "' in parents and "
        "name = '" + filename.replace("'", "\\'") + "' and "
        "trashed = false"
    )
    res = drive.files().list(
        q=query,
        fields="files(id,name)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        spaces="drive",
        corpora="allDrives",
        pageSize=10,
    ).execute()
    files = res.get("files", [])
    if files:
        return files[0].get("id")
    return None


def _upload_or_replace(drive, folder_id: str, file_path: str) -> None:
    filename = os.path.basename(file_path)
    mime = _mime_for(file_path)
    media = MediaFileUpload(file_path, mimetype=mime, resumable=True)

    existing_id = _find_by_name_in_folder(drive, folder_id, filename)
    meta = {"name": filename, "parents": [folder_id]}

    try:
        if existing_id:
            updated = drive.files().update(
                fileId=existing_id,
                media_body=media,
                fields="id,name,size,modifiedTime",
                supportsAllDrives=True,
            ).execute()
            print("♻️  Aggiornato:", updated.get("name"), "(id:", updated.get("id"), ")")
        else:
            created = drive.files().create(
                body=meta,
                media_body=media,
                fields="id,name,size,createdTime",
                supportsAllDrives=True,
            ).execute()
            print("⬆️  Caricato:", created.get("name"), "(id:", created.get("id"), ")")
    except HttpError as e:
        print("❌ Errore Drive su", filename, ":", str(e))


# ------------------------------------------
# Main
# ------------------------------------------

def main() -> int:
    # 1) Cartella di destinazione da secret/variabile (URL o ID)
    user_folder = os.environ.get("DRIVE_FOLDER_URL", "").strip()
    print("User DRIVE_FOLDER:", "***" if user_folder else "''")
    folder_id = _resolve_folder_id(user_folder)
    print("→ ID risolto:", folder_id if folder_id else "(vuoto)")
    if not folder_id:
        print("❌ DRIVE_FOLDER_URL/ID mancante. Imposta il secret/variabile 'DRIVE_FOLDER_URL'.")
        return 1

    # 2) Glob immagini (puoi cambiarlo dal workflow con IMAGE_GLOB)
    image_glob = os.environ.get("IMAGE_GLOB", "**/*.png")
    candidates = glob.glob(image_glob, recursive=True)
    paths = _ensure_paths_exist(candidates)
    if not paths:
        print("⚠️  Nessun file immagine trovato. Imposta IMAGE_GLOB o verifica i percorsi.")
        return 0

    # 3) Service e verifica cartella
    drive = _drive_service()
    try:
        meta = drive.files().get(
            fileId=folder_id,
            fields="id,name,mimeType",
            supportsAllDrives=True,
        ).execute()
        if meta.get("mimeType") != "application/vnd.google-apps.folder":
            print("❌ L'ID indicato non è una cartella Drive.")
            return 1
        print("📁 Drive OK. Cartella:", meta.get("name"))
    except HttpError as e:
        print("❌ Errore sul target della cartella:", str(e))
        return 1

    # 4) Upload
    for p in paths:
        _upload_or_replace(drive, folder_id, p)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
