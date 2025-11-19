# ==========================================================
#  ✅ SCREENSHOT BOT MULTIFONTE ADATTATO PER GITHUB ACTIONS
#  Obiettivo: Drive ON, Sheets OFF
# ==========================================================

# --- LIBRERIE ---
import asyncio, re, os, random, glob, json, base64 # Aggiunto base64
import nest_asyncio
from playwright.async_api import async_playwright
from PIL import Image, ImageOps 

# Importazioni per Google Drive
from google.auth.transport.requests import Request # Mantenuto per compatibilità, non strettamente necessario con SA
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ==========================================================
#  CONFIG
# ==========================================================
# Rimosso SHEET_ID e SHEET_NAME
DRIVE_FOLDER_ID = "1Oy6nEebc7hE0OOyD3DKnqb3PaGSLk2eO" # ID trovato nello script originale [cite: 1]
MAX_MATCH = 10
GIORNATA = 12 # o la giornata corretta
START_ROW_GAZZETTA = 12 # Mantenuto per non toccare la logica interna di Gazzetta (anche se non usiamo Sheets)

# ==========================================================
#  AUTENTICAZIONE E SERVIZI (ADATTATA PER SECRET B64)
# ==========================================================

SCOPES = ["https://www.googleapis.com/auth/drive"] 
drive_svc = None
# Rimosso: sheets_gc, ws

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

# Funzione da chiamare all'inizio dell'esecuzione
init_google_drive()

# ==========================================================
#  UTIL (DRIVE REINTRODOTTA, SHEETS RIMOSSA)
# ==========================================================
# LA FUNZIONE drive_upload_or_replace (RI-INTRODOTTA SOTTO)
# Rimosso: def propaga_match_ad_altre_fonti()
nest_asyncio.apply()
