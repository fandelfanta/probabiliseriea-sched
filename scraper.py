import os
import re
import base64
import nest_asyncio
nest_asyncio.apply()

from PIL import Image
from playwright.async_api import async_playwright
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


OUTPUT_DIR = "out"
MAX_MATCH = 10

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)


# ----------------------------
# Google Drive Upload Helper
# ----------------------------
def upload_or_replace(drive, folder_id, path_file):
    filename = os.path.basename(path_file)

    results = drive.files().list(
        q=f"name='{filename}' and '{folder_id}' in parents and trashed=false",
        fields="files(id, name)"
    ).execute()

    items = results.get("files", [])

    if items:
        file_id = items[0]["id"]
        media = MediaFileUpload(path_file, resumable=True)
        drive.files().update(fileId=file_id, media_body=media).execute()
        print("Aggiornato:", filename)
    else:
        metadata = {"name": filename, "parents": [folder_id]}
        media = MediaFileUpload(path_file, resumable=True)
        drive.files().create(body=metadata, media_body=media, fields="id").execute()
        print("Caricato:", filename)


# ----------------------------
# SosFanta
# ----------------------------
async def estrai_sosfanta(page, drive, folder_id):
    print("=== SOSFANTA ===")

    await page.goto(
        "https://www.sosfanta.com/lista-formazioni/probabili-formazioni-serie-a/",
        wait_until="domcontentloaded",
        timeout=60000
    )

    # Cookie
    for sel in [
        "button:has-text('Accetta e continua')",
        "button:has-text('Accetta')",
        "text='Accetta'"
    ]:
        try:
            await page.locator(sel).first.click(timeout=1500)
            break
        except:
            pass

    # Attesa necessaria per layout SosFanta
    await page.wait_for_timeout(3500)

    # Riconoscimento blocchi partita
    divs = await page.query_selector_all("div[id]")

    ids = []
    for d in divs:
        did = await d.get_attribute("id")
        if did and re.match(r"^[A-Z]{3}-[A-Z]{3}(-\d+)?$", did):
            ids.append(did)

    print("Trovati:", ids)

    for idx, did in enumerate(ids[:MAX_MATCH], start=1):
        await page.evaluate(
            "id => document.getElementById(id).scrollIntoView({block:'center'})",
            did
        )
        await page.wait_for_timeout(400)

        raw = os.path.join(OUTPUT_DIR, f"_sos_{idx}.png")
        final = os.path.join(OUTPUT_DIR, f"sosfanta_{idx}.png")

        await page.locator(f"#{did}").screenshot(path=raw)

        img = Image.open(raw)
        w, h = img.size
        img.crop((120, 0, w - 120, h)).save(final)

        upload_or_replace(drive, folder_id, final)


# ----------------------------
# Fantacalcio
# ----------------------------
async def estrai_fantacalcio(page, drive, folder_id):
    print("=== FANTACALCIO ===")

    await page.goto(
        "https://www.fantacalcio.it/probabili-formazioni-serie-a",
        wait_until="domcontentloaded",
        timeout=60000
    )

    await page.wait_for_timeout(3000)

    cards = await page.query_selector_all("div[class*='probabili-formazioni__match-card']")

    print("Trovati:", len(cards))

    for idx, c in enumerate(cards[:MAX_MATCH], start=1):
        raw = os.path.join(OUTPUT_DIR, f"_fc_{idx}.png")
        final = os.path.join(OUTPUT_DIR, f"fantacalcio_{idx}.png")

        await c.scroll_into_view_if_needed()
        await page.wait_for_timeout(300)
        await c.screenshot(path=raw)

        upload_or_replace(drive, folder_id, raw)
        os.rename(raw, final)


# ----------------------------
# Gazzetta
# ----------------------------
async def estrai_gazzetta(page, drive, folder_id):
    print("=== GAZZETTA ===")

    await page.goto(
        "https://www.gazzetta.it/Calcio/probabili-formazioni-serie-a/",
        wait_until="domcontentloaded",
        timeout=60000
    )

    await page.wait_for_timeout(3000)

    cards = await page.query_selector_all("section.match-card")

    print("Trovati:", len(cards))

    for idx, c in enumerate(cards[:MAX_MATCH], start=1):
        raw = os.path.join(OUTPUT_DIR, f"_gaz_{idx}.png")
        final = os.path.join(OUTPUT_DIR, f"gazzetta_{idx}.png")

        await c.scroll_into_view_if_needed()
        await page.wait_for_timeout(300)
        await c.screenshot(path=raw)

        upload_or_replace(drive, folder_id, raw)
        os.rename(raw, final)


# ----------------------------
# MAIN
# ----------------------------
async def main():
    print("=== AVVIO SCRAPER ===")

    # Decodifica credenziali Drive
    creds_b64 = os.environ["GOOGLE_CREDENTIALS_B64"]
    decoded = base64.b64decode(creds_b64).decode("utf-8")

    with open("credentials.json", "w") as f:
        f.write(decoded)

    creds = service_account.Credentials.from_service_account_file(
        "credentials.json",
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    drive = build("drive", "v3", credentials=creds)

    folder_url = os.environ["DRIVE_FOLDER_URL"]
    folder_id = folder_url.split("/")[-1]

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--ignore-gpu-blocklist",
                "--window-size=1366,768"
            ]
        )

        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
            is_mobile=False,
            has_touch=False
        )

        page = await context.new_page()

        await estrai_sosfanta(page, drive, folder_id)
        await estrai_fantacalcio(page, drive, folder_id)
        await estrai_gazzetta(page, drive, folder_id)

        await browser.close()

    print("=== COMPLETATO ===")
