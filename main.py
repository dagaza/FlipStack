import sys
import os

# We force the 'cairo' renderer before GTK initializes. 
# This fixes list scrolling artifacts/jitter on many Linux systems.
os.environ["GSK_RENDERER"] = "gl"

import gi
import data_engine as db
import study_session 
import deck_editor
import performance_view 
import dashboard_view 
import traceback
import re

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Adw, Gio, Gdk, GObject, GLib, Pango, PangoCairo

class FlipStackWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="FlipStack")
        self.set_size_request(1200, 900) 

        # --- THEME LOGIC START ---
        self.settings = db.load_settings()
        style_manager = Adw.StyleManager.get_default()
        
        # Check saved setting. Default to 'system' if not found.
        saved_theme = self.settings.get("theme", "system")
        
        if saved_theme == "dark":
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        elif saved_theme == "light":
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)
        # --- THEME LOGIC END ---
        
        # Base CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            .red-icon { color: #ed333b; }
            .red-icon:hover { color: #c01c28; background: alpha(#ed333b, 0.1); }
            
            .heatmap-box { border-radius: 2px; }
            
            /* DYNAMIC COLOR FIX:
               Uses the text color (@theme_fg_color) with low opacity.
               - Dark Mode: 10% White = Dark Gray (Preserves the look you like)
               - Light Mode: 10% Black = Light Gray (Fixes the black box bug)
            */
            .hm-0 { background-color: alpha(@theme_fg_color, 0.1); }
            
            /* Future dates: Transparent with a subtle border so it works in both modes */
            .hm-future { background-color: transparent; border: 1px solid alpha(@theme_fg_color, 0.2); }
            
            /* Green scaling logic */
            .hm-1 { background-color: #26a269; opacity: 0.4; }
            .hm-2 { background-color: #26a269; opacity: 0.6; }
            .hm-3 { background-color: #26a269; opacity: 0.8; }
            .hm-4 { background-color: #26a269; opacity: 1.0; }
        """)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # Dynamic Font CSS Provider
        self.font_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.font_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(main_vbox)
        self.set_content(self.toast_overlay)

        self.header_bar = Adw.HeaderBar()
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base_dir, "assets", "Icons", "io.github.dagaza.FlipStack.svg")
       
        if os.path.exists(logo_path):
            self.logo_img = Gtk.Image.new_from_file(logo_path)
        else:
            # Fallback if something goes wrong
            self.logo_img = Gtk.Image.new_from_icon_name("applications-science-symbolic")

        self.logo_img.set_pixel_size(32)
        
        logo_box = Gtk.Box()
        logo_box.set_margin_start(8)
        logo_box.set_margin_end(8)
        logo_box.append(self.logo_img)
        
        self.header_bar.pack_start(logo_box)
        # -----------------------------------------

        main_vbox.append(self.header_bar)

        self.split_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.split_box.set_vexpand(True)
        main_vbox.append(self.split_box)

        # Sidebar
        self.sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.sidebar.set_size_request(450, -1); self.sidebar.set_hexpand(False)
        self.sidebar.add_css_class("background")
        self.split_box.append(self.sidebar)
        self.split_box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # --- Sidebar Toolbar ---
        toolbar_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        toolbar_container.set_margin_top(10); toolbar_container.set_margin_bottom(10)
        toolbar_container.set_margin_start(10); toolbar_container.set_margin_end(10)
        
        # Left Group
        group_left = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        btn_dash = Gtk.Button(icon_name="go-home-symbolic"); btn_dash.set_tooltip_text("Dashboard"); btn_dash.add_css_class("flat"); btn_dash.connect("clicked", self.on_dashboard_clicked); group_left.append(btn_dash)
        btn_search = Gtk.ToggleButton(icon_name="system-search-symbolic"); btn_search.set_tooltip_text("Search"); btn_search.add_css_class("flat"); btn_search.connect("toggled", self.on_search_toggled); group_left.append(btn_search)
        btn_import = Gtk.Button(icon_name="document-open-symbolic"); btn_import.set_tooltip_text("Import Deck"); btn_import.add_css_class("flat"); btn_import.connect("clicked", self.on_import_clicked); group_left.append(btn_import)
        btn_export = Gtk.Button(icon_name="document-save-symbolic"); btn_export.set_tooltip_text("Export Deck"); btn_export.add_css_class("flat"); btn_export.connect("clicked", self.on_export_clicked); group_left.append(btn_export)
        btn_backup = Gtk.Button(icon_name="document-save-as-symbolic"); btn_backup.set_tooltip_text("Backup All Data"); btn_backup.add_css_class("flat"); btn_backup.connect("clicked", self.on_backup_clicked); group_left.append(btn_backup)
        btn_help = Gtk.Button(icon_name="help-about-symbolic"); btn_help.set_tooltip_text("Help & About"); btn_help.add_css_class("flat"); btn_help.connect("clicked", self.on_help_clicked); group_left.append(btn_help)
        
        toolbar_container.append(group_left); toolbar_container.append(Gtk.Label(hexpand=True))

        # Center Group
        group_center = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.settings = db.load_settings()
        
        self.btn_sound = Gtk.Button(); self.btn_sound.set_tooltip_text("Toggle Sounds"); self.btn_sound.add_css_class("flat"); self.update_sound_icon(); self.btn_sound.connect("clicked", self.on_sound_toggle); group_center.append(self.btn_sound)
        
        # Font Settings Button
        btn_font = Gtk.Button(icon_name="preferences-desktop-font-symbolic"); btn_font.set_tooltip_text("Text Settings"); btn_font.add_css_class("flat"); btn_font.connect("clicked", self.on_font_clicked); group_center.append(btn_font)
        
        btn_theme = Gtk.Button(icon_name="weather-clear-night-symbolic"); btn_theme.set_tooltip_text("Toggle Theme"); btn_theme.add_css_class("flat"); btn_theme.connect("clicked", self.on_theme_toggle); group_center.append(btn_theme)
        toolbar_container.append(group_center); toolbar_container.append(Gtk.Label(hexpand=True))

        # Right Group
        group_right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        btn_cat = Gtk.Button(icon_name="folder-new-symbolic"); btn_cat.set_tooltip_text("New Category"); btn_cat.add_css_class("flat"); btn_cat.connect("clicked", self.on_new_category_clicked); group_right.append(btn_cat)
        btn_new = Gtk.Button(icon_name="list-add-symbolic"); btn_new.set_tooltip_text("Create New Deck"); btn_new.add_css_class("suggested-action"); btn_new.connect("clicked", self.on_new_deck_clicked); group_right.append(btn_new)
        toolbar_container.append(group_right)
        self.sidebar.append(toolbar_container)

        self.search_revealer = Gtk.Revealer(); self.search_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.search_entry = Gtk.SearchEntry(placeholder_text="Search cards or #tag..."); self.search_entry.set_margin_start(10); self.search_entry.set_margin_end(10); self.search_entry.set_margin_bottom(10); self.search_entry.connect("search-changed", self.on_search_changed); self.search_revealer.set_child(self.search_entry); self.sidebar.append(self.search_revealer)

        self.sidebar_scroll = Gtk.ScrolledWindow(); self.sidebar_scroll.set_vexpand(True)
        self.deck_list = Gtk.ListBox(); self.deck_list.add_css_class("navigation-sidebar")
        self.deck_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.deck_list.connect("row-selected", self.on_deck_selected)
        self.sidebar_scroll.set_child(self.deck_list)
        self.sidebar.append(self.sidebar_scroll)

        self.right_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); self.right_panel.set_hexpand(True); self.split_box.append(self.right_panel)
        self.content_stack = Gtk.Stack(); self.content_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE); self.right_panel.append(self.content_stack)

        self.placeholder = Adw.StatusPage(icon_name="folder-open-symbolic", title="Ready to Study", description="Select a deck or go to Dashboard.")
        self.content_stack.add_named(self.placeholder, "placeholder")

        self.dash_view = dashboard_view.DashboardView()
        self.content_stack.add_named(self.dash_view, "dashboard")
        
        self.search_view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.search_results_list = Gtk.ListBox(); self.search_results_list.add_css_class("boxed-list")
        s_s = Gtk.ScrolledWindow(); s_s.set_child(self.search_results_list)
        self.search_view.append(s_s)
        self.content_stack.add_named(self.search_view, "global_search")

        self.apply_font_settings() # Apply saved fonts on startup
        self.refresh_sidebar()
        self.on_dashboard_clicked(None) 

        self.set_default_size(1280, 900)

        if self.settings.get("first_run", True):
            GLib.idle_add(self.show_welcome_dialog)

    def natural_sort_key(self, s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]    

    # --- FONT LOGIC (Modern) ---
    def on_font_clicked(self, btn):
        # 1. Get system fonts
        font_map = PangoCairo.FontMap.get_default()
        families = font_map.list_families()
        font_names = sorted([f.get_name() for f in families])
        
        curr_font = self.settings.get("font_family", "Cantarell")
        if curr_font not in font_names:
            font_names.insert(0, curr_font)

        # 2. Controls
        sl_fonts = Gtk.StringList.new(font_names)
        dropdown = Gtk.DropDown(model=sl_fonts, enable_search=True)
        try:
            dropdown.set_selected(font_names.index(curr_font))
        except ValueError:
            dropdown.set_selected(0)

        # -- SHARED ADJUSTMENT --
        curr_size = self.settings.get("font_size", 16)
        adj = Gtk.Adjustment(value=curr_size, lower=8, upper=72, step_increment=1, page_increment=5, page_size=0)
        
        spin_size = Gtk.SpinButton(adjustment=adj, climb_rate=1, digits=0)
        scale_size = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
        scale_size.set_digits(0) 
        scale_size.set_draw_value(False) 
        scale_size.set_hexpand(True)
        scale_size.add_mark(16, Gtk.PositionType.BOTTOM, None) 

        # -- Preview Setup
        entry_preview = Gtk.Entry(placeholder_text="Type here to check language support...")
        entry_preview.set_text("The quick brown fox jumps over the lazy dog. 12345")

        scroll_preview = Gtk.ScrolledWindow()
        scroll_preview.set_size_request(-1, 120)
        scroll_preview.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll_preview.add_css_class("view") 

        lbl_preview = Gtk.Label()
        lbl_preview.set_wrap(True)
        lbl_preview.set_max_width_chars(60)
        scroll_preview.set_child(lbl_preview)
        
        lbl_preview_heading = Gtk.Label(label="Live Preview", xalign=0, css_classes=["heading"])
        
        frame_preview = Gtk.Frame() # Removed label from here
        preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        preview_box.set_margin_top(10); preview_box.set_margin_bottom(10)
        preview_box.set_margin_start(10); preview_box.set_margin_end(10)
        preview_box.append(entry_preview)
        preview_box.append(Gtk.Separator())
        preview_box.append(scroll_preview)
        frame_preview.set_child(preview_box)

        # 3. Dynamic Update Logic
        def update_preview(*args):
            selected_item = dropdown.get_selected_item()
            if not selected_item: return
            f_name = selected_item.get_string()
            f_size = int(adj.get_value())
            
            raw_text = entry_preview.get_text()
            escaped_text = GLib.markup_escape_text(raw_text)
            markup = f"<span font_desc='{f_name} {f_size}'>{escaped_text}</span>"
            lbl_preview.set_markup(markup)

        dropdown.connect("notify::selected-item", update_preview)
        adj.connect("value-changed", update_preview)
        entry_preview.connect("changed", update_preview)
        update_preview()

        # 4. Layout
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_top(10)
        
        box.set_size_request(600, -1) 
        
        size_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        size_box.append(scale_size)
        size_box.append(spin_size)

        grid = Gtk.Grid(column_spacing=20, row_spacing=10)
        grid.attach(Gtk.Label(label="Font Family", xalign=0, css_classes=["heading"]), 0, 0, 1, 1)
        dropdown.set_hexpand(True) 
        grid.attach(dropdown, 1, 0, 1, 1)
        
        grid.attach(Gtk.Label(label="Size", xalign=0, css_classes=["heading"]), 0, 1, 1, 1)
        grid.attach(size_box, 1, 1, 1, 1)
        
        box.append(grid)
        
        box.append(lbl_preview_heading)
        box.append(frame_preview)

        # 5. Dialog Setup
        dialog = Adw.MessageDialog(heading="Text Settings", transient_for=self)
        dialog.set_extra_child(box)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def on_response(d, response):
            if response == "save":
                selected_item = dropdown.get_selected_item()
                if selected_item:
                    self.settings["font_family"] = selected_item.get_string()
                    self.settings["font_size"] = int(adj.get_value())
                    db.save_settings(self.settings)
                    self.apply_font_settings()
            d.close()

        dialog.connect("response", on_response)
        dialog.present()

    def apply_font_settings(self):
        fam = self.settings.get("font_family", "Cantarell")
        size = self.settings.get("font_size", 16)
        css = f"""
        .card-text {{
            font-family: "{fam}";
            font-size: {size}px;
        }}
        """
        self.font_provider.load_from_data(css.encode('utf-8'))

    # --- Callbacks ---
    def update_sound_icon(self):
        icon = "audio-volume-high-symbolic" if self.settings.get("sound_enabled", True) else "audio-volume-muted-symbolic"
        self.btn_sound.set_icon_name(icon)

    def on_sound_toggle(self, btn):
        current = self.settings.get("sound_enabled", True); self.settings["sound_enabled"] = not current; db.save_settings(self.settings); self.update_sound_icon()

    def go_back_to_dashboard(self):
        self.on_dashboard_clicked(None)

    def on_dashboard_clicked(self, btn):
        self.content_stack.set_visible_child_name("dashboard"); self.deck_list.select_row(None); 
        if hasattr(self.dash_view, 'refresh'): self.dash_view.refresh()

    def on_backup_clicked(self, btn):
        if db.create_backup(): self.toast_overlay.add_toast(Adw.Toast.new("Backup created in 'backups/'"))
        else: self.toast_overlay.add_toast(Adw.Toast.new("Backup failed"))

    def on_help_clicked(self, btn):
        self.show_welcome_dialog(first_run_trigger=False)

    def show_welcome_dialog(self, first_run_trigger=True):
        # 1. First Run Logic (Create Tutorial Deck)
        if first_run_trigger:
            self.settings["first_run"] = False
            db.save_settings(self.settings)
            
            # Create the deck silently
            db.create_tutorial_deck()
            self.refresh_sidebar() 

        # 2. Build the Dialog
        d = Adw.MessageDialog(heading="Welcome to FlipStack!", transient_for=self)
        d.add_response("ok", "Got it!")
        d.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        
        # Main Content Box
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        box.set_margin_top(10)
        
        # --- A. New User Banner (Only on first run) ---
        if first_run_trigger:
            info_bar = Gtk.Box(spacing=10)
            info_bar.add_css_class("card") # Gives it a nice background look
            info_bar.set_margin_bottom(10)
            icon = Gtk.Image.new_from_icon_name("emblem-favorite-symbolic")
            icon.add_css_class("red-icon")
            lbl = Gtk.Label(label="<b>We created a 'Welcome' deck for you!</b>\nTry playing it to learn the basics.", use_markup=True, xalign=0)
            info_bar.append(icon)
            info_bar.append(lbl)
            box.append(info_bar)
        
        # --- B. The Full Manual (Always visible) ---
        box.append(Gtk.Label(label="<b>📚 Basics</b>", use_markup=True, xalign=0))
        lbl_basic = Gtk.Label(label="Create Categories and Decks to organize your flashcards.\nUse tags (e.g. #history) to group cards across decks.", xalign=0, wrap=True)
        lbl_basic.set_max_width_chars(50)
        box.append(lbl_basic)
        
        box.append(Gtk.Label(label="<b>🧠 Study Modes</b>", use_markup=True, xalign=0))
        lbl_modes = Gtk.Label(label="• <b>Standard:</b> Spaced Repetition (Leitner system) for efficient long-term retention.\n• <b>Cram:</b> Review all cards instantly.\n• <b>Reverse:</b> Flip Question/Answer sides.", use_markup=True, xalign=0, wrap=True)
        lbl_modes.set_max_width_chars(50); box.append(lbl_modes)
        
        box.append(Gtk.Label(label="<b>📊 Grading</b>", use_markup=True, xalign=0))
        lbl_grade = Gtk.Label(label="• <b>Good (1):</b> Card returns later.\n• <b>Hard (2):</b> Card returns sooner.\n• <b>Miss (3):</b> Card returns tomorrow.", use_markup=True, xalign=0, wrap=True)
        lbl_grade.set_max_width_chars(50)
        box.append(lbl_grade)
        
        box.append(Gtk.Label(label="<b>⌨️ Shortcuts</b>", use_markup=True, xalign=0))
        lbl_keys = Gtk.Label(label="• <b>Space:</b> Flip Card\n• <b>1 / 2 / 3:</b> Rate (Good / Hard / Miss)", use_markup=True, xalign=0, wrap=True)
        lbl_keys.set_max_width_chars(50)
        box.append(lbl_keys)

        # Updated: Dual Install Instructions for Fonts
        box.append(Gtk.Label(label="<b>🔤 Fonts</b>", use_markup=True, xalign=0))
        lbl_fonts = Gtk.Label(label="• <b>Missing Chars:</b> If you see boxes (□), the font doesn't support your language.\n• <b>Install:</b> Once you download and install a new font on your machine, the app will automatically detect it, and you may be able to start using it for your card fonts (restart required after installing a new font).", use_markup=True, xalign=0, wrap=True)
        lbl_fonts.set_max_width_chars(50); box.append(lbl_fonts)

        # 3. Present
        d.set_extra_child(box)
        d.present()

    def on_theme_toggle(self, btn):
        manager = Adw.StyleManager.get_default()
        if manager.get_dark(): manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        else: manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

    def refresh_sidebar(self, search_query=""):
        # stats = db.load_stats() <-- Removed since we're not using it, check if anything breaks and then delete if not
        
        while child := self.deck_list.get_first_child(): 
            self.deck_list.remove(child)
            
        all_files = db.get_all_decks()
        raw_cats = db.get_categories()
        if "Uncategorized" not in raw_cats: raw_cats.append("Uncategorized")
        
        others = [c for c in raw_cats if c != "Uncategorized"]
        others.sort(key=self.natural_sort_key)
        sorted_categories = ["Uncategorized"] + others
        
        grouped = {c: [] for c in sorted_categories}
        for f in all_files:
            if search_query and search_query.lower() not in f.lower().replace("_", " "): continue
            cat = db.get_deck_category(f)
            target = cat if cat in grouped else "Uncategorized"
            grouped[target].append(f)
            
        for cat in sorted_categories:
            decks = grouped[cat]
            decks.sort(key=self.natural_sort_key)
            
            # --- CATEGORY ROW ---
            cat_row = Gtk.ListBoxRow()
            cat_row.set_selectable(False)
            cat_row.set_activatable(False)
            
            cat_box = Gtk.Box()
            cat_lbl = Gtk.Label(label=cat, xalign=0)
            cat_lbl.add_css_class("heading")
            cat_lbl.set_margin_start(10); cat_lbl.set_margin_top(10); cat_lbl.set_margin_bottom(5)
            
            # NEW: Double-click to rename Category
            if cat != "Uncategorized":
                ctrl_cat = Gtk.GestureClick()
                ctrl_cat.set_button(0) # Listen to all buttons (left click is standard)
                ctrl_cat.connect("pressed", lambda g, n, x, y, c=cat: self.on_category_label_click(n, c))
                cat_lbl.add_controller(ctrl_cat)
            
            cat_box.append(cat_lbl)
            
            if cat != "Uncategorized":
                cat_box.append(Gtk.Label(hexpand=True))
                
                # We wrap the button in a box to control opacity easily
                cat_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
                cat_actions.set_opacity(0) # Hide by default
                
                btn_del = Gtk.Button(icon_name="user-trash-symbolic")
                btn_del.add_css_class("flat")
                btn_del.set_tooltip_text("Delete Category")
                btn_del.connect("clicked", lambda b, c=cat: self.on_delete_category(c))
                
                cat_actions.append(btn_del)
                cat_box.append(cat_actions)
                
                # Add Hover Controller to the ROW (so hovering anywhere on the row reveals the button)
                hover_ctrl = Gtk.EventControllerMotion()
                hover_ctrl.connect("enter", lambda c, x, y, b=cat_actions: b.set_opacity(1))
                hover_ctrl.connect("leave", lambda c, b=cat_actions: b.set_opacity(0))
                cat_row.add_controller(hover_ctrl)
                
            cat_row.set_child(cat_box)
            self.deck_list.append(cat_row)
            
            # --- DECK ROWS ---
            for filename in decks:
                cards = db.load_deck(filename)
                deck_name = filename.replace(".json", "").replace("_", " ").title()
                
                row = Gtk.ListBoxRow()
                row._filename = filename 
                
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                box.set_margin_top(8); box.set_margin_bottom(8)
                box.set_margin_start(30); box.set_margin_end(8)
                
                try: avatar = Adw.Avatar(size=24, text=deck_name, show_initials=True); box.append(avatar)
                except: box.append(Gtk.Image.new_from_icon_name("folder-symbolic"))
                
                vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                vbox.set_margin_start(5)
                
                lbl_name = Gtk.Label(label=deck_name, xalign=0)
                lbl_name.set_ellipsize(3)
                lbl_name.set_max_width_chars(25)
                lbl_name.add_css_class("body")
                
                # NEW: Double-click to rename Deck
                ctrl_deck = Gtk.GestureClick()
                ctrl_deck.set_button(0)
                ctrl_deck.connect("pressed", lambda g, n, x, y, f=filename: self.on_deck_label_click(n, f))
                lbl_name.add_controller(ctrl_deck)
                
                vbox.append(lbl_name)
                
                mastery = db.get_deck_mastery(filename)
                if cards:
                    lvl = Gtk.Box(spacing=5); bar = Gtk.LevelBar(min_value=0, max_value=1.0)
                    bar.set_value(mastery); bar.set_size_request(80, 2)
                    if mastery == 1.0: bar.add_css_class("accent")
                    lvl.append(bar); vbox.append(lvl)
                    
                box.append(vbox); box.append(Gtk.Label(hexpand=True))
                
                actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
                actions_box.set_opacity(0)
                hover_ctrl = Gtk.EventControllerMotion()
                hover_ctrl.connect("enter", lambda c, x, y, b=actions_box: b.set_opacity(1))
                hover_ctrl.connect("leave", lambda c, b=actions_box: b.set_opacity(0))
                row.add_controller(hover_ctrl)
                
                btn_play = Gtk.Button(icon_name="media-playback-start-symbolic")
                btn_play.add_css_class("flat"); btn_play.set_tooltip_text("Study Now")
                btn_play.connect("clicked", lambda b, f=filename: self.open_study_session(f))
                actions_box.append(btn_play)
                
                btn_move = Gtk.Button(icon_name="folder-symbolic")
                btn_move.add_css_class("flat"); btn_move.set_tooltip_text("Move")
                btn_move.connect("clicked", lambda b, f=filename: self.on_move_deck(f))
                actions_box.append(btn_move)
                
                btn_stats = Gtk.Button(icon_name="power-profile-performance-symbolic")
                btn_stats.set_tooltip_text("View Stats"); btn_stats.add_css_class("flat")
                btn_stats.connect("clicked", lambda b, f=filename: self.open_stats_view(f))
                actions_box.append(btn_stats)
                
                btn_edit = Gtk.Button(icon_name="document-edit-symbolic")
                btn_edit.add_css_class("flat"); btn_edit.set_tooltip_text("Edit Deck")
                btn_edit.connect("clicked", lambda b, f=filename: self.open_editor(f))
                actions_box.append(btn_edit)
                
                btn_del = Gtk.Button(icon_name="user-trash-symbolic")
                btn_del.add_css_class("flat"); btn_del.set_tooltip_text("Delete Deck"); btn_del.add_css_class("red-icon")
                btn_del.connect("clicked", lambda b, f=filename: self.on_delete_deck(f))
                actions_box.append(btn_del)
                
                box.append(actions_box)
                row.set_child(box)
                self.deck_list.append(row)

    def on_search_changed(self, entry):
        query = entry.get_text(); self.refresh_sidebar(query)
        if len(query) > 2:
            self.content_stack.set_visible_child_name("global_search")
            while child := self.search_results_list.get_first_child(): self.search_results_list.remove(child)
            results = db.search_all_cards(query)
            if not results: self.search_results_list.append(Adw.ActionRow(title="No cards found"))
            else:
                for res in results:
                    row = Adw.ActionRow(title=res['front'], subtitle=f"{res['deck_name']} • {res['back']}")
                    btn = Gtk.Button(icon_name="go-next-symbolic", css_classes=["flat"])
                    btn.connect("clicked", lambda b, f=res['filename']: self.open_editor(f))
                    row.add_suffix(btn); self.search_results_list.append(row)
        else:
            if self.content_stack.get_visible_child_name() == "global_search": self.content_stack.set_visible_child_name("placeholder")

    def on_search_toggled(self, btn):
        reveal = btn.get_active(); self.search_revealer.set_reveal_child(reveal)
        if reveal: self.search_entry.grab_focus()
        else: self.search_entry.set_text(""); self.content_stack.set_visible_child_name("dashboard")

    def on_move_deck(self, filename):
        dlg = Adw.MessageDialog(transient_for=self, heading="Move Deck"); dlg.add_response("cancel", "Cancel"); dlg.add_response("move", "Move"); dlg.set_response_appearance("move", Adw.ResponseAppearance.SUGGESTED)
        cats = db.get_categories(); sl = Gtk.StringList(); [sl.append(c) for c in cats]; dropdown = Gtk.DropDown(model=sl); curr = db.get_deck_category(filename)
        if curr in cats: dropdown.set_selected(cats.index(curr))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); box.append(Gtk.Label(label="Select Category:")); box.append(dropdown); dlg.set_extra_child(box)
        def on_resp(d, r):
            if r == "move": db.set_deck_category(filename, cats[dropdown.get_selected()]); self.refresh_sidebar(); d.close()
        dlg.connect("response", on_resp); dlg.present()

    def on_new_category_clicked(self, btn):
        dlg = Adw.MessageDialog(transient_for=self, heading="New Category"); dlg.add_response("cancel", "Cancel"); dlg.add_response("create", "Create"); dlg.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED); entry = Gtk.Entry(placeholder_text="Name"); entry.connect("activate", lambda w: dlg.response("create")); dlg.set_extra_child(entry)
        def on_r(d, r):
            if r == "create" and entry.get_text(): db.add_category(entry.get_text()); self.refresh_sidebar(); d.close()
        dlg.connect("response", on_r); dlg.present()

    def on_delete_category(self, cat):
        def c(d, r): 
            if r=="delete": db.delete_category(cat); self.refresh_sidebar()
        dlg = Adw.MessageDialog(transient_for=self, heading=f"Delete {cat}?", body="Decks moved to Uncategorized."); dlg.add_response("cancel", "Cancel"); dlg.add_response("delete", "Delete"); dlg.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE); dlg.connect("response", c); dlg.present()

    def on_new_deck_clicked(self, btn):
        dlg = Adw.MessageDialog(transient_for=self, heading="New Deck"); dlg.add_response("cancel", "Cancel"); dlg.add_response("create", "Create"); dlg.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED); box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); entry = Gtk.Entry(placeholder_text="Deck Name"); box.append(entry); cats = db.get_categories(); sl = Gtk.StringList(); [sl.append(c) for c in cats]; dropdown = Gtk.DropDown(model=sl); box.append(dropdown); dlg.set_extra_child(box)
        def on_r(d, r):
            if r=="create" and entry.get_text(): db.create_empty_deck(entry.get_text(), cats[dropdown.get_selected()]); self.refresh_sidebar(); d.close()
        dlg.connect("response", on_r); dlg.present()

    def on_export_clicked(self, btn):
        row = self.deck_list.get_selected_row()
        if not row or not hasattr(row, '_filename'): self.toast_overlay.add_toast(Adw.Toast.new("Select a deck first")); return
        fname = row._filename
        dlg = Adw.MessageDialog(transient_for=self, heading="Export"); dlg.add_response("cancel", "Cancel"); dlg.add_response("json", "JSON"); dlg.add_response("csv", "CSV")
        def on_f(d, r):
            if r in ("json","csv") and hasattr(Gtk, "FileDialog"):
                fd = Gtk.FileDialog(); fd.set_initial_name(fname.replace(".json", f".{r}"))
                def on_s(f, res):
                    try:
                        fi = f.save_finish(res)
                        if fi:
                            if r=="json": db.export_deck_to_json(fname, fi.get_path())
                            else: db.export_deck_to_csv(fname, fi.get_path())
                            self.toast_overlay.add_toast(Adw.Toast.new("Exported"))
                    except: pass
                fd.save(self, None, on_s)
        dlg.connect("response", on_f); dlg.present()

    def on_deck_selected(self, lb, row): 
        if row and hasattr(row, '_filename'): self.open_study_session(row._filename)
    
    def open_study_session(self, fname):
        n = f"study_{fname}"
        if e:=self.content_stack.get_child_by_name(n): self.content_stack.remove(e)
        self.content_stack.add_named(study_session.StudySession(fname, self.handle_session_nav), n)
        self.content_stack.set_visible_child_name(n)

    def open_editor(self, fname):
        try:
            n = f"edit_{fname}"
            if e:=self.content_stack.get_child_by_name(n): self.content_stack.remove(e)
            self.content_stack.add_named(deck_editor.DeckEditor(fname, self.go_back_to_dashboard), n)
            self.content_stack.set_visible_child_name(n)
        except Exception as e: print(f"Error opening editor: {e}"); self.toast_overlay.add_toast(Adw.Toast.new(f"Error opening editor: {e}"))

    def open_stats_view(self, fname):
        n = f"stats_{fname}"
        if e:=self.content_stack.get_child_by_name(n): self.content_stack.remove(e)
        self.content_stack.add_named(performance_view.PerformanceView(fname, None, self.go_back_to_dashboard), n)
        self.content_stack.set_visible_child_name(n)

    def handle_session_nav(self, action, data):
        if action == "close": 
            self.content_stack.set_visible_child_name("dashboard")
            self.deck_list.select_row(None)
            self.refresh_sidebar()
            if hasattr(self.dash_view, 'refresh'): self.dash_view.refresh()
        elif action == "stats":
            view = self.content_stack.get_visible_child()
            fname = view.filename
            n = f"stats_{fname}"
            if e:=self.content_stack.get_child_by_name(n): self.content_stack.remove(e)
            self.content_stack.add_named(performance_view.PerformanceView(fname, data, self.go_back_to_dashboard), n)
            self.content_stack.set_visible_child_name(n)

    def on_delete_deck(self, fname):
        def c(d, r):
            if r=="delete": db.delete_deck(fname); self.refresh_sidebar(); self.content_stack.set_visible_child_name("dashboard")
        dlg = Adw.MessageDialog(transient_for=self, heading="Delete?", body="Irreversible.")
        dlg.add_response("cancel", "Cancel"); dlg.add_response("delete", "Delete")
        dlg.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE); dlg.connect("response", c); dlg.present()

    def on_import_clicked(self, btn):
        if hasattr(Gtk, "FileDialog"):
            d = Gtk.FileDialog()
            f_csv = Gtk.FileFilter(); f_csv.set_name("CSV Files"); f_csv.add_pattern("*.csv")
            f_anki = Gtk.FileFilter(); f_anki.set_name("Anki Decks"); f_anki.add_pattern("*.apkg")
            f_any = Gtk.FileFilter(); f_any.set_name("All Supported"); f_any.add_pattern("*.csv"); f_any.add_pattern("*.apkg")
            filters = Gio.ListStore.new(Gtk.FileFilter); filters.append(f_any); filters.append(f_csv); filters.append(f_anki)
            d.set_filters(filters); d.set_default_filter(f_any)
            def on_o(d, r):
                try:
                    res = d.open_finish(r)
                    if res:
                        path = res.get_path(); name = res.get_basename(); success = False
                        if path.lower().endswith(".apkg"): name = name.replace(".apkg", ""); success = db.import_anki_apkg(path, name)
                        elif path.lower().endswith(".csv"): name = name.replace(".csv", ""); success = db.import_csv(path, name)
                        else: self.toast_overlay.add_toast(Adw.Toast.new("Unsupported file format")); return
                        if success: self.refresh_sidebar(); self.toast_overlay.add_toast(Adw.Toast.new("Import Successful"))
                        else: self.toast_overlay.add_toast(Adw.Toast.new("Import Failed"))
                except Exception as e: 
                    if "Dismissed by user" not in str(e): print(e)
            d.open(self, None, on_o)

    # --- DOUBLE CLICK HANDLERS ---
    def on_category_label_click(self, n_press, cat_name):
        # n_press 2 means double click
        if n_press == 2:
            self.on_rename_category(cat_name)

    def on_deck_label_click(self, n_press, filename):
        if n_press == 2:
            self.on_rename_deck_sidebar(filename)

    def on_rename_deck_sidebar(self, old_filename):
        clean_name = old_filename.replace('.json', '').replace('_', ' ').title()
        
        dialog = Adw.MessageDialog(heading=f"Rename Deck", transient_for=self)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("rename", "Rename")
        dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)
        
        entry = Gtk.Entry(text=clean_name)
        entry.connect("activate", lambda w: dialog.response("rename"))
        dialog.set_extra_child(entry)
        
        def on_response(d, r):
            if r == "rename":
                new_name = entry.get_text().strip()
                if new_name:
                    new_filename = db.rename_deck(old_filename, new_name)
                    if new_filename:
                        
                        curr_view = self.content_stack.get_visible_child_name()
                        if curr_view and old_filename in curr_view:
                            self.on_dashboard_clicked(None)
                        
                        self.refresh_sidebar()
            d.close()
            
        dialog.connect("response", on_response)
        dialog.present()

    def on_rename_category(self, old_name):
        dialog = Adw.MessageDialog(heading=f"Rename {old_name}", transient_for=self)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("rename", "Rename")
        dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)
        
        entry = Gtk.Entry(text=old_name)
        entry.connect("activate", lambda w: dialog.response("rename"))
        dialog.set_extra_child(entry)
        
        def on_response(d, r):
            if r == "rename":
                new_name = entry.get_text().strip()
                if new_name and new_name != old_name:
                    db.rename_category(old_name, new_name)
                    self.refresh_sidebar() # Refresh to show new name
            d.close()
            
        dialog.connect("response", on_response)
        dialog.present()

    

class FlipStackApp(Adw.Application):
    def __init__(self): super().__init__(application_id="io.github.dagaza.FlipStack", flags=0)
    def do_activate(self):
        win = self.props.active_window
        if not win: win = FlipStackWindow(self)
        win.present()

if __name__ == "__main__":
    app = FlipStackApp()
    try:
        app.run(sys.argv)
    except KeyboardInterrupt:
        pass