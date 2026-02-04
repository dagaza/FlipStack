# FlipStack

FlipStack is a modern, open-source Flashcard application built for Linux. It uses Spaced Repetition (SRS) to help you master any subject efficiently—from languages and history to math and programming. Built with Python and GTK4/LibAdwaita, it offers a clean, native experience on Linux Mint, Ubuntu, Fedora, and other modern distributions.

![FlipStack Screenshot](https://raw.githubusercontent.com/dagaza/flipstack/main/assets/screenshots/flashcard_front_light.png) 

## 🧠 Features

* **Smart Study Modes:**
    * **Spaced Repetition:** Uses a Leitner-style system to schedule cards based on your performance.
    * **Cram Mode:** Review an entire deck instantly, ignoring the schedule.
    * **Reverse Mode:** Flip question/answer sides to test bidirectional knowledge.
    * **Shuffle:** Randomize your session order.
* **Rich Dashboard:** Visualize your consistency with a GitHub-style activity heatmap and streak counter.
* **Deck Management:**
    * Organize decks into custom **Categories**.
    * **Import** from CSV files or other flashcard apps such as Anki (`.apkg`).
    * **Export** your data to JSON or CSV.
* **Powerful Editor:**
    * Supports **Images** and **Audio**.
    * Rich text support (Bold/Italic/Strikethrough/Code blocks via Markdown syntax).
    * **Leech Management:** Automatically suspends cards you constantly miss.
* **Customization:**
    * Dark/Light mode toggle.
    * Dynamic font family and size adjustments.
    * Sound effects (toggleable).

## 📦 Dependencies

FlipStack is built with **Python 3**, **GTK4**, and **LibAdwaita**.

### System Requirements (Ubuntu/Debian/Fedora)
You need the system-level development headers for GObject Introspection and GTK4.

**Ubuntu / Debian / Linux Mint:**
```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 libgirepository1.0-dev
```

**Fedora:**
```bash
sudo dnf install python3-gobject gtk4 libadwaita speech-dispatcher
```

## 🚀 Installation & Running Locally

1. **Clone the repository:**
   ```bash
   git clone https://github.com/dagaza/FlipStack.git
   cd FlipStack
   ```

2. **Set up a virtual environment (Optional but recommended):**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Python requirements:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app:**
   ```bash
   python3 main.py
   ```

## 🛠️ Project Structure

* `main.py`: The entry point and main window logic.
* `data_engine.py`: Handles database operations (JSON), imports, and the SRS algorithm.
* `study_session.py`: The logic for the flashcard review screen.
* `dashboard_view.py`: The "Home" screen with the heatmap and stats.
* `performance_view.py`: The "Performance" screen displaying stats for individual decks.
* `deck_editor.py`: The GUI for adding/editing cards and assets.
* `assets/`: Contains static application resources (Read-Only).
  * `assets/icons/`: Application logos and window icons.
  * `assets/sounds/`: UI sound effects (correct, incorrect, flip).
  * `assets/screenshots/`: Images used in the README and AppStream metadata.
* `user_data/`: Contains all user-generated content (Ignored by Git).
  * `user_data/decks/`: Flashcard data stored as JSON files.
  * `user_data/assets/`: Media files (images/audio) attached to user flashcards.
  * `user_data/backups/`: Automatic backups (*.zip) of the user database.

## 🤝 Contributing

Contributions are welcome! If you find a bug, want to add a feature, or improve the UX, feel free to open an Issue or Pull Request.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

Distributed under the MIT License. See LICENSE for more information.
