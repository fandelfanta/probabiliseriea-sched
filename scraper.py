import os
import re
import nest_asyncio
nest_asyncio.apply()

from PIL import Image
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from playwright.async_api import async_playwright

OUTPUT_DIR = "out"
MAX_MATCH = 10

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)


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
        file_metadata = {"name": filename, "parents": [folder_id]}
        media = MediaFileUpload(path_file, resumable=True)
        drive.files().create(body=file_metadata, media_body=media, fields="id").execute()
        print("Caricato:", filename)


async def estrai_sosfanta(drive, folder_id):
    print("\n=== SOSFANTA ===")

    url = "https://www.sosfanta.com/lista-formazioni/probabili-formazioni-serie-a/"

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
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # accetta cookie se presenti
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

        # SosFanta carica dinamicamente, serve attesa secca
        await page.wait_for_timeout(3500)

        # Nessuna attesa su selector: prende tutto e filtra
        divs = await page.query_selector_all("div[id]")
        ids = []

        for d in divs:
            did = await d.get_attribute("id")
            if did and re.match(r"^[A-Z]{3}-[A-Z]{3}(-\d+)?$", did):
                ids.append(did)

        print("Partite trovate:", ids)

        for idx, did in enumerate(ids[:MAX_MATCH], start=1):
            await page.evaluate(
                "id => document.getElementById(id).scrollIntoView({block:'center'})",
                did
            )
            await page.wait_for_timeout(500)

            raw = os.path.join(OUTPUT_DIR, f"_sos_{idx}.png")
            final = os.path.join(OUTPUT_DIR, f"sosfanta_{idx}.png")

            await page.locator(f"#{did}").screenshot(path=raw)

            img = Image.open(raw)
            w, h = img.size
            img.crop((120, 0, w - 120, h)).save(final)

            upload_or_replace(drive, folder_id, final)

        await browser.close()


async def main():
    print("=== AVVIO ===")

    creds_json = os.environ["GOOGLE_CREDENTIALS_B64"]
    creds_bytes = creds_json.encode("utf-8")
    import base64
    decoded = base64.b64decode(creds_bytes).decode("utf-8")

    with open("credentials.json", "w") as f:
        f.write(decoded)

    creds = service_account.Credentials.from_service_account_file(
        "credentials.json",
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    drive = build("drive", "v3", credentials=creds)

    folder_url = os.environ["DRIVE_FOLDER_URL"]
    folder_id = folder_url.split("/")[-1]

    await estrai_sosfanta(drive, folder_id)

    print("=== FATTO ===")
