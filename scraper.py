import os
import re
import asyncio
import glob
from PIL import Image, ImageOps

from playwright.async_api import async_playwright
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# ==========================================================
# CONFIG
# ==========================================================

OUTPUT_DIR = "./output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

SCOPES = ["https://www.googleapis.com/auth/drive"]
CREDENTIALS_FILE = "credentials.json"

# cartella Drive da secret
DRIVE_FOLDER_URL = os.getenv("DRIVE_FOLDER_URL", "")
MAX_MATCH = 10
GIORNATA = 12


# ==========================================================
# DRIVE
# ==========================================================

def extract_folder_id(url_or_id: str) -> str:
    if not url_or_id:
        return ""
    m = re.search(r"/folders/([A-Za-z0-9_\-]+)", url_or_id)
    return m.group(1) if m else url_or_id.strip()


def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def upload_or_replace(drive, folder_id: str, local_path: str):
    filename = os.path.basename(local_path)

    safe_name = filename.replace("'", " ")  # zero backslash

    q = "'{folder}' in parents and name = '{name}' and trashed = false".format(
        folder=folder_id, name=safe_name
    )

    res = drive.files().list(
        q=q,
        fields="files(id)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        pageSize=2
    ).execute()

    files = res.get("files", [])
    media = MediaFileUpload(local_path, mimetype="image/png", resumable=False)

    if files:
        file_id = files[0]["id"]
        drive.files().update(
            fileId=file_id,
            media_body=media,
            fields="id,name,size,modifiedTime",
            supportsAllDrives=True,
        ).execute()
        print("♻️ Aggiornato:", filename)
    else:
        drive.files().create(
            body={"name": filename, "parents": [folder_id]},
            media_body=media,
            fields="id,name,size,createdTime",
            supportsAllDrives=True,
        ).execute()
        print("⬆️ Caricato:", filename)


# ==========================================================
# SCRAPING
# ==========================================================

async def estrai_sosfanta(drive, folder_id):
    print("\n=== SOSFANTA ===")

    URL = "https://www.sosfanta.com/lista-formazioni/probabili-formazioni-serie-a/"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1600, "height": 4000})

        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # chiudi cookie
        for sel in [
            "button:has-text('Accetta')",
            "button:has-text('Accetta e continua')",
            "text='ACCETTA E CONTINUA'"
        ]:
            try:
                await page.locator(sel).first.click(timeout=2000)
                break
            except:
                pass

        # trova blocchi partite
        blocchi = []
        for el in await page.query_selector_all("div[id]"):
            _id = await el.get_attribute("id")
            if _id and re.match(r"^[A-Z]{3}-[A-Z]{3}(-\d+)?$", _id):
                blocchi.append(_id)

        blocchi = blocchi[:MAX_MATCH]
        print("Partite trovate:", blocchi)

        for idx, dom_id in enumerate(blocchi, start=1):
            try:
                await page.evaluate(
                    "dom_id => document.getElementById(dom_id).scrollIntoView({block:'center'})",
                    dom_id
                )
                await page.wait_for_timeout(700)

                dest = os.path.join(OUTPUT_DIR, f"sosfanta_{idx}.png")
                await page.locator(f"#{dom_id}").screenshot(path=dest)

                upload_or_replace(drive, folder_id, dest)
            except Exception as e:
                print("Errore:", e)

        await browser.close()


async def estrai_fantacalcio(drive, folder_id):
    print("\n=== FANTACALCIO ===")

    URL = "https://www.fantacalcio.it/probabili-formazioni-serie-a"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1600, "height": 4000})
        await page.goto(URL, wait_until="domcontentloaded")

        matches = await page.query_selector_all("li.match.match-item")
        matches = matches[:MAX_MATCH]

        print("Partite trovate:", len(matches))

        for idx, match in enumerate(matches, start=1):
            try:
                dest = os.path.join(OUTPUT_DIR, f"fantacalcio_{idx}.png")
                await match.screenshot(path=dest)
                upload_or_replace(drive, folder_id, dest)
            except Exception as e:
                print("Errore:", e)

        await browser.close()


async def estrai_gazzetta(drive, folder_id):
    print("\n=== GAZZETTA ===")

    URL = "https://www.gazzetta.it/Calcio/prob_form/"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1600, "height": 4000})
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        boxes = await page.query_selector_all(".bck-box-match-details")
        boxes = boxes[:MAX_MATCH]

        print("Partite trovate:", len(boxes))

        for idx, box in enumerate(boxes, start=1):
            try:
                dest = os.path.join(OUTPUT_DIR, f"gazzetta_{idx}.png")
                await box.screenshot(path=dest)
                upload_or_replace(drive, folder_id, dest)
            except Exception as e:
                print("Errore:", e)

        await browser.close()


# ==========================================================
# MAIN
# ==========================================================

async def main():
    folder_id = extract_folder_id(DRIVE_FOLDER_URL)
    if not folder_id:
        print("❌ DRIVE_FOLDER_URL non impostato.")
        return

    drive = get_drive_service()

    await estrai_sosfanta(drive, folder_id)
    await estrai_fantacalcio(drive, folder_id)
    await estrai_gazzetta(drive, folder_id)

    print("\n🟢 COMPLETATO\n")
