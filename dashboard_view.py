import gi
import data_engine as db
from datetime import datetime, timedelta

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk

class DashboardView(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.set_margin_top(30)
        self.set_margin_bottom(30)
        self.set_margin_start(40)
        self.set_margin_end(40)

        # Title
        title = Gtk.Label(label="Activity Dashboard")
        title.add_css_class("title-1")
        self.append(title)

        # Stats Section (Centered)
        stats = db.load_stats()
        stats_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        stats_box.set_halign(Gtk.Align.CENTER)
        
        # Streak Card (Kept reference for refresh)
        self.lbl_streak_val = Gtk.Label(label=str(stats['streak']))
        self.lbl_streak_val.add_css_class("title-1")
        
        card_streak = self.create_stat_card("🔥 Streak", self.lbl_streak_val)
        stats_box.append(card_streak)
        
        self.append(stats_box)
        self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # --- Heatmap Header ---
        hm_header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hm_header_box.set_halign(Gtk.Align.CENTER)
        
        self.current_view_year = datetime.now().year
        
        btn_prev = Gtk.Button(icon_name="go-previous-symbolic")
        btn_prev.add_css_class("flat")
        btn_prev.set_tooltip_text("Previous Year")
        btn_prev.connect("clicked", lambda x: self.change_year(-1))
        
        self.lbl_year = Gtk.Label(label=f"{self.current_view_year} Contributions")
        self.lbl_year.add_css_class("heading")
        
        btn_next = Gtk.Button(icon_name="go-next-symbolic")
        btn_next.add_css_class("flat")
        btn_next.set_tooltip_text("Next Year")
        btn_next.connect("clicked", lambda x: self.change_year(1))
        
        hm_header_box.append(btn_prev)
        hm_header_box.append(self.lbl_year)
        hm_header_box.append(btn_next)
        
        self.append(hm_header_box)

        # Scrollable Heatmap Container
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_min_content_height(200) 
        scroll.set_kinetic_scrolling(False) # X11 Fix
        
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_halign(Gtk.Align.CENTER)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flowbox.set_min_children_per_line(10)
        self.flowbox.set_max_children_per_line(60)
        self.flowbox.set_row_spacing(3)
        self.flowbox.set_column_spacing(3)
        
        scroll.set_child(self.flowbox)
        self.append(scroll)

        # --- Legend Grid (3x2) ---
        legend_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        legend_box.set_halign(Gtk.Align.CENTER)
        legend_box.set_margin_top(10)
        
        # Grid Setup
        grid = Gtk.Grid(column_spacing=20, row_spacing=8)
        
        # Helper to create a legend item (Box + Label)
        def create_legend_item(css_class, text):
            item = Gtk.Box(spacing=8)
            
            # The colored square
            square = Gtk.Box()
            square.set_size_request(14, 14)
            square.add_css_class("heatmap-box")
            square.add_css_class(css_class)
            
            lbl = Gtk.Label(label=text)
            lbl.add_css_class("caption")
            
            item.append(square)
            item.append(lbl)
            return item

        # Row 1
        grid.attach(create_legend_item("hm-0", "No Activity"), 0, 0, 1, 1)        # Gray
        grid.attach(create_legend_item("hm-future", "Future Date"), 1, 0, 1, 1)   # Outline
                
        # Row 2
        grid.attach(create_legend_item("hm-1", "Light (<30)"), 0, 1, 1, 1)        # Low Opacity Green
        grid.attach(create_legend_item("hm-2", "Normal (30-50)"), 1, 1, 1, 1)     # Med Opacity Green
        
        # Row 3
        grid.attach(create_legend_item("hm-3", "Heavy (50-100)"), 0, 2, 1, 1)     # High Opacity Green
        grid.attach(create_legend_item("hm-4", "Heroic (100+)"), 1, 2, 1, 1)      # Full Opacity Green

        
        legend_box.append(grid)
        self.append(legend_box)

        self.render_heatmap()

    def refresh(self):
        # 1. Reloads Stats
        stats = db.load_stats()
        self.lbl_streak_val.set_label(str(stats['streak']))
        # 2. Redraws heatmap
        self.render_heatmap()

    def create_stat_card(self, title, val_widget):
        frame = Gtk.Frame()
        frame.set_size_request(140, 90)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_top(10); box.set_margin_bottom(10)
        
        box.append(val_widget)
        
        lbl_tit = Gtk.Label(label=title)
        lbl_tit.add_css_class("caption-heading"); lbl_tit.add_css_class("dim-label")
        box.append(lbl_tit)
        
        frame.set_child(box)
        return frame

    def change_year(self, delta):
        self.current_view_year += delta
        self.lbl_year.set_label(f"{self.current_view_year} Contributions")
        self.render_heatmap()

    def render_heatmap(self):
        while child := self.flowbox.get_first_child():
            self.flowbox.remove(child)

        data = db.get_heatmap_data() 
        today = datetime.today().date()
        
        target_year = self.current_view_year
        start_date = datetime(target_year, 1, 1).date()
        next_year_start = datetime(target_year + 1, 1, 1).date()
        days_in_year = (next_year_start - start_date).days
        
        for i in range(days_in_year):
            curr_date = start_date + timedelta(days=i)
            date_str = curr_date.strftime("%Y-%m-%d")
            count = data.get(date_str, 0)
            
            color_class = "hm-0" 
            tooltip = f"{date_str}: {count} reviews"

            if curr_date > today:
                color_class = "hm-future" 
                tooltip = f"{date_str}"
            elif count > 0:
                # Thresholds
                if count > 100: color_class = "hm-4"      # Heroic
                elif count > 50: color_class = "hm-3"     # Heavy
                elif count >= 30: color_class = "hm-2"    # Normal
                else: color_class = "hm-1"                # Light (<30)
            
            box = Gtk.Box()
            box.set_size_request(14, 14)
            box.add_css_class("heatmap-box")
            box.add_css_class(color_class)
            box.set_tooltip_text(tooltip)
            
            self.flowbox.append(box)