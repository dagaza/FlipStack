import sys
import os
import re
import traceback

# Force 'gl' renderer (Restored from your working version)
os.environ["GSK_RENDERER"] = "gl"

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('PangoCairo', '1.0')

from gi.repository import Gtk, Adw, Gio, Gdk, GObject, GLib, Pango, PangoCairo

# Import your local modules
import data_engine as db
import study_session 
import deck_editor
import performance_view 
import dashboard_view 

class FlipStackWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="FlipStack")

        # --- APP ID & ICONS ---
        self.set_startup_id("io.github.dagaza.FlipStack")
        GLib.set_prgname("io.github.dagaza.FlipStack")
        
        # Set minimum size to support 360px mobile width
        self.set_size_request(360, 600) 
        self.set_default_size(1100, 750)

        # --- THEME & STYLES ---
        self.settings = db.load_settings()
        self.apply_theme_settings()
        self.load_css_providers()

        # --- ACTIONS ---
        self.setup_actions()

        # --- MAIN LAYOUT ---
        self.split_view = Adw.NavigationSplitView()
        self.split_view.set_min_sidebar_width(360)
        self.split_view.set_max_sidebar_width(360)
        
        # --- 1. SIDEBAR PAGE (The "Library") ---
        self.sidebar_page = Adw.NavigationPage(title="Library", tag="sidebar")
        
        sidebar_toolbar_view = Adw.ToolbarView()
        
        # === ROW 1: HEADER BAR (Logo + Window Controls) ===
        header_bar = Adw.HeaderBar()
        header_bar.set_show_title(False)
        header_bar.add_css_class("flat")
        
        # Logo
        base_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base_dir, "assets", "icons", "io.github.dagaza.FlipStack.svg")
        if os.path.exists(logo_path):
            logo_img = Gtk.Image.new_from_file(logo_path)
        else:
            logo_img = Gtk.Image.new_from_icon_name("applications-science-symbolic")
        logo_img.set_pixel_size(24)
        logo_img.set_margin_start(4)
        header_bar.pack_start(logo_img)
        
        sidebar_toolbar_view.add_top_bar(header_bar)

        # === ROW 2: TOOLBAR (Buttons) ===
        toolbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        toolbar_box.add_css_class("toolbar")
        toolbar_box.set_margin_bottom(8)
        toolbar_box.set_margin_start(8); toolbar_box.set_margin_end(8)
        
        # 1. Home
        self.btn_dash = Gtk.Button(icon_name="go-home-symbolic", css_classes=["flat"])
        self.btn_dash.set_tooltip_text("Dashboard")
        self.btn_dash.connect("clicked", self.on_dashboard_clicked)
        toolbar_box.append(self.btn_dash)

        # 2. Search
        self.btn_search_toggle = Gtk.ToggleButton(icon_name="system-search-symbolic", css_classes=["flat"])
        self.btn_search_toggle.set_tooltip_text("Toggle Search")
        self.btn_search_toggle.connect("toggled", self.on_search_toggled)
        toolbar_box.append(self.btn_search_toggle)

        # 3. Theme
        self.btn_theme = Gtk.Button(icon_name="weather-clear-night-symbolic", css_classes=["flat"])
        self.btn_theme.set_tooltip_text("Toggle Theme")
        self.btn_theme.connect("clicked", self.on_theme_toggle)
        toolbar_box.append(self.btn_theme)

        # 4. Sound
        self.btn_sound = Gtk.Button(css_classes=["flat"])
        self.btn_sound.set_tooltip_text("Toggle Sound")
        self.update_sound_icon() 
        self.btn_sound.connect("clicked", self.on_sound_toggle)
        toolbar_box.append(self.btn_sound)

        # Spacer (Pushes Menu to right)
        toolbar_box.append(Gtk.Label(hexpand=True))

        # 5. Menu (Hamburger)
        menu_model = Gio.Menu()
        
        def append_menu_item(menu, label, action, icon_name):
            item = Gio.MenuItem.new(label, action)
            icon = Gio.ThemedIcon.new(icon_name)
            item.set_icon(icon)
            menu.append_item(item)

        # Section 1: Create
        sec_create = Gio.Menu()
        append_menu_item(sec_create, "New Deck", "win.new_deck", "list-add-symbolic")
        append_menu_item(sec_create, "New Category", "win.new_category", "folder-new-symbolic")
        menu_model.append_section(None, sec_create)
        
        # Section 2: Data
        sec_data = Gio.Menu()
        append_menu_item(sec_data, "Import Deck", "win.import_deck", "document-open-symbolic")
        append_menu_item(sec_data, "Export Deck", "win.export_deck", "document-save-symbolic")
        append_menu_item(sec_data, "Backup Data", "win.backup_data", "document-save-as-symbolic")
        menu_model.append_section(None, sec_data)

        # Section 3: Preferences & Help
        sec_pref = Gio.Menu()
        append_menu_item(sec_pref, "Text Settings", "win.text_settings", "preferences-desktop-font-symbolic")
        append_menu_item(sec_pref, "Help", "win.help", "help-about-symbolic")
        menu_model.append_section(None, sec_pref)

        self.btn_menu = Gtk.MenuButton(icon_name="open-menu-symbolic")
        self.btn_menu.set_menu_model(menu_model)
        self.btn_menu.set_tooltip_text("Menu")
        toolbar_box.append(self.btn_menu)

        sidebar_toolbar_view.add_top_bar(toolbar_box)

        # === SIDEBAR CONTENT ===
        sidebar_content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # --- Search Bar Setup ---
        self.search_revealer = Gtk.Revealer()
        self.search_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        
        # Container for Entry + Button
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        search_box.set_margin_start(10); search_box.set_margin_end(10); search_box.set_margin_bottom(10)
        
        # 1. The Input Field
        self.search_entry = Gtk.Entry(placeholder_text="Search decks, cards, tags...")
        self.search_entry.set_hexpand(True)
        
        # FIX: The "activate" signal is the standard way to catch "Enter" on a Gtk.Entry
        self.search_entry.connect("activate", self.on_search_trigger)
        
        # 2. The "Go" Button
        btn_go_search = Gtk.Button(label="Go")
        btn_go_search.add_css_class("suggested-action") 
        btn_go_search.set_tooltip_text("Run Search")
        btn_go_search.connect("clicked", self.on_search_trigger)
        
        search_box.append(self.search_entry)
        search_box.append(btn_go_search)
        
        self.search_revealer.set_child(search_box)
        sidebar_content_box.append(self.search_revealer)

        # Deck List
        self.sidebar_scroll = Gtk.ScrolledWindow()
        self.sidebar_scroll.set_vexpand(True)
        self.deck_list = Gtk.ListBox()
        self.deck_list.add_css_class("navigation-sidebar")
        self.deck_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        
        # --- FIX FOR MOBILE NAVIGATION ---
        # 1. Enable activation on single click (standard for mobile lists)
        self.deck_list.set_activate_on_single_click(True)
        
        # 2. Connect to 'row-activated' instead of 'row-selected'
        # This ensures the action fires even if you tap the already-selected row.
        self.deck_list.connect("row-activated", self.on_deck_selected)
        # ---------------------------------
        
        self.sidebar_scroll.set_child(self.deck_list)
        sidebar_content_box.append(self.sidebar_scroll)
        
        sidebar_toolbar_view.set_content(sidebar_content_box)
        self.sidebar_page.set_child(sidebar_toolbar_view)
        self.split_view.set_sidebar(self.sidebar_page)


        # --- 2. CONTENT PAGE ---
        self.content_page = Adw.NavigationPage(title="Dashboard", tag="content")
        
        content_toolbar_view = Adw.ToolbarView()
        self.content_header = Adw.HeaderBar()
        content_toolbar_view.add_top_bar(self.content_header)
        
        self.content_stack = Gtk.Stack()
        self.content_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.content_stack.set_vexpand(True)
        self.content_stack.set_hexpand(True)
        
        # Dashboard Scrolling
        self.dash_scroll = Gtk.ScrolledWindow()
        self.dash_scroll.set_vexpand(True)
        self.dash_scroll.set_hexpand(True)
        self.dash_scroll.set_min_content_height(400)
        self.dash_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self.dash_view = dashboard_view.DashboardView()
        self.dash_view.set_vexpand(True) 
        
        self.dash_scroll.set_child(self.dash_view)
        self.content_stack.add_named(self.dash_scroll, "dashboard")
        
        self.search_view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        # FIX: Ensure search view expands
        self.search_view.set_vexpand(True)
        
        self.search_results_list = Gtk.ListBox(); self.search_results_list.add_css_class("boxed-list")
        
        s_s = Gtk.ScrolledWindow()
        # FIX: Ensure scrolled window expands
        s_s.set_vexpand(True)
        s_s.set_child(self.search_results_list)
        
        self.search_view.append(s_s)
        self.content_stack.add_named(self.search_view, "global_search")
        
        content_toolbar_view.set_content(self.content_stack)
        self.content_page.set_child(content_toolbar_view)
        self.split_view.set_content(self.content_page)


        # --- 3. RESPONSIVE SETUP ---
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 800px"))
        bp.add_setter(self.split_view, "collapsed", True)
        self.add_breakpoint(bp)

        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(self.split_view)
        self.set_content(self.toast_overlay)

        # --- FINAL INIT ---
        self.apply_font_settings()
        self.refresh_sidebar()
        
        if self.settings.get("first_run", True):
            GLib.idle_add(self.show_welcome_dialog)

    # --- ACTION SETUP ---
    def setup_actions(self):
        # Global Actions
        actions = [
            ('new_deck', self.on_new_deck_clicked),
            ('new_category', self.on_new_category_clicked),
            ('import_deck', self.on_import_clicked),
            ('export_deck', self.on_export_clicked),
            ('backup_data', self.on_backup_clicked),
            ('text_settings', self.on_font_clicked),
            ('help', lambda x: self.show_welcome_dialog())
        ]
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda a, p, cb=callback: cb(None))
            self.add_action(action)

        # Deck Context Actions (Parameterized with Filename)
        deck_actions = [
            ('deck_stats', self.on_action_deck_stats),
            ('deck_edit', self.on_action_deck_edit),
            ('deck_move', self.on_action_deck_move),
            ('deck_rename', self.on_action_deck_rename),
            ('deck_export', self.on_action_deck_export),
            ('deck_delete', self.on_action_deck_delete)
        ]
        for name, callback in deck_actions:
            # "s" means it expects a string parameter
            action = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            action.connect("activate", callback)
            self.add_action(action)

            # --- NEW: Category Context Actions ---
        cat_actions = [
            ('cat_rename', self.on_action_cat_rename),
            ('cat_delete', self.on_action_cat_delete)
        ]
        for name, callback in cat_actions:
            action = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            action.connect("activate", callback)
            self.add_action(action)

    # --- ACTION HANDLERS FOR CATEGORY MENU ---
    def on_action_cat_rename(self, action, param):
        self.on_rename_category(param.get_string())

    def on_action_cat_delete(self, action, param):
        self.on_delete_category(param.get_string())

    # --- ACTION HANDLERS FOR DECK MENU ---
    def on_action_deck_stats(self, action, param):
        self.open_stats_view(param.get_string())

    def on_action_deck_edit(self, action, param):
        self.open_editor(param.get_string())

    def on_action_deck_move(self, action, param):
        self.on_move_deck(param.get_string())

    def on_action_deck_rename(self, action, param):
        self.on_rename_deck(param.get_string())

    def on_action_deck_export(self, action, param):
        # Direct export for specific deck
        self.save_export_file(param.get_string())

    def on_action_deck_delete(self, action, param):
        self.on_delete_deck(param.get_string())

    # --- HELPERS ---

    def load_css_providers(self):
        css_provider = Gtk.CssProvider()
        css_provider.load_from_string("""
            .red-icon { color: #ed333b; }
            .red-icon:hover { color: #c01c28; background: alpha(#ed333b, 0.1); }
            .heading { font-weight: bold; font-size: 11pt; color: alpha(currentColor, 0.8); }
            
            /* HEATMAP COLORS */
            .hm-0 { background-color: alpha(@theme_fg_color, 0.1); }
            .hm-future { background-color: transparent; border: 1px solid alpha(@theme_fg_color, 0.2); }
            .hm-1 { background-color: #26a269; opacity: 0.4; }
            .hm-2 { background-color: #26a269; opacity: 0.6; }
            .hm-3 { background-color: #26a269; opacity: 0.8; }
            .hm-4 { background-color: #26a269; opacity: 1.0; }
        """)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        
        self.font_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.font_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def apply_theme_settings(self):
        style_manager = Adw.StyleManager.get_default()
        saved_theme = self.settings.get("theme", "system")
        if saved_theme == "dark": style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        elif saved_theme == "light": style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        else: style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

    def natural_sort_key(self, s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

    # --- FONT LOGIC ---
    def on_font_clicked(self, btn):
        font_map = PangoCairo.FontMap.get_default()
        families = font_map.list_families()
        font_names = sorted([f.get_name() for f in families])
        curr_font = self.settings.get("font_family", "Cantarell")
        if curr_font not in font_names: font_names.insert(0, curr_font)

        sl_fonts = Gtk.StringList.new(font_names)
        dropdown = Gtk.DropDown(model=sl_fonts, enable_search=True)
        expression = Gtk.PropertyExpression.new(Gtk.StringObject, None, "string")
        dropdown.set_expression(expression)
        try: dropdown.set_selected(font_names.index(curr_font))
        except ValueError: dropdown.set_selected(0)

        curr_size = self.settings.get("font_size", 16)
        adj = Gtk.Adjustment(value=curr_size, lower=8, upper=72, step_increment=1, page_increment=5, page_size=0)
        spin_size = Gtk.SpinButton(adjustment=adj, climb_rate=1, digits=0)
        
        lbl_preview = Gtk.Label(label="The quick brown fox.", wrap=True, max_width_chars=40)
        scroll_preview = Gtk.ScrolledWindow(min_content_height=80, child=lbl_preview)
        
        def update_preview(*args):
            item = dropdown.get_selected_item()
            if not item: return
            f_name = item.get_string()
            f_size = int(adj.get_value())
            lbl_preview.set_markup(f"<span font_desc='{f_name} {f_size}'>{lbl_preview.get_text()}</span>")
        
        dropdown.connect("notify::selected-item", update_preview)
        adj.connect("value-changed", update_preview)
        update_preview()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.append(Gtk.Label(label="Font Family", xalign=0, css_classes=["heading"]))
        box.append(dropdown)
        box.append(Gtk.Label(label="Size", xalign=0, css_classes=["heading"]))
        box.append(spin_size)
        box.append(Gtk.Separator())
        box.append(scroll_preview)
        
        d = Adw.MessageDialog(heading="Text Settings", transient_for=self)
        d.set_extra_child(box)
        d.add_response("cancel", "Cancel")
        d.add_response("save", "Save")
        d.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        
        def on_resp(dlg, r):
            if r == "save":
                item = dropdown.get_selected_item()
                if item:
                    self.settings["font_family"] = item.get_string()
                    self.settings["font_size"] = int(adj.get_value())
                    db.save_settings(self.settings)
                    self.apply_font_settings()
            dlg.close()
        d.connect("response", on_resp)
        d.present()

    def apply_font_settings(self):
        fam = self.settings.get("font_family", "Cantarell")
        size = self.settings.get("font_size", 16)
        css = f".card-text {{ font-family: \"{fam}\"; font-size: {size}px; }}"
        self.font_provider.load_from_string(css)

    # --- NAVIGATION & ACTIONS ---

    def on_dashboard_clicked(self, btn):
        self.content_stack.set_visible_child_name("dashboard")
        self.content_page.set_title("Dashboard")
        self.deck_list.select_row(None)
        if hasattr(self.dash_view, 'refresh'): self.dash_view.refresh()
        self.split_view.set_show_content(True)

    def on_deck_selected(self, lb, row): 
        if row and hasattr(row, '_filename'): 
            self.open_study_session(row._filename)
            # FIX: Use set_show_content(True) here too
            self.split_view.set_show_content(True)

    def open_study_session(self, fname):
        deck_name = fname.replace(".json", "").replace("_", " ").title()
        n = f"study_{fname}"
        if e := self.content_stack.get_child_by_name(n): self.content_stack.remove(e)
        self.content_stack.add_named(study_session.StudySession(fname, self.handle_session_nav), n)
        self.content_stack.set_visible_child_name(n)
        self.content_page.set_title(deck_name)

    def handle_session_nav(self, action, data):
        if action == "close": self.on_dashboard_clicked(None)
        elif action == "stats":
            view = self.content_stack.get_visible_child()
            fname = view.filename
            n = f"stats_{fname}"
            if e := self.content_stack.get_child_by_name(n): self.content_stack.remove(e)
            self.content_stack.add_named(performance_view.PerformanceView(fname, data, self.go_back_to_dashboard), n)
            self.content_stack.set_visible_child_name(n)
            self.content_page.set_title("Stats: " + fname.replace(".json", ""))

    def go_back_to_dashboard(self):
        self.on_dashboard_clicked(None)

    # --- SIDEBAR REFRESH ---
    def refresh_sidebar(self, search_query=""):
        while child := self.deck_list.get_first_child(): self.deck_list.remove(child)
        
        all_files = db.get_all_decks()
        cats = db.get_categories()
        if "Uncategorized" not in cats: cats.append("Uncategorized")
        
        if search_query:
            all_files = [f for f in all_files if search_query.lower() in f.lower().replace("_", " ")]

        grouped = {c: [] for c in cats}
        for f in all_files:
            c = db.get_deck_category(f)
            target = c if c in grouped else "Uncategorized"
            grouped[target].append(f)
            
        sorted_cats = sorted([c for c in cats if c != "Uncategorized"], key=self.natural_sort_key)
        sorted_cats.insert(0, "Uncategorized")
        
        for cat in sorted_cats:
            decks = grouped[cat]
            if not decks and search_query: continue 
            
            # Cat Header
            row_cat = Gtk.ListBoxRow(selectable=False, activatable=False)
            box_cat = Gtk.Box(spacing=10, margin_top=15, margin_bottom=5, margin_start=10)
            lbl_cat = Gtk.Label(label=cat, css_classes=["heading"], xalign=0)
            box_cat.append(lbl_cat)
            
            if cat != "Uncategorized":
                # Double-click to rename (Optional: You can keep or remove this)
                ctrl = Gtk.GestureClick(button=0)
                ctrl.connect("pressed", lambda g, n, x, y, c=cat: self.on_rename_category(c) if n==2 else None)
                lbl_cat.add_controller(ctrl)
                
                # --- NEW: KEBAB MENU FOR CATEGORY ---
                cat_menu = Gio.Menu()
                
                # Helper for category items
                def append_cat_item(m, label, action_name, arg, icon):
                    item = Gio.MenuItem.new(label, f"win.{action_name}")
                    item.set_action_and_target_value(f"win.{action_name}", GLib.Variant.new_string(arg))
                    item.set_icon(Gio.ThemedIcon.new(icon))
                    m.append_item(item)

                # 1. Rename
                append_cat_item(cat_menu, "Rename", "cat_rename", cat, "document-edit-symbolic")
                
                # 2. Delete (Separate section)
                sec_cat_del = Gio.Menu()
                append_cat_item(sec_cat_del, "Delete", "cat_delete", cat, "user-trash-symbolic")
                cat_menu.append_section(None, sec_cat_del)

                btn_cat_more = Gtk.MenuButton(icon_name="view-more-symbolic", css_classes=["flat"])
                btn_cat_more.set_menu_model(cat_menu)
                btn_cat_more.set_valign(Gtk.Align.CENTER)
                btn_cat_more.set_tooltip_text("Category Options")
                
                box_cat.append(btn_cat_more)
                # ------------------------------------

            row_cat.set_child(box_cat)
            self.deck_list.append(row_cat)
            
            # Decks
            decks.sort(key=self.natural_sort_key)
            for fname in decks:
                deck_name = fname.replace(".json", "").replace("_", " ").title()
                display_name = deck_name
                if len(deck_name) > 23:
                    display_name = deck_name[:20] + "..."
                
                row = Gtk.ListBoxRow()
                row._filename = fname
                
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3, margin_top=6, margin_bottom=6, margin_start=12, margin_end=6)
                
                try: icon = Adw.Avatar(size=32, text=deck_name, show_initials=True)
                except: icon = Gtk.Image.new_from_icon_name("folder-symbolic")
                box.append(icon)
                
                vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                # CHANGE: Allow this box to grow, pushing the menu button to the right
                vbox.set_hexpand(True) 
                # vbox.set_size_request(150, -1)  <-- You can remove this fixed size now
                
                lbl = Gtk.Label(label=display_name, xalign=0, css_classes=["body"])
                # ... (Label logic) ...
                vbox.append(lbl)
                
                mastery = db.get_deck_mastery(fname)
                if mastery > 0:
                    bar = Gtk.LevelBar(min_value=0, max_value=1.0, value=mastery)
                    bar.set_size_request(140, 2) # Keep the bar small/fixed if you like
                    bar.set_halign(Gtk.Align.START) 
                    if mastery == 1.0: bar.add_css_class("accent")
                    vbox.append(bar)
                
                box.append(vbox)
                
                # --- KEBAB MENU IMPLEMENTATION ---
                menu = Gio.Menu()
                
                def append_deck_item(m, label, action_name, arg, icon):
                    item = Gio.MenuItem.new(label, f"win.{action_name}")
                    item.set_action_and_target_value(f"win.{action_name}", GLib.Variant.new_string(arg))
                    item.set_icon(Gio.ThemedIcon.new(icon))
                    m.append_item(item)

                # 1. View Stats
                append_deck_item(menu, "View Stats", "deck_stats", fname, "power-profile-performance-symbolic")
                # 2. Edit Deck
                append_deck_item(menu, "Edit Deck", "deck_edit", fname, "document-edit-symbolic")

                # 3. --- NEW: Move Deck ---
                append_deck_item(menu, "Move Category", "deck_move", fname, "folder-symbolic")
                # ----------------------

                # 4. Rename
                append_deck_item(menu, "Rename", "deck_rename", fname, "document-properties-symbolic")
                # 5. Export
                append_deck_item(menu, "Export Deck", "deck_export", fname, "document-save-symbolic")
                
                # 6. Delete (Separate section)
                sec_del = Gio.Menu()
                append_deck_item(sec_del, "Delete", "deck_delete", fname, "user-trash-symbolic")
                menu.append_section(None, sec_del)

                btn_more = Gtk.MenuButton(icon_name="view-more-symbolic", css_classes=["flat"])
                btn_more.set_menu_model(menu)
                btn_more.set_valign(Gtk.Align.CENTER)
                
                box.append(btn_more)
                # ---------------------------------

                row.set_child(box)
                self.deck_list.append(row)

    # --- SEARCH ---
    def on_search_toggled(self, btn):
        reveal = btn.get_active()
        self.search_revealer.set_reveal_child(reveal)
        if reveal: self.search_entry.grab_focus()
        else: self.search_entry.set_text("")

    # --- SEARCH ---
    def on_search_toggled(self, btn):
        reveal = btn.get_active()
        self.search_revealer.set_reveal_child(reveal)
        if reveal: self.search_entry.grab_focus()
        else: self.search_entry.set_text("")

    def on_search_trigger(self, widget):
        """Triggered by Enter key or Search Button."""
        query = self.search_entry.get_text()
        if not query: return
        
        self.content_stack.set_visible_child_name("global_search")
        
        # FIX: Use set_show_content(True) instead of set_show_sidebar(False)
        self.split_view.set_show_content(True)
        
        while child := self.search_results_list.get_first_child(): 
            self.search_results_list.remove(child)
            
        results = db.search_global(query)
        
        def add_header(title):
            row = Gtk.ListBoxRow()
            row.set_activatable(False); row.set_selectable(False)
            lbl = Gtk.Label(label=title, xalign=0, css_classes=["heading", "dim-label"])
            lbl.set_margin_top(15); lbl.set_margin_bottom(5); lbl.set_margin_start(10)
            row.set_child(lbl)
            self.search_results_list.append(row)

        has_results = False

        # 1. Deck Results
        if results['decks']:
            has_results = True
            add_header("Decks")
            for fname in results['decks']:
                # RAW TEXT
                raw_name = fname.replace(".json", "").replace("_", " ").title()
                # SAFE TEXT (Escaped)
                clean_name = GLib.markup_escape_text(raw_name)
                
                row = Adw.ActionRow(title=clean_name, subtitle="Open Deck")
                row.add_suffix(Gtk.Image.new_from_icon_name("folder-open-symbolic"))
                
                def open_deck_search(r, f=fname):
                    self.open_study_session(f)
                
                btn = Gtk.Button(icon_name="media-playback-start-symbolic", css_classes=["flat"])
                btn.set_valign(Gtk.Align.CENTER)
                btn.connect("clicked", lambda b, f=fname: open_deck_search(None, f))
                row.add_suffix(btn)
                self.search_results_list.append(row)

        # 2. Card Results
        if results['cards']:
            has_results = True
            add_header("Cards")
            for res in results['cards']:
                # RAW TEXT
                raw_front = res['front'].replace("\n", " ")
                raw_back = res['back'].replace("\n", " ")
                raw_deck = res['deck_name']
                
                # SAFE TEXT (Escaped)
                # We escape the content so 'P&L' becomes 'P&amp;L' safely
                title = GLib.markup_escape_text(raw_front)
                subtitle = GLib.markup_escape_text(f"{raw_deck} • {raw_back}")
                
                row = Adw.ActionRow(title=title, subtitle=subtitle)
                row.set_subtitle_lines(1)
                row.set_title_lines(1)
                
                btn = Gtk.Button(icon_name="document-edit-symbolic", css_classes=["flat"])
                btn.set_valign(Gtk.Align.CENTER)
                btn.connect("clicked", lambda b, f=res['filename']: self.open_editor(f))
                row.add_suffix(btn)
                self.search_results_list.append(row)

        # 3. Tag Results
        if results['tags']:
            has_results = True
            add_header("Tags")
            for tag in results['tags']:
                safe_tag = GLib.markup_escape_text(f"#{tag}")
                row = Adw.ActionRow(title=safe_tag, subtitle="Filter by this tag")
                row.add_suffix(Gtk.Image.new_from_icon_name("tag-symbolic"))
                self.search_results_list.append(row)

        if not has_results:
            # Escape the query too, just in case they searched for "&"
            safe_query = GLib.markup_escape_text(query)
            self.search_results_list.append(Adw.ActionRow(title="No results found", subtitle=f"No matches for '{safe_query}'"))

    def on_search_toggled(self, btn):
        # Just toggles visibility, doesn't clear immediately
        reveal = btn.get_active()
        self.search_revealer.set_reveal_child(reveal)
        if reveal: 
            self.search_entry.grab_focus()
        else:
            # Optional: Clear results when closing bar?
            # self.content_stack.set_visible_child_name("dashboard") 
            pass

    # --- THEME TOGGLE ---
    def on_theme_toggle(self, btn):
        manager = Adw.StyleManager.get_default()
        current = self.settings.get("theme", "system")
        if manager.get_dark():
            manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            self.settings["theme"] = "light"
        else:
            manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            self.settings["theme"] = "dark"
        db.save_settings(self.settings)

    # --- EDITOR & UTILS ---
    def open_editor(self, fname):
        n = f"edit_{fname}"
        if e := self.content_stack.get_child_by_name(n): self.content_stack.remove(e)
        self.content_stack.add_named(deck_editor.DeckEditor(fname, self.go_back_to_dashboard), n)
        self.content_stack.set_visible_child_name(n)
        self.content_page.set_title("Edit Deck")
        self.split_view.set_show_content(True)

    def open_stats_view(self, fname):
        n = f"stats_{fname}"
        if e := self.content_stack.get_child_by_name(n): self.content_stack.remove(e)
        self.content_stack.add_named(performance_view.PerformanceView(fname, None, self.go_back_to_dashboard), n)
        self.content_stack.set_visible_child_name(n)
        self.content_page.set_title("Performance")
        self.split_view.set_show_content(True)

    # --- DIALOG WRAPPERS ---
    def on_new_deck_clicked(self, btn):
        d = Adw.MessageDialog(heading="New Deck", transient_for=self)
        d.add_response("cancel", "Cancel")
        d.add_response("create", "Create")
        d.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        entry = Gtk.Entry(placeholder_text="Deck Name")
        
        # FIX: Pressing Enter triggers the "create" response
        entry.connect("activate", lambda w: d.response("create"))

        cats = db.get_categories()
        sl = Gtk.StringList.new(cats)
        dd = Gtk.DropDown(model=sl)
        
        box.append(entry)
        box.append(dd)
        d.set_extra_child(box)
        
        def on_r(dlg, r):
            if r == "create" and entry.get_text():
                db.create_empty_deck(entry.get_text(), cats[dd.get_selected()])
                self.refresh_sidebar()
            dlg.close()
        d.connect("response", on_r)
        d.present()

    def on_new_category_clicked(self, btn):
        d = Adw.MessageDialog(heading="New Category", transient_for=self)
        d.add_response("cancel", "Cancel")
        d.add_response("create", "Create")
        entry = Gtk.Entry(placeholder_text="Category Name")

        # FIX: Pressing Enter triggers the "create" response
        entry.connect("activate", lambda w: d.response("create"))

        d.set_extra_child(entry)
        def on_r(dlg, r):
            if r=="create" and entry.get_text():
                db.add_category(entry.get_text())
                self.refresh_sidebar()
            dlg.close()
        d.connect("response", on_r)
        d.present()

    def on_delete_deck(self, fname):
        d = Adw.MessageDialog(heading="Delete Deck?", body="This cannot be undone.", transient_for=self)
        d.add_response("cancel", "Cancel")
        d.add_response("delete", "Delete")
        d.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        def on_r(dlg, r):
            if r=="delete": 
                db.delete_deck(fname)
                self.refresh_sidebar()
                self.on_dashboard_clicked(None)
            dlg.close()
        d.connect("response", on_r)
        d.present()

    def on_delete_category(self, cat):
        d = Adw.MessageDialog(heading=f"Delete {cat}?", body="Decks will move to Uncategorized.", transient_for=self)
        d.add_response("cancel", "Cancel")
        d.add_response("delete", "Delete")
        d.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        def on_r(dlg, r):
            if r=="delete":
                db.delete_category(cat)
                self.refresh_sidebar()
            dlg.close()
        d.connect("response", on_r)
        d.present()

    def on_rename_deck(self, fname):
        clean = fname.replace(".json", "").replace("_", " ").title()
        d = Adw.MessageDialog(heading="Rename Deck", transient_for=self)
        d.add_response("cancel", "Cancel")
        d.add_response("rename", "Rename")
        d.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)
        
        # FIX: Pressing Enter triggers the "rename" response
        entry.connect("activate", lambda w: d.response("rename"))
        
        d.set_extra_child(entry)

        def on_r(dlg, r):
            if r=="rename" and entry.get_text():
                db.rename_deck(fname, entry.get_text())
                self.refresh_sidebar()
            dlg.close()
        d.connect("response", on_r)
        d.present()

    def on_rename_category(self, old_name):
        d = Adw.MessageDialog(heading="Rename Category", transient_for=self)
        d.add_response("cancel", "Cancel")
        d.add_response("rename", "Rename")
        entry = Gtk.Entry(text=old_name)

        # FIX: Pressing Enter triggers the "rename" response
        entry.connect("activate", lambda w: d.response("rename"))

        d.set_extra_child(entry)
        def on_r(dlg, r):
            if r=="rename" and entry.get_text():
                db.rename_category(old_name, entry.get_text())
                self.refresh_sidebar()
            dlg.close()
        d.connect("response", on_r)
        d.present()

    def on_move_deck(self, filename):
        dlg = Adw.MessageDialog(transient_for=self, heading="Move Deck")
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("move", "Move")
        dlg.set_response_appearance("move", Adw.ResponseAppearance.SUGGESTED)
        
        cats = db.get_categories()
        sl = Gtk.StringList.new(cats)
        dropdown = Gtk.DropDown(model=sl)
        
        # Pre-select current category
        curr = db.get_deck_category(filename)
        if curr in cats:
            dropdown.set_selected(cats.index(curr))
            
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.append(Gtk.Label(label="Select Category:", xalign=0))
        box.append(dropdown)
        dlg.set_extra_child(box)
        
        def on_resp(d, r):
            if r == "move":
                selected_cat = cats[dropdown.get_selected()]
                db.set_deck_category(filename, selected_cat)
                self.refresh_sidebar()
            d.close()
        dlg.connect("response", on_resp)
        dlg.present()

    # --- EXPORT / IMPORT / MISC ---
    
    def on_export_clicked(self, btn):
        all_decks = db.get_all_decks()
        if not all_decks:
            self.toast_overlay.add_toast(Adw.Toast.new("No decks to export."))
            return

        d = Adw.MessageDialog(heading="Export Deck", transient_for=self)
        d.add_response("cancel", "Cancel")
        d.add_response("export", "Export")
        d.set_response_appearance("export", Adw.ResponseAppearance.SUGGESTED)
        
        display_names = [f.replace(".json", "").replace("_", " ").title() for f in all_decks]
        sl = Gtk.StringList.new(display_names)
        dd = Gtk.DropDown(model=sl)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.append(Gtk.Label(label="Select deck to export:", xalign=0))
        box.append(dd)
        d.set_extra_child(box)
        
        def on_dialog_response(dlg, res):
            if res == "export":
                selected_idx = dd.get_selected()
                filename = all_decks[selected_idx]
                dlg.close()
                self.save_export_file(filename)
            else:
                dlg.close()
                
        d.connect("response", on_dialog_response)
        d.present()

    def save_export_file(self, source_filename):
        if hasattr(Gtk, "FileDialog"):
            d = Gtk.FileDialog()
            clean_name = source_filename.replace(".json", "")
            d.set_initial_name(f"{clean_name}.csv")

            filters = Gio.ListStore.new(Gtk.FileFilter)
            f_csv = Gtk.FileFilter(); f_csv.set_name("CSV File"); f_csv.add_pattern("*.csv"); filters.append(f_csv)
            f_json = Gtk.FileFilter(); f_json.set_name("FlipStack JSON"); f_json.add_pattern("*.json"); filters.append(f_json)
            d.set_filters(filters); d.set_default_filter(f_csv)

            def on_save(d, res):
                try: 
                    f = d.save_finish(res)
                    if f:
                        dest_path = f.get_path()
                        success = False
                        if dest_path.endswith(".csv"): success = db.export_deck_to_csv(source_filename, dest_path)
                        elif dest_path.endswith(".json"): success = db.export_deck_to_json(source_filename, dest_path)
                        else: dest_path += ".csv"; success = db.export_deck_to_csv(source_filename, dest_path)
                            
                        if success: self.toast_overlay.add_toast(Adw.Toast.new("Export Successful"))
                        else: self.toast_overlay.add_toast(Adw.Toast.new("Export Failed"))
                except: pass
            d.save(self, None, on_save)

    def on_import_clicked(self, btn):
        if hasattr(Gtk, "FileDialog"):
            d = Gtk.FileDialog()
            def on_open(d, res):
                try: 
                    f = d.open_finish(res)
                    if f:
                        path = f.get_path(); name = f.get_basename()
                        if path.endswith(".apkg"): db.import_anki_apkg(path, name.replace(".apkg",""))
                        elif path.endswith(".csv"): db.import_csv(path, name.replace(".csv",""))
                        self.refresh_sidebar()
                        self.toast_overlay.add_toast(Adw.Toast.new("Import Successful"))
                except: pass
            d.open(self, None, on_open)

    def on_backup_clicked(self, btn):
        if db.create_backup(): self.toast_overlay.add_toast(Adw.Toast.new("Backup Created"))
        else: self.toast_overlay.add_toast(Adw.Toast.new("Backup Failed"))

    def update_sound_icon(self):
        icon = "audio-volume-high-symbolic" if self.settings.get("sound_enabled", True) else "audio-volume-muted-symbolic"
        self.btn_sound.set_icon_name(icon)

    def on_sound_toggle(self, btn):
        curr = self.settings.get("sound_enabled", True)
        self.settings["sound_enabled"] = not curr
        db.save_settings(self.settings)
        self.update_sound_icon()
        
    def show_welcome_dialog(self):
        # Determine if this is the First Run or just "Help"
        is_first_run = self.settings.get("first_run", True)
        
        title = "Welcome to FlipStack!" if is_first_run else "Help & Manual"
        d = Adw.MessageDialog(heading=title, transient_for=self)
        d.add_response("ok", "Got it")
        
        # 1. SCROLLABLE CONTAINER (Crucial for Mobile)
        # We wrap the content in a ScrolledWindow so it fits on short 600px screens.
        scroll = Gtk.ScrolledWindow()
        scroll.set_propagate_natural_height(True)
        scroll.set_max_content_height(450) # Limit height so it doesn't cover the whole desktop
        scroll.set_min_content_height(300)
        
        # 2. CLAMP (For readability)
        # Keeps text narrow on desktop, but fills width on mobile.
        clamp = Adw.Clamp(maximum_size=400)
        scroll.set_child(clamp)
        
        # 3. CONTENT BOX
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(10); content.set_margin_bottom(10)
        content.set_margin_start(10); content.set_margin_end(10)
        clamp.set_child(content)

        # --- A. New User Banner (Only on first run) ---
        if is_first_run:
            banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            banner.add_css_class("card") # Adds the nice background/border
            banner.set_margin_bottom(5)
            
            icon = Gtk.Image.new_from_icon_name("emblem-favorite-symbolic")
            icon.add_css_class("red-icon")
            icon.set_pixel_size(16)
            
            lbl_ban = Gtk.Label(label="<b>We created a 'Welcome to FlipStack' tutorial deck!</b>\nTry playing it to learn the basics.", use_markup=True, xalign=0)
            lbl_ban.set_wrap(True)
            
            banner.append(icon); banner.append(lbl_ban)
            content.append(banner)

        # --- Helper for Manual Sections ---
        def add_section(emoji_title, body_text):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            
            lbl_t = Gtk.Label(label=f"<b>{emoji_title}</b>", use_markup=True, xalign=0)
            lbl_t.add_css_class("heading")
            
            lbl_b = Gtk.Label(label=body_text, use_markup=True, xalign=0)
            lbl_b.set_wrap(True) # <--- The key to mobile responsiveness
            lbl_b.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            lbl_b.add_css_class("dim-label") # Slightly dimmer for hierarchy
            
            box.append(lbl_t); box.append(lbl_b)
            content.append(box)

        # --- B. The Full Manual ---
        add_section("📚 Basics", 
            "Create Categories and Decks to organize your flashcards.\nUse tags (e.g. #history) to group cards across decks.")
        
        add_section("🧠 Study Modes", 
            "• <b>Standard:</b> Spaced Repetition (Leitner system) for efficient retention.\n• <b>Cram:</b> Review all cards instantly.\n• <b>Reverse:</b> Flip Question/Answer sides.")
        
        add_section("📊 Grading", 
            "• <b>Good (Green):</b> Card returns later.\n• <b>Hard (Yellow):</b> Card returns sooner.\n• <b>Miss (Red):</b> Card returns tomorrow.")
        
        # Combined Gestures & Keyboard for Mobile/Desktop context
        add_section("👆 Controls and Gestures", 
            "• <b>Tap / Space:</b> Flip Card\n• <b>Swipe Right / '1':</b> Good\n• <b>Swipe Up / '2':</b> Hard\n• <b>Swipe Left / '3':</b> Miss")

        add_section("🔤 Fonts", 
            "If you see boxes (□), the font doesn't support your language. Install a new font on your system, and the app will automatically detect it.")

        d.set_extra_child(scroll)
        d.present()
        
        # --- First Run Logic ---
        if is_first_run:
            self.settings["first_run"] = False
            db.save_settings(self.settings)
            db.create_tutorial_deck()
            self.refresh_sidebar()

class FlipStackApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.dagaza.FlipStack", flags=0)
    def do_activate(self):
        win = self.props.active_window
        if not win: win = FlipStackWindow(self)
        win.present()

if __name__ == "__main__":
    sys.exit(FlipStackApp().run(sys.argv))