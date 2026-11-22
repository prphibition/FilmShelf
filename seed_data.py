"""Демонстрационные данные: тайтлы каталога, пользователи и их оценки.

Оценки и списки пользователей сгенерированы случайно (с фиксированным
начальным значением) и нужны только для показа возможностей приложения.
"""
import random
import sqlite3

from .repository import ListRepository, ReviewRepository, TitleRepository
from .security import hash_password

# (название, оригинальное название, тип, год, страна, серий, мин., жанры, описание)
TITLES = [
    ("Паразиты", "Gisaengchung", "movie", 2019, "Южная Корея", 1, 132,
     ["Драма", "Триллер", "Комедия"],
     "Бедная семья по очереди устраивается на работу в дом состоятельных "
     "людей, скрывая родственные связи."),
    ("Поезд в Пусан", "Busanhaeng", "movie", 2016, "Южная Корея", 1, 118,
     ["Ужасы", "Боевик", "Триллер"],
     "Пассажиры скоростного поезда пытаются выжить во время вспышки "
     "неизвестной инфекции."),
    ("Олдбой", "Oldboy", "movie", 2003, "Южная Корея", 1, 120,
     ["Триллер", "Детектив", "Драма"],
     "Человек, много лет проведший в заключении без объяснений, выходит на "
     "свободу и ищет тех, кто это устроил."),
    ("Воспоминания об убийстве", "Salinui chueok", "movie", 2003, "Южная Корея", 1, 131,
     ["Детектив", "Криминал", "Драма"],
     "Сыщики провинциального городка ищут серийного убийцу в конце 1980-х годов."),
    ("Crash Landing on You", "Sarangui Bulsichak", "drama", 2019, "Южная Корея", 16, 80,
     ["Романтика", "Комедия", "Драма"],
     "Наследница южнокорейской компании после аварии на параплане оказывается "
     "по ту сторону границы."),
    ("Goblin", "Dokkaebi", "drama", 2016, "Южная Корея", 16, 75,
     ["Фэнтези", "Романтика", "Драма"],
     "Бессмертный дух-гоблин ищет невесту, способную освободить его от "
     "векового бремени."),
    ("Игра в кальмара", "Ojingeo Geim", "drama", 2021, "Южная Корея", 9, 55,
     ["Триллер", "Драма"],
     "Люди, обременённые долгами, соглашаются участвовать в смертельных "
     "детских играх ради денежного приза."),
    ("Королевство", "Kingdom", "drama", 2019, "Южная Корея", 12, 50,
     ["Ужасы", "Исторический", "Триллер"],
     "В эпоху Чосон наследный принц расследует таинственную эпидемию, "
     "превращающую людей в одержимых."),
    ("Унесённые призраками", "Sen to Chihiro no Kamikakushi", "anime", 2001, "Япония", 1, 125,
     ["Фэнтези", "Приключения", "Семейный"],
     "Девочка попадает в мир духов и должна спасти родителей, превращённых в свиней."),
    ("Твоё имя", "Kimi no Na wa.", "anime", 2016, "Япония", 1, 107,
     ["Романтика", "Драма", "Фэнтези"],
     "Подростки из разных мест начинают меняться телами во сне и пытаются "
     "найти друг друга."),
    ("Мой сосед Тоторо", "Tonari no Totoro", "anime", 1988, "Япония", 1, 86,
     ["Семейный", "Фэнтези"],
     "Две сестры переезжают в деревню и знакомятся с добрыми лесными духами."),
    ("Принцесса Мононоке", "Mononoke-hime", "anime", 1997, "Япония", 1, 134,
     ["Приключения", "Фэнтези", "Драма"],
     "Юный воин оказывается между людьми и духами леса, воюющими за природные ресурсы."),
    ("Тетрадь смерти", "Death Note", "anime", 2006, "Япония", 37, 23,
     ["Триллер", "Детектив", "Мистика"],
     "Школьник находит тетрадь, позволяющую убивать людей, и сталкивается с "
     "гениальным детективом."),
    ("Стальной алхимик: Братство", "Hagane no Renkinjutsushi: FA", "anime", 2009,
     "Япония", 64, 24, ["Приключения", "Фэнтези", "Боевик"],
     "Братья-алхимики отправляются на поиски философского камня, чтобы "
     "вернуть утраченное."),
    ("Начало", "Inception", "movie", 2010, "США", 1, 148,
     ["Фантастика", "Триллер", "Боевик"],
     "Вор, проникающий в сны, получает задание внедрить идею в сознание человека."),
    ("Побег из Шоушенка", "The Shawshank Redemption", "movie", 1994, "США", 1, 142,
     ["Драма"],
     "Банкир, несправедливо осуждённый за убийство, находит надежду в "
     "дружбе за стенами тюрьмы."),
    ("Интерстеллар", "Interstellar", "movie", 2014, "США", 1, 169,
     ["Фантастика", "Драма", "Приключения"],
     "Экспедиция отправляется через червоточину на поиски нового дома для человечества."),
    ("Крёстный отец", "The Godfather", "movie", 1972, "США", 1, 175,
     ["Криминал", "Драма"],
     "Сага о нью-йоркской семье итальянских мафиози и передаче власти от отца к сыну."),
    ("Криминальное чтиво", "Pulp Fiction", "movie", 1994, "США", 1, 154,
     ["Криминал", "Драма", "Комедия"],
     "Несколько переплетённых историй о бандитах, боксёре и жене гангстера в Лос-Анджелесе."),
    ("Леон", "Léon", "movie", 1994, "Франция", 1, 110,
     ["Боевик", "Криминал", "Драма"],
     "Профессиональный убийца берёт под опеку двенадцатилетнюю соседку, "
     "оставшуюся без семьи."),
    ("Амели", "Le Fabuleux Destin d'Amélie Poulain", "movie", 2001, "Франция", 1, 122,
     ["Комедия", "Романтика"],
     "Парижская официантка тайно делает окружающих счастливее и ищет собственную любовь."),
    ("Во все тяжкие", "Breaking Bad", "series", 2008, "США", 62, 47,
     ["Криминал", "Драма", "Триллер"],
     "Школьный учитель химии, узнав о тяжёлой болезни, начинает производство "
     "наркотиков."),
    ("Шерлок", "Sherlock", "series", 2010, "Великобритания", 13, 90,
     ["Детектив", "Драма"],
     "Современная версия приключений знаменитого сыщика и доктора Ватсона в Лондоне."),
    ("Чернобыль", "Chernobyl", "series", 2019, "США", 5, 65,
     ["Драма", "Исторический"],
     "Мини-сериал о причинах аварии на Чернобыльской АЭС и ликвидации её последствий."),
    ("Брат", "Брат", "movie", 1997, "Россия", 1, 100,
     ["Криминал", "Драма"],
     "Демобилизованный солдат приезжает в Петербург к старшему брату и "
     "оказывается втянут в криминальные разборки."),
    ("Левиафан", "Левиафан", "movie", 2014, "Россия", 1, 141,
     ["Драма"],
     "Житель северного городка борется с местной властью за свой дом и землю."),
    ("Герой", "Ying xiong", "movie", 2002, "Китай", 1, 99,
     ["Боевик", "Исторический", "Приключения"],
     "Безымянный воин рассказывает правителю, как победил трёх опасных "
     "убийц, угрожавших его жизни."),
    ("Крадущийся тигр, затаившийся дракон", "Wo hu cang long", "movie", 2000, "Китай", 1, 120,
     ["Боевик", "Приключения", "Романтика"],
     "Похищение легендарного меча приводит к столкновению мастеров боевых искусств."),
    ("Nirvana in Fire", "Langya Bang", "drama", 2015, "Китай", 54, 45,
     ["Исторический", "Драма", "Интриги"],
     "Стратег под чужим именем возвращается в столицу, чтобы восстановить "
     "справедливость и честь друзей."),
]

# Другие названия (английские и прочие), по которым пользователи ищут тайтлы; индекс = номер − 1
ALT_NAMES = [
    "Parasite", "Train to Busan", "Old Boy", "Memories of Murder", "CLOY",
    "Guardian: The Lonely and Great God, Гоблин", "Squid Game", "Kingdom",
    "Spirited Away", "Your Name, Kimi no Na wa", "My Neighbor Totoro", "Princess Mononoke",
    "Death Note", "Fullmetal Alchemist: Brotherhood, FMA", "Inception",
    "The Shawshank Redemption", "Interstellar", "The Godfather", "Pulp Fiction",
    "The Professional, Leon", "Amelie, Amélie", "Breaking Bad", "Sherlock", "Chernobyl",
    "Brother", "Leviathan", "Hero", "Crouching Tiger, Hidden Dragon", "Langya Bang",
]

DEMO_PASSWORD = "demo1234"
ADMIN_LOGIN, ADMIN_PASSWORD = "admin", "admin123"

# Личный список пользователя demo: (индекс тайтла, статус, оценка, прогресс)
DEMO_LIST = [
    (0, "completed", 9, None), (1, "completed", 8, None),
    (4, "completed", 10, None), (6, "watching", 8, 5),
    (7, "watching", 9, 4), (14, "completed", 9, None),
    (20, "plan", None, None), (12, "on_hold", 7, 11),
    (21, "dropped", 5, 9), (9, "completed", 10, None),
    (22, "plan", None, None), (28, "watching", 8, 12),
]

REVIEW_TEXTS = [
    "Сильная режиссура и отличная актёрская игра, смотрится на одном дыхании.",
    "Сюжет затягивает с первых минут, а финал заставляет задуматься.",
    "Хорошая работа, но местами не хватает динамики; всё равно рекомендую.",
    "Визуальный стиль и музыка выше всяких похвал, пересматривал дважды.",
]


def is_empty(conn: sqlite3.Connection) -> bool:
    return TitleRepository(conn).count() == 0


def ensure_demo_posters(conn: sqlite3.Connection) -> None:
    """Дополняет демонстрационные тайтлы в базах прежних версий: постеры и другие названия."""
    for number, item in enumerate(TITLES, start=1):
        conn.execute("UPDATE titles SET poster = ? WHERE name = ? AND original_name = ? "
                     "AND poster = ''", (f"p{number:02d}.png", item[0], item[1]))
        conn.execute("UPDATE titles SET alt_names = ? WHERE name = ? AND original_name = ? "
                     "AND alt_names = ''", (ALT_NAMES[number - 1], item[0], item[1]))
    conn.commit()


def seed_demo_data(conn: sqlite3.Connection) -> None:
    """Заполняет пустую базу каталогом, пользователями, оценками и отзывами."""
    titles = TitleRepository(conn)
    ids = []
    for number, (name, orig, kind, year, country, eps, dur, genres, desc) in enumerate(
            TITLES, start=1):
        ids.append(titles.add(
            {"name": name, "original_name": orig, "kind": kind, "year": year,
             "country": country, "episodes": eps, "duration": dur,
             "description": desc, "poster": f"p{number:02d}.png",
             "alt_names": ALT_NAMES[number - 1]}, genres))

    users = {}
    for username, role, password in (
            (ADMIN_LOGIN, "admin", ADMIN_PASSWORD), ("demo", "user", DEMO_PASSWORD),
            *((f"viewer{i}", "user", DEMO_PASSWORD) for i in range(1, 8))):
        salt, digest = hash_password(password)
        cur = conn.execute(
            "INSERT INTO users (username, email, salt, password_hash, role) "
            "VALUES (?, ?, ?, ?, ?)",
            (username, f"{username}@example.com", salt, digest, role))
        users[username] = cur.lastrowid
    conn.commit()

    entries, reviews = ListRepository(conn), ReviewRepository(conn)
    for idx, status, score, progress in DEMO_LIST:
        eps = TITLES[idx][5]
        entries.upsert(users["demo"], ids[idx], status, score,
                       eps if status == "completed" else (progress or 0))

    rng = random.Random(2026)
    for i in range(1, 8):
        uid = users[f"viewer{i}"]
        for idx in rng.sample(range(len(TITLES)), 14):
            status = rng.choices(["completed", "watching", "plan", "dropped"],
                                 weights=[10, 2, 3, 1])[0]
            eps = TITLES[idx][5]
            score = None if status == "plan" else min(10, max(3, round(rng.gauss(7.8, 1.5))))
            progress = eps if status == "completed" else (
                0 if status == "plan" else rng.randint(1, max(1, eps)))
            entries.upsert(uid, ids[idx], status, score, progress)
        if i <= len(REVIEW_TEXTS):
            reviews.upsert(uid, ids[(i * 5) % len(TITLES)], REVIEW_TEXTS[i - 1])
    reviews.upsert(users["demo"], ids[4], "Очень тёплая история: герои и "
                   "второстепенные персонажи получились живыми, а саундтрек запоминается.")
