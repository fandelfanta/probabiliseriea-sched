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

# === CONFIG DI DEFAULT (usate solo come fallback) ===
DEFAULT_DRIVE_FOLDER_ID = "1Oy6nEebc7hE0OOyD3DKnqb3PaGSLk2eO"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Se non imposti IMAGE_GLOB come variabile d'ambiente,
# cerchiamo le PNG in output/ ricorsivamente.
DEFAULT_IMAGE_GLOB = "output/**/*.png"


def _extract_folder_id(value: str | None) -> str:
    """
    Accetta una URL di Drive o un ID; ritorna un ID valido.
    """
    if not value:
        return DEFAULT_DRIVE_FOLDER_ID
    # URL tipo .../folders/<ID>
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", value)
    if m:
        return m.group(1)
    # già un ID "nudo"?
    if re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return value
    # fallback
    return DEFAULT_DRIVE_FOLDER_ID


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


def _discover_images() -> List[str]:
    """
    Raccoglie i file da caricare:
    - se IMAGE_GLOB è impostato, usa quello (es. 'output/**/*.png');
    - altrimenti usa DEFAULT_IMAGE_GLOB.
    """
    pattern = os.getenv("IMAGE_GLOB", DEFAULT_IMAGE_GLOB)
    files = sorted(glob.glob(pattern, recursive=True))
    files = [f for f in files if os.path.isfile(f)]
    return files


def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        "credentials.json", scopes=SCOPES
    )
    print(f"🔑 Service Account: {getattr(creds, 'service_account_email', 'n/a')}")
    return build("drive", "v3", credentials=creds)


def _find_by_name_in_folder(drive, *, folder_id: str, filename: str):
    """
    Cerca un file con lo stesso nome nella cartella (My Drive o Shared Drive).
    Ritorna l'ID se esiste, altrimenti None.
    """
    # Escapa gli apici nel nome file PRIMA di costruire l'f-string,
    # così l'espressione {safe_name} è semplice (niente backslash nell'espressione).
    safe_name = filename.replace("'", "\\'")

    q = (
        f"'{folder_id}' in parents and "
        f"name = '{safe_name}' and "
        f"trashed = false"
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
            print(f"♻️  Aggiornato: {updated['name']} (id: {updated['id']})")
        else:
            created = drive.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, name, size, createdTime",
                supportsAllDrives=True,
            ).execute()
            print(f"⬆️  Caricato:  {created['name']} (id: {created['id']})")
    except HttpError as e:
        print(f"❌ Errore Drive su {filename}: {e}")


def main():
    # 1) Prendiamo cartella da env (URL o ID)
    folder_env = os.getenv("DRIVE_FOLDER")
    folder_id = _extract_folder_id(folder_env)
    print(f"📁 User DRIVE_FOLDER: {folder_env!r} → ID risolto: {folder_id}")

    # 2) Scopriamo le immagini da caricare
    images = _discover_images()
    if not images:
        print("⚠️  Nessun file immagine trovato. Imposta IMAGE_GLOB o verifica il percorso.")
        return
    print(f"📷 File da caricare ({len(images)}):")
    for p in images:
        print("   -", p)

    # 3) Verifica cartella
    drive = get_drive_service()
    try:
        meta = drive.files().get(
            fileId=folder_id, fields="id, name, mimeType", supportsAllDrives=True
        ).execute()
        if meta.get("mimeType") != "application/vnd.google-apps.folder":
            print("❌ L'ID indicato non è una cartella Drive.")
            return
        print("✅ Cartella OK:", meta["name"])
    except HttpError as e:
        print("❌ Cartella non raggiungibile:", e)
        return

    # 4) Upload
    for p in images:
        upload_or_replace(drive, folder_id=folder_id, file_path=p)


if __name__ == "__main__":
    main()
