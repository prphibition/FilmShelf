"""Экран входа и регистрации."""
import tkinter as tk
from tkinter import ttk

from ..config import APP_NAME
from ..services import ServiceError
from .theme import ACCENT_HI


class LoginFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.mode = "login"
        self.username = tk.StringVar()
        self.email = tk.StringVar()
        self.password = tk.StringVar()
        self.confirm = tk.StringVar()

        box = ttk.Frame(self, padding=32, style="Card.TFrame")
        box.place(relx=0.5, rely=0.45, anchor="center")
        ttk.Label(box, text=APP_NAME, style="Card.TLabel", foreground=ACCENT_HI,
                  font=("TkDefaultFont", 24, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 2))
        ttk.Label(box, text="Ваша личная фильмотека", style="CardMuted.TLabel").grid(
            row=1, column=0, columnspan=2, pady=(0, 14))
        self.heading = ttk.Label(box, text="Вход", style="Card.TLabel",
                                font=("TkDefaultFont", 13, "bold"))
        self.heading.grid(row=2, column=0, columnspan=2, pady=(0, 8))

        self.rows = {}
        for r, (key, text, var, secret) in enumerate((
                ("username", "Логин", self.username, False),
                ("email", "Электронная почта", self.email, False),
                ("password", "Пароль", self.password, True),
                ("confirm", "Повтор пароля", self.confirm, True)), start=3):
            label = ttk.Label(box, text=text, style="Card.TLabel")
            entry = ttk.Entry(box, textvariable=var, width=32, show="•" if secret else "")
            label.grid(row=r, column=0, sticky="w", pady=3, padx=(0, 10))
            entry.grid(row=r, column=1, pady=3)
            self.rows[key] = (label, entry)

        self.error = ttk.Label(box, text="", style="CardError.TLabel", wraplength=330)
        self.error.grid(row=7, column=0, columnspan=2, pady=(6, 0))
        self.submit = ttk.Button(box, text="Войти", command=self.on_submit,
                                 style="Accent.TButton")
        self.submit.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        self.switch = ttk.Button(box, text="Нет аккаунта? Зарегистрироваться",
                                 command=self.toggle_mode)
        self.switch.grid(row=9, column=0, columnspan=2, sticky="ew")
        self.apply_mode()
        self.rows["username"][1].focus_set()
        self.bind_all("<Return>", lambda e: self.on_submit() if self.winfo_exists() else None)

    def apply_mode(self) -> None:
        register = self.mode == "register"
        for key in ("email", "confirm"):
            for widget in self.rows[key]:
                widget.grid() if register else widget.grid_remove()
        self.heading.config(text="Регистрация" if register else "Вход")
        self.submit.config(text="Создать аккаунт" if register else "Войти")
        self.switch.config(text="Уже есть аккаунт? Войти" if register
                           else "Нет аккаунта? Зарегистрироваться")
        self.error.config(text="")

    def toggle_mode(self) -> None:
        self.mode = "register" if self.mode == "login" else "login"
        self.apply_mode()

    def on_submit(self) -> None:
        auth = self.app.services.auth
        try:
            if self.mode == "register":
                if self.password.get() != self.confirm.get():
                    raise ServiceError("Пароли не совпадают.")
                user = auth.register(self.username.get(), self.email.get(),
                                     self.password.get())
            else:
                user = auth.login(self.username.get(), self.password.get())
        except ServiceError as exc:
            self.error.config(text=str(exc))
            return
        self.unbind_all("<Return>")
        self.app.on_login(user)
