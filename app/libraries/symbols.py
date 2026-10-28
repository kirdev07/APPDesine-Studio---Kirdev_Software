"""Библиотека значков Google Material Symbols (Apache 2.0): ~3900 значков в стилях «контурные», «скруглённые»,
«острые», у каждого — вариант с заливкой. Без Qt.

Данные — app/resources/material_symbols.json.gz (сборка: tools/build_symbols.py), лицензия —
app/resources/MATERIAL_SYMBOLS_LICENSE.txt. Загружаются при первом обращении. Поиск — по английскому имени и
по русским словам (словарь частых слов ниже).
"""

from __future__ import annotations

import gzip
import json
from functools import lru_cache
from pathlib import Path

from app.core.document.pathdata import normalize, parse, to_string, transform

DATA = Path(__file__).resolve().parent.parent / "resources" / "material_symbols.json.gz"
LICENSE = DATA.with_name("MATERIAL_SYMBOLS_LICENSE.txt")
STYLES = {"outlined": "Контурные", "rounded": "Скруглённые", "sharp": "Острые"}
VIEWBOX = 960

# русские слова к частым частям английских имён: «корзина» найдёт shopping_cart, «дом» — home
RU = {
    "home": "дом главная", "search": "поиск найти", "menu": "меню", "close": "закрыть крестик", "add": "добавить плюс",
    "remove": "убрать минус", "delete": "удалить корзина мусор", "edit": "изменить карандаш редактировать",
    "check": "галочка готово", "settings": "настройки шестерёнка", "person": "человек профиль пользователь",
    "people": "люди", "group": "группа люди", "account": "аккаунт профиль", "favorite": "избранное сердце лайк",
    "star": "звезда рейтинг", "share": "поделиться", "notifications": "уведомления колокольчик",
    "notification": "уведомление", "mail": "почта письмо", "email": "почта", "chat": "чат сообщение",
    "message": "сообщение", "call": "звонок телефон", "phone": "телефон", "smartphone": "смартфон телефон",
    "camera": "камера фото", "photo": "фото", "image": "картинка изображение", "video": "видео",
    "videocam": "видеокамера", "mic": "микрофон", "music": "музыка", "play": "играть пуск воспроизвести",
    "pause": "пауза", "stop": "стоп", "skip": "пропустить", "volume": "громкость звук", "headphones": "наушники",
    "shopping": "покупки магазин", "cart": "корзина", "bag": "сумка пакет", "store": "магазин", "sell": "продажа",
    "payments": "платежи оплата", "payment": "оплата", "credit": "кредит", "card": "карта", "wallet": "кошелёк",
    "money": "деньги", "attach": "прикрепить скрепка", "receipt": "чек", "local": "местный", "offer": "предложение",
    "calendar": "календарь", "today": "сегодня", "event": "событие", "schedule": "расписание время часы",
    "alarm": "будильник", "timer": "таймер", "history": "история", "access": "доступ", "time": "время",
    "location": "место геолокация", "place": "место", "map": "карта", "navigation": "навигация", "near": "рядом",
    "directions": "маршрут", "car": "машина авто", "bus": "автобус", "train": "поезд", "flight": "самолёт полёт",
    "bike": "велосипед", "walk": "пешком", "delivery": "доставка", "shipping": "доставка", "truck": "грузовик",
    "lock": "замок", "open": "открыть", "visibility": "видимость глаз показать", "off": "выключить",
    "key": "ключ", "security": "безопасность", "shield": "щит защита", "verified": "проверено",
    "fingerprint": "отпечаток пальца", "password": "пароль", "login": "вход войти", "logout": "выход выйти",
    "arrow": "стрелка", "back": "назад", "forward": "вперёд", "upward": "вверх", "downward": "вниз",
    "left": "влево левый", "right": "вправо правый", "up": "вверх", "down": "вниз", "expand": "раскрыть",
    "chevron": "шеврон стрелка", "more": "ещё", "vert": "вертикально", "horiz": "горизонтально",
    "refresh": "обновить", "sync": "синхронизация", "download": "скачать загрузка", "upload": "загрузить",
    "cloud": "облако", "file": "файл", "folder": "папка", "description": "документ описание", "article": "статья",
    "list": "список", "grid": "сетка плитка", "view": "вид", "filter": "фильтр", "sort": "сортировка",
    "tune": "настроить", "info": "сведения информация", "help": "помощь вопрос", "warning": "внимание",
    "error": "ошибка", "report": "жалоба отчёт", "done": "готово", "cancel": "отмена", "block": "блок запрет",
    "light": "светлый свет", "dark": "тёмный", "mode": "режим", "sunny": "солнце", "bedtime": "ночь луна",
    "wifi": "вайфай wi-fi", "bluetooth": "блютуз", "battery": "батарея заряд", "signal": "сигнал",
    "language": "язык глобус", "public": "глобус мир", "translate": "перевод", "work": "работа портфель",
    "school": "школа учёба", "book": "книга", "bookmark": "закладка", "label": "метка", "tag": "тег метка",
    "flag": "флаг", "gift": "подарок", "redeem": "подарок бонус", "celebration": "праздник",
    "thumb": "палец", "thumb_up": "нравится лайк", "mood": "настроение смайл", "sentiment": "эмоция",
    "sports": "спорт", "fitness": "фитнес", "restaurant": "ресторан еда", "local_cafe": "кафе кофе",
    "coffee": "кофе", "fastfood": "фастфуд еда", "cake": "торт", "pets": "питомцы лапа", "health": "здоровье",
    "medical": "медицина", "hospital": "больница", "dashboard": "панель", "analytics": "аналитика",
    "trending": "тренд", "bar": "столбец", "chart": "график диаграмма", "insights": "аналитика",
    "qr": "qr код", "code": "код", "link": "ссылка", "content": "содержимое", "copy": "копировать",
    "paste": "вставить", "cut": "вырезать", "print": "печать", "save": "сохранить", "send": "отправить",
    "inbox": "входящие", "drafts": "черновики", "archive": "архив", "unarchive": "разархивировать",
    "visibility_off": "скрыть", "pin": "булавка закрепить", "push": "закрепить", "tv": "телевизор",
    "computer": "компьютер", "laptop": "ноутбук", "tablet": "планшет", "watch": "часы", "keyboard": "клавиатура",
    "mouse": "мышь", "print_": "печать", "brush": "кисть", "palette": "палитра цвета", "format": "формат",
    "text": "текст", "title": "заголовок", "font": "шрифт", "image_": "картинка", "crop": "обрезать",
    "rotate": "повернуть", "zoom": "масштаб", "fullscreen": "полный экран", "exit": "выйти",
    "apps": "приложения", "widgets": "виджеты", "extension": "расширение", "build": "сборка инструмент",
    "bug": "баг жук", "terminal": "терминал", "storage": "хранилище", "database": "база данных",
    "smart": "умный", "toy": "игрушка", "rocket": "ракета", "bolt": "молния", "eco": "эко лист",
    "water": "вода", "local_fire_department": "огонь", "whatshot": "огонь популярное", "new": "новый",
    "release": "выпуск", "support": "поддержка", "agent": "агент", "contact": "контакт", "contacts": "контакты",
    "badge": "бейдж", "id": "удостоверение", "face": "лицо", "emoji": "эмодзи", "add_circle": "добавить",
    "radio": "радио", "button": "кнопка", "toggle": "переключатель", "checkbox": "флажок", "circle": "круг",
    "square": "квадрат", "crop_square": "квадрат", "change": "сменить", "swap": "поменять", "repeat": "повтор",
    "shuffle": "перемешать", "queue": "очередь", "playlist": "плейлист", "library": "библиотека", "album": "альбом",
    "podcasts": "подкасты", "live": "прямой эфир", "movie": "фильм кино", "theaters": "кинотеатр", "games": "игры",
    "sports_esports": "игры геймпад", "weekend": "выходные диван", "hotel": "отель", "beach": "пляж",
    "home_work": "дом работа", "apartment": "квартира", "house": "дом", "garage": "гараж", "cleaning": "уборка",
    "lightbulb": "лампочка идея", "tips": "советы", "psychology": "мысль", "school_": "школа",
}


POPULAR = (
    "home", "search", "menu", "close", "add", "arrow_back", "arrow_forward", "more_vert", "more_horiz", "settings",
    "person", "account_circle", "favorite", "star", "share", "notifications", "mail", "chat", "call", "photo_camera",
    "image", "play_arrow", "pause", "shopping_cart", "shopping_bag", "storefront", "payments", "credit_card",
    "calendar_month", "schedule", "location_on", "map", "directions_car", "lock", "visibility", "visibility_off",
    "login", "logout", "edit", "delete", "check", "check_circle", "info", "help", "warning", "error", "download",
    "upload", "refresh", "filter_list", "tune", "sort", "grid_view", "list", "bookmark", "local_offer", "redeem",
    "dark_mode", "light_mode", "language", "wifi", "battery_full", "mic", "videocam", "send", "attach_file", "link",
    "content_copy", "qr_code_2", "fingerprint", "shield", "key", "group", "work", "school", "restaurant",
    "local_cafe", "flight", "hotel", "fitness_center", "pets", "music_note", "headphones", "thumb_up", "chevron_left",
    "chevron_right", "expand_more", "expand_less", "dashboard", "analytics", "trending_up", "bolt", "rocket_launch",
)


@lru_cache(maxsize=1)
def _data() -> dict:
    if not DATA.exists():
        return {"version": "", "styles": {s: {} for s in STYLES}}
    return json.loads(gzip.decompress(DATA.read_bytes()).decode("utf-8"))


def available() -> bool:
    return DATA.exists()


def version() -> str:
    return _data().get("version", "")


@lru_cache(maxsize=1)
def names() -> tuple[str, ...]:
    """Имена значков (без «-fill»), по алфавиту."""
    icons = _data()["styles"].get("outlined", {})
    return tuple(sorted(n for n in icons if not n.endswith("-fill")))


def raw(name: str, style: str = "outlined", filled: bool = False) -> str | None:
    icons = _data()["styles"].get(style, {})
    return icons.get(f"{name}-fill" if filled else name) or icons.get(name)


@lru_cache(maxsize=4096)
def path(name: str, style: str = "outlined", filled: bool = False) -> str | None:
    """Путь значка в квадрате 0…960 (исходный viewBox сдвинут на 960 вниз), нормализованный для документа."""
    d = raw(name, style, filled)
    if not d:
        return None
    return normalize(to_string(transform(parse(d), (1, 0, 0, 1, 0, VIEWBOX))))


def keywords(name: str) -> str:
    """Строка поиска значка: английское имя и русские слова его частей."""
    parts = name.split("_")
    ru = [RU.get(name, "")] + [RU.get(p, "") for p in parts]
    return (name.replace("_", " ") + " " + " ".join(r for r in ru if r)).lower()


@lru_cache(maxsize=1)
def _index() -> tuple[tuple[str, str], ...]:
    return tuple((n, keywords(n)) for n in names())


def search(query: str, limit: int | None = None) -> list[str]:
    """Значки, у которых все слова запроса встречаются в имени или русских словах. Точные совпадения — первыми."""
    words = query.lower().replace("ё", "е").split()
    if not words:  # без запроса — сначала популярные значки интерфейсов, потом остальные по алфавиту
        top = [n for n in POPULAR if n in set(names())]
        found = top + [n for n in names() if n not in set(top)]
    else:
        found = []
        for n, kw in _index():
            hay = kw.replace("ё", "е")
            if all(w in hay for w in words):
                found.append(n)
        q = "_".join(words)
        found.sort(key=lambda n: (n != q, not n.startswith(words[0]), len(n), n))
    return found[:limit] if limit else found


def russian_name(name: str) -> str:
    """Подпись по-русски для слоя: первое русское слово имени или само имя."""
    for key in (name, *name.split("_")):
        if key in RU:
            return RU[key].split()[0].capitalize()
    return name.replace("_", " ")
