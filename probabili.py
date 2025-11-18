# probabili.py  — versione NO f-strings (compatibile con GitHub Actions)
from __future__ import annotations

import os
import re
import glob
import mimetypes
from typing import List, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


# ---------------------------- CONFIG / ENV ----------------------------------

# Cartella di destinazione (URL completo o soltanto ID) passato da secret/ENV
DRIVE_FOLDER_URL = os.environ.get("DRIVE_FOLDER_URL", "").strip()

# GLOB per trovare le PNG nel workspace (puoi restringerlo a una cartella)
IMAGE_GLOB = os.environ.get("IMAGE_GLOB", "**/*.png").strip()

SCOPES = ["https://www.googleapis.com/auth/drive"]


# ---------------------------- UTIL ------------------------------------------

def _extract_folder_id(url_or_id: str) -> Optional[str]:
    """Accetta sia URL che ID puro; ritorna l'ID cartella o None."""
    if not url_or_id:
        return None
    s = url_or_id.strip()

    # Se è proprio l'ID puro (niente slash e niente 'http')
    if ("/" not in s) and ("http" not in s):
        return s

    # Prova a prendere l'ID dall'URL
    # Esempi validi:
    #   https://drive.google.com/drive/folders/1Oy6...k2e0
    #   https://drive.google.com/drive/u/0/folders/1Oy6...k2e0?usp=...
    m = re.search(r"/folders/([A-Za-z0-9_\-]+)/?", s)
    if m:
        return m.group(1)

    return None


def _mime_for(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if mime is None:
        # fallback ragionevole
        lower = path.lower()
        if lower.endswith(".png"):
            mime = "image/png"
        elif lower.endswith(".jpg") or lower.endswith(".jpeg"):
            mime = "image/jpeg"
        else:
            mime = "application/octet-stream"
    return mime


def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        "credentials.json", scopes=SCOPES
    )
    email = getattr(creds, "service_account_email", "n/a")
    print("🔑 Service Account:", email)
    return build("drive", "v3", credentials=creds)


def _find_by_name_in_folder(drive, folder_id: str, filename: str) -> Optional[str]:
    """
    Cerca un file con lo stesso nome nella cartella (My Drive o Shared Drive).
    Ritorna l'ID se esiste, altrimenti None.
    (NO f-strings: uso .format e precomputo la stringa escaped)
    """
    safe_name = filename.replace("'", "\\'")
    q = (
        "'{folder}' in parents and name = '{name}' and trashed = false"
        .format(folder=folder_id, name=safe_name)
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
    if files:
        return files[0].get("id")
    return None


def upload_or_replace(drive, folder_id: str, file_path: str) -> None:
    """
    Carica un file in Drive; se esiste già un file con lo stesso nome nella cartella
    lo sostituisce (update).
    """
    filename = os.path.basename(file_path)
    mime = _mime_for(file_path)
    media = MediaFileUpload(file_path, mimetype=mime, resumable=True)

    existing_id = _find_by_name_in_folder(drive, folder_id, filename)

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
                body={"name": filename, "parents": [folder_id]},
                media_body=media,
                fields="id,name,size,createdTime",
                supportsAllDrives=True,
            ).execute()
            print("⬆️  Caricato:", created.get("name"), "(id:", created.get("id"), ")")

    except HttpError as e:
        print("❌ Errore Drive su", filename, ":", e)


# ---------------------------- MAIN ------------------------------------------

def main() -> None:
    print("Esecuzione probabili.py")

    # 1) Risolvo ID cartella da URL/ID
    user_folder = DRIVE_FOLDER_URL or ""
    print("User DRIVE_FOLDER:", ("***" if user_folder else "''"))
    folder_id = _extract_folder_id(user_folder)
    print("→ ID risolto:", (folder_id if folder_id else "(vuoto)"))
    if not folder_id:
        print("❌ DRIVE_FOLDER_URL/ID mancante o non valido. Imposta il secret/variabile 'DRIVE_FOLDER_URL'.")
        raise SystemExit(1)

    # 2) Trovo i PNG (o il glob che preferisci) nel workspace
    print("GLOB immagini:", IMAGE_GLOB)
    files = glob.glob(IMAGE_GLOB, recursive=True)
    files = [p for p in files if os.path.isfile(p)]
    if not files:
        print("⚠️  Nessun file immagine trovato. Imposta IMAGE_GLOB o verifica i percorsi.")
        return

    print("PNG trovate nel workspace:", len(files))
    for p in files:
        print(" -", p)

    # 3) Upload
    drive = get_drive_service()

    # Verifica che l'ID sia davvero una cartella
    try:
        meta = drive.files().get(
            fileId=folder_id,
            fields="id,name,mimeType",
            supportsAllDrives=True,
        ).execute()
        if meta.get("mimeType") != "application/vnd.google-apps.folder":
            print("❌ L'ID indicato non è una cartella Drive.")
            return
        print("📁 Cartella OK. Nome:", meta.get("name"))
    except HttpError as e:
        print("❌ Errore nel recupero metadati cartella:", e)
        return

    for p in files:
        upload_or_replace(drive, folder_id, p)


if __name__ == "__main__":
    main()
