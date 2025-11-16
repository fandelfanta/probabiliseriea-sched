# -*- coding: utf-8 -*-
"""
Probabili - versione compatibile con GitHub Actions
"""

# ==========================================================
#  LIBRERIE
# ==========================================================
import asyncio, re, os, random, glob
import nest_asyncio

from google.auth import default
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import gspread
from playwright.async_api import async_playwright
from PIL import Image, ImageOps

# ==========================================================
#  CONFIG
# ==========================================================
SHEET_ID   = "1l8v3uDyzk1A9sMUwoV2L_rhOns-vJRV7iOTRfLK4ZvU"
SHEET_NAME = "Probabili"
DRIVE_FOLDER_ID = "1Oy6nEebc7hE0OOyD3DKnqb3PaGSLk2eO"
GIORNATA = 12
MAX_MATCH = 10

# ==========================================================
#  GOOGLE CONNECTION
# ==========================================================
SCOPES = ["https://www.googleapis.com/auth/drive",
          "https://www.googleapis.com/auth/spreadsheets"]

creds, _ = default(scopes=SCOPES)
drive_svc = build("drive", "v3", credentials=creds)
sheets_gc = gspread.authorize(creds)
ws = sheets_gc.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
nest_asyncio.apply()

# ==========================================================
#  UTIL
# ==========================================================
def drive_upload_or_replace(local_path, name):
    media = MediaFileUpload(local_path, mimetype="image/png", resumable=False)
    res = drive_svc.files().list(
        q=f"name='{name}' and '{DRIVE_FOLDER_ID}' in parents and trashed=false",
        fields="files(id)", supportsAllDrives=True
    ).execute()
    files = res.get("files", [])
    file_id = files[0]["id"] if files else None

    if file_id:
        drive_svc.files().update(
            fileId=file_id,
            media_body=media,
            keepRevisionForever=False,
            supportsAllDrives=True
        ).execute()
    else:
        meta = {"name": name, "parents": [DRIVE_FOLDER_ID], "mimeType": "image/png"}
        file_id = drive_svc.files().create(
            body=meta, media_body=media, fields="id", supportsAllDrives=True
        ).execute()["id"]

        drive_svc.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"},
            fields="id"
        ).execute()

    return f"https://drive.google.com/uc?id={file_id}"


def propaga_match_ad_altre_fonti():
    data = ws.get_all_values()
    if not data:
        print("ℹ️ Foglio vuoto, nessuna propagazione.")
        return

    header, rows = data[0], data[1:]
    col_fonte  = header.index("Fonte")
    col_match  = header.index("Match")

    ref = [r[col_match] for r in rows if r[col_fonte] == "Sos Fanta" and r[col_match]]

    if not ref:
        print("ℹ️ Nessun match SosFanta trovato.")
        return

    updates, current, idx = [], None, 0

    for i, r in enumerate(rows, start=2):
        fonte = r[col_fonte]

        if fonte != current:
            current, idx = fonte, 0

        if fonte != "Sos Fanta":
            if not r[col_match] or r[col_match].strip() == "":
                if idx < len(ref):
                    updates.append({"range": f"D{i}", "values": [[ref[idx]]]})
                idx += 1
            else:
                idx += 1

    if updates:
        ws.batch_update(updates)
        print(f"🟢 Propagati {len(updates)} match.")
    else:
        print("ℹ️ Nessun match da propagare.")

# ==========================================================
#  BLOCCO PRIVACY
# ==========================================================
async def block_privacy_requests(route):
    url = route.request.url.lower()
    if any(x in url for x in [
        "privacy", "cookie", "consent", "cmp", "rcs", "quantcast"
    ]):
        await route.abort()
    else:
        await route.continue_()

# ==========================================================
#  FONTE 1 — SOSFANTA
# ==========================================================
async def estrai_screenshots_sosfanta():
    FONTE = "Sos Fanta"
    URL = "https://www.sosfanta.com/lista-formazioni/probabili-formazioni-serie-a/"
    rows = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width":1600,"height":4000})
        page = await context.new_page()

        await page.goto(URL, timeout=60000)
        await page.wait_for_timeout(800)

        # Chiudi cookie
        for sel in [
            "button:has-text('Accetta e continua')",
            "button:has-text('Accetta')"
        ]:
            try:
                await page.locator(sel).first.click(timeout=2000)
                break
            except:
                pass

        # Rileva partite
        ids = []
        for el in await page.query_selector_all("div[id]"):
            _id = await el.get_attribute("id")
            if _id and re.match(r"^[A-Z]{3}-[A-Z]{3}", _id):
                ids.append(_id)

        ids = ids[:MAX_MATCH]
        print(f"🔎 SosFanta: {len(ids)} partite trovate")

        for idx, dom_id in enumerate(ids, start=1):
            try:
                container = await page.query_selector(f"div#{dom_id}")
                raw_path = f"/tmp/raw_sos_{idx}.png"
                final_path = f"/tmp/sosfanta_{idx}.png"

                await container.screenshot(path=raw_path)

                img = Image.open(raw_path)
                w, h = img.size
                cropped = img.crop((120, 0, w - 120, h))
                cropped.save(final_path)

                a,b,_ = dom_id.split("-")
                if a == "HEL": a="VER"
                if b == "HEL": b="VER"

                match_txt = f"{a} - {b}"
                link = drive_upload_or_replace(final_path, f"sosfanta_{idx}.png")

                rows.append([FONTE, GIORNATA, idx, match_txt, link])
                print(f"✅ SosFanta → partita {idx}")

            except Exception as e:
                print(f"⚠️ SosFanta errore {dom_id}: {e}")

        await browser.close()

        if rows:
            ws.update(f"A2:E{1+len(rows)}", rows)
            print("🟢 Foglio aggiornato (SosFanta)")

# ==========================================================
#  FONTE 2 — FANTACALCIO
# ==========================================================
async def estrai_screenshots_fantacalcio():
    FONTE = "Fantacalcio"
    URL = "https://www.fantacalcio.it/probabili-formazioni-serie-a"
    rows = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage"]
        )
        context = await browser.new_context(viewport={"width":1600,"height":4000})
        page = await context.new_page()

        await page.goto(URL, timeout=60000)
        await page.wait_for_timeout(1500)

        matches = await page.query_selector_all("li.match.match-item")
        print(f"🔎 Fantacalcio: {len(matches)} partite trovate")

        for idx, match in enumerate(matches, start=1):
            try:
                blockA = await match.query_selector("div.row.col-sm")
                blockB = await match.query_selector("section.mt-4.match-graphs.burn")

                imgs = []
                if blockA:
                    pA="/tmp/fcA.png"; await blockA.screenshot(path=pA); imgs.append(Image.open(pA))
                if blockB:
                    pB="/tmp/fcB.png"; await blockB.screenshot(path=pB); imgs.append(Image.open(pB))

                if not imgs:
                    continue

                widths=[i.width for i in imgs]; heights=[i.height for i in imgs]
                final_w=max(widths); final_h=sum(heights)

                final=Image.new("RGB",(final_w,final_h),"white")
                y=0
                for im in imgs: final.paste(im,(0,y)); y+=im.height

                final_path=f"/tmp/fantacalcio_{idx}.png"
                final.save(final_path)

                link = drive_upload_or_replace(final_path,f"fantacalcio_{idx}.png")
                rows.append([FONTE,GIORNATA,idx,f"Partita {idx}",link])

                print(f"✅ Fantacalcio → partita {idx}")

            except Exception as e:
                print(f"⚠️ Errore Fantacalcio {idx}: {e}")

        if rows:
            all_vals = ws.get_all_values()
            start = next(i for i,r in enumerate(all_vals,start=1) if i>1 and r[0]=="Fantacalcio")
            ws.update(f"A{start}:E{start+len(rows)-1}", rows)
            print("🟢 Foglio aggiornato (Fantacalcio)")

        await browser.close()

# ==========================================================
#  FONTE 3 — GAZZETTA
# ==========================================================
async def estrai_screenshots_gazzetta():
    FONTE="Gazzetta"
    URL="https://www.gazzetta.it/Calcio/prob_form/"
    START_ROW=12

    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=["--no-sandbox"])
        context=await browser.new_context(viewport={"width":1600,"height":4000})
        await context.route("**/*", block_privacy_requests)
        page=await context.new_page()

        await page.goto(URL,timeout=60000)
        await page.wait_for_timeout(1500)

        matches=await page.query_selector_all(".bck-box-match-details")
        print(f"🔎 Gazzetta: {len(matches)} partite trovate")

        success=0

        for idx, box in enumerate(matches[:MAX_MATCH], start=1):
            try:
                lineup = await box.query_selector(".match-details__lineup")
                notes  = await box.query_selector(".match-details__notes")

                lineup_path=f"/tmp/gaz_l_{idx}.png"
                notes_path=f"/tmp/gaz_n_{idx}.png"

                if lineup:
                    await lineup.screenshot(path=lineup_path)

                if notes:
                    await notes.screenshot(path=notes_path)

                imgs = [Image.open(p) for p in [lineup_path, notes_path] if os.path.exists(p)]
                if not imgs:
                    continue

                final_w = max(i.width for i in imgs)
                final_h = sum(i.height for i in imgs)
                final = Image.new("RGB", (final_w, final_h), (253,233,235))

                y=0
                for im in imgs:
                    final.paste(im,(0,y))
                    y+=im.height

                final_path=f"/tmp/gazzetta_{idx}.png"
                final.save(final_path)

                link = drive_upload_or_replace(final_path,f"gazzetta_{idx}.png")
                ws.update(f"E{START_ROW+idx-1}", [[link]])

                success+=1
                print(f"✅ Gazzetta → partita {idx}")

            except Exception as e:
                print(f"⚠️ Errore Gazzetta {idx}: {e}")

        print(f"🟢 Foglio aggiornato (Gazzetta): {success} righe")
        await browser.close()

# ==========================================================
#  MANAGER — ESECUZIONE IN SEQUENZA
# ==========================================================
async def aggiorna_tutte_le_fonti():
    print("▶️ Avvio SosFanta...")
    await estrai_screenshots_sosfanta()

    print("▶️ Avvio Fantacalcio...")
    await estrai_screenshots_fantacalcio()

    print("▶️ Avvio Gazzetta...")
    await estrai_screenshots_gazzetta()

    print("▶️ Propagazione Match...")
    propaga_match_ad_altre_fonti()

    print("🟢 COMPLETATO TUTTO")

# ==========================================================
#  START
# ==========================================================
if __name__ == "__main__":
    asyncio.run(aggiorna_tutte_le_fonti())
