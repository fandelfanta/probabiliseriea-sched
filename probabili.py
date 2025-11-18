# probabili.py (versione senza f-strings)

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


# ====== CONFIG ======
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Se passi un URL di cartella come secret/var ENV DRIVE_FOLDER_URL,
# estraggo l'ID; altrimenti puoi impostare direttamente un ID qui.
DRIVE_FOLDER_FALLBACK_ID = ""   # opzionale (es. "1Oy6nEebc7hE0OOyD3DKnqb3PaGSLk2eO")

# Glob dei file immagine da caricare (puoi sovrascriverlo con ENV IMAGE_GLOB)
DEFAULT_IMAGE_GLOB = "**/*.png"
# =====================


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
    present = [p for p in paths if os.path.isfile(p)]
    missing = [p for p in paths if p not in present]
    if missing:
        print("⚠️  Mancano questi file locali, li salto:", missing)
    return present


def _resolve_drive_folder_id() -> str:
    """Ricava l'ID cartella da ENV DRIVE_FOLDER_URL (URL o ID)."""
    env_val = os.getenv("DRIVE_FOLDER_URL", "").strip()
    if env_val:
        # se è già un ID (nessun slash), usalo
        if "/" not in env_val:
            return env_val
        # altrimenti prova ad estrarre l'ID dall'URL
        m = re.search(r"/folders/([A-Za-z0-9_\-]+)", env_val)
        if m:
            return m.group(1)

    return DRIVE_FOLDER_FALLBACK_ID.strip()


def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        "credentials.json", scopes=SCOPES
    )
    print("🔑 Service Account:", getattr(creds, "service_account_email", "n/a"))
    return build("drive", "v3", credentials=creds)


def _find_by_name_in_folder(drive, *, folder_id: str, filename: str):
    """Cerca (per nome) un file nella cartella. Ritorna l'ID se esiste, altrimenti None."""
    # Escape dell'apice: NIENTE backslash dentro espressioni di f-string (qui non usiamo f-string)
    safe_name = filename.replace("'", "\\'")
    q = (
        "'{folder}' in parents and name = '{name}' and trashed = false"
        .format(folder=folder_id, name=safe_name)
    )

    res = drive.files().list(
        q=q,
        fields="files(id, name)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        spaces="drive",
        corpora="allDrives",
        pageSize=10,
    ).execute()

    files = res.get("files", [])
    return files[0]["id"] if files else None


def upload_or_replace(drive, *, folder_id: str, file_path: str):
    """Carica un file in Drive; se esiste già con lo stesso nome lo sostituisce (update)."""
    filename = os.path.basename(file_path)
    mime = _mime_for(file_path)
    media = MediaFileUpload(file_path, mimetype=mime, resumable=True)

    existing_id = _find_by_name_in_folder(drive, folder_id=folder_id, filename=filename)

    file_metadata = {"name": filename, "parents": [folder_id]}

    try:
        if existing_id:
            updated = drive.files().update(
                fileId=existing_id,
                media_body=media,
                fields="id, name, size, modifiedTime",
                supportsAllDrives=True,
            ).execute()
            print("♻️  Aggiornato: {n} (id: {i})".format(n=updated["name"], i=updated["id"]))
        else:
            created = drive.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, name, size, createdTime",
                supportsAllDrives=True,
            ).execute()
            print("⬆️  Caricato:  {n} (id: {i})".format(n=created["name"], i=created["id"]))
    except HttpError as e:
        print("❌ Errore Drive su {fn}: {err}".format(fn=filename, err=e))


def main():
    # 1) Ricavo ID cartella
    folder_id = _resolve_drive_folder_id()
    print("User DRIVE_FOLDER:", "***" if folder_id else "''")
    print("→ ID risolto:", folder_id if folder_id else "(vuoto)")
    if not folder_id:
        print("❌ DRIVE_FOLDER_URL/ID mancante. Imposta il secret/variabile 'DRIVE_FOLDER_URL'.")
        raise SystemExit(1)

    # 2) Immagini locali
    image_glob = os.getenv("IMAGE_GLOB", DEFAULT_IMAGE_GLOB)
    all_paths = sorted(glob.glob(image_glob, recursive=True))
    all_paths = [p for p in all_paths if os.path.isfile(p)]
    print("PNG trovate nel workspace:", len(all_paths))
    if not all_paths:
        print("⚠️  Nessun file immagine trovato. Imposta IMAGE_GLOB o verifica i percorsi.")
        return

    paths = _ensure_paths_exist(all_paths)

    # 3) Verifica cartella
    drive = get_drive_service()
    try:
        folder = drive.files().get(
            fileId=folder_id,
            fields="id, name, mimeType",
            supportsAllDrives=True,
        ).execute()
        if folder.get("mimeType") != "application/vnd.google-apps.folder":
            print("❌ L'ID indicato non è una cartella Drive.")
            return
        print("📁 Drive OK. Cartella:", folder["name"])
    except HttpError as e:
        print("❌ Cartella non raggiungibile:", str(e))
        return

    # 4) Upload/replace
    for p in paths:
        upload_or_replace(drive, folder_id=folder_id, file_path=p)


if __name__ == "__main__":
    main()
