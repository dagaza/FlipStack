import gi
import data_engine as db
import os

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, Gio, GObject

class DeckEditor(Gtk.Box):
    def __init__(self, filename, back_callback=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.filename = filename
        self.back_callback = back_callback
        
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header_box.set_margin_top(20); header_box.set_margin_bottom(20)
        header_box.set_margin_start(20); header_box.set_margin_end(20)
        
        if self.back_callback:
            btn_back = Gtk.Button(icon_name="go-previous-symbolic")
            btn_back.add_css_class("flat"); btn_back.set_tooltip_text("Return")
            btn_back.connect("clicked", lambda x: self.back_callback())
            header_box.append(btn_back)
        
        title = Gtk.Label(label=f"Edit: {filename.replace('.json', '').replace('_', ' ').title()}")
        title.add_css_class("title-1"); header_box.append(title)
        self.append(header_box); self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        self.scroll = Gtk.ScrolledWindow(); self.scroll.set_hexpand(True); self.scroll.set_vexpand(True); self.append(self.scroll)
        self.clamp = Adw.Clamp(maximum_size=800); self.scroll.set_child(self.clamp)
        self.list_box = Gtk.ListBox(); self.list_box.add_css_class("boxed-list"); self.list_box.set_selection_mode(Gtk.SelectionMode.NONE); self.list_box.set_margin_top(20); self.list_box.set_margin_bottom(20); self.list_box.set_margin_start(20); self.list_box.set_margin_end(20); self.clamp.set_child(self.list_box)
        self.refresh_list()

    def refresh_list(self):
        while child := self.list_box.get_first_child(): self.list_box.remove(child)
        cards = db.load_deck(self.filename)
        if not cards: self.list_box.append(Adw.ActionRow(title="No cards yet")); return
        for card in cards:
            f_txt = card.get("front", "???"); b_txt = card.get("back", "???"); row = Adw.ActionRow(title=f_txt, subtitle=b_txt)
            icon_box = Gtk.Box(spacing=5)
            if card.get("image"): icon_box.append(Gtk.Image.new_from_icon_name("image-x-generic-symbolic"))
            if card.get("audio"): icon_box.append(Gtk.Image.new_from_icon_name("audio-x-generic-symbolic"))
            if card.get("suspended"): lbl = Gtk.Label(label="⚠️ Leech"); lbl.add_css_class("error"); icon_box.append(lbl)
            row.add_prefix(icon_box)
            btn_edit = Gtk.Button(icon_name="document-edit-symbolic"); btn_edit.add_css_class("flat"); btn_edit.connect("clicked", lambda b, c=card: self.on_edit_clicked(c)); row.add_suffix(btn_edit)
            btn_del = Gtk.Button(icon_name="user-trash-symbolic"); btn_del.add_css_class("flat"); btn_del.add_css_class("destructive-action"); btn_del.connect("clicked", lambda b, cid=card.get("id"): self.on_delete_clicked(cid)); row.add_suffix(btn_del); self.list_box.append(row)

    def on_delete_clicked(self, card_id):
        if card_id: db.delete_card(self.filename, card_id); self.refresh_list()

    def on_edit_clicked(self, card):
        dialog = Adw.MessageDialog(heading="Edit Card", transient_for=self.get_root()); dialog.set_modal(True); dialog.add_response("cancel", "Cancel"); dialog.add_response("save", "Save"); dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED); box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        box.append(Gtk.Label(label="Front", xalign=0))
        tf = Gtk.TextView(); tf.set_wrap_mode(3); tf.set_left_margin(10); tf.set_right_margin(10); tf.set_top_margin(10); tf.set_bottom_margin(10); tf.get_buffer().set_text(card.get("front", ""))
        
        # --- FIX 1: Increased height and added hexpand ---
        scroll_f = Gtk.ScrolledWindow(min_content_height=150)
        scroll_f.set_propagate_natural_height(True)
        scroll_f.set_hexpand(True)
        scroll_f.set_child(tf); box.append(Gtk.Frame(child=scroll_f))
        
        box.append(Gtk.Label(label="Back", xalign=0))
        tb = Gtk.TextView(); tb.set_wrap_mode(3); tb.set_left_margin(10); tb.set_right_margin(10); tb.set_top_margin(10); tb.set_bottom_margin(10); tb.get_buffer().set_text(card.get("back", ""))
        
        # --- FIX 1: Increased height and added hexpand ---
        scroll_b = Gtk.ScrolledWindow(min_content_height=150)
        scroll_b.set_propagate_natural_height(True)
        scroll_b.set_hexpand(True)
        scroll_b.set_child(tb); box.append(Gtk.Frame(child=scroll_b))
        
        box.append(Gtk.Label(label="Hint (Optional)", xalign=0)); th = Gtk.Entry(); th.set_text(card.get("hint", "")); box.append(th)
        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        box.append(Gtk.Label(label="Tags (comma separated)", xalign=0)); ent_tags = Gtk.Entry(); ent_tags.set_text(", ".join(card.get("tags", []))); box.append(ent_tags)
        
        self.new_img = card.get("image"); self.new_aud = card.get("audio")
        row_img = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_img = Gtk.Label(label=os.path.basename(self.new_img) if self.new_img else "No Image", hexpand=True, xalign=0)
        btn_img_del = Gtk.Button(icon_name="user-trash-symbolic", visible=bool(self.new_img))
        btn_img_add = Gtk.Button(icon_name="insert-image-symbolic")
        def on_img_del(b): self.new_img = None; lbl_img.set_label("No Image"); btn_img_del.set_visible(False)
        def on_img_pick(b): self.pick_file("image", lambda p: setattr(self, 'new_img', p) or lbl_img.set_label(os.path.basename(p)) or btn_img_del.set_visible(True))
        btn_img_del.connect("clicked", on_img_del); btn_img_add.connect("clicked", on_img_pick)
        row_img.append(lbl_img); row_img.append(btn_img_add); row_img.append(btn_img_del); box.append(row_img)

        row_aud = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl_aud = Gtk.Label(label=os.path.basename(self.new_aud) if self.new_aud else "No Audio", hexpand=True, xalign=0)
        btn_aud_del = Gtk.Button(icon_name="user-trash-symbolic", visible=bool(self.new_aud))
        btn_aud_add = Gtk.Button(icon_name="audio-volume-high-symbolic")
        def on_aud_del(b): self.new_aud = None; lbl_aud.set_label("No Audio"); btn_aud_del.set_visible(False)
        def on_aud_pick(b): self.pick_file("audio", lambda p: setattr(self, 'new_aud', p) or lbl_aud.set_label(os.path.basename(p)) or btn_aud_del.set_visible(True))
        btn_aud_del.connect("clicked", on_aud_del); btn_aud_add.connect("clicked", on_aud_pick)
        row_aud.append(lbl_aud); row_aud.append(btn_aud_add); row_aud.append(btn_aud_del); box.append(row_aud)
        
        if card.get("suspended"):
            btn_unsus = Gtk.Button(label="Unsuspend Leech"); box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)); box.append(btn_unsus); self.unsuspend_flag = False
            def unsus(b): self.unsuspend_flag = True; b.set_sensitive(False)
            btn_unsus.connect("clicked", unsus)
        else: self.unsuspend_flag = False

        # --- FIX 2: Wrap in Clamp for wider dialog ---
        clamp = Adw.Clamp(maximum_size=800)
        clamp.set_child(box)
        dialog.set_extra_child(clamp)

        def on_response(d, r):
            if r == "save":
                s, e = buf_f.get_bounds(); new_f = buf_f.get_text(s, e, True).strip()
                s, e = buf_b.get_bounds(); new_b = buf_b.get_text(s, e, True).strip()
                tags = [t.strip() for t in ent_tags.get_text().split(",") if t.strip()]
                hint_val = th.get_text().strip()
                if new_f and new_b:
                    db.edit_card(self.filename, card["id"], new_f, new_b, self.new_img, self.new_aud, tags, not self.unsuspend_flag and card.get("suspended", False), hint_val)
                    self.refresh_list()
        
        buf_f = tf.get_buffer(); buf_b = tb.get_buffer()
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