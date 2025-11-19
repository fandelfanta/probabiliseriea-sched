#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import re
import glob
import mimetypes
from typing import List

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# -----------------------
# Config via ENV
# -----------------------
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
IMAGE_GLOB = os.environ.get("IMAGE_GLOB", "**/*.png")
DRIVE_FOLDER_URL = os.environ.get("DRIVE_FOLDER_URL", "")  # può essere URL o solo ID
SCOPES = ["https://www.googleapis.com/auth/drive"]


def extract_folder_id(url_or_id: str) -> str:
    """Accetta sia ID nudo sia URL /drive/folders/<ID>."""
    if not url_or_id:
        return ""
    m = re.search(r"/folders/([A-Za-z0-9_\-]{10,})", url_or_id)
    return m.group(1) if m else url_or_id.strip()


def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(GOOGLE_CREDENTIALS, scopes=SCOPES)
    print("🔑 Service Account:", getattr(creds, "service_account_email", "n/a"))
    return build("drive", "v3", credentials=creds)


def check_folder(drive, folder_id: str) -> str:
    meta = drive.files().get(
        fileId=folder_id,
        fields="id, name, mimeType",
        supportsAllDrives=True
    ).execute()
    if meta.get("mimeType") != "application/vnd.google-apps.folder":
        raise RuntimeError("L'ID indicato non è una cartella Drive.")
    return meta["name"]


def find_pngs(pattern: str) -> List[str]:
    files = sorted(glob.glob(pattern, recursive=True))
    return [f for f in files if os.path.isfile(f)]


def mime_for(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def _escape_for_drive_query(name: str) -> str:
    """Drive query usa singoli apici per i valori; occorre escapare l'apice nel nome file."""
    return name.replace("'", "\\'")


def upload_or_replace(drive, folder_id: str, local_path: str):
    name = os.path.basename(local_path)
    media = MediaFileUpload(local_path, mimetype=mime_for(local_path), resumable=True)

    # prepara query senza f-string (niente backslash dentro espressioni)
    safe_name = _escape_for_drive_query(name)
    q = "'{folder_id}' in parents and name = '{safe_name}' and trashed = false".format(
        folder_id=folder_id, safe_name=safe_name
    )

    res = drive.files().list(
        q=q,
        fields="files(id,name)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        pageSize=2
    ).execute()
    files = res.get("files", [])

    if files:
        file_id = files[0]["id"]
        updated = drive.files().update(
            fileId=file_id,
            media_body=media,
            fields="id, name, size, modifiedTime",
            supportsAllDrives=True
        ).execute()
        print("♻️  Aggiornato: {} (id: {})".format(updated["name"], updated["id"]))
    else:
        created = drive.files().create(
            body={"name": name, "parents": [folder_id]},
            media_body=media,
            fields="id, name, size, createdTime",
            supportsAllDrives=True
        ).execute()
        print("⬆️  Caricato:  {} (id: {})".format(created["name"], created["id"]))


def main():
    folder_id = extract_folder_id(DRIVE_FOLDER_URL)
    if not folder_id:
        print("❌ DRIVE_FOLDER_URL/ID mancante. Imposta il secret/variabile 'DRIVE_FOLDER_URL'.")
        sys.exit(1)

    print("🔎 IMAGE_GLOB:", IMAGE_GLOB)
    images = find_pngs(IMAGE_GLOB)
    if not images:
        print("⚠️  Nessun file immagine trovato con il GLOB indicato.")
        sys.exit(0)

    drive = get_drive_service()
    try:
        folder_name = check_folder(drive, folder_id)
        print("📁 Cartella OK:", folder_name)
    except HttpError as e:
        print("❌ Cartella non raggiungibile:", e)
        sys.exit(1)

    for p in images:
        try:
            upload_or_replace(drive, folder_id, p)
        except HttpError as e:
            print("❌ Errore caricando {}: {}".format(p, e))


if __name__ == "__main__":
    main()
