# probabili.py
from __future__ import annotations
import os
import mimetypes
from typing import List

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# === CONFIG ===
DRIVE_FOLDER_ID = "1Oy6nEebc7hE0OOyD3DKnqb3PaGSLk2eO"  # cartella di destinazione
SCOPES = [
    "https://www.googleapis.com/auth/drive",
]

# TODO: inserisci qui i path locali delle immagini generate dal tuo script.
# Puoi anche costruirla dinamicamente. I file devono esistere localmente prima dell'upload.
IMAGE_PATHS: List[str] = [
    # ESEMPI:
    # "output/JUV-MIL_01_gazzetta.png",
    # "output/JUV-MIL_02_fantacalcio.png",
    # "output/INT-ROM_01_gazzetta.png",
]


def _mime_for(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if mime is None:
        # fallback ragionevole
        if path.lower().endswith((".png",)):
            mime = "image/png"
        elif path.lower().endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        else:
            mime = "application/octet-stream"
    return mime


def _ensure_paths_exist(paths: List[str]) -> List[str]:
    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        print("⚠️  Mancano questi file locali, li salto:", missing)
    return [p for p in paths if os.path.isfile(p)]


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
    q = (
        f"'{folder_id}' in parents and "
        f"name = '{filename.replace(\"'\", \"\\'\")}' and "
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
    """
    Carica un file in Drive; se esiste già un file con lo stesso nome nella cartella
    lo sostituisce (update).
    """
    filename = os.path.basename(file_path)
    mime = _mime_for(file_path)
    media = MediaFileUpload(file_path, mimetype=mime, resumable=True)

    # Cerca se esiste già
    existing_id = _find_by_name_in_folder(drive, folder_id=folder_id, filename=filename)

    file_metadata = {
        "name": filename,
        "parents": [folder_id],
    }

    try:
        if existing_id:
            # Update (sostituisce il contenuto mantenendo stesso nome)
            updated = drive.files().update(
                fileId=existing_id,
                media_body=media,
                fields="id, name, size, modifiedTime",
                supportsAllDrives=True,
            ).execute()
            print(f"♻️  Aggiornato: {updated['name']} (id: {updated['id']})")
        else:
            # Create
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
    # 1) Se il tuo script genera le immagini, chiamalo QUI
    #    e costruisci l’elenco IMAGE_PATHS dinamicamente.
    #    Esempio:
    #    IMAGE_PATHS.extend(genera_immagini_e_restituisci_percorsi())

    # 2) Filtra quelli realmente esistenti
    paths = _ensure_paths_exist(IMAGE_PATHS)
    if not paths:
        print("⚠️  Nessun file immagine da caricare. (Controlla IMAGE_PATHS)")
        return

    # 3) Upload su Drive
    drive = get_drive_service()
    # Verifica che la cartella esista (opzionale)
    try:
        folder = drive.files().get(
            fileId=DRIVE_FOLDER_ID,
            fields="id, name, mimeType",
            supportsAllDrives=True,
        ).execute()
        if folder.get("mimeType") != "application/vnd.google-apps.folder":
            print("❌ L'ID fornito non è una cartella.")
            return
        print(f"📁 Cartella di destinazione: {folder['name']}")
    except HttpError as e:
        print(f"❌ Cartella non raggiungibile: {e}")
        return

    for p in paths:
        upload_or_replace(drive, folder_id=DRIVE_FOLDER_ID, file_path=p)


if __name__ == "__main__":
    main()
