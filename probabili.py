# probabili.py
from __future__ import annotations

import os
import re
import sys
import glob
import mimetypes
from typing import List, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


# =========================
# Config da ENV (nessuna modifica al tuo generatore)
# =========================
ENV_DRIVE = os.getenv("DRIVE_FOLDER_URL", "").strip()
IMAGE_GLOB = os.getenv("IMAGE_GLOB", "output/**/*.png").strip()
CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")

SCOPES = ["https://www.googleapis.com/auth/drive"]


# ---------- Utilità ----------
def log(msg: str) -> None:
    print(msg, flush=True)


def _folder_id_from_url_or_id(value: str) -> str:
    """
    Accetta sia:
      - ID puro (es. 1Oy6nEebc7hE0OOyD3DKnqb3PaGSLk2eO)
      - URL tipo https://drive.google.com/drive/folders/<ID>
      - URL tipo https://drive.google.com/drive/u/0/folders/<ID>
    Ritorna sempre l'ID.
    """
    v = value.strip()
    if not v:
        return ""

    # Se è già un ID (niente slash) lo restituisco
    if "/" not in v and "google.com" not in v:
        return v

    # Estrazione da URL
    m = re.search(r"/folders/([a-zA-Z0-9_\-]{20,})", v)
    if m:
        return m.group(1)

    # Fallback: restituisco com’è (tenterò con Drive)
    return v


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


def _collect_files(pattern: str) -> List[str]:
    files = sorted(glob.glob(pattern, recursive=True))
    # Filtra solo file reali (evita cartelle)
    files = [f for f in files if os.path.isfile(f)]
    return files


def _drive_service(credentials_path: str):
    if not os.path.isfile(credentials_path):
        log("❌ File credenziali non trovato: {}".format(credentials_path))
        sys.exit(1)

    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=SCOPES
    )
    log("🔑 Service Account: {}".format(getattr(creds, "service_account_email", "n/a")))
    return build("drive", "v3", credentials=creds)


def _ensure_drive_folder(drive, folder_id: str) -> Optional[str]:
    """
    Verifica che l'ID esista e sia una cartella Drive.
    Ritorna il nome della cartella se ok, altrimenti None.
    """
    try:
        meta = drive.files().get(
            fileId=folder_id,
            fields="id,name,mimeType",
            supportsAllDrives=True,
        ).execute()
        if meta.get("mimeType") != "application/vnd.google-apps.folder":
            log("❌ L'ID fornito non è una cartella Drive.")
            return None
        return meta.get("name")
    except HttpError as e:
        log("❌ Cartella non raggiungibile: {}".format(e))
        return None


def _find_existing_in_folder(drive, folder_id: str, filename: str) -> Optional[str]:
    """
    Cerca un file con lo stesso nome all'interno della cartella.
    Ritorna l'ID se trovato, altrimenti None.
    """
    # Attenzione alle quote nel nome
    safe_name = filename.replace("'", "\\'")
    q = "'{}' in parents and name = '{}' and trashed = false".format(folder_id, safe_name)

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


def _upload_or_update(drive, folder_id: str, path: str) -> None:
    fname = os.path.basename(path)
    mime = _mime_for(path)
    media = MediaFileUpload(path, mimetype=mime, resumable=True)

    existing_id = _find_existing_in_folder(drive, folder_id, fname)

    try:
        if existing_id:
            updated = drive.files().update(
                fileId=existing_id,
                media_body=media,
                fields="id,name,size,modifiedTime",
                supportsAllDrives=True,
            ).execute()
            log("♻️  Aggiornato: {} (id: {})".format(updated["name"], updated["id"]))
        else:
            meta = {"name": fname, "parents": [folder_id]}
            created = drive.files().create(
                body=meta,
                media_body=media,
                fields="id,name,size,createdTime",
                supportsAllDrives=True,
            ).execute()
            log("⬆️  Caricato:  {} (id: {})".format(created["name"], created["id"]))
    except HttpError as e:
        log("❌ Errore durante upload di {}: {}".format(fname, e))


# ---------- Main ----------
def main() -> None:
    log("Esecuzione probabili.py")
    log("User DRIVE_FOLDER: '{}'".format(ENV_DRIVE))

    folder_id = _folder_id_from_url_or_id(ENV_DRIVE)
    log("→ ID risolto: {}".format(folder_id if folder_id else "(vuoto)"))

    if not folder_id:
        log("❌ DRIVE_FOLDER_URL/ID mancante. Imposta il secret/variabile 'DRIVE_FOLDER_URL'.")
        sys.exit(1)

    files = _collect_files(IMAGE_GLOB)
    if not files:
        log("⚠️  Nessun file immagine trovato. Imposta IMAGE_GLOB o verifica i percorsi.")
        sys.exit(0)

    drive = _drive_service(CREDENTIALS_PATH)

    folder_name = _ensure_drive_folder(drive, folder_id)
    if not folder_name:
        sys.exit(1)

    log("📁 Cartella OK: {}".format(folder_name))
    log("📸 {} file da caricare (pattern: {}).".format(len(files), IMAGE_GLOB))

    for p in files:
        _upload_or_update(drive, folder_id, p)

    log("✅ Fine.")


if __name__ == "__main__":
    main()
