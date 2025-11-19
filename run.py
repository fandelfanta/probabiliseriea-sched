# ==========================================================
#  ✅ SCREENSHOT BOT MULTIFONTE ADATTATO PER GITHUB ACTIONS
#  Obiettivo: Drive ON, Sheets OFF (Service Account B64) - FIX SOS FANTA + LOG PULITI
# ==========================================================

# --- LIBRERIE ---
import asyncio, re, os, glob, json, base64
import nest_asyncio
from playwright.async_api import async_playwright
from PIL import Image, ImageOps 

# Importazioni per Google Drive
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ==========================================================
#  CONFIG
# ==========================================================
# ID della cartella Drive per il salvataggio (Recuperato dal tuo script originale)
DRIVE_FOLDER_ID = "1Oy6nEebc7hE0OOyD3DKnqb3PaGSLk2eO" 
MAX_MATCH = 10
GIORNATA = 12
START_ROW_GAZZETTA = 12 

# ==========================================================
#  AUTENTICAZIONE E SERVIZI (ADATTATA PER SECRET B64)
# ==========================================================

SCOPES = ["https://www.googleapis.com/auth/drive"] 
drive_svc = None

def init_google_drive():
    """Autentica con la chiave JSON del Service Account decodificata dal Secret."""
    global drive_svc
    
    # Legge il Secret B64 da GitHub
    b64_key = os.environ.get("GOOGLE_CREDENTIALS_B64")
    if not b64_key:
        print("🛑 ERRORE: La variabile d'ambiente GOOGLE_CREDENTIALS_B64 non è impostata.")
        return None

    try:
        # Decodifica Base64 e carica il JSON
        json_key = base64.b64decode(b64_key).decode('utf-8')
        creds_info = json.loads(json_key)
        
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        
        drive_svc = build("drive", "v3", credentials=creds)
        print("✅ Autenticazione Google Drive (Service Account) riuscita.")
        return drive_svc
    except Exception as e:
        print(f"🛑 ERRORE di Autenticazione Drive: {e}")
        return None

init_google_drive()
nest_asyncio.apply()


# ==========================================================
#  FUNZIONE DRIVE
# ==========================================================
def drive_upload_or_replace(local_path, name):
    """Carica o sostituisce un file su Google Drive."""
    global drive_svc
    if not drive_svc:
        print("⚠️ Drive Service non disponibile. Salto l'upload.")
        return "UPLOAD_FAILED"
        
    try:
        media = MediaFileUpload(local_path, mimetype="image/png", resumable=False)
        res = drive_svc.files().list(
            q=f"name='{name}' and '{DRIVE_FOLDER_ID}' in parents and trashed=false",
            fields="files(id)", supportsAllDrives=True
        ).execute()
        files = res.get("files", [])
        file_id = files[0]["id"] if files else None
        
        if file_id:
            # Aggiorna
            drive_svc.files().update(
                fileId=file_id, media_body=media,
                keepRevisionForever=False, supportsAllDrives=True
            ).execute()
            status = "⬆️ File aggiornato"
        else:
            # Carica
            meta = {"name": name, "parents": [DRIVE_FOLDER_ID], "mimeType": "image/png"}
            file = drive_svc.files().create(
                body=meta, media_body=media, fields="id, webViewLink", supportsAllDrives=True
            ).execute()
            file_id = file["id"]
            # Condivisione pubblica
            drive_svc.permissions().create(
                fileId=file_id, 
                body={"role": "reader", "type": "anyone"}, fields="id"
            ).execute()
            status = "➕ File caricato"

        link = f"https://drive.google.com/uc?id={file_id}"
        print(f"{status}: {name} → {link}") # Log unificato e pulito
        return link
    
    except Exception as e:
        print(f"🛑 ERRORE durante l'upload di {name}: {e}")
        return "UPLOAD_FAILED"


# ==========================================================
#  FONTE 1: SosFanta (FIXATO per 0 partite)
# ==========================================================
async def estrai_screenshots_sosfanta():
    FONTE = "Sos Fanta"
    URL = "https://www.sosfanta.com/lista-formazioni/probabili-formazioni-serie-a/"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=["--no-sandbox", "--disable-dev-shm-usage", "--headless=new"]
        )
        context = await browser.new_context(viewport={"width":1600,"height":4000})
        page = await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # COOKIE (Reso più robusto)
        for sel in [
            "button:has-text('Accetta e continua')", "button:has-text('Accetta')", "text='ACCETTA E CONTINUA'"
        ]:
            try:
                await page.locator(sel).first.click(timeout=3000, force=True)
                await page.wait_for_timeout(700)
                break
            except:
                pass

        # Mostra tutte le partite (FIX CRITICO per 0 partite)
        try:
            selector_all = ".scheduled-matches__list .match-cell[match='ALL']"
            
            # Attende che il pulsante sia cliccabile
            btn = await page.wait_for_selector(selector_all, timeout=15000)

            if btn:
                # Clicca con forza e scrolla
                await page.evaluate("el => el.scrollIntoView({block:'center'})", btn)
                await btn.click(force=True)
                print("✅ SosFanta: Cliccato su 'Mostra tutte le partite'.")

                # Attende l'apparizione di un match (con ID index 0) come conferma
                await page.wait_for_selector("div[id*='-0']", timeout=15000) 
                await asyncio.sleep(1.5) # Attesa extra per il rendering

        except Exception as e:
            print(f"⚠️ SosFanta errore nel cliccare 'Mostra tutte le partite': {e}")
            pass

        # Scroll per caricare (mantenuto)
        for box in await page.query_selector_all("div[id]"):
            _id = await box.get_attribute("id")
            if not _id or not re.match(r"^[A-Z]{3}-[A-Z]{3}(-\d+)?$", _id):
                continue
            await page.evaluate("el => el.scrollIntoView({block:'center'})", box)
            await asyncio.sleep(1.2)

        # Legge ID partite
        ids = []
        for el in await page.query_selector_all("div[id]"):
            _id = (await el.get_attribute("id")) or ""
            if re.match(r"^[A-Z]{3}-[A-Z]{3}(-\d+)?$", _id):
                ids.append(_id)

        ids = ids[:MAX_MATCH]
        print(f"🔎 SosFanta: trovate {len(ids)} partite → {ids}")

        # LOOP PARTITE
        for idx, dom_id in enumerate(ids, start=1):
            a, b, _ = dom_id.split("-")
            if a == "HEL": a = "VER"
            if b == "HEL": b = "VER"
            match_txt = f"{a} - {b}"

            # CORREZIONE PATHING: Uso percorsi relativi
            filename = f"sosfanta_{idx}.png"
            raw_path = f"raw_{filename}"    
            final_path = f"{filename}"      

            try:
                # Esecuzione logica JS (rimozione header, reset layout note...)
                await page.evaluate(f"""
                    dom_id => {{
                        const box = document.getElementById(dom_id);
                        if (!box) return;
                        box.classList.remove('is-hidden');
                        box.style.display='block';
                        box.style.opacity=1;
                        const heads = box.querySelectorAll('.bck-gn-match-formation-teams');
                        heads.forEach(h => h.remove());

                        // Reset totale layout note (la parte lunga per il fix)
                        const notes = box.querySelector('.bck-gn-match-formation-teams-notes');
                        if (notes) {{
                            const labels = [...notes.querySelectorAll('.note-label')];
                            const indis = labels.find(el => el.textContent.trim().toLowerCase() === "indisponibili");
                            if (indis) {{
                                const container = indis.parentElement;
                                const columns = container.querySelector(".columns");
                                if (columns) {{
                                    container.style.display = "flex";
                                    container.style.flexDirection = "column";
                                    container.style.alignItems = "center";
                                    columns.className = "";
                                    columns.style.cssText = "display: flex; flex-direction: column; align-items: center; justify-content: center; width: 100%; max-width: 600px; margin: 0 auto; gap: 10px;";
                                    columns.querySelectorAll('.note-team').forEach(t => {{
                                        t.style.cssText = "text-align: center; margin: 0 auto; float: none; width: 100%; display: block;";
                                        t.classList.remove("has-text-right", "is-pulled-right", "has-text-left");
                                    }});
                                    columns.querySelectorAll('[class*="column"]').forEach(col => {{
                                        col.className = "";
                                        col.style.cssText = "margin: 0 auto; padding: 0; text-align: center; display: block; width: 100%;";
                                    }});
                                }}
                            }}
                        }}
                    }}
                """, dom_id)


                # Scroll su box
                await page.evaluate(
                    "dom_id => document.getElementById(dom_id).scrollIntoView({block:'center'})",
                    dom_id
                )
                await page.wait_for_timeout(800)

                # ---- SCREENSHOT RAW e CROP LATERALE 120px ----
                container = await page.query_selector(f"div#{dom_id}")
                await container.screenshot(path=raw_path)

                from PIL import Image
                img = Image.open(raw_path)
                w, h = img.size
                cropped = img.crop((120, 0, w - 120, h))
                cropped.save(final_path)

                # --- Upload su Drive ---
                drive_upload_or_replace(final_path, filename)
                print(f"✅ SosFanta | {match_txt} → {filename} (Salvato su Drive)") # Log modificato

            except Exception as e:
                print(f"⚠️ SosFanta errore su {match_txt}: {e}")

        await context.close()
        await browser.close()
    


# ==========================================================
#  FONTE 2: Fantacalcio
# ==========================================================
async def estrai_screenshots_fantacalcio():
    FONTE = "Fantacalcio"
    URL = "https://www.fantacalcio.it/probabili-formazioni-serie-a"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=["--no-sandbox", "--disable-dev-shm-usage", "--headless=new"]
        )
        context = await browser.new_context(viewport={"width":1600,"height":4000})
        page = await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # cookie/privacy
        for sel in ["button:has-text('Accetta')", "button:has-text('Accetta e continua')", "text='CONFIRM'", "button:has-text('Confirm')"]:
            try:
                await page.locator(sel).first.click(timeout=2500, force=True)
                await page.wait_for_timeout(600)
                break
            except: pass
        await page.evaluate("""
            () => {
                document.documentElement.style.overflow='auto';
                document.body.style.overflow='auto';
                document.querySelectorAll('[role="dialog"], .fc-consent-root, .modal, .popup').forEach(e=>e.remove());
            }
        """)

        matches = await page.query_selector_all("li.match.match-item")
        print(f"🔎 Fantacalcio: trovate {len(matches)} partite")

        for idx, match in enumerate(matches[:MAX_MATCH], start=1):
            try:
                await match.scroll_into_view_if_needed()
                await page.wait_for_timeout(700)
                
                team_names = await match.query_selector_all("h3.h6.team-name")
                if len(team_names) >= 2:
                    home = (await team_names[0].inner_text()).strip()[:3].upper()
                    away = (await team_names[1].inner_text()).strip()[:3].upper()
                    if home == "HEL": home = "VER"
                    if away == "HEL": away = "VER"
                    match_txt = f"{home} - {away}"
                else:
                    match_txt = f"Match {idx}"

                filename = f"fantacalcio_{idx}.png"
                path = f"{filename}"

                await match.screenshot(path=path)
                drive_upload_or_replace(path, filename)
                print(f"✅ Fantacalcio | {match_txt} → {filename} (Salvato su Drive)") # Log modificato

            except Exception as e:
                print(f"⚠️ Errore su match {idx}: {e}")

        await context.close(); await browser.close()


# ==========================================================
#  FONTE 3: Gazzetta.it — versione stabile 9:16 optimized (Log puliti)
# ==========================================================
# Blocca richieste privacy (mantenuto)
async def block_privacy_requests(route):
    url = route.request.url
    if any(x in url for x in [
        "privacy.rcs.it", "sp-prod.net", "consent.cookiebot.com", "cdn.privacy-mgmt.com"
    ]):
        await route.abort()
    else:
        await route.continue_()

async def estrai_screenshots_gazzetta():
    FONTE = "Gazzetta"
    URL = "https://www.gazzetta.it/Calcio/prob_form/"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=["--no-sandbox", "--disable-dev-shm-usage", "--headless=new"]
        )
        context = await browser.new_context(viewport={"width": 1600, "height": 4000})
        await context.route("**/*", block_privacy_requests)
        page = await context.new_page()

        # --- 1️⃣ Caricamento pagina ---
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        print("🌐 Pagina Gazzetta caricata.")

        # --- 2️⃣ Gestione banner cookie ---
        try:
            await page.wait_for_selector("button:has-text('ACCETTA E CONTINUA')", timeout=6000)
            await page.locator("button:has-text('ACCETTA E CONTINUA')").click(force=True)
            print("✅ Banner cookie chiuso correttamente.")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1200)
        except:
            print("ℹ️ Nessun banner cookie rilevato (o già bloccato).")

        # --- 3️⃣ Pulizia overlay privacy/consent ---
        try:
            await page.wait_for_load_state("networkidle")
            await page.evaluate("""
                () => {
                    const patterns = ['sp_message','qc-cmp','cmp','consent','privacy'];
                    document.querySelectorAll('iframe,[role="dialog"],div').forEach(el=>{
                        const html=(el.outerHTML||'').toLowerCase();
                        if (patterns.some(k=>html.includes(k))) el.remove();
                    });
                    if (document.body) document.body.style.overflow='auto';
                    if (document.documentElement) document.documentElement.style.overflow='auto';
                }
            """)
        except Exception as e:
            # Stampiamo solo l'errore per il debug interno, non è un problema critico di scraping
            print(f"⚠️ Pulizia DOM saltata (context unstable): {e}")

        # --- 4️⃣ Selezione dei box partita ---
        await page.wait_for_selector(".bck-box-match-details", timeout=25000)
        matches = await page.query_selector_all(".bck-box-match-details")
        print(f"🔎 Gazzetta: trovate {len(matches)} partite.") # Log pulito qui

        # --- 5️⃣ Loop sulle partite ---
        for idx, match_box in enumerate(matches[:MAX_MATCH], start=1):
            try:
                dom_id = await match_box.get_attribute("id") or f"match_{idx}"

                await match_box.scroll_into_view_if_needed()
                await page.wait_for_timeout(1500)

                lineup = await page.query_selector(f"#{dom_id} .match-details__lineup")
                notes = await page.query_selector(f"#{dom_id} .match-details__notes")

                if not lineup and not notes: continue

                # Rimuove prime due righe e allarga notes (JS)
                if notes:
                    await page.evaluate(f"(sel) => {{ const el = document.querySelector(sel); if (!el) return; el.querySelectorAll('.match-details__note-row, .match-details_note-row').forEach((r, i) => {{ if (i < 2) r.remove(); }}); }}", f"#{dom_id} .match-details__notes")
                    await page.evaluate(f"(sel) => {{ const el = document.querySelector(sel); if (el) {{ el.style.cssText = 'width: 100%; max-width: 100%; margin: 0; padding: 0;'; }} }}", f"#{dom_id} .match-details__notes")

                # --- Screenshot RAW ---
                lineup_path = None
                if lineup:
                    lineup_path = f"gazzetta_{idx}_lineup.png"
                    await lineup.screenshot(path=lineup_path)

                notes_path = None
                if notes:
                    notes_path = f"gazzetta_{idx}_notes.png"
                    await notes.screenshot(path=notes_path)

                # --- Unione Immagini (PIL) ---
                images = [Image.open(p) for p in [lineup_path, notes_path] if p and os.path.exists(p)]
                if not images: continue

                # Logica complessa di Unione Immagini e PIL (mantenuta intatta)
                lineup_img = images[0]
                notes_img  = images[1] if len(images) == 2 else None
                rosa = (253, 233, 235)
                
                # 1. TAGLIO LINEUP
                cut_left, cut_right = 175, 175
                if lineup_img.width > cut_left + cut_right:
                    lineup_img = lineup_img.crop((cut_left, 0, lineup_img.width - cut_right, lineup_img.height))
                base_width = lineup_img.width
                
                # 2. TROVA COLONNA DI SEPARAZIONE NOTE (omesso per brevità, codice mantenuto)
                if notes_img:
                    w, h = notes_img.width, notes_img.height
                    notes_pixels = notes_img.load()
                    best_col = w // 2 # Fallback
                    min_dark = 999999
                    
                    for offset in range(-7, 8):
                        x = w // 2 + offset
                        dark = sum(1 for y in range(0, h, 6) if sum(notes_pixels[x, y]) < 690)
                        if dark < min_dark:
                            min_dark, best_col = dark, x
                            
                    notes_left = notes_img.crop((0, 0, best_col, h))
                    notes_right = notes_img.crop((best_col, 0, w, h))

                    # 3. RIDUZIONE NOTES
                    scale_notes = 0.88
                    new_width = int(base_width * scale_notes)
                    def resize_ratio(im, target_w):
                        ratio = target_w / im.width
                        new_h = int(im.height * ratio)
                        return im.resize((target_w, new_h), resample=Image.LANCZOS)

                    notes_left, notes_right = resize_ratio(notes_left, new_width), resize_ratio(notes_right, new_width)

                    # 4. UNIONE NOTE IN COLONNA
                    sep_height, sep_margin = 4, 10
                    separator_full = Image.new("RGB", (new_width, sep_height + sep_margin * 2), rosa)
                    separator_line = Image.new("RGB", (new_width, sep_height), (210, 190, 190))
                    separator_full.paste(separator_line, (0, sep_margin))
                    
                    notes_column_height = notes_left.height + separator_full.height + notes_right.height
                    notes_column = Image.new("RGB", (new_width, notes_column_height), rosa)
                    y = 0
                    notes_column.paste(notes_left, (0, y)); y += notes_left.height
                    notes_column.paste(separator_full, (0, y)); y += separator_full.height
                    notes_column.paste(notes_right, (0, y))
                    
                    # 5. CENTRA NOTES
                    delta = (base_width - new_width) // 2
                    notes_img = ImageOps.expand(notes_column, border=(delta, 0, base_width - new_width - delta, 0), fill=rosa)
                else:
                    notes_img = None
                    
                # 6. COMBINA LINEUP + GAP + NOTES
                gap = 30
                gap_block = Image.new("RGB", (base_width, gap), rosa)
                total_height = lineup_img.height + (gap + notes_img.height if notes_img else 0)
                combined = Image.new("RGB", (base_width, total_height), rosa)

                y = 0
                combined.paste(lineup_img, (0, y))
                if notes_img:
                    y += lineup_img.height
                    combined.paste(gap_block, (0, y)); y += gap
                    combined.paste(notes_img, (0, y))

                # 7. PADDING FINALE
                combined = ImageOps.expand(combined, border=(20, 40, 20, 40), fill=rosa)

                combined_path = f"gazzetta_{idx}.png"
                combined.save(combined_path)

                # --- Upload su Drive (Log pulito) ---
                drive_upload_or_replace(combined_path, f"gazzetta_{idx}.png")
                print(f"✅ Gazzetta | Partita {idx} → gazzetta_{idx}.png (Salvato su Drive)") # Log modificato

            except Exception as e:
                print(f"⚠️ Errore su match {idx}: {e}")

        await context.close()
        await browser.close()
        print("🟢 Operazione completata.")


# ==========================================================
#  MANAGER
# ==========================================================
async def aggiorna_tutte_le_fonti():
    await estrai_screenshots_sosfanta()
    await estrai_screenshots_fantacalcio()
    await estrai_screenshots_gazzetta()

# ==========================================================
#  ESECUZIONE PRINCIPALE
# ==========================================================
if __name__ == "__main__":
    print("=== AVVIO SCRAPER ===")
    asyncio.run(aggiorna_tutte_le_fonti()) 
    print("=== SCRAPER COMPLETATO ===")
