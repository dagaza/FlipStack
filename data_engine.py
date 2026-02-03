import json
import os
import csv
import datetime
import html
import shutil
import glob
import zipfile
import sqlite3
import re
import tempfile
import sys

# --- PATH CONFIGURATION ---

# 1. Detect if we are running as a Flatpak or standard Linux install
if os.environ.get("FLATPAK_ID") or os.environ.get("XDG_DATA_HOME"):
    # PRODUCTION MODE
    # Uses standard Linux data paths (e.g. ~/.var/app/io.github.dagaza.FlipStack/data/flipstack)
    base_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    BASE_DIR = os.path.join(base_data, "flipstack")
else:
    # DEV / GITHUB MODE
    # Uses a local folder 'user_data' inside your project so you don't pollute your hard drive
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = os.path.join(PROJECT_ROOT, "user_data")

# 2. Define Sub-folders based on that Base Directory
DATA_DIR = os.path.join(BASE_DIR, "decks")       # <--- JSON files go here
ASSETS_DIR = os.path.join(BASE_DIR, "assets")     # <--- User images/audio go here
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

# 3. Create them if they don't exist
for d in [BASE_DIR, DATA_DIR, ASSETS_DIR, BACKUP_DIR]:
    os.makedirs(d, exist_ok=True)

DATA_DIR = os.path.join(BASE_DIR, "decks")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
STATS_FILE = os.path.join(BASE_DIR, "stats.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
CATEGORIES_FILE = os.path.join(BASE_DIR, "categories.json")
DECK_META_FILE = os.path.join(BASE_DIR, "deck_meta.json")
COLORS_FILE = os.path.join(BASE_DIR, "deck_colors.json")

# Ensure directories exist
for d in [BASE_DIR, DATA_DIR, ASSETS_DIR, BACKUP_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

# --- Settings ---
def load_settings():
    default = {"sound_enabled": True}
    if not os.path.exists(SETTINGS_FILE): return default
    try:
        with open(SETTINGS_FILE, "r") as f:
            return {**default, **json.load(f)}
    except: return default

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)

# --- Categories ---
def get_categories():
    if not os.path.exists(CATEGORIES_FILE):
        return ["Uncategorized"]
    try:
        with open(CATEGORIES_FILE, "r") as f:
            cats = json.load(f)
            if "Uncategorized" not in cats:
                cats.insert(0, "Uncategorized")
            return cats
    except:
        return ["Uncategorized"]

def add_category(name):
    cats = get_categories()
    if name not in cats:
        cats.append(name)
        with open(CATEGORIES_FILE, "w") as f:
            json.dump(cats, f)

def delete_category(name):
    if name == "Uncategorized": return
    cats = get_categories()
    if name in cats:
        cats.remove(name)
        with open(CATEGORIES_FILE, "w") as f:
            json.dump(cats, f)

def get_deck_category(filename):
    meta = {}
    if os.path.exists(DECK_META_FILE):
        try:
            with open(DECK_META_FILE, "r") as f:
                meta = json.load(f)
        except:
            pass
    return meta.get(filename, "Uncategorized")

def set_deck_category(filename, category):
    meta = {}
    if os.path.exists(DECK_META_FILE):
        try:
            with open(DECK_META_FILE, "r") as f:
                meta = json.load(f)
        except:
            pass
    meta[filename] = category
    with open(DECK_META_FILE, "w") as f:
        json.dump(meta, f)

# --- Global Search & Tags ---
def search_all_cards(query):
    results = []
    if not query: return []
    query = query.lower()
    files = get_all_decks()
    for fname in files:
        cards = load_deck(fname)
        deck_name = fname.replace(".json", "").replace("_", " ").title()
        for card in cards:
            tags = " ".join(card.get("tags", [])).lower()
            if query in card.get("front", "").lower() or \
               query in card.get("back", "").lower() or \
               query in tags:
                results.append({
                    "deck_name": deck_name,
                    "filename": fname,
                    "front": card["front"],
                    "back": card["back"]
                })
    return results

def get_cards_by_tag(tag):
    tag = tag.lower().strip()
    files = get_all_decks()
    virtual_deck = []
    for fname in files:
        cards = load_deck(fname)
        for card in cards:
            if tag in [t.lower() for t in card.get("tags", [])]:
                virtual_deck.append(card)
    return virtual_deck

# --- Asset Handling ---
def save_asset(source_path):
    """
    Copies a user-selected file to the internal ASSETS_DIR.
    1. Preserves the original filename if possible.
    2. If a file with that name exists, appends a counter (image.png -> image_1.png).
    3. Returns the FINAL filename used.
    """
    if not source_path or not os.path.exists(source_path):
        return None

    # 1. Get the original filename (e.g., "my_photo.jpg")
    original_filename = os.path.basename(source_path)
    name_part, extension = os.path.splitext(original_filename)

    # 2. Basic cleanup (remove characters that break Linux filesystems)
    # Allows letters, numbers, spaces, hyphens, underscores
    safe_name = re.sub(r'[^\w\s-]', '', name_part).strip().replace(' ', '_')
    if not safe_name: safe_name = "asset" # Fallback if name was only special chars

    final_filename = f"{safe_name}{extension}"
    destination_path = os.path.join(ASSETS_DIR, final_filename)

    # 3. Collision Detection (The "Smart" part)
    counter = 1
    while os.path.exists(destination_path):
        # Check if it's actually the exact same file (optimization)
        # If the file in the folder is identical to the new one, we can just reuse it!
        # (This prevents duplicating "icon.png" 50 times if the user re-imports it)
        try:
            if file_is_identical(source_path, destination_path):
                return final_filename
        except:
            pass # If comparison fails, just rename to be safe

        # If different, try new name: "my_photo_1.jpg"
        final_filename = f"{safe_name}_{counter}{extension}"
        destination_path = os.path.join(ASSETS_DIR, final_filename)
        counter += 1

    # 4. Perform the Copy
    try:
        shutil.copy2(source_path, destination_path)
        return final_filename
    except Exception as e:
        print(f"Error copying asset: {e}")
        return None

def file_is_identical(file1, file2):
    """Helper to check if two files are effectively the same content."""
    # Simple check: same size?
    if os.path.getsize(file1) != os.path.getsize(file2):
        return False
    # (Optional) You could do a hash check here for 100% certainty, 
    # but size is usually a "good enough" proxy for UI speed.
    return True

def get_asset_path(filename):
    if not filename: return None
    return os.path.join(ASSETS_DIR, filename)

# --- Deck Logic ---
def get_all_decks():
    if not os.path.exists(DATA_DIR): return []
    return [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]

def load_deck(filename):
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return []

def save_deck(filename, cards):
    with open(os.path.join(DATA_DIR, filename), "w") as f:
        json.dump(cards, f, indent=2)

def create_empty_deck(name, category="Uncategorized"):
    safe = "".join([c for c in name if c.isalnum() or c in (' ', '_')]).strip()
    fname = f"{safe.lower().replace(' ', '_')}.json"
    save_deck(fname, [])
    set_deck_category(fname, category)
    return fname

def delete_deck(filename):
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
            new_h = [e for e in history if e.get("deck") != filename]
            with open(HISTORY_FILE, "w") as f:
                json.dump(new_h, f, indent=2)
        except:
            pass

def get_deck_mastery(filename):
    cards = load_deck(filename)
    if not cards: return 0.0
    learned = len([c for c in cards if c.get("bucket", 0) > 0 and not c.get("suspended", False)])
    return learned / len(cards)

# --- Card Logic ---
def add_card_to_deck(filename, front, back, image_path=None, audio_path=None, tags=None, hint=None):
    cards = load_deck(filename)
    img_file = save_asset(image_path) if image_path else None
    aud_file = save_asset(audio_path) if audio_path else None
    
    cards.append({
        "id": str(datetime.datetime.now().timestamp()),
        "front": front, "back": back,
        "image": img_file,
        "audio": aud_file,
        "tags": tags or [],
        "hint": hint or "",
        "bucket": 0, "next_review": None,
        "miss_streak": 0,
        "suspended": False
    })
    save_deck(filename, cards)

def edit_card(filename, card_id, f_txt, b_txt, img_path=None, aud_path=None, tags=None, suspended=False, hint=None):
    cards = load_deck(filename)
    for c in cards:
        if c["id"] == card_id:
            c["front"] = f_txt
            c["back"] = b_txt
            if img_path: c["image"] = save_asset(img_path)
                        
            if img_path:
                if os.sep in img_path: c["image"] = save_asset(img_path)
                else: c["image"] = img_path # Keep existing filename
            else:
                c["image"] = None # Clear it

            if aud_path:
                if os.sep in aud_path: c["audio"] = save_asset(aud_path)
                else: c["audio"] = aud_path
            else:
                c["audio"] = None

            if tags is not None: c["tags"] = tags
            c["hint"] = hint or ""
            c["suspended"] = suspended
            if not suspended: c["miss_streak"] = 0
            break
    save_deck(filename, cards)

def delete_card(filename, cid):
    cards = load_deck(filename)
    new_c = [c for c in cards if c["id"] != cid]
    save_deck(filename, new_c)

# --- Progress ---
# UPDATED: Added hint_used logic
def log_review(deck, rating, sid=None, hint_used=False):
    entry = { 
        "timestamp": datetime.datetime.now().isoformat(), 
        "deck": deck, 
        "rating": rating, 
        "session_id": sid,
        "hint_used": hint_used 
    }
    hist = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                hist = json.load(f)
        except:
            pass
    hist.append(entry)
    if len(hist) > 10000:
        hist = hist[-10000:]
    with open(HISTORY_FILE, "w") as f:
        json.dump(hist, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

def get_deck_history(filename):
    if not os.path.exists(HISTORY_FILE): return []
    try:
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
            return [d for d in data if d["deck"] == filename]
    except:
        return []

def get_heatmap_data():
    if not os.path.exists(HISTORY_FILE): return {}
    try:
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
        data = {}
        for h in history:
            ts = h.get("timestamp", h.get("date"))
            if not ts: continue
            day = ts.split("T")[0]
            data[day] = data.get(day, 0) + 1
        return data
    except:
        return {}

# UPDATED: Added hint_used param
def update_card_progress(filename, card_id, rating, session_id=None, hint_used=False):
    log_review(filename, rating, session_id, hint_used)
    cards = load_deck(filename)
    leech_alert = False
    
    for c in cards:
        if c["id"] == card_id:
            if rating == 1:
                c["miss_streak"] = c.get("miss_streak", 0) + 1
                if c["miss_streak"] >= 8:
                    c["suspended"] = True
                    leech_alert = True
            else:
                c["miss_streak"] = 0

            if rating == 3: c["bucket"] = c.get("bucket", 0) + 1
            elif rating == 1: c["bucket"] = 0
            if rating == 2 and c.get("bucket", 0) == 0: c["bucket"] = 1
            
            days = 0 if c.get("bucket", 0) == 0 else 2 ** c["bucket"]
            c["next_review"] = (datetime.date.today() + datetime.timedelta(days=days)).isoformat()
            break
            
    save_deck(filename, cards)
    update_streak()
    return leech_alert

def create_backup():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = os.path.join(BACKUP_DIR, f"flipstack_backup_{ts}")
    try:
        shutil.make_archive(zip_name, 'zip', root_dir='.', base_dir=DATA_DIR)
        return True
    except:
        return False

# --- STATISTICS ENGINE ---
def log_stats(deck_name, rating):
    """
    Logs a review event to stats.json.
    Rating: 3=Good (Correct), 2=Hard (Correct), 1=Miss (Incorrect)
    """
    stats_path = os.path.join(DATA_DIR, 'stats.json')
    today = datetime.now().strftime("%Y-%m-%d")
    
    data = {}
    if os.path.exists(stats_path):
        try:
            with open(stats_path, 'r') as f:
                data = json.load(f)
        except: pass

    # Initialize structure: data[deck_name][date]
    if deck_name not in data: data[deck_name] = {}
    if today not in data[deck_name]: 
        data[deck_name][today] = {"correct": 0, "total": 0}

    # Update counts
    data[deck_name][today]["total"] += 1
    # We count Good (3) and Hard (2) as "Correct" for accuracy tracking
    if rating >= 2:
        data[deck_name][today]["correct"] += 1
        
    try:
        with open(stats_path, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Failed to save stats: {e}")

def get_stats_history(deck_name):
    """Returns the last 7 days of stats for the graph."""
    stats_path = os.path.join(DATA_DIR, 'stats.json')
    if not os.path.exists(stats_path): return {}
    try:
        with open(stats_path, 'r') as f:
            full_data = json.load(f)
            return full_data.get(deck_name, {})
    except: return {}

# --- Utils ---
def load_stats():
    if not os.path.exists(STATS_FILE): return {"streak": 0, "last_study_date": None}
    try:
        with open(STATS_FILE, "r") as f: return json.load(f)
    except: return {"streak": 0, "last_study_date": None}

def save_stats(stats):
    with open(STATS_FILE, "w") as f: json.dump(stats, f)

def update_streak():
    stats = load_stats()
    today = datetime.date.today().isoformat()
    if stats.get("last_study_date") == today: return stats["streak"]
    if stats.get("last_study_date"):
        delta = (datetime.date.today() - datetime.date.fromisoformat(stats["last_study_date"])).days
        if delta == 1: stats["streak"] += 1
        else: stats["streak"] = 1
    else: stats["streak"] = 1
    stats["last_study_date"] = today
    save_stats(stats)
    return stats["streak"]

# --- MARKDOWN PARSER (FINAL ROBUST VERSION) ---
def format_text(text):
    if not text: return ""
    
    # 1. Escape HTML first (Critical for Pango)
    text = html.escape(text)

    # 2. Helper function to process code blocks
    def code_block_replacer(match):
        content = match.group(1)
        
        if re.match(r'^\w+\s*\n', content):
            parts = content.split('\n', 1)
            if len(parts) > 1:
                content = parts[1] # Keep everything after the first line
        
        return f'\n<span font_family="monospace" background="#303030" foreground="#eeeeee" size="small"> {content} </span>\n'

    # 3. Apply the Code Block Regex
    text = re.sub(r'```([\s\S]*?)```', code_block_replacer, text)

    # 4. Inline Code (`...`)
    text = re.sub(
        r'`([^`\n]+)`', 
        r'<span font_family="monospace" background="#3d3d3d" foreground="#f2f2f2"> \1 </span>', 
        text
    )

    # 5. Bold (**...**)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)

    # 6. Italic (*...*)
    text = re.sub(r'\*(?!\*)(.*?)\*', r'<i>\1</i>', text)

    # 7. Strikethrough (~~...~~)
    text = re.sub(r'~~(.*?)~~', r'<s>\1</s>', text)

    # 8. Headers (# ...)
    text = re.sub(r'^# (.*?)$', r'<span size="x-large" weight="bold">\1</span>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.*?)$', r'<span size="large" weight="bold">\1</span>', text, flags=re.MULTILINE)
    
    return text

# --- IMPORTERS ---
def import_csv(path, name):
    cards = []
    if not path or not os.path.exists(path): return False
    encodings = ['utf-8-sig', 'utf-8', 'latin-1']
    delimiters = [',', ';', '\t']
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                lines = f.readlines()
                if not lines: continue
                first = lines[0]
                best_delim = ','
                for d in delimiters:
                    if d in first:
                        best_delim = d
                        break
                parsed_cards = []
                for line in lines:
                    line = line.strip()
                    if not line: continue
                    parts = line.split(best_delim)
                    if len(parts) >= 2:
                        front = parts[0].strip().strip('"')
                        back = parts[1].strip().strip('"')
                        if front and back:
                            parsed_cards.append({
                                "id": str(datetime.datetime.now().timestamp())+str(len(parsed_cards)), 
                                "front": front, "back": back,
                                "bucket": 0, "suspended": False,
                                "hint": ""
                            })
                if parsed_cards:
                    cards = parsed_cards
                    break
        except Exception:
            continue
    if cards:
        fname = create_empty_deck(name)
        save_deck(fname, cards)
        return True
    return False

def import_anki_apkg(path, name):
    if not path or not os.path.exists(path): return False
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(path, 'r') as z:
                z.extractall(temp_dir)
            media_map_file = os.path.join(temp_dir, "media")
            if os.path.exists(media_map_file):
                try:
                    with open(media_map_file, "r") as f:
                        media_map = json.load(f)
                    for k, v in media_map.items():
                        src = os.path.join(temp_dir, k)
                        dst = os.path.join(ASSETS_DIR, v)
                        if os.path.exists(src): shutil.copy(src, dst)
                except: pass
            db_path = os.path.join(temp_dir, "collection.anki2")
            if not os.path.exists(db_path): return False
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT flds FROM notes")
            rows = cursor.fetchall()
            cards = []
            for row in rows:
                if not row or not row[0]: continue
                fields = row[0].split('\x1f')
                if len(fields) >= 2:
                    front_raw = fields[0]
                    back_raw = fields[1]
                    img_match = re.search(r'<img src="([^"]+)"', front_raw + back_raw)
                    image_file = img_match.group(1) if img_match else None
                    clean_f = re.sub(r'<[^>]+>', '', front_raw).strip()
                    clean_b = re.sub(r'<[^>]+>', '', back_raw).strip()
                    if clean_f and clean_b:
                        cards.append({
                            "id": str(datetime.datetime.now().timestamp())+str(len(cards)),
                            "front": clean_f, "back": clean_b, "image": image_file,
                            "bucket": 0, "suspended": False, "next_review": None, "hint": ""
                        })
            conn.close()
            if cards:
                fname = create_empty_deck(name)
                save_deck(fname, cards)
                return True
    except Exception as e:
        print(f"Anki Import Error: {e}")
        return False
    return False

def export_deck_to_csv(fname, path):
    cards = load_deck(fname)
    try:
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for c in cards: writer.writerow([c.get('front',''), c.get('back','')])
        return True
    except: return False

def export_deck_to_json(fname, path):
    try:
        shutil.copy(os.path.join(DATA_DIR, fname), path)
        return True
    except: return False

def rename_deck(old_filename, new_display_name):
    """
    Renames a deck file and updates all references in history and meta files.
    Returns the new filename.
    """
    # 1. Generate new safe filename
    safe = "".join([c for c in new_display_name if c.isalnum() or c in (' ', '_')]).strip()
    new_filename = f"{safe.lower().replace(' ', '_')}.json"
    
    if new_filename == old_filename:
        return old_filename
        
    old_path = os.path.join(DATA_DIR, old_filename)
    new_path = os.path.join(DATA_DIR, new_filename)
    
    if os.path.exists(new_path):
        return None # Prevent overwriting existing deck
        
    try:
        # 2. Rename the actual file
        os.rename(old_path, new_path)
        
        # 3. Update Category Meta (deck_meta.json)
        if os.path.exists(DECK_META_FILE):
            with open(DECK_META_FILE, "r") as f:
                meta = json.load(f)
            if old_filename in meta:
                meta[new_filename] = meta.pop(old_filename)
                with open(DECK_META_FILE, "w") as f:
                    json.dump(meta, f)
                    
        # 4. Update History (history.json)
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
            changed = False
            for entry in history:
                if entry.get("deck") == old_filename:
                    entry["deck"] = new_filename
                    changed = True
            if changed:
                with open(HISTORY_FILE, "w") as f:
                    json.dump(history, f, indent=2)
                    
        return new_filename
    except Exception as e:
        print(f"Rename failed: {e}")
        return None

def rename_category(old_name, new_name):
    """
    Renames a category in the list and updates all decks assigned to it.
    """
    if old_name == "Uncategorized": return False # Can't rename default
    
    # 1. Update Categories List
    cats = get_categories()
    if old_name in cats:
        idx = cats.index(old_name)
        cats[idx] = new_name
        with open(CATEGORIES_FILE, "w") as f:
            json.dump(cats, f)
            
    # 2. Update references in Deck Meta
    if os.path.exists(DECK_META_FILE):
        try:
            with open(DECK_META_FILE, "r") as f:
                meta = json.load(f)
            changed = False
            for filename, cat in meta.items():
                if cat == old_name:
                    meta[filename] = new_name
                    changed = True
            if changed:
                with open(DECK_META_FILE, "w") as f:
                    json.dump(meta, f)
            return True
        except:
            return False
    return True

def create_tutorial_deck():
    """Generates a comprehensive tutorial deck for first-time users."""
    # Safe name generation
    name = "Welcome to FlipStack"
    safe = "".join([c for c in name if c.isalnum() or c in (' ', '_')]).strip()
    filename = f"{safe.lower().replace(' ', '_')}.json"
    
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        return filename # Already exists, don't overwrite
    
    # Comprehensive Tutorial Content (Markdown)
    cards = [
        # --- Basics ---
        {
            "front": "**Welcome to FlipStack!**\n\nPress **Space** to flip this card, then rate how well you knew it.",
            "back": "Great! Use the buttons below or keyboard shortcuts:\n\n**1 (Good)**: You know it well.\n**2 (Hard)**: You struggled.\n**3 (Miss)**: You forgot it.",
            "tags": ["basics"],"hint": ""
        },
        {
            "front": "How do you **Edit** a card while studying?",
            "back": "Click the **Pencil Icon** in the top right corner of the card to fix typos immediately. You can also use the Edit button in the navigation bar on the left-hand side for a specific deck, and then seek the card you want to edit. ",
            "tags": ["basics"], "hint": ""
        },
        
        # --- Organization ---
        {
            "front": "How do you create a new **Category**?",
            "back": "Click the **New Folder** icon in the left-hand sidebar, in the toolbar at the top.",
            "tags": ["organization"], "hint": "Sidebar"
        },
         {
            "front": "How do you create a new **Deck**?",
            "back": "Click the blue **+** icon in the left-hand sidebar, in the toolbar at the top.",
            "tags": ["organization"], "hint": "Sidebar"
        },
        {
            "front": "How do you **Rename** a Category or Deck?",
            "back": "**Double-click** the name of any Category or Deck in the sidebar to rename it. Note that the 'Uncategorized' category cannot be renamed.",
            "tags": ["organization"], "hint": "Double Click"
        },{
            "front": "How do you **Move** a Deck to another Category?",
            "back": "Click the **Move** icon found in line with the Deck you want to move (hover over the deck's name in the sidebar). Choose from the dialog box the destination Category.",
            "tags": ["organization"], "hint": "Sidebar"
        },
        
        # --- Data Management ---
        {
            "front": "How do you **Import** decks?",
            "back": "Click the **Import** icon (see tooltips when hovering over the icons) in the top-left toolbar.\nWe support **CSV** files as well as **Anki (.apkg)**.",
            "tags": ["data"], "hint": "Import"
        },
        {
            "front": "How do you **Backup** your data?",
            "back": "Click the **Save As** icon (see tooltips when hovering over the icons) in the toolbar. This creates a full ZIP backup of all your decks and media in the 'backups' folder.",
            "tags": ["data"], "hint": "Backup"
        },
        
        # --- Settings & Appearance ---
        {
            "front": "How do you change the **Font**?",
            "back": "Click the **'ab'** icon (see tooltips when hovering over icons) in the center toolbar on the left-hand sidebar to adjust the font family and size for all cards.",
            "tags": ["appearance"], "hint": "Text Settings"
        },
        {
            "front": "How do you toggle **Dark/Light Mode**?",
            "back": "Click the **Sun/Moon** icon in the center toolbar on the left-hand sidebar.",
            "tags": ["appearance"], "hint": "Theme"
        },
        {
            "front": "How do you turn **Sound Effects** On/Off?",
            "back": "Click the **Speaker** icon in the center toolbar on the left-hand sidebar to mute or unmute app sounds (like the flip and grade sounds). This will not mute the audio of the cards you are studying, to which you may have added audio yourself.",
            "tags": ["settings"], "hint": "SFX"
        },
        
        # --- Study Modes ---
        {
            "front": "What is **Cram Mode**?",
            "back": "Click the **Storm** icon (cloud with lightning) in the study screen, above this card, in the top-right.\n\nThis lets you review **all** cards in the deck immediately, ignoring the spaced repetition schedule. This is useful if you have an exam coming up or need to review a lot of cards quickly without following the spaced repetition schedule.",
            "tags": ["study-modes"], "hint": "Storm Icon"
        },
        {
            "front": "What is **Reverse Mode**?",
            "back": "Click the **Rotate** icon at the top of te study screen, above this card, to swap the Front and Back of cards temporarily. This is useful for learning things more thoroughly, and testing yourself from both sides of the knowledge spectrum.",
            "tags": ["study-modes"], "hint": "Rotate Icon"
        },
        {
            "front": "How do you **Shuffle** cards?",
            "back": "Click the **Shuffle** icon (see the tooltips when hovering over the icons) in the study header above this card to randomize the order of the remaining cards in your session.",
            "tags": ["study-modes"], "hint": "Randomize"
        },
        
        # --- Management ---
        {
            "front": "How do you **Edit** a Deck (add/remove/edit cards)?",
            "back": "Hover over a deck in the sidebar on the left-hand side and click the **Edit** (Pencil) icon.\n\nOr, use the **Search** bar to find specific cards.",
            "tags": ["management"], "hint": "Deck Editor"
        },
        {
            "front": "How do you see **Performance Stats**?",
            "back": "Hover over a deck and click the **Gauge** icon ('View Stats' tooltip).\n\nThis shows your study history, accuracy, and retention rates.",
            "tags": ["stats"], "hint": "Graphs"
        }
    ]
    
    deck_data = []
    for i, c in enumerate(cards):
        deck_data.append({
            "id": f"tutorial_{i}",
            "front": c["front"], "back": c["back"],
            "image": None, "audio": None,
            "tags": c["tags"], "hint": c["hint"],
            "bucket": 0, "next_review": None,
            "miss_streak": 0, "suspended": False
        })
    
    with open(path, "w") as f:
        json.dump(deck_data, f, indent=2)

    add_category("FlipStack Tutorial")
        
    set_deck_category(filename, "FlipStack Tutorial")
    return filename