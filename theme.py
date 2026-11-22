"""Тёмная чёрно-фиолетовая тема оформления для Tkinter/ttk."""
from tkinter import ttk

BG = "#0d0a14"          # фон окна
SURFACE = "#171122"     # карточки, таблицы, поля
SURFACE2 = "#221836"    # поля ввода, заголовки таблиц
STRIPE = "#1d1630"      # чётные строки таблиц
BORDER = "#3a2a5c"
TEXT = "#ece7f7"
MUTED = "#9a8db8"
ACCENT = "#8b5cf6"      # основной фиолетовый
ACCENT_HI = "#b79cff"
ACCENT_LO = "#5b34b8"
DANGER = "#fb7185"
BAR_COLORS = {"watching": "#8b5cf6", "completed": "#c4b5fd", "plan": "#6d4fc4",
              "on_hold": "#a855f7", "dropped": "#e879f9"}


def apply_theme(root) -> None:
    """Применяет тему ко всему приложению (ttk-стили и параметры tk-виджетов)."""
    root.configure(background=BG)
    for pattern, value in {
        "*TCombobox*Listbox.background": SURFACE2, "*TCombobox*Listbox.foreground": TEXT,
        "*TCombobox*Listbox.selectBackground": ACCENT, "*TCombobox*Listbox.selectForeground": "white",
        "*Text.background": SURFACE, "*Text.foreground": TEXT, "*Text.insertBackground": TEXT,
        "*Text.selectBackground": ACCENT_LO, "*Text.relief": "flat",
        "*Text.highlightThickness": 1, "*Text.highlightBackground": BORDER,
        "*Text.highlightColor": ACCENT,
    }.items():
        root.option_add(pattern, value)

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=TEXT, fieldbackground=SURFACE2,
                bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                troughcolor=SURFACE, focuscolor=ACCENT, insertcolor=TEXT)
    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=SURFACE, bordercolor=BORDER, relief="solid", borderwidth=1)
    s.configure("TLabel", background=BG, foreground=TEXT)
    s.configure("Card.TLabel", background=SURFACE, foreground=TEXT)
    s.configure("Muted.TLabel", foreground=MUTED)
    s.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED)
    s.configure("Title.TLabel", foreground=ACCENT_HI)
    s.configure("Error.TLabel", foreground=DANGER)
    s.configure("CardError.TLabel", background=SURFACE, foreground=DANGER)
    s.configure("TLabelframe", background=BG, bordercolor=BORDER, relief="solid")
    s.configure("TLabelframe.Label", background=BG, foreground=ACCENT_HI,
                font=("TkDefaultFont", 10, "bold"))

    s.configure("TButton", background=SURFACE2, foreground=TEXT, bordercolor=BORDER,
                padding=(14, 6), relief="flat")
    s.map("TButton", background=[("pressed", ACCENT), ("active", ACCENT_LO)],
          foreground=[("active", "white")], bordercolor=[("active", ACCENT)])
    s.configure("Accent.TButton", background=ACCENT, foreground="white", bordercolor=ACCENT)
    s.map("Accent.TButton", background=[("pressed", ACCENT_LO), ("active", ACCENT_HI)],
          foreground=[("active", "#120a24")])

    for name in ("TEntry", "TSpinbox", "TCombobox"):
        s.configure(name, fieldbackground=SURFACE2, foreground=TEXT, insertcolor=TEXT,
                    bordercolor=BORDER, arrowcolor=ACCENT_HI, padding=4)
        s.map(name, bordercolor=[("focus", ACCENT)], fieldbackground=[("readonly", SURFACE2)],
              foreground=[("readonly", TEXT)], selectbackground=[("readonly", SURFACE2)],
              selectforeground=[("readonly", TEXT)])

    s.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
    s.configure("TNotebook.Tab", background=SURFACE, foreground=MUTED, padding=(18, 8),
                borderwidth=0)
    s.map("TNotebook.Tab", background=[("selected", ACCENT), ("active", SURFACE2)],
          foreground=[("selected", "white"), ("active", TEXT)])

    s.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                rowheight=28, bordercolor=BORDER, borderwidth=0)
    s.map("Treeview", background=[("selected", ACCENT_LO)], foreground=[("selected", "white")])
    s.configure("Posters.Treeview", rowheight=66)        # строки с миниатюрами постеров 40×60
    s.configure("Treeview.Heading", background=SURFACE2, foreground=ACCENT_HI, relief="flat",
                padding=(6, 6), font=("TkDefaultFont", 10, "bold"))
    s.map("Treeview.Heading", background=[("active", ACCENT_LO)], foreground=[("active", "white")])

    # Плоский узкий ползунок без стрелок: единый прямоугольник, а не «разобранный» на части
    for orient in ("Vertical", "Horizontal"):
        name = f"{orient}.TScrollbar"
        sticky = "ns" if orient == "Vertical" else "ew"
        s.layout(name, [(f"{orient}.Scrollbar.trough", {"sticky": sticky, "children": [
            (f"{orient}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
        s.configure(name, gripcount=0, background=ACCENT_LO, darkcolor=ACCENT_LO, lightcolor=ACCENT_LO,
                    troughcolor=SURFACE, bordercolor=SURFACE, borderwidth=0, relief="flat", width=11)
        s.map(name, background=[("pressed", ACCENT_HI), ("active", ACCENT)],
              darkcolor=[("pressed", ACCENT_HI), ("active", ACCENT)],
              lightcolor=[("pressed", ACCENT_HI), ("active", ACCENT)])
    s.configure("Toolbutton", background=SURFACE, foreground=MUTED, padding=(14, 6),
                bordercolor=BORDER)
    s.map("Toolbutton", background=[("selected", ACCENT), ("active", SURFACE2)],
          foreground=[("selected", "white"), ("active", TEXT)])
    s.configure("TSeparator", background=BORDER)
    s.configure("Horizontal.TProgressbar", troughcolor=SURFACE2, background=ACCENT, bordercolor=BORDER,
                lightcolor=ACCENT, darkcolor=ACCENT)
    s.configure("TCheckbutton", background=BG, foreground=TEXT, indicatorbackground=SURFACE2,
                indicatorforeground=ACCENT_HI, bordercolor=BORDER)
    s.map("TCheckbutton", background=[("active", BG)], indicatorbackground=[("selected", ACCENT_LO)])
