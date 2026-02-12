import gi
import data_engine as db
import os
import html
import re

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, Gio, GObject, GLib

class DeckEditor(Gtk.Box):
    def __init__(self, filename, back_callback=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.filename = filename
        self.back_callback = back_callback
        # 0 = Default (Creation Date), 1 = A-Z, 2 = Z-A
        self.sort_mode = 0
        
        # --- 1. Compact Header ---
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        # Mobile-friendly margins (12px)
        header_box.set_margin_top(12); header_box.set_margin_bottom(12)
        header_box.set_margin_start(12); header_box.set_margin_end(12)
        
        if self.back_callback:
            btn_back = Gtk.Button(icon_name="go-previous-symbolic")
            btn_back.add_css_class("flat"); btn_back.set_tooltip_text("Return")
            btn_back.connect("clicked", lambda x: self.back_callback())
            header_box.append(btn_back)
        
        title_text = filename.replace('.json', '').replace('_', ' ').title()
        title = Gtk.Label(label=f"Edit: {title_text}")
        title.add_css_class("title-2")
        title.set_ellipsize(3) 
        header_box.append(title)

        # Spacer to push Add button to the right
        header_box.append(Gtk.Label(hexpand=True))

        # Sort Button
        # Logic: Current sort is A-Z (Ascending), so the button shows the option to switch to Z-A (Descending)
        self.btn_sort = Gtk.Button(icon_name="view-sort-descending-symbolic") 
        self.btn_sort.add_css_class("flat")
        self.btn_sort.set_tooltip_text("Sort: Z-A")
        self.btn_sort.connect("clicked", self.toggle_sort)
        header_box.append(self.btn_sort)

        # Add "New Card" Button
        btn_add = Gtk.Button(icon_name="list-add-symbolic")
        btn_add.add_css_class("suggested-action")
        btn_add.set_tooltip_text("Add New Card")
        btn_add.connect("clicked", lambda x: self.show_card_dialog("add"))
        header_box.append(btn_add)
        
        self.append(header_box)
        self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # --- 2. Scrollable List ---
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_hexpand(True); self.scroll.set_vexpand(True)
        self.append(self.scroll)
        
        self.clamp = Adw.Clamp(maximum_size=800)
        self.clamp.set_margin_top(12); self.clamp.set_margin_bottom(12)
        self.clamp.set_margin_start(12); self.clamp.set_margin_end(12)
        self.scroll.set_child(self.clamp)
        
        self.list_box = Gtk.ListBox()
        self.list_box.add_css_class("boxed-list")
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.clamp.set_child(self.list_box)
        
        self.refresh_list()

    def toggle_sort(self, btn):
        # Toggle 0 <-> 1
        self.sort_mode = 1 - self.sort_mode
        
        if self.sort_mode == 0: # Current View is A-Z
            # Button offers Z-A
            self.btn_sort.set_icon_name("view-sort-descending-symbolic")
            self.btn_sort.set_tooltip_text("Sort: Z-A")
        else: # Current View is Z-A
            # Button offers A-Z
            self.btn_sort.set_icon_name("view-sort-ascending-symbolic")
            self.btn_sort.set_tooltip_text("Sort: A-Z")
            
        self.refresh_list()

    def get_clean_text(self, card):
        """
        Robust cleaner: 
        1. Removes ALL punctuation/markdown (**, ?, (), #, etc).
        2. Strips whitespace.
        3. Converts to lowercase.
        """
        raw = card.get("front", "")
        # [^\w\s] matches anything that is NOT a word char (a-z, 0-9) or whitespace
        clean = re.sub(r'[^\w\s]', '', raw).strip().lower()
        return clean

    def refresh_list(self):
        while child := self.list_box.get_first_child(): self.list_box.remove(child)
        cards = db.load_deck(self.filename)

       # --- 2-STATE SORTING ---
        if self.sort_mode == 0:   # A -> Z
            cards.sort(key=self.get_clean_text)
        else:                     # Z -> A
            cards.sort(key=self.get_clean_text, reverse=True)
        # -----------------------
        
        if not cards:
            status = Adw.StatusPage(icon_name="folder-open-symbolic", title="No Cards", description="Click '+' to add a card.")
            status.set_vexpand(True)
            self.list_box.append(status)
            return
        
        for card in cards:
            f_raw = card.get("front", "???")
            b_raw = card.get("back", "???")
            f_txt = html.escape(f_raw)
            b_txt = html.escape(b_raw)
            
            row = Adw.ActionRow(title=f_txt, subtitle=b_txt)
            row.set_title_lines(2)
            row.set_subtitle_lines(2)
            
            icon_box = Gtk.Box(spacing=5)
            if card.get("image"): icon_box.append(Gtk.Image.new_from_icon_name("image-x-generic-symbolic"))
            if card.get("audio"): icon_box.append(Gtk.Image.new_from_icon_name("audio-x-generic-symbolic"))
            if card.get("suspended"): 
                lbl = Gtk.Label(label="⚠️"); lbl.set_tooltip_text("Leech (Suspended)")
                icon_box.append(lbl)
            
            if icon_box.get_first_child(): row.add_prefix(icon_box)

            # Edit Button triggers the Unified Dialog
            btn_edit = Gtk.Button(icon_name="document-edit-symbolic")
            btn_edit.add_css_class("flat")
            btn_edit.set_tooltip_text("Edit")
            btn_edit.connect("clicked", lambda b, c=card: self.show_card_dialog("edit", c))
            row.add_suffix(btn_edit)
            
            btn_del = Gtk.Button(icon_name="user-trash-symbolic")
            btn_del.add_css_class("flat"); btn_del.add_css_class("destructive-action")
            btn_del.set_tooltip_text("Delete")
            btn_del.connect("clicked", lambda b, c=card: self.confirm_delete(c))
            row.add_suffix(btn_del)
            
            self.list_box.append(row)

    def on_delete_clicked(self, card_id):
        if card_id: db.delete_card(self.filename, card_id); self.refresh_list()

    # FIX: Unified Dialog for ADD and EDIT with Media Support
    def show_card_dialog(self, mode, card=None):
        title = "Add Card" if mode == "add" else "Edit Card"
        dialog = Adw.MessageDialog(heading=title, transient_for=self.get_root())
        dialog.set_modal(True)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        
        # Responsive Height Logic
        win_width = self.get_root().get_width()
        is_narrow = win_width < 500
        box_height = 90 if is_narrow else 120

        # Main Layout
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        # Front
        box.append(Gtk.Label(label="Front", xalign=0, css_classes=["heading"]))
        tf = Gtk.TextView(); tf.set_wrap_mode(3)
        tf.set_left_margin(10); tf.set_right_margin(10); tf.set_top_margin(10); tf.set_bottom_margin(10)
        if card: tf.get_buffer().set_text(card.get("front", ""))
        
        scroll_f = Gtk.ScrolledWindow(min_content_height=box_height)
        scroll_f.set_propagate_natural_height(True); scroll_f.set_hexpand(True)
        scroll_f.set_child(tf)
        box.append(Gtk.Frame(child=scroll_f))
        
        # Back
        box.append(Gtk.Label(label="Back", xalign=0, css_classes=["heading"]))
        tb = Gtk.TextView(); tb.set_wrap_mode(3)
        tb.set_left_margin(10); tb.set_right_margin(10); tb.set_top_margin(10); tb.set_bottom_margin(10)
        if card: tb.get_buffer().set_text(card.get("back", ""))
        
        scroll_b = Gtk.ScrolledWindow(min_content_height=box_height)
        scroll_b.set_propagate_natural_height(True); scroll_b.set_hexpand(True)
        scroll_b.set_child(tb)
        box.append(Gtk.Frame(child=scroll_b))
        
        # Metadata
        box.append(Gtk.Label(label="Hint", xalign=0, css_classes=["heading"]))
        th = Gtk.Entry()
        if card: th.set_text(card.get("hint", ""))
        box.append(th)
        
        box.append(Gtk.Label(label="Tags", xalign=0, css_classes=["heading"]))
        ent_tags = Gtk.Entry(); ent_tags.set_placeholder_text("tag1, tag2")
        if card: ent_tags.set_text(", ".join(card.get("tags", [])))
        box.append(ent_tags)
        
        # --- MEDIA CONTROLS ---
        self.temp_img = card.get("image") if card else None
        self.temp_aud = card.get("audio") if card else None
        
        # FIX: The create_media_row function now correctly appends items to the row!
        def create_media_row(label_text, current_val, type_hint):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            lbl = Gtk.Label(label=os.path.basename(current_val) if current_val else f"No {label_text}", hexpand=True, xalign=0)
            lbl.set_ellipsize(3)
            
            btn_del = Gtk.Button(icon_name="user-trash-symbolic", visible=bool(current_val))
            btn_add = Gtk.Button(icon_name="list-add-symbolic")
            if type_hint == "image": btn_add.set_icon_name("insert-image-symbolic")
            if type_hint == "audio": btn_add.set_icon_name("audio-volume-high-symbolic")
            
            # CRITICAL FIX: Append the widgets to the row!
            row.append(lbl)
            row.append(btn_add)
            row.append(btn_del)
            
            return row, lbl, btn_add, btn_del

        # Image Row
        row_img, lbl_img, btn_img_add, btn_img_del = create_media_row("Image", self.temp_img, "image")
        def on_img_del(b): self.temp_img = None; lbl_img.set_label("No Image"); btn_img_del.set_visible(False)
        def on_img_pick(b): self.pick_file("image", lambda p: setattr(self, 'temp_img', p) or lbl_img.set_label(os.path.basename(p)) or btn_img_del.set_visible(True))
        btn_img_del.connect("clicked", on_img_del); btn_img_add.connect("clicked", on_img_pick)
        box.append(row_img)

        # Audio Row
        row_aud, lbl_aud, btn_aud_add, btn_aud_del = create_media_row("Audio", self.temp_aud, "audio")
        def on_aud_del(b): self.temp_aud = None; lbl_aud.set_label("No Audio"); btn_aud_del.set_visible(False)
        def on_aud_pick(b): self.pick_file("audio", lambda p: setattr(self, 'temp_aud', p) or lbl_aud.set_label(os.path.basename(p)) or btn_aud_del.set_visible(True))
        btn_aud_del.connect("clicked", on_aud_del); btn_aud_add.connect("clicked", on_aud_pick)
        box.append(row_aud)
        
        # Unsuspend (Only for Edit Mode)
        self.unsuspend_flag = False
        if mode == "edit" and card.get("suspended"):
            btn_unsus = Gtk.Button(label="Unsuspend Leech"); box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)); box.append(btn_unsus)
            def unsus(b): self.unsuspend_flag = True; b.set_sensitive(False)
            btn_unsus.connect("clicked", unsus)

        # Layout Inversion (Scroll -> Clamp -> Content)
        scroll_main = Gtk.ScrolledWindow()
        scroll_main.set_propagate_natural_height(True)
        scroll_main.set_max_content_height(500)

        clamp = Adw.Clamp(maximum_size=600)
        clamp.set_margin_start(12); clamp.set_margin_end(12); clamp.set_margin_bottom(12)
        clamp.set_child(box)
        
        scroll_main.set_child(clamp)
        dialog.set_extra_child(scroll_main)

        def on_response(d, r):
            if r == "save":
                buf_f = tf.get_buffer(); buf_b = tb.get_buffer()
                s, e = buf_f.get_bounds(); new_f = buf_f.get_text(s, e, True).strip()
                s, e = buf_b.get_bounds(); new_b = buf_b.get_text(s, e, True).strip()
                tags = [t.strip() for t in ent_tags.get_text().split(",") if t.strip()]
                hint_val = th.get_text().strip()
                
                if new_f and new_b:
                    if mode == "add":
                        db.add_card_to_deck(self.filename, new_f, new_b, self.temp_img, self.temp_aud, tags, hint_val)
                    else:
                        is_suspended = not self.unsuspend_flag and card.get("suspended", False)
                        db.edit_card(self.filename, card["id"], new_f, new_b, self.temp_img, self.temp_aud, tags, is_suspended, hint_val)
                    self.refresh_list()
        
        dialog.connect("response", on_response); dialog.present()

    def pick_file(self, type_hint, callback):
        if hasattr(Gtk, "FileDialog"):
            d = Gtk.FileDialog(); f = Gtk.FileFilter()
            if type_hint == "image": f.set_name("Images"); f.add_pixbuf_formats()
            elif type_hint == "audio": f.set_name("Audio"); f.add_mime_type("audio/*")
            filters = Gio.ListStore.new(Gtk.FileFilter); filters.append(f); d.set_filters(filters); d.set_default_filter(f)
            def on_o(f, r):
                try: 
                    res = f.open_finish(r)
                    if res: callback(res.get_path())
                except: pass
            d.open(self.get_root(), None, on_o)

    def confirm_delete(self, card):
        # 1. Create the Dialog
        # We use the card content in the body to be specific about what is being deleted
        front_text = card.get("front", "this card")
        if len(front_text) > 30: front_text = front_text[:30] + "..."
        
        dialog = Adw.MessageDialog(
            heading="Delete Card?",
            body=f"Are you sure you want to delete '{front_text}'? This cannot be undone.",
            transient_for=self.get_root()
        )

        # 2. Add Responses
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")

        # 3. Style the "Delete" button as destructive (red)
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        # 4. Handle Response
        def on_response(d, response):
            if response == "delete":
                self.on_delete_clicked(card.get("id"))
            d.close()

        dialog.connect("response", on_response)
        dialog.present()