# ==========================================================
#  ✅ SCREENSHOT BOT MULTIFONTE ADATTATO PER GITHUB ACTIONS
#  NOTE: Rimossa tutta la logica di Google Drive/Sheets.
# ==========================================================

# --- CONFIGURAZIONE E LIBRERIE ---
import asyncio, re, os, random, glob
import nest_asyncio
from playwright.async_api import async_playwright
from PIL import Image, ImageOps # Necessita di Pillow

# Le chiamate !pip install e !playwright install (linee 1-8) vanno rimosse, 
# saranno gestite dal workflow YAML e dal requirements.txt.
# Le importazioni di google.colab (linee 23-30) sono state rimosse.

# ==========================================================
#  CONFIG
# ==========================================================
# Le seguenti variabili non sono più usate ma mantenute per struttura:
# SHEET_ID   = "..." 
# SHEET_NAME = "Probabili"
# DRIVE_FOLDER_ID = "..." 
GIORNATA = 12
MAX_MATCH = 10

# ==========================================================
#  FUNZIONI GOOGLE (Rimosse o modificate)
# ==========================================================

# La funzione drive_upload_or_replace (linee 40-62) è stata RIMOSSA.
# I file saranno salvati nella cartella locale del runner di GitHub.

# La funzione propaga_match_ad_altre_fonti (linee 64-84) è stata RIMOSSA.

# La connessione a gspread e drive_svc (linee 32-37) è stata RIMOSSA.
# nest_asyncio.apply() è mantenuto se necessario per il tuo ambiente.
nest_asyncio.apply()


# ==========================================================
#  UTIL (Blocco richieste privacy - mantenuto)
# ==========================================================
async def block_privacy_requests(route):
    url = route.request.url
    if any(x in url for x in [
        "privacy.rcs.it", "sp-prod.net", "consent.cookiebot.com", "cdn.privacy-mgmt.com"
    ]):
        await route.abort()
    else:
        await route.continue_()


# ==========================================================
#  FONTE 1: SosFanta (Aggiornato per GitHub Actions)
# ==========================================================
async def estrai_screenshots_sosfanta():
    FONTE = "Sos Fanta"
    URL = "https://www.sosfanta.com/lista-formazioni/probabili-formazioni-serie-a/"
    # Rimosso: rows = [] e tutta la logica di Google Sheets

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            # AGGIUNTO: "--headless=new" per compatibilità CI/CD
            args=["--no-sandbox", "--disable-dev-shm-usage", "--headless=new"]
        )
        context = await browser.new_context(viewport={"width":1600,"height":4000})
        page = await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # COOKIE (Mantenuto e reso più robusto con force=True)
        for sel in [
            "button:has-text('Accetta e continua')",
            "button:has-text('Accetta')",
            "text='ACCETTA E CONTINUA'"
        ]:
            try:
                # Usiamo force=True per cliccare anche se coperto da un overlay
                await page.locator(sel).first.click(timeout=3000, force=True)
                await page.wait_for_timeout(700)
                break
            except:
                pass

        # Mostra tutte le partite (FIX PER 0 PARTITE)
        try:
            selector_all = ".scheduled-matches__list .match-cell[match='ALL']"
            
            # 1. Attendiamo che il pulsante 'ALL' sia nel DOM
            btn = await page.wait_for_selector(selector_all, timeout=10000)

            if btn:
                # 2. Clicchiamo con forza (force=True) per superare problemi di visibilità
                await btn.click(force=True)
                print("✅ SosFanta: Cliccato su 'Mostra tutte le partite'.")

                # 3. Attendiamo l'apparizione del primo match ID come conferma (es. CAG-GEN-0)
                # Questo è cruciale per assicurare che il DOM si sia aggiornato
                await page.wait_for_selector("div[id*='-0']", timeout=15000) 
                await asyncio.sleep(1.5) # Attesa extra per il rendering

        except Exception as e:
            print(f"⚠️ SosFanta errore nel cliccare 'Mostra tutte le partite': {e}")
            pass # Continuiamo l'esecuzione per vedere cosa trova

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
            raw_path = f"raw_{filename}" # Rimosso /content/
            final_path = f"{filename}"   # Rimosso /content/

            try:
                # Rimuove header (Logica JS Mantenuta)
                await page.evaluate("""
                    dom_id => {
                        const box = document.getElementById(dom_id);
                        if (!box) return;

                        box.classList.remove('is-hidden');
                        box.style.display='block';
                        box.style.opacity=1;

                        const heads = box.querySelectorAll('.bck-gn-match-formation-teams');
                        heads.forEach(h => h.remove());
                    }
                """, dom_id)

                # Reset layout note (Logica JS Mantenuta)
                await page.evaluate("""
                    dom_id => {
                        const box = document.getElementById(dom_id);
                        if (!box) return;

                        const notes = box.querySelector('.bck-gn-match-formation-teams-notes');
                        if (!notes) return;

                        const labels = [...notes.querySelectorAll('.note-label')];
                        const indis = labels.find(el => el.textContent.trim().toLowerCase() === "indisponibili");
                        if (!indis) return;

                        const container = indis.parentElement;
                        const columns = container.querySelector(".columns");
                        if (!columns) return;

                        // Reset totale layout
                        container.style.display = "flex";
                        container.style.flexDirection = "column";
                        container.style.alignItems = "center";
                        container.style.width = "100%";
                        container.style.textAlign = "center";

                        columns.style.display = "flex";
                        columns.style.flexDirection = "column";
                        columns.style.alignItems = "center";
                        columns.style.justifyContent = "center";
                        columns.style.width = "100%";
                        columns.style.maxWidth = "600px";
                        columns.style.margin = "0 auto";
                        columns.style.gap = "10px";
                        columns.className = "";
                        
                        const teams = columns.querySelectorAll('.note-team');
                        teams.forEach(t => {
                            t.style.textAlign = "center";
                            t.style.margin = "0 auto";
                            t.style.float = "none";
                            t.style.width = "100%";
                            t.style.display = "block";

                            // Rimuove classi che Bulma applica sui testi
                            t.classList.remove("has-text-right");
                            t.classList.remove("is-pulled-right");
                            t.classList.remove("has-text-left");
                        });
                        
                        columns.querySelectorAll('[class*="column"]').forEach(col => {
                            col.className = "";
                            col.style.margin = "0 auto";
                            col.style.padding = "0";
                            col.style.textAlign = "center";
                            col.style.display = "block";
                            col.style.width = "100%";
                        });
                    }
                """, dom_id)

                # Scroll su box
                await page.evaluate(
                    "dom_id => document.getElementById(dom_id).scrollIntoView({block:'center'})",
                    dom_id
                )
                await page.wait_for_timeout(800)

                # ---- SCREENSHOT RAW ----
                container = await page.query_selector(f"div#{dom_id}")
                await container.screenshot(path=raw_path)

                # ---- CROP LATERALE 120px ----
                from PIL import Image
                img = Image.open(raw_path)
                w, h = img.size
                cropped = img.crop((120, 0, w - 120, h))
                cropped.save(final_path)

                # Rimosso: Upload a Drive e Aggiornamento Foglio
                print(f"✅ SosFanta | {match_txt} → {filename} (Salvato localmente)")

            except Exception as e:
                print(f"⚠️ SosFanta errore su {match_txt}: {e}")

        await context.close()
        await browser.close()

    # Rimosso l'aggiornamento finale del foglio

# ==========================================================
#  FONTE 2: Fantacalcio (Aggiornato)
# ==========================================================
async def estrai_screenshots_fantacalcio():
    FONTE = "Fantacalcio"
    URL = "https://www.fantacalcio.it/probabili-formazioni-serie-a"
    # La lista rows e l'uso di ws.update sono stati rimossi.

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=["--no-sandbox", "--disable-dev-shm-usage", "--headless=new"] # Aggiunto "--headless=new"
        )
        context = await browser.new_context(viewport={"width":1600,"height":4000})
        page = await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # cookie/privacy (linee 279-286)
        for sel in ["button:has-text('Accetta')", "button:has-text('Accetta e continua')", "text='CONFIRM'", "button:has-text('Confirm')"]:
            try:
                await page.locator(sel).first.click(timeout=2500)
                await page.wait_for_timeout(600)
                break
            except: pass
            
        # Pulizia DOM (linee 287-292)
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
                
                # ... (Logica Nomi Squadre Mantenuta) ...
                team_names = await match.query_selector_all("h3.h6.team-name")
                if len(team_names) >= 2:
                    home = (await team_names[0].inner_text()).strip()[:3].upper()
                    away = (await team_names[1].inner_text()).strip()[:3].upper()
                    if home == "HEL": home = "VER"
                    if away == "HEL": away = "VER"
                    match_txt = f"{home} - {away}"
                else:
                    match_txt = f"Match {idx}"

                # !!! MODIFICA: Pathing Locale (Rimosso /content/) !!!
                filename = f"fantacalcio_{idx}.png"
                path = filename

                await match.screenshot(path=path)
                
                # !!! Rimosso: Upload a Drive e Aggiornamento Foglio (linee 329-331) !!!
                print(f"✅ Fantacalcio | {match_txt} → {filename} (Salvato localmente)")

            except Exception as e:
                print(f"⚠️ Errore su match {idx}: {e}")

        await context.close(); await browser.close()
        
    # Rimosso l'aggiornamento finale del foglio (linee 337-342)


# ==========================================================
#  FONTE 3: Gazzetta.it (Aggiornato)
# ==========================================================
async def estrai_screenshots_gazzetta():
    FONTE = "Gazzetta"
    URL = "https://www.gazzetta.it/Calcio/prob_form/"
    # START_ROW_GAZZETTA non più necessario

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=["--no-sandbox", "--disable-dev-shm-usage", "--headless=new"] # Aggiunto "--headless=new"
        )
        context = await browser.new_context(viewport={"width": 1600, "height": 4000})
        await context.route("**/*", block_privacy_requests)
        page = await context.new_page()

        # --- 1️⃣ Caricamento pagina ---
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        print("🌐 Pagina Gazzetta caricata.")

        # --- 2️⃣ Gestione banner cookie (linee 379-387) ---
        try:
            await page.wait_for_selector("button:has-text('ACCETTA E CONTINUA')", timeout=6000)
            await page.locator("button:has-text('ACCETTA E CONTINUA')").click()
            print("✅ Banner cookie chiuso correttamente.")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1200)
        except:
            print("ℹ️ Nessun banner cookie rilevato (o già bloccato).")

        # --- 3️⃣ Pulizia overlay privacy/consent (linee 390-405) ---
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
            print(f"⚠️ Pulizia DOM saltata (context unstable): {e}")

        # ... (Logica Loop Partite Mantenuta) ...
        await page.wait_for_selector(".bck-box-match-details", timeout=25000)
        matches = await page.query_selector_all(".bck-box-match-details")
        print(f"🔎 Gazzetta: trovate {len(matches)} partite nella pagina.")

        # --- 5️⃣ Loop sulle partite ---
        for idx, match_box in enumerate(matches[:MAX_MATCH], start=1):
            try:
                dom_id = await match_box.get_attribute("id") or f"match_{idx}"
                
                # Forza rendering
                await match_box.scroll_into_view_if_needed()
                await page.wait_for_timeout(1500)

                # Attesa caricamento lineup
                try:
                    await page.wait_for_selector(f"#{dom_id} .match-details__lineup",
                                               state="attached", timeout=4000)
                except:
                    print(f"⚠️ Partita {idx}: lineup non ancora caricata (lazy).")

                lineup = await page.query_selector(f"#{dom_id} .match-details__lineup")
                notes = await page.query_selector(f"#{dom_id} .match-details__notes")

                if not lineup and not notes:
                    print(f"⚠️ Partita {idx}: sezioni non trovate, salto.")
                    continue
                
                # ... (Logica JavaScript per pulizia NOTE e allargamento Mantenuta) ...

                # --- Rimuove prime due righe delle note --- (linee 449-456)
                if notes:
                    await page.evaluate("""
                        (sel) => {
                            const el = document.querySelector(sel);
                            if (!el) return;
                            const rows = el.querySelectorAll('.match-details__note-row, .match-details_note-row');
                            rows.forEach((r, i) => { if (i < 2) r.remove(); });
                        }
                    """, f"#{dom_id} .match-details__notes")

                # --- Allarga notes al 100% --- (linee 459-469)
                if notes:
                    await page.evaluate("""
                        (sel) => {
                            const el = document.querySelector(sel);
                            if (el) {
                                el.style.width = '100%';
                                el.style.maxWidth = '100%';
                                el.style.margin = '0';
                                el.style.padding = '0';
                            }
                        }
                    """, f"#{dom_id} .match-details__notes")

                # --- Screenshot lineup ---
                lineup_path = None
                if lineup:
                    await lineup.scroll_into_view_if_needed()
                    await page.wait_for_timeout(800)
                    # !!! MODIFICA: Pathing Locale (Rimosso /content/) !!!
                    lineup_path = f"gazzetta_{idx}_lineup.png"
                    await lineup.screenshot(path=lineup_path)
                    print(f"📸 Lineup partita {idx} salvata.")

                # --- Screenshot notes ---
                notes_path = None
                if notes:
                    await notes.scroll_into_view_if_needed()
                    await page.wait_for_timeout(800)
                    # !!! MODIFICA: Pathing Locale (Rimosso /content/) !!!
                    notes_path = f"gazzetta_{idx}_notes.png"
                    await notes.screenshot(path=notes_path)
                    print(f"📸 Notes partita {idx} salvate correttamente.")
                    
                # ======================================================
                #     🔥 6️⃣ UNIONE + FIX FORMATO (NOTES IN COLONNA)
                # ======================================================

                # ... (Logica di Combinazione e Cropping con PIL Mantenuta) ...
                
                images = [Image.open(p) for p in [lineup_path, notes_path] if p]
                if not images:
                    continue

                lineup_img = images[0]
                notes_img  = images[1] if len(images) == 2 else None
                rosa = (253, 233, 235)

                # 1️⃣ TAGLIO LINEUP (linee 516-523)
                cut_left  = 175
                cut_right = 175
                if lineup_img.width > cut_left + cut_right:
                    lineup_img = lineup_img.crop((
                        cut_left, 0, lineup_img.width - cut_right, lineup_img.height
                    ))
                base_width = lineup_img.width

                # 2️⃣ TROVA LA COLONNA DI SEPARAZIONE NOTE (linee 532-555)
                if notes_img:
                    w, h = notes_img.width, notes_img.height
                    notes_pixels = notes_img.load()
                    best_col, min_dark = None, 999999
                    for offset in range(-7, 8):
                        x = w // 2 + offset
                        dark = 0
                        for y in range(0, h, 6):
                            r,g,b = notes_pixels[x, y]
                            if (r+g+b) < 690:
                                dark += 1
                        if dark < min_dark:
                            min_dark = dark
                            best_col = x
                    if best_col is None: best_col = w // 2
                    notes_left  = notes_img.crop((0, 0, best_col, h))
                    notes_right = notes_img.crop((best_col, 0, w, h))

                    # 3️⃣ RIDUZIONE NOTES (linee 560-578)
                    scale_notes = 0.88
                    new_width   = int(base_width * scale_notes)

                    def resize_ratio(im, target_w):
                        ratio = target_w / im.width
                        new_h = int(im.height * ratio)
                        return im.resize((target_w, new_h), resample=Image.LANCZOS)

                    notes_left  = resize_ratio(notes_left,  new_width)
                    notes_right = resize_ratio(notes_right, new_width)

                    # 4️⃣ UNIONE NOTE IN COLONNA (linee 581-615)
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

                    # 5️⃣ CENTRA NOTES RISULTANTI (linee 618-627)
                    delta = (base_width - new_width) // 2
                    notes_img = ImageOps.expand(
                        notes_column,
                        border=(delta, 0, base_width - new_width - delta, 0),
                        fill=rosa
                    )
                else:
                    notes_img = None

                # 6️⃣ COMBINA LINEUP + GAP + NOTES (linee 630-652)
                gap, rosa = 30, (253, 233, 235)
                gap_block = Image.new("RGB", (base_width, gap), rosa)

                total_height = lineup_img.height + (gap + notes_img.height if notes_img else 0)
                combined = Image.new("RGB", (base_width, total_height), rosa)

                y = 0
                combined.paste(lineup_img, (0, y))
                if notes_img:
                    y += lineup_img.height
                    combined.paste(gap_block, (0, y)); y += gap
                    combined.paste(notes_img, (0, y))

                # 7️⃣ PADDING FINALE (linee 655-661)
                combined = ImageOps.expand(
                    combined,
                    border=(20, 40, 20, 40),
                    fill=rosa
                )

                # !!! MODIFICA: Pathing Locale (Rimosso /content/) !!!
                combined_path = f"gazzetta_{idx}.png"
                combined.save(combined_path)

                # !!! Rimosso: Upload a Drive e Aggiornamento Foglio (linee 667-669) !!!
                print(f"✅ Partita {idx}: salvata correttamente → {combined_path}")

            except Exception as e:
                print(f"⚠️ Errore su match {idx}: {e}")

        # --- Chiusura browser ---
        await context.close()
        await browser.close()
        print("🟢 Operazione completata")


# ==========================================================
#  MANAGER
# ==========================================================
async def aggiorna_tutte_le_fonti():
    await estrai_screenshots_sosfanta()
    await estrai_screenshots_fantacalcio()
    await estrai_screenshots_gazzetta()
    # Rimosso: propaga_match_ad_altre_fonti()

# ==========================================================
#  ESECUZIONE PRINCIPALE (per schedulazione)
# ==========================================================
if __name__ == "__main__":
    print("=== AVVIO SCRAPER ===")
    import asyncio
    asyncio.run(aggiorna_tutte_le_fonti()) 
    print("=== SCRAPER COMPLETATO ===")
