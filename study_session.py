import gi
import data_engine as db
from datetime import datetime
import uuid
import random
import subprocess
import threading
import os
import html

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Pango', '1.0')
from gi.repository import Gtk, Adw, Gdk, Gio, GLib, GObject, Pango

class StudySession(Gtk.Box):
    def __init__(self, filename, navigation_callback=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.filename = filename
        self.nav_callback = navigation_callback 
        self.session_id = str(uuid.uuid4())
        
        self.session_stats = {"good": 0, "hard": 0, "miss": 0, "total": 0, "session_id": self.session_id}
        
        self.is_cram_mode = False
        self.is_reverse_mode = False
        self.hint_used = False

        # --- NEW: State Flags ---
        self.current_img_path = None 
        self.input_locked = False       # <--- Prevents ghost clicks
        self.has_finished_deck = False  # <--- Prevents double audio
        self.is_editing = False
        # ------------------------

        self.setup_css()
        self.load_cards()
        self.current_index = 0
        self.is_flipped = False
        
        self.build_ui()
        self.setup_views()
        self.refresh_view()

        self.key_controller = Gtk.EventControllerKey()
        self.key_controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(self.key_controller)

        self.setup_gestures()

    def setup_css(self):
        css_provider = Gtk.CssProvider()
        css_provider.load_from_string("""
            .btn-green { background: #2ec27e; color: white; }
            .btn-green:hover { background: #26a269; }
            .btn-yellow { background: #f5c211; color: black; }
            .btn-yellow:hover { background: #e5a50a; }
            .btn-red { background: #ed333b; color: white; }
            .btn-red:hover { background: #c01c28; }
            .progress-label { font-size: 12px; color: alpha(currentColor, 0.7); }
            .card-btn-edit { background: transparent; color: alpha(currentColor, 0.5); box-shadow: none; margin-right: 20px;}
            .card-btn-edit:hover { color: currentColor; background: alpha(currentColor, 0.1); }
            .audio-btn-large { padding: 10px; border-radius: 50%; background: alpha(currentColor, 0.1); color: #3584e4; }
            .audio-btn-large:hover { background: alpha(#3584e4, 0.2); }
            .hint-text { color: #f5c211; font-weight: bold; }
            
            /* UPDATED: Frame Style Flash */
            .flash-success { 
                border: 6px solid #2ec27e; /* Green */
                background-color: transparent; 
            }
            .flash-warning { 
                border: 6px solid #f5c211; /* Yellow (Hard) */
                background-color: transparent; 
            }
            .flash-error { 
                border: 6px solid #ed333b; /* Red */
                background-color: transparent; 
            }
        """)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def build_ui(self):
        deck_name = self.filename.replace(".json", "").replace("_", " ").title()
        
        # FIX: Reduced margins for mobile
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        header.set_margin_top(10); header.set_margin_bottom(10)
        header.set_margin_start(10); header.set_margin_end(10)
        
        # FIX: Allow title to shrink/ellipsize
        title = Gtk.Label(label=deck_name, xalign=0)
        title.add_css_class("title-2")
        title.set_ellipsize(Pango.EllipsizeMode.END) 
        title.set_hexpand(True) # Takes available space
        
        header.append(title)
        
        # Buttons (Compact)
        btn_rev = Gtk.ToggleButton(icon_name="object-rotate-left-symbolic"); btn_rev.set_tooltip_text("Reverse Mode"); btn_rev.add_css_class("flat"); btn_rev.connect("toggled", self.on_reverse_toggled); header.append(btn_rev)
        btn_cram = Gtk.ToggleButton(icon_name="weather-storm-symbolic"); btn_cram.set_tooltip_text("Cram Mode"); btn_cram.add_css_class("flat"); btn_cram.connect("toggled", self.on_cram_toggled); header.append(btn_cram)
        btn_shuf = Gtk.Button(icon_name="media-playlist-shuffle-symbolic"); btn_shuf.set_tooltip_text("Shuffle"); btn_shuf.add_css_class("flat"); btn_shuf.connect("clicked", self.on_shuffle_clicked); header.append(btn_shuf)
        btn_add = Gtk.Button(icon_name="list-add-symbolic"); btn_add.set_tooltip_text("Add Card"); btn_add.add_css_class("flat"); btn_add.connect("clicked", self.on_add_clicked); header.append(btn_add)
        
        self.append(header); self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # --- CENTERED PROGRESS ROW ---
        prog_row = Gtk.CenterBox()
        prog_row.set_margin_top(5); prog_row.set_margin_bottom(5)
        
        # Center: Progress Stack
        prog_stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_size_request(200, -1) 
        self.progress_bar.set_halign(Gtk.Align.CENTER)
        self.lbl_progress = Gtk.Label(label="0 / 0")
        self.lbl_progress.add_css_class("progress-label")
        prog_stack.append(self.progress_bar)
        prog_stack.append(self.lbl_progress)
        
        prog_row.set_center_widget(prog_stack)
        
        # End: Edit Button
        edit_container = Gtk.Box()
        edit_container.set_margin_end(20) 
        self.btn_card_edit = Gtk.Button(icon_name="document-edit-symbolic")
        self.btn_card_edit.set_tooltip_text("Edit This Card")
        self.btn_card_edit.add_css_class("card-btn-edit")
        self.btn_card_edit.connect("clicked", self.on_edit_clicked)
        edit_container.append(self.btn_card_edit)
        
        prog_row.set_end_widget(edit_container)
        self.append(prog_row)

        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20); center.set_valign(Gtk.Align.START); center.set_margin_top(10); center.set_halign(Gtk.Align.CENTER); center.set_hexpand(True); center.set_vexpand(True)
        clamp = Adw.Clamp(maximum_size=700); clamp.set_child(center); self.append(clamp)
        self.card_stack = Gtk.Stack(); self.card_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT); self.card_stack.set_size_request(300, 445); center.append(self.card_stack)
   
    def load_cards(self):
        all_cards = db.load_deck(self.filename)
        self.total_cards_in_deck = len(all_cards) # <--- NEW: Track total size
        if self.is_cram_mode: self.cards = all_cards; random.shuffle(self.cards)
        else:
            today = datetime.today().isoformat()
            self.cards = sorted([c for c in all_cards if not c.get("next_review") or c.get("next_review") <= today], key=lambda c: c.get("next_review") or "0000-00-00")
    
    def setup_views(self):
        # 0. Void
        page_void = Adw.StatusPage(icon_name="folder-new-symbolic", title="Empty Deck", description="This deck has no cards yet.")
        btn_add_first = Gtk.Button(label="Add Your First Card"); btn_add_first.add_css_class("pill"); btn_add_first.add_css_class("suggested-action")
        btn_add_first.connect("clicked", self.on_add_clicked); page_void.set_child(btn_add_first)
        self.card_stack.add_named(page_void, "void")

        # 1. Empty
        page = Adw.StatusPage(icon_name="edit-copy-symbolic", title="Deck Complete", description="No cards due right now.")
        btn_cram = Gtk.Button(label="Review All Cards"); btn_cram.add_css_class("pill")
        btn_cram.connect("clicked", lambda x: self.on_cram_toggled(None, force_on=True)); page.set_child(btn_cram)
        self.card_stack.add_named(page, "empty")

        # 2. Done
        page_done = Adw.StatusPage(icon_name="emblem-ok-symbolic", title="Session Complete!", description="Great job!")
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15); vbox.set_halign(Gtk.Align.CENTER)
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15); row1.set_halign(Gtk.Align.CENTER)
        btn_close = Gtk.Button(label="Close Deck"); btn_close.add_css_class("pill"); btn_close.connect("clicked", lambda x: self.nav_callback("close", None)); row1.append(btn_close)
        btn_stats = Gtk.Button(label="Show Performance"); btn_stats.add_css_class("pill"); btn_stats.connect("clicked", lambda x: self.nav_callback("stats", self.session_stats)); row1.append(btn_stats); vbox.append(row1)
        btn_play = Gtk.Button(label="Play Again"); btn_play.add_css_class("suggested-action"); btn_play.add_css_class("pill"); btn_play.set_size_request(200, -1); btn_play.connect("clicked", lambda x: self.restart_session()); vbox.append(btn_play)
        page_done.set_child(vbox); self.card_stack.add_named(page_done, "done")

        # 3. Front (REVERTED TO ORIGINAL LAYOUT)
        self.box_front = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.box_front.set_valign(Gtk.Align.CENTER); self.box_front.set_margin_bottom(10)
        
        # Image (Standard Scaling + Lightbox)
        self.img_front = Gtk.Picture()
        self.img_front.set_size_request(-1, 150) # Balanced size
        self.img_front.set_content_fit(Gtk.ContentFit.SCALE_DOWN)
        self.img_front.set_visible(False)
        self.img_front.set_cursor(Gdk.Cursor.new_from_name("pointer", None))
        
        click_f = Gtk.GestureClick(); click_f.connect("pressed", self.on_image_click)
        self.img_front.add_controller(click_f)
        self.box_front.append(self.img_front)
        
        self.btn_audio_front = Gtk.Button(icon_name="audio-volume-high-symbolic"); self.btn_audio_front.add_css_class("audio-btn-large"); self.btn_audio_front.set_size_request(60, 60); self.btn_audio_front.set_halign(Gtk.Align.CENTER); self.btn_audio_front.set_visible(False); self.btn_audio_front.connect("clicked", self.on_play_card_audio); self.box_front.append(self.btn_audio_front)
        
        scroll_f = Gtk.ScrolledWindow(); scroll_f.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC); scroll_f.set_max_content_height(300); scroll_f.set_propagate_natural_height(True)
        self.lbl_front = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, css_classes=["card-text"])
        self.lbl_front.set_wrap_mode(Pango.WrapMode.WORD_CHAR); scroll_f.set_child(self.lbl_front); self.box_front.append(scroll_f)
        
        self.box_hint = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5); self.btn_hint = Gtk.Button(label="💡 Hint", css_classes=["pill", "flat"]); self.btn_hint.connect("clicked", self.on_hint_clicked); self.lbl_hint = Gtk.Label(css_classes=["hint-text"], wrap=True, justify=Gtk.Justification.CENTER); self.box_hint.append(self.btn_hint); self.box_hint.append(self.lbl_hint); self.box_front.append(self.box_hint)
        btn_flip = Gtk.Button(label="Show Answer (Space)"); btn_flip.add_css_class("pill"); btn_flip.add_css_class("suggested-action"); btn_flip.set_halign(Gtk.Align.CENTER); btn_flip.set_size_request(200, 50); btn_flip.connect("clicked", self.flip_card); self.box_front.append(btn_flip)
        self.lbl_tags = Gtk.Label(css_classes=["dim-label", "caption"], margin_top=5); self.box_front.append(self.lbl_tags)
        self.card_stack.add_named(self.box_front, "front")

        # 4. Back (REVERTED TO ORIGINAL LAYOUT)
        self.content_back = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.content_back.set_valign(Gtk.Align.CENTER); self.content_back.set_margin_bottom(30)
        
        self.img_back = Gtk.Picture(); self.img_back.set_size_request(-1, 60)
        self.img_back.set_content_fit(Gtk.ContentFit.SCALE_DOWN); self.img_back.set_visible(False)
        self.img_back.set_cursor(Gdk.Cursor.new_from_name("pointer", None))
        
        click_b = Gtk.GestureClick(); click_b.connect("pressed", self.on_image_click)
        self.img_back.add_controller(click_b)
        self.content_back.append(self.img_back)
        
        self.btn_audio_back = Gtk.Button(icon_name="audio-volume-high-symbolic"); self.btn_audio_back.add_css_class("audio-btn-large"); self.btn_audio_back.set_size_request(60, 60); self.btn_audio_back.set_halign(Gtk.Align.CENTER); self.btn_audio_back.set_visible(False); self.btn_audio_back.connect("clicked", self.on_play_card_audio)
        self.content_back.append(self.btn_audio_back)
        
        self.text_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        scroll_b_ctx = Gtk.ScrolledWindow(); scroll_b_ctx.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC); scroll_b_ctx.set_max_content_height(100)
        self.lbl_back_ctx = Gtk.Label(css_classes=["heading"], opacity=0.6, wrap=True); scroll_b_ctx.set_child(self.lbl_back_ctx)
        self.text_container.append(scroll_b_ctx)
        self.text_container.append(Gtk.Separator())
        scroll_b = Gtk.ScrolledWindow(); scroll_b.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC); scroll_b.set_max_content_height(300); scroll_b.set_propagate_natural_height(True); 
        self.lbl_back = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, css_classes=["card-text"])
        self.lbl_back.set_wrap_mode(Pango.WrapMode.WORD_CHAR); scroll_b.set_child(self.lbl_back)
        self.text_container.append(scroll_b)
        
        self.flash_overlay = Gtk.Overlay()
        self.flash_overlay.set_child(self.text_container)
        self.flash_box = Gtk.Box(); self.flash_box.set_halign(Gtk.Align.FILL); self.flash_box.set_valign(Gtk.Align.FILL); self.flash_box.set_opacity(0); self.flash_box.set_can_target(False)
        self.flash_overlay.add_overlay(self.flash_box)
        self.content_back.append(self.flash_overlay)
        
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_homogeneous(True); btn_box.set_halign(Gtk.Align.FILL); btn_box.set_margin_start(10); btn_box.set_margin_end(10)
        self.btn_good = Gtk.Button(label="Good"); self.btn_good.add_css_class("btn-green"); self.btn_good.set_size_request(-1, 55); self.btn_good.connect("clicked", lambda b: self.rate_card(3))
        btn_hard = Gtk.Button(label="Hard"); btn_hard.add_css_class("btn-yellow"); btn_hard.set_size_request(-1, 55); btn_hard.connect("clicked", lambda b: self.rate_card(2))
        btn_miss = Gtk.Button(label="Miss"); btn_miss.add_css_class("btn-red"); btn_miss.set_size_request(-1, 55); btn_miss.connect("clicked", lambda b: self.rate_card(1))
        btn_box.append(self.btn_good); btn_box.append(btn_hard); btn_box.append(btn_miss); 
        self.content_back.append(btn_box)
        self.card_stack.add_named(self.content_back, "back")
    
    def refresh_view(self):
        # Reset input lock so user can interact with the new card
        self.input_locked = False 
        
        self.hint_used = False
        total = len(self.cards)
        
        # Update progress bar logic...
        if total > 0: self.progress_bar.set_fraction(self.current_index / total); self.lbl_progress.set_label(f"{self.current_index + 1} / {total}")
        else: self.progress_bar.set_fraction(0); self.lbl_progress.set_label("0 / 0")
        
        self.btn_card_edit.set_visible(self.cards and self.current_index < len(self.cards))
        
        if self.total_cards_in_deck == 0: 
            self.card_stack.set_visible_child_name("void")
            self.lbl_progress.set_label("0 / 0")
            return

        if not self.cards: self.card_stack.set_visible_child_name("empty"); return

        # --- FIX: DOUBLE AUDIO PREVENTION ---
        if self.current_index >= len(self.cards): 
            self.card_stack.set_visible_child_name("done")
            self.lbl_progress.set_label(f"{total} / {total}")
            
            # Only play sound if NOT already finished
            if not self.has_finished_deck:
                self.has_finished_deck = True
                self.play_sound("cheering")
            return
        # ------------------------------------

        # Reset finish flag if we are viewing cards again
        self.has_finished_deck = False
        
        card = self.cards[self.current_index]
        f_text = card["back"] if self.is_reverse_mode else card["front"]; b_text = card["front"] if self.is_reverse_mode else card["back"]
        self.lbl_front.set_markup(db.format_text(f_text)); self.lbl_back_ctx.set_markup(db.format_text(f_text)); self.lbl_back.set_markup(db.format_text(b_text))
        tags = card.get("tags", []); self.lbl_tags.set_text("#" + " #".join(tags)) if tags else self.lbl_tags.set_text("")
        hint_txt = card.get("hint", ""); self.btn_hint.set_visible(bool(hint_txt)); self.lbl_hint.set_text(hint_txt); self.lbl_hint.set_visible(False)
        
        # Image Logic
        img_visible = False
        self.current_img_path = None # Reset tracker
        if card.get("image"):
            path = db.get_asset_path(card["image"])
            if path and os.path.exists(path): 
                self.img_front.set_filename(path)
                self.img_back.set_filename(path)
                self.current_img_path = path # Store for lightbox
                img_visible = True
        self.img_front.set_visible(img_visible)
        self.img_back.set_visible(img_visible)

        audio_visible = False
        if card.get("audio") and db.get_asset_path(card["audio"]): audio_visible = True
        self.btn_audio_front.set_visible(audio_visible); self.btn_audio_back.set_visible(audio_visible)
        self.card_stack.set_visible_child_name("front"); self.is_flipped = False

    def on_hint_clicked(self, btn): self.hint_used = True; self.btn_hint.set_visible(False); self.lbl_hint.set_visible(True)
    
    def flip_card(self, *args):
        # Prevent flipping if already locked (though unlikely here)
        if self.input_locked or self.is_editing: return # <--- ADD check here

        self.play_sound("flip")
        self.card_stack.set_visible_child_name("back")
        self.is_flipped = True
        
        # Disable "Good" if hint used
        if self.hint_used: 
            self.btn_good.set_sensitive(False)
            self.btn_good.set_tooltip_text("Disabled because Hint was used")
        else: 
            self.btn_good.set_sensitive(True)
            self.btn_good.set_tooltip_text("")

        # FIX: Lock input for 300ms to prevent ghost clicks on grading buttons
        self.input_locked = True
        GLib.timeout_add(300, self._unlock_input)

    def _unlock_input(self):
        self.input_locked = False
        return False

    def setup_gestures(self):
        # Swipe Controller (Left/Right/Up)
        swipe = Gtk.GestureSwipe()
        # Note: GestureSwipe automatically detects X/Y velocity.
        # We handle direction logic inside on_swipe instead.
        swipe.connect("swipe", self.on_swipe)
        self.add_controller(swipe)

    def on_swipe(self, controller, vel_x, vel_y):
        if self.input_locked or self.is_editing: return # <--- ADD check here
        
        # Only handle swipes if we are looking at the BACK of a card
        if not self.is_flipped: 
            return

        # Check if the swipe is vertical or horizontal
        if abs(vel_y) > abs(vel_x):
            # VERTICAL SWIPE
            if vel_y < 0: # Swipe Up -> Hard
                self.rate_card(2)
        else:
            # HORIZONTAL SWIPE
            if vel_x > 0: # Swipe Right -> Good
                if not self.hint_used: 
                    self.rate_card(3)
                else: 
                    # Feedback if they try to mark Good after using a hint
                    toast = Adw.Toast.new("Cannot swipe 'Good' when Hint is used.")
                    self.get_root().get_content().add_toast(toast)
            elif vel_x < 0: # Swipe Left -> Miss
                self.rate_card(1)

    def rate_card(self, rating):
        # 1. Check Lock
        if self.input_locked or self.is_editing: return # <--- ADD check here
        
        # 2. LOCK IMMEDIATELY to prevent accidental swipes (e.g. "Good" click + micro-swipe up)
        self.input_locked = True 
        
        color_class = ""
        if rating == 3: color_class = "flash-success"
        elif rating == 2: color_class = "flash-warning"
        elif rating == 1: color_class = "flash-error"
        
        self.flash_box.set_css_classes([color_class])
        self.flash_box.set_opacity(1.0) 
        
        def fade_out():
            self.flash_box.set_opacity(0)
            self._finalize_rating(rating)
            return False

        GLib.timeout_add(150, fade_out)

    def _finalize_rating(self, rating):
        if rating == 3: self.play_sound("good")
        elif rating == 1: self.play_sound("miss")
        
        self.session_stats["total"] += 1
        if rating == 3: self.session_stats["good"] += 1
        elif rating == 2: self.session_stats["hard"] += 1
        elif rating == 1: self.session_stats["miss"] += 1
        
        if not self.is_cram_mode: 
            db.update_card_progress(self.filename, self.cards[self.current_index]["id"], rating, self.session_id, self.hint_used)
            
        self.current_index += 1
        self.refresh_view()

    def play_sound(self, type):
        settings = db.load_settings()
        if not settings.get("sound_enabled", True): return

        # 1. Locate the App's Assets Folder
        # This works in Flatpak (/app/share/flipstack/assets) AND Local (flipstack/assets)
        app_install_dir = os.path.dirname(os.path.abspath(__file__))
        app_assets_dir = os.path.join(app_install_dir, "assets", "sounds")

        # 2. Define our bundled sounds
        # Note: We renamed them to simple names (good.oga, miss.oga) when copying
        sound_map = {
            "good": os.path.join(app_assets_dir, "good.oga"),
            "miss": os.path.join(app_assets_dir, "miss.oga"),
            "flip": os.path.join(app_assets_dir, "flip.wav"),
            #New: Cheering sound on session complete
            "cheering": os.path.join(app_assets_dir, "cheering.wav")
        }

        # 3. Play
        target_path = sound_map.get(type)
        if target_path and os.path.exists(target_path):
            threading.Thread(target=lambda: subprocess.run(["paplay", target_path], stderr=subprocess.DEVNULL), daemon=True).start()
        else:
            print(f"Sound Warning: Missing asset '{target_path}'")
    
    def on_play_card_audio(self, btn):
        if not self.cards: return
        card = self.cards[self.current_index]
        if card.get("audio"):
            path = db.get_asset_path(card["audio"])
            if path and os.path.exists(path): threading.Thread(target=lambda: subprocess.run(["paplay", path]), daemon=True).start()
    
    def on_speak_clicked(self, btn):
        if not self.cards: return
        card = self.cards[self.current_index]
        if card.get("audio") and db.get_asset_path(card["audio"]): self.on_play_card_audio(None); return
        text = card["back"] if self.is_flipped else card["front"]
        if self.is_reverse_mode: text = card["front"] if self.is_flipped else card["back"]
        threading.Thread(target=lambda: subprocess.run(["spd-say", text]), daemon=True).start()
    
    # FIXED: Restart session also resets stats WITH ID
    def restart_session(self): 
        self.has_finished_deck = False # <--- Reset flag
        self.current_index = 0
        self.session_id = str(uuid.uuid4())
        self.session_stats = {"good": 0, "hard": 0, "miss": 0, "total": 0, "session_id": self.session_id}
        self.load_cards()
        self.refresh_view()
    
    def on_reverse_toggled(self, btn): self.is_reverse_mode = btn.get_active(); self.refresh_view()
    
    def on_cram_toggled(self, btn, force_on=False):
        self.has_finished_deck = False # <--- Reset flag
        if force_on: self.is_cram_mode = True
        else: self.is_cram_mode = btn.get_active()
        self.current_index = 0; self.load_cards(); self.refresh_view()
    
    def on_shuffle_clicked(self, btn):
        if not self.cards: return
        rem = self.cards[self.current_index:]; done = self.cards[:self.current_index]; random.shuffle(rem); self.cards = done + rem; self.refresh_view(); toast = Adw.Toast.new("Cards Shuffled"); self.get_root().get_content().add_toast(toast)
    
    def on_key_pressed(self, controller, keyval, keycode, state):
        if self.input_locked or self.is_editing: return # <--- ADD check here

        if keyval == Gdk.KEY_space and not self.is_flipped: 
            self.flip_card()
            return True
            
        if self.is_flipped:
            if keyval == Gdk.KEY_1:
                # FIX: Check if hint was used before allowing "Good"
                if self.hint_used:
                    # Optional: Visual feedback that it's disabled
                    toast = Adw.Toast.new("Cannot score 'Good' when Hint is used.")
                    self.get_root().get_content().add_toast(toast)
                    return True
                self.rate_card(3)
                return True
            if keyval == Gdk.KEY_2: self.rate_card(2); return True
            if keyval == Gdk.KEY_3: self.rate_card(1); return True
        return False
    
    def on_add_clicked(self, *args): self.show_card_dialog(mode="add")
    
    def on_edit_clicked(self, *args):
        if not self.cards or self.current_index >= len(self.cards): return
        card = self.cards[self.current_index]; self.show_card_dialog(mode="edit", card=card)

    def show_card_dialog(self, mode, card=None):
        self.is_editing = True # <--- LOCK INPUTS IMMEDIATELY
        title = "Add Card" if mode == "add" else "Edit Card"
        d = Adw.MessageDialog(heading=title, transient_for=self.get_root())
        d.set_modal(True)
        d.add_response("cancel", "Cancel")
        d.add_response("save", "Save")
        d.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        
        # Responsive Height Check
        win_width = self.get_root().get_width()
        is_narrow = win_width < 500
        box_height = 90 if is_narrow else 150
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        # Front
        box.append(Gtk.Label(label="Front", xalign=0))
        tf = Gtk.TextView(); tf.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        tf.set_left_margin(10); tf.set_right_margin(10)
        tf.set_top_margin(10); tf.set_bottom_margin(10)
        if card: tf.get_buffer().set_text(card.get("front", ""))

        scroll_f = Gtk.ScrolledWindow(min_content_height=box_height) 
        scroll_f.set_propagate_natural_height(True)
        scroll_f.set_hexpand(True)
        scroll_f.set_child(tf)
        box.append(Gtk.Frame(child=scroll_f))
        
        # Back
        box.append(Gtk.Label(label="Back", xalign=0))
        tb = Gtk.TextView(); tb.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        tb.set_left_margin(10); tb.set_right_margin(10)
        tb.set_top_margin(10); tb.set_bottom_margin(10)
        if card: tb.get_buffer().set_text(card.get("back", ""))

        scroll_b = Gtk.ScrolledWindow(min_content_height=box_height)
        scroll_b.set_propagate_natural_height(True)
        scroll_b.set_hexpand(True)
        scroll_b.set_child(tb)
        box.append(Gtk.Frame(child=scroll_b))
        
        # Metadata
        box.append(Gtk.Label(label="Hint (Optional)", xalign=0)); th = Gtk.Entry()
        if card: th.set_text(card.get("hint", ""))
        box.append(th)
        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        box.append(Gtk.Label(label="Tags (comma separated)", xalign=0)); ent_tags = Gtk.Entry() 
        if card: ent_tags.set_text(", ".join(card.get("tags", [])))
        box.append(ent_tags)

        self.temp_img = card.get("image") if card else None
        self.temp_aud = card.get("audio") if card else None

        # Media Rows
        row_img = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_img = Gtk.Label(label=os.path.basename(self.temp_img) if self.temp_img else "No Image", hexpand=True, xalign=0)
        lbl_img.set_ellipsize(3)
        btn_img_del = Gtk.Button(icon_name="user-trash-symbolic", visible=bool(self.temp_img))
        btn_img_add = Gtk.Button(icon_name="insert-image-symbolic")
        
        def on_img_del(b): self.temp_img = None; lbl_img.set_label("No Image"); btn_img_del.set_visible(False)
        def on_img_pick(b): self.pick_file("image", lambda p: setattr(self, 'temp_img', p) or lbl_img.set_label(os.path.basename(p)) or btn_img_del.set_visible(True))
        btn_img_del.connect("clicked", on_img_del); btn_img_add.connect("clicked", on_img_pick)
        row_img.append(lbl_img); row_img.append(btn_img_add); row_img.append(btn_img_del); box.append(row_img)

        row_aud = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_aud = Gtk.Label(label=os.path.basename(self.temp_aud) if self.temp_aud else "No Audio", hexpand=True, xalign=0)
        lbl_aud.set_ellipsize(3)
        btn_aud_del = Gtk.Button(icon_name="user-trash-symbolic", visible=bool(self.temp_aud))
        btn_aud_add = Gtk.Button(icon_name="audio-volume-high-symbolic")
        
        def on_aud_del(b): self.temp_aud = None; lbl_aud.set_label("No Audio"); btn_aud_del.set_visible(False)
        def on_aud_pick(b): self.pick_file("audio", lambda p: setattr(self, 'temp_aud', p) or lbl_aud.set_label(os.path.basename(p)) or btn_aud_del.set_visible(True))
        btn_aud_del.connect("clicked", on_aud_del); btn_aud_add.connect("clicked", on_aud_pick)
        row_aud.append(lbl_aud); row_aud.append(btn_aud_add); row_aud.append(btn_aud_del); box.append(row_aud)

        # FIX: Layout Inversion (Scroll -> Clamp -> Content)
        # This puts the scrollbar at the dialog edge, not overlaying text.
        scroll_main = Gtk.ScrolledWindow()
        scroll_main.set_propagate_natural_height(True)
        scroll_main.set_max_content_height(500) 

        clamp = Adw.Clamp(maximum_size=800)
        # Add padding to keep text off the scrollbar
        clamp.set_margin_start(12); clamp.set_margin_end(12); clamp.set_margin_bottom(12)
        clamp.set_child(box)
        
        scroll_main.set_child(clamp)
        d.set_extra_child(scroll_main)

        def on_r(dlg, res):
            if res == "save":
                bf, bb = tf.get_buffer(), tb.get_buffer()
                f = bf.get_text(bf.get_start_iter(), bf.get_end_iter(), True).strip()
                b = bb.get_text(bb.get_start_iter(), bb.get_end_iter(), True).strip()
                tags = [t.strip() for t in ent_tags.get_text().split(",") if t.strip()]
                hint_val = th.get_text().strip()
                if f and b:
                    if mode == "add": db.add_card_to_deck(self.filename, f, b, self.temp_img, self.temp_aud, tags, hint_val)
                    else: db.edit_card(self.filename, card["id"], f, b, self.temp_img, self.temp_aud, tags, card.get("suspended", False), hint_val)
                    self.load_cards(); self.refresh_view()
            
            # --- UNLOCK LOGIC ---
            # We delay unlocking slightly to swallow any "Enter/Space" key release events 
            # that triggered the Save button, preventing them from flipping the card underneath.
            def unlock():
                self.is_editing = False
                return False
            GLib.timeout_add(200, unlock) 
            
        d.connect("response", on_r)
        d.present()

    def pick_file(self, type_hint, callback):
        if hasattr(Gtk, "FileDialog"):
            d = Gtk.FileDialog(); f = Gtk.FileFilter()
            if type_hint == "image": f.set_name("Images"); f.add_pixbuf_formats()
            elif type_hint == "audio": f.set_name("Audio"); f.add_mime_type("audio/*")
            filters = Gio.ListStore.new(Gtk.FileFilter); filters.append(f); d.set_filters(filters); d.set_default_filter(f)
            def on_o(f, r):
                try: 
                    res = f.open_finish(r)
                    if res: 
                        path = res.get_path()
                        if type_hint == "audio" and os.path.getsize(path) > 10 * 1024 * 1024: toast = Adw.Toast.new("File too large! Max 10MB."); self.get_root().get_content().add_toast(toast); return
                        callback(path)
                except: pass
            d.open(self.get_root(), None, on_o)

            # --- NEW: LIGHTBOX METHODS ---
    def on_image_click(self, gesture, n_press, x, y):
        if self.current_img_path:
            self.show_lightbox(self.current_img_path)

    def show_lightbox(self, path):
        # Create a modal window
        win = Adw.Window(title="Image View")
        win.set_modal(True)
        win.set_transient_for(self.get_root())
        
        # Adaptive size (90% of screen)
        root_w = self.get_root().get_width()
        root_h = self.get_root().get_height()
        win.set_default_size(int(root_w * 0.9), int(root_h * 0.9))
        
        # Toolbar
        tb_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        tb_view.add_top_bar(header)
        
        # FIX: Add a container with margins to act as a "Matte"
        # This forces a 20px gap around the image so it never touches the border
        matte = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        matte.set_margin_top(20)
        matte.set_margin_bottom(20)
        matte.set_margin_start(20)
        matte.set_margin_end(20)
        
        # The Picture
        pic = Gtk.Picture.new_for_filename(path)
        # CONTAIN ensures the aspect ratio is preserved
        pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        # can_shrink is crucial to stop it from forcing the window larger
        pic.set_can_shrink(True) 
        
        # Expand to fill the "matte" box (minus the margins)
        pic.set_hexpand(True)
        pic.set_vexpand(True)
        
        matte.append(pic)
        tb_view.set_content(matte)
        
        win.set_content(tb_view)
        win.present()