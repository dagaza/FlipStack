import gi
import data_engine as db
from datetime import datetime, timedelta

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk

class PerformanceView(Gtk.Box):
    def __init__(self, filename, session_stats=None, back_callback=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.filename = filename
        self.back_callback = back_callback
        deck_name = filename.replace(".json", "").replace("_", " ").title()

        css_provider = Gtk.CssProvider()
        css_provider.load_from_string("""
            .bar-green block.filled { background-color: #2ec27e; }
            .bar-yellow block.filled { background-color: #f5c211; }
            .bar-red block.filled { background-color: #ed333b; }
        """)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        
        # Load Data
        raw_history = db.get_deck_history(filename)
        sessions = self.group_into_sessions(raw_history)
        
        if session_stats and session_stats.get('total', 0) > 0:
            is_dup = False
            target_id = session_stats.get('session_id')
            
            # 1. Primary Check: Match by Session ID (100% accurate)
            if target_id:
                for s in sessions:
                    if s.get('session_id') == target_id:
                        is_dup = True
                        break
            
            # 2. Fallback Check: Timestamp heuristic (for legacy/missing IDs)
            elif sessions:
                last = sessions[-1]
                try:
                    dt_last = datetime.fromisoformat(last['start_time'])
                    # Increased tolerance to 10 minutes just in case, but ID check should catch 99%
                    if (datetime.now() - dt_last) < timedelta(minutes=10) and last['count'] == session_stats['total']:
                        is_dup = True
                except: pass
            
            if not is_dup:
                sessions.append({
                    'start_time': datetime.now().isoformat(),
                    'count': session_stats['total'],
                    'good': session_stats['good'],
                    'hard': session_stats['hard'],
                    'miss': session_stats['miss'],
                    'session_id': target_id
                })

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header.set_margin_top(20); header.set_margin_bottom(20)
        header.set_margin_start(20); header.set_margin_end(20)
        
        if self.back_callback:
            btn_back = Gtk.Button(icon_name="go-previous-symbolic")
            btn_back.add_css_class("flat")
            btn_back.set_tooltip_text("Return")
            btn_back.connect("clicked", lambda x: self.back_callback())
            header.append(btn_back)

        lbl_title = Gtk.Label(label=f"Performance: {deck_name}")
        lbl_title.add_css_class("title-1")
        header.append(lbl_title)
        
        self.append(header)
        self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True); scrolled.set_vexpand(True)
        self.append(scrolled)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=30)
        content_box.set_margin_top(20); content_box.set_margin_bottom(40)
        content_box.set_margin_start(40); content_box.set_margin_end(40)
        scrolled.set_child(content_box)

        # Daily Accuracy
        if raw_history:
            daily_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
            
            # Header with Tooltip
            head_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            head_box.append(Gtk.Label(label="Daily Accuracy", xalign=0, css_classes=["title-2"]))
            
            icon_info = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
            icon_info.set_tooltip_text("Accuracy Algorithm:\n• Good: 100%\n• Hard (No Hint): 100%\n• Hard (With Hint): 50%\n• Miss: 0%")
            head_box.append(icon_info)
            daily_box.append(head_box)
            
            daily_stats = {}
            for entry in raw_history:
                ts = entry.get('timestamp', entry.get('date', ''))
                date_str = ts.split("T")[0] 
                if date_str not in daily_stats: daily_stats[date_str] = []
                daily_stats[date_str].append(entry)

            sorted_dates = sorted(daily_stats.keys())[-7:]
            grid = Gtk.Grid(column_spacing=20, row_spacing=10)
            
            for i, d in enumerate(sorted_dates):
                entries = daily_stats[d]
                total_score = 0.0
                
                for e in entries:
                    r = e['rating']
                    hint = e.get('hint_used', False)
                    
                    if r == 3: # Good
                        total_score += 1.0
                    elif r == 2: # Hard
                        if hint: total_score += 0.5
                        else: total_score += 1.0
                    # Miss is 0
                
                acc = total_score / len(entries) if entries else 0.0
                
                grid.attach(Gtk.Label(label=d, xalign=0), 0, i, 1, 1)
                bar = Gtk.LevelBar(min_value=0, max_value=1.0)
                bar.set_value(acc); bar.set_hexpand(True)
                grid.attach(bar, 1, i, 1, 1)
                grid.attach(Gtk.Label(label=f"{int(acc*100)}%"), 2, i, 1, 1)
            
            daily_box.append(grid)
            content_box.append(daily_box)
            content_box.append(Gtk.Separator())

        # Session History
        sess_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        sess_box.append(Gtk.Label(label="Session Log", xalign=0, css_classes=["title-2"]))

        if not sessions:
            sess_box.append(Gtk.Label(label="No sessions recorded yet.", css_classes=["dim-label"]))
        else:
            for sess in reversed(sessions):
                sess_frame = Gtk.Frame()
                sess_inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
                sess_inner.set_margin_top(15); sess_inner.set_margin_bottom(15)
                sess_inner.set_margin_start(15); sess_inner.set_margin_end(15)
                sess_frame.set_child(sess_inner)

                try:
                    dt_obj = datetime.fromisoformat(sess['start_time'])
                    pretty_date = dt_obj.strftime("%A, %b %d at %H:%M")
                except:
                    pretty_date = "Unknown Date"
                
                info_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
                info_row.append(Gtk.Label(label=pretty_date, css_classes=["heading"]))
                info_row.append(Gtk.Label(hexpand=True))
                info_row.append(Gtk.Label(label=f"{sess['count']} cards", css_classes=["dim-label"]))
                sess_inner.append(info_row)

                stats_grid = Gtk.Grid(column_spacing=15, row_spacing=5)
                
                stats_grid.attach(Gtk.Label(label="Good", xalign=0), 0, 0, 1, 1)
                bar_g = Gtk.LevelBar(min_value=0, max_value=sess['count'])
                bar_g.set_value(sess['good']); bar_g.add_css_class("bar-green"); bar_g.set_hexpand(True)
                stats_grid.attach(bar_g, 1, 0, 1, 1)
                stats_grid.attach(Gtk.Label(label=str(sess['good'])), 2, 0, 1, 1)

                stats_grid.attach(Gtk.Label(label="Hard", xalign=0), 0, 1, 1, 1)
                bar_h = Gtk.LevelBar(min_value=0, max_value=sess['count'])
                bar_h.set_value(sess['hard']); bar_h.add_css_class("bar-yellow"); bar_h.set_hexpand(True)
                stats_grid.attach(bar_h, 1, 1, 1, 1)
                stats_grid.attach(Gtk.Label(label=str(sess['hard'])), 2, 1, 1, 1)

                stats_grid.attach(Gtk.Label(label="Miss", xalign=0), 0, 2, 1, 1)
                bar_m = Gtk.LevelBar(min_value=0, max_value=sess['count'])
                bar_m.set_value(sess['miss']); bar_m.add_css_class("bar-red"); bar_m.set_hexpand(True)
                stats_grid.attach(bar_m, 1, 2, 1, 1)
                stats_grid.attach(Gtk.Label(label=str(sess['miss'])), 2, 2, 1, 1)

                sess_inner.append(stats_grid)
                sess_box.append(sess_frame)

        content_box.append(sess_box)

    def group_into_sessions(self, raw_history):
        if not raw_history: return []
        
        legacy = []
        modern = []
        
        for r in raw_history:
            if 'session_id' in r and r['session_id']:
                modern.append(r)
            else:
                if 'timestamp' not in r and 'date' in r:
                    r['timestamp'] = r['date'] + "T12:00:00"
                if 'timestamp' in r:
                    legacy.append(r)

        sessions = []
        modern_groups = {}
        modern_order = [] 
        
        for entry in modern:
            sid = entry['session_id']
            if sid not in modern_groups:
                modern_groups[sid] = self.new_session_dict(datetime.fromisoformat(entry['timestamp']))
                modern_groups[sid]['session_id'] = sid # Store ID in group for lookup
                modern_order.append(sid)
            
            s = modern_groups[sid]
            s['count'] += 1
            ts = datetime.fromisoformat(entry['timestamp'])
            st = datetime.fromisoformat(s['start_time'])
            if ts < st: s['start_time'] = entry['timestamp']
            
            r = entry['rating']
            if r == 3: s['good'] += 1
            elif r == 2: s['hard'] += 1
            elif r == 1: s['miss'] += 1
            
        for sid in modern_order:
            sessions.append(modern_groups[sid])

        if legacy:
            legacy.sort(key=lambda x: x['timestamp'])
            current_session = None
            for entry in legacy:
                ts = datetime.fromisoformat(entry['timestamp'])
                if not current_session:
                    current_session = self.new_session_dict(ts)
                else:
                    last_ts = current_session['last_ts_obj']
                    if (ts - last_ts) > timedelta(minutes=2):
                        sessions.append(current_session)
                        current_session = self.new_session_dict(ts)
                
                current_session['count'] += 1
                current_session['last_ts_obj'] = ts
                r = entry['rating']
                if r == 3: current_session['good'] += 1
                elif r == 2: current_session['hard'] += 1
                elif r == 1: current_session['miss'] += 1
            if current_session: sessions.append(current_session)

        sessions.sort(key=lambda s: s['start_time'])
        return sessions

    def new_session_dict(self, ts_obj):
        return { 
            'start_time': ts_obj.isoformat(), 
            'last_ts_obj': ts_obj, 
            'count': 0, 'good': 0, 'hard': 0, 'miss': 0,
            'session_id': None 
        }