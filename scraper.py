# scraper.py — versione IDENTICA allo script Colab, senza Google Sheets

import os
import re
import asyncio
from PIL import Image, ImageOps
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from playwright.async_api import async_playwright

# ===========================================
# CONFIG
# ===========================================

OUTPUT_DIR = "./output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CREDENTIALS_FILE = "credentials.json"
DRIVE_FOLDER_URL = os.getenv("DRIVE_FOLDER_URL", "")
SCOPES = ["https://www.googleapis.com/auth/drive"]
MAX_MATCH = 10
GIORNATA = 12


# ===========================================
# DRIVE — IDENTICO AL COLAB (senza Sheets)
# ===========================================

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
    safe_name = filename.replace("'", " ")

    q = "'{folder}' in parents and name = '{name}' and trashed = false".format(
        folder=folder_id, name=safe_name
    )

    res = drive.files().list(
        q=q,
        fields="files(id)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        pageSize=2,
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
        print("♻️  Aggiornato:", filename)
    else:
        drive.files().create(
            body={"name": filename, "parents": [folder_id]},
            media_body=media,
            fields="id,name,size,createdTime",
            supportsAllDrives=True,
        ).execute()
        print("⬆️  Caricato:", filename)
# ===========================================
# BLOCCO SOSFANTA – IDENTICO AL COLAB
# ===========================================

async def estrai_sosfanta(drive, folder_id):
    print("\n=== SOSFANTA ===")

    URL = "https://www.sosfanta.com/lista-formazioni/probabili-formazioni-serie-a/"

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=False,    # <<< OBBLIGATORIO
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--ignore-gpu-blocklist",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
                "--window-size=1366,768"
            ]
        )

        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            is_mobile=False,
            has_touch=False,
            device_scale_factor=1,
            locale="it-IT"
        )

        page = await context.new_page()

        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # Cookie handling
        for sel in [
            "button:has-text('Accetta e continua')",
            "button:has-text('Accetta')",
            "text='Accetta'"
        ]:
            try:
                await page.locator(sel).first.click(timeout=2000)
                await page.wait_for_timeout(500)
                break
            except:
                pass

        await page.wait_for_timeout(3500)

        divs = await page.query_selector_all("div[id]")

        blocchi = []
        for d in divs:
            dom_id = await d.get_attribute("id")
            if dom_id and re.match(r"^[A-Z]{3}-[A-Z]{3}(-\d+)?$", dom_id):
                blocchi.append(dom_id)

        print("Blocchi trovati:", blocchi)
        blocchi = blocchi[:MAX_MATCH]

        for idx, dom_id in enumerate(blocchi, start=1):
            await page.evaluate(
                "id => document.getElementById(id).scrollIntoView({block:'center'})",
                dom_id
            )
            await page.wait_for_timeout(400)

            raw = os.path.join(OUTPUT_DIR, f"_sos_{idx}.png")
            final = os.path.join(OUTPUT_DIR, f"sosfanta_{idx}.png")

            await page.locator(f"#{dom_id}").screenshot(path=raw)

            img = Image.open(raw)
            w, h = img.size
            img.crop((120, 0, w - 120, h)).save(final)

            upload_or_replace(drive, folder_id, final)

        await browser.close()

# ===========================================
# FANTACALCIO – IDENTICO AL COLAB (versione semplificata, MA ORIGINALE)
# ===========================================

async def estrai_fantacalcio(drive, folder_id):
    print("\n=== FANTACALCIO ===")

    URL = "https://www.fantacalcio.it/probabili-formazioni-serie-a"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1600, "height": 4000})

        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        matches = await page.query_selector_all("li.match.match-item")
        matches = matches[:MAX_MATCH]

        for idx, match in enumerate(matches, start=1):
            try:
                dest = os.path.join(OUTPUT_DIR, f"fantacalcio_{idx}.png")
                await match.screenshot(path=dest)
                upload_or_replace(drive, folder_id, dest)
            except Exception as e:
                print("Errore FC:", e)

        await browser.close()


# ===========================================
# GAZZETTA – **VERSIONE COMPLETA** IDENTICA AL COLAB
# ===========================================

async def estrai_gazzetta(drive, folder_id):
    print("\n=== GAZZETTA ===")

    URL = "https://www.gazzetta.it/Calcio/prob_form/"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page(viewport={"width": 1600, "height": 4000})
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        boxes = await page.query_selector_all(".bck-box-match-details")
        boxes = boxes[:MAX_MATCH]

        print("Partite:", len(boxes))

        for idx, box in enumerate(boxes, start=1):
            try:
                await box.scroll_into_view_if_needed()
                await page.wait_for_timeout(1500)

                lineup = await box.query_selector(".match-details__lineup")
                notes = await box.query_selector(".match-details__notes")

                if not lineup:
                    continue

                path_lineup = os.path.join(OUTPUT_DIR, f"gz_lineup_{idx}.png")
                await lineup.screenshot(path=path_lineup)

                notes_img = None
                if notes:
                    path_notes = os.path.join(OUTPUT_DIR, f"gz_notes_{idx}.png")
                    await notes.screenshot(path=path_notes)
                    notes_img = Image.open(path_notes)

                # CROP, COMBINA, PAD — IDENTICO AL COLAB
                base = Image.open(path_lineup)

                rosa = (253, 233, 235)
                gap = 30
                base_w = base.width

                if notes_img:
                    gap_block = Image.new("RGB", (base_w, gap), rosa)
                    total_h = base.height + gap + notes_img.height
                    combined = Image.new("RGB", (base_w, total_h), rosa)

                    y = 0
                    combined.paste(base, (0, y))
                    y += base.height
                    combined.paste(gap_block, (0, y))
                    y += gap
                    combined.paste(notes_img, (0, y))
                else:
                    combined = base

                final = ImageOps.expand(combined, border=(20, 40, 20, 40), fill=rosa)
                final_path = os.path.join(OUTPUT_DIR, f"gazzetta_{idx}.png")
                final.save(final_path)

                upload_or_replace(drive, folder_id, final_path)

            except Exception as e:
                print("Errore Gazzetta:", e)

        await browser.close()


# ===========================================
# MAIN – A + B + C IN SEQUENZA
# ===========================================

async def main():
    folder_id = extract_folder_id(DRIVE_FOLDER_URL)
    if not folder_id:
        print("❌ DRIVE_FOLDER_URL mancante")
        return

    drive = get_drive_service()

    await estrai_sosfanta(drive, folder_id)
    await estrai_fantacalcio(drive, folder_id)
    await estrai_gazzetta(drive, folder_id)

    print("\n🟢 COMPLETATO\n")
