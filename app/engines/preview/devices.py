"""Профили устройств предпросмотра и пересчёт экрана под устройство. Без Qt.

Единицы макета: Android-экран хранится в пикселях своего устройства (dp × плотность/160), Windows-экран —
в логических пикселях при масштабе 100 %. Под другое устройство экран перестраивается движком раскладки
(Auto Layout, привязки), а не растягивается картинкой. Это симуляция: системные панели, вырез и клавиатура
нарисованы приближённо, реальный Compose / Qt на устройстве может отличаться.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.core.document.model import PLATFORM_ANDROID, PLATFORM_WINDOWS, Screen
from app.engines.layout import LayoutEngine
from app.engines.layout.engine import Diagnostic, resize_screen
from app.libraries.catalog import device


@dataclass(frozen=True)
class PreviewProfile:
    id: str
    name: str
    platform: str
    kind: str          # phone | foldable | tablet | window
    width: int         # пиксели в «родной» ориентации (телефон — портрет, окно — альбом)
    height: int
    dpi: int
    corner_dp: int = 0
    cutout: bool = False


PROFILES: tuple[PreviewProfile, ...] = (
    PreviewProfile("phone_compact", "Телефон компактный", PLATFORM_ANDROID, "phone", 720, 1600, 320, 20),
    PreviewProfile("phone", "Телефон", PLATFORM_ANDROID, "phone", 1080, 2400, 420, 28, True),
    PreviewProfile("phone_large", "Телефон большой", PLATFORM_ANDROID, "phone", 1440, 3120, 560, 32, True),
    PreviewProfile("foldable", "Складной (раскрыт)", PLATFORM_ANDROID, "foldable", 1812, 2176, 420, 20, True),
    PreviewProfile("tablet", "Планшет", PLATFORM_ANDROID, "tablet", 1600, 2560, 320, 18),
    PreviewProfile("tablet_large", "Планшет большой", PLATFORM_ANDROID, "tablet", 1848, 2960, 360, 18),
    PreviewProfile("win_1280", "Окно 1280 × 800", PLATFORM_WINDOWS, "window", 1280, 800, 96),
    PreviewProfile("win_1366", "Ноутбук 1366 × 768", PLATFORM_WINDOWS, "window", 1366, 768, 96),
    PreviewProfile("win_1920", "Full HD 1920 × 1080 (125 %)", PLATFORM_WINDOWS, "window", 1920, 1080, 120),
    PreviewProfile("win_2560", "QHD 2560 × 1440 (150 %)", PLATFORM_WINDOWS, "window", 2560, 1440, 144),
)
KIND_RU = {"phone": "Телефоны", "foldable": "Складные", "tablet": "Планшеты", "window": "Окна"}
ANDROID_DENSITIES = ((160, "mdpi"), (240, "hdpi"), (320, "xhdpi"), (420, "420 dpi"), (480, "xxhdpi"),
                     (560, "560 dpi"), (640, "xxxhdpi"))
WINDOWS_SCALES = (100, 125, 150, 175, 200)

STATUS_DP = 24       # строка состояния Android
CUTOUT_STATUS_DP = 32
GESTURE_DP = 24      # жестовая панель навигации
TITLE_BAR = 32       # заголовок окна Windows (логические пиксели), рисуется вне содержимого
SIMULATION_LIMITS = (
    "Это симуляция, а не запуск на устройстве: APK/EXE не собирается.",
    "Android рисуется движком студии (приближение Compose / Material 3): шрифты, тени, эффекты нажатия "
    "и системные панели могут отличаться от устройства.",
    "Windows — отрисовка студии с рамкой окна; нативные виджеты Qt в предпросмотре не используются.",
    "Касания имитируются мышью; мультитач, датчики, вибрация и звук не моделируются.",
    "Экранная клавиатура — упрощённая раскладка; автозамена и методы ввода не моделируются.",
)


def profile(profile_id: str) -> PreviewProfile:
    for p in PROFILES:
        if p.id == profile_id:
            return p
    raise KeyError(profile_id)


def profiles_for(platform: str) -> list[PreviewProfile]:
    return [p for p in PROFILES if p.platform == platform]


def custom_profile(platform: str, width: int, height: int, dpi: int) -> PreviewProfile:
    width, height = max(200, min(8000, int(width))), max(200, min(8000, int(height)))
    dpi = max(72, min(800, int(dpi)))
    kind = "window" if platform == PLATFORM_WINDOWS else ("tablet" if min(width, height) * 160 / dpi >= 600
                                                         else "phone")
    return PreviewProfile("custom", f"Свой размер {width} × {height}", platform, kind, width, height, dpi,
                          0 if kind == "window" else 16)


def default_profile(screen: Screen) -> PreviewProfile:
    """Профиль, ближайший к устройству, под которое нарисован экран."""
    cands = profiles_for(screen.platform)
    try:
        d = device(screen.device_id)
        for p in cands:
            if (p.width, p.height, p.dpi) == (d.width, d.height, d.dpi):
                return p
        return custom_profile(screen.platform, d.width, d.height, d.dpi) if d.platform == screen.platform \
            else cands[0]
    except KeyError:
        return min(cands, key=lambda p: abs(p.width - screen.width) + abs(p.height - screen.height))


def screen_dpi(screen: Screen) -> int:
    """Плотность, в которой нарисован экран (как у базовых компонентов)."""
    if screen.platform != PLATFORM_ANDROID:
        return 96
    try:
        return device(screen.device_id).dpi
    except KeyError:
        return max(160, round(screen.width / 411 * 160))


@dataclass(frozen=True)
class Insets:
    top: float = 0
    bottom: float = 0
    left: float = 0
    right: float = 0


@dataclass(frozen=True)
class ViewSpec:
    profile: PreviewProfile
    orientation: str = "portrait"   # portrait | landscape (для окна не меняется)
    dpi: int = 0                     # 0 — плотность профиля

    @property
    def density(self) -> int:
        return self.dpi or self.profile.dpi

    @property
    def rotatable(self) -> bool:
        return self.profile.kind != "window"

    def px_size(self) -> tuple[int, int]:
        w, h = self.profile.width, self.profile.height
        if self.rotatable and (self.orientation == "landscape") != (w > h):
            w, h = h, w
        return w, h

    def logical_size(self) -> tuple[float, float]:
        """dp для Android, логические пиксели (с учётом масштаба) для Windows."""
        base = 160 if self.profile.platform == PLATFORM_ANDROID else 96
        w, h = self.px_size()
        return w * base / self.density, h * base / self.density

    def units(self, screen: Screen) -> float:
        """Единиц макета на один dp (Android) или логический пиксель (Windows)."""
        return screen_dpi(screen) / 160 if screen.platform == PLATFORM_ANDROID else 1.0

    def design_size(self, screen: Screen) -> tuple[int, int]:
        u = self.units(screen)
        w, h = self.logical_size()
        return max(1, round(w * u)), max(1, round(h * u))

    def insets(self, screen: Screen) -> Insets:
        """Безопасные области (системные панели и вырез) в единицах макета."""
        if self.profile.platform != PLATFORM_ANDROID:
            return Insets()
        u = self.units(screen)
        top = (CUTOUT_STATUS_DP if self.profile.cutout else STATUS_DP) * u
        landscape = self.px_size()[0] > self.px_size()[1] and self.profile.kind == "phone"
        if landscape:  # вырез уходит вбок, строка состояния остаётся сверху
            return Insets(STATUS_DP * u, GESTURE_DP * u, (CUTOUT_STATUS_DP * u) if self.profile.cutout else 0, 0)
        return Insets(top, GESTURE_DP * u, 0, 0)

    def with_(self, **kw) -> ViewSpec:
        return replace(self, **kw)

    def describe(self) -> str:
        w, h = self.px_size()
        lw, lh = self.logical_size()
        if self.profile.platform == PLATFORM_ANDROID:
            return f"{w} × {h} px · {self.density} dpi · {lw:.0f} × {lh:.0f} dp"
        return f"{w} × {h} px · масштаб {round(self.density / 96 * 100)} % · {lw:.0f} × {lh:.0f} логических px"


def adapt(screen: Screen, spec: ViewSpec, engine: LayoutEngine) -> tuple[Screen, list[Diagnostic]]:
    """Экран под размер устройства: перестройка раскладкой. Тот же размер — без изменений."""
    w, h = spec.design_size(screen)
    if (w, h) == (screen.width, screen.height):
        return screen, []
    return resize_screen(screen, w, h, engine)
