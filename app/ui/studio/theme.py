"""Окно «Тема и стиль»: готовые темы картинками, свой цвет бренда, светлая / тёмная тема, шрифт, скругления,
поведение готового приложения (тема телефона, цвета обоев) и текущий экран в светлом и тёмном вариантах рядом."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGraphicsScene, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from app.core.document import tree
from app.core.document.model import ARTBOARD_COLORS, Appearance, Screen
from app.engines.material.restyle import FONTS, PRESETS, SHAPES, THEMES, appearance_of, color_map, restyle_node, \
    shape_factor
from app.libraries import components
from app.ui.widgets import label
from app.ui.workspace.canvas import build_scene, render_thumbnail
from app.ui.workspace.panels import ColorField

SAMPLE = QSize(120, 240)
_cache: dict = {}


def _layout(screen: Screen, engine) -> None:
    changes, _ = engine.layout_screen(screen)
    m = tree.node_map(screen)
    for nid, props in changes.items():
        for k, v in props.items():
            setattr(m[nid], k, v)


def sample(ap: Appearance, like: Screen, engine) -> QPixmap:
    """Мини-экран темы: верхняя панель, карточка, кнопка, переключатель, нижняя навигация."""
    key = (ap.accent, ap.theme, ap.font_family, ap.corner_radius, ap.material, like.width, like.height,
           like.device_id)
    if key in _cache:
        return _cache[key]
    s = Screen(name="образец", platform="android", width=like.width, height=like.height, device_id=like.device_id)
    k = s.width / 411
    nodes = []
    for kind, y in (("m3_top_app_bar", None), ("m3_card", 84), ("m3_switch", 300), ("m3_button_filled", 360),
                    ("m3_chip_filter", 420), ("m3_nav_bar", None)):
        n = components.build(kind, s, ap)
        if y is not None:
            dx, dy = 16 * k - n.x, y * k - n.y
            for d, _, _ in tree.walk([n]):
                d.x, d.y = d.x + dx, d.y + dy
        nodes.append(n)
    s.nodes = nodes
    _layout(s, engine)
    pm = render_thumbnail(s, ARTBOARD_COLORS.get(ap.theme, "#000000"), SAMPLE.width(), SAMPLE.height(),
                          bg=ARTBOARD_COLORS.get(ap.theme, "#000000"))
    _cache[key] = pm
    return pm


def restyled_copy(screen: Screen, old: Appearance, new: Appearance) -> Screen:
    copy = Screen.from_dict(screen.to_dict())
    cmap = color_map(old, new)
    f = shape_factor(old.corner_radius, new.corner_radius)
    for n, _, _ in tree.walk(copy.nodes):
        restyle_node(n, cmap, f, old.font_family, new.font_family)
    if new.material != old.material and copy.platform == "android":  # другое поколение Material
        from app.engines.material import generations
        from app.engines.material.color import scheme
        from app.engines.preview.devices import screen_dpi
        generations.apply(copy.nodes, new.material, scheme(new.accent, new.theme != "light"), screen_dpi(copy) / 160)
    return copy


class ThemeDialog(QDialog):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Тема и стиль")
        self.resize(980, 640)
        self.editor = editor
        self.old = editor.doc.meta.appearance
        self.like = editor.screen() or editor.doc.screens[0]
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addWidget(label("Готовые темы", "H2"))
        # проект только для Windows: без настроек Android (поколение Material, тема телефона, цвета обоев)
        self.android = "android" in editor.doc.meta.platforms or any(s.platform == "android"
                                                                     for s in editor.doc.screens)
        left.addWidget(label("Щёлкните тему — все экраны перекрасятся по ролям цвета Material 3: свои цвета, "
                             "не входящие в схему, останутся." if self.android else
                             "Щёлкните тему — экраны Windows перекрасятся: цвет акцента, светлое или тёмное окно, "
                             "шрифт; свои цвета останутся.", "Muted", wrap=True))
        self.presets = QListWidget()
        self.presets.setViewMode(QListWidget.ViewMode.IconMode)
        self.presets.setIconSize(SAMPLE)
        self.presets.setGridSize(QSize(SAMPLE.width() + 16, SAMPLE.height() + 44))
        self.presets.setMovement(QListWidget.Movement.Static)
        self.presets.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.presets.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.presets.setWordWrap(True)
        for p in PRESETS:
            it = QListWidgetItem(QIcon(sample(appearance_of(p, self.old), self.like, editor.engine)), p.name)
            it.setData(Qt.ItemDataRole.UserRole, p.key)
            it.setToolTip(f"{p.hint}\nШрифт: {p.font} · скругления: {SHAPES[p.shape][0].lower()}")
            self.presets.addItem(it)
        # только по щелчку или Enter: при показе окна список получает фокус и сам выбирает первую тему —
        # тема проекта сбрасывалась бы на неё
        self.presets.itemClicked.connect(self._pick)
        self.presets.itemActivated.connect(self._pick)
        left.addWidget(self.presets, 1)
        root.addLayout(left, 3)

        right = QVBoxLayout()
        right.addWidget(label("Настроить", "H2"))
        form = QFormLayout()
        self.accent = ColorField(allow_none=False)
        self.accent.committed.connect(lambda v: (self.accent.set_value(v), self.refresh()))
        form.addRow("Цвет бренда", self.accent)
        self.theme = QComboBox()
        for k, t in THEMES.items():
            self.theme.addItem(t, k)
        form.addRow("Тема", self.theme)
        self.font = QComboBox()
        self.font.addItems(FONTS)
        self.font.setEditable(True)
        form.addRow("Шрифт", self.font)
        self.shape = QComboBox()
        for v, (t, _) in SHAPES.items():
            self.shape.addItem(t, v)
        form.addRow("Скругления", self.shape)
        from app.engines.material.generations import GENERATIONS
        self.material = QComboBox()
        for k, t in GENERATIONS:
            self.material.addItem(t, k)
        self.material.setToolTip("Вид компонентов: Material 1 и 2 — малые скругления, кнопки заглавными, цветная "
                                 "шапка; Material 3 — тональные цвета; Expressive — крупные выразительные формы")
        form.addRow("Поколение", self.material)
        form.setRowVisible(self.material, self.android)
        right.addLayout(form)
        android_head = label("Готовое Android-приложение", "H2")
        right.addWidget(android_head)
        self.follow = QCheckBox("Светлая или тёмная — как в телефоне")
        self.follow.setToolTip("Приложение переключается вместе с темой телефона; иначе — всегда как в дизайне")
        self.dynamic = QCheckBox("Цвета из обоев телефона (Android 12+)")
        self.dynamic.setToolTip("Material You: на Android 12 и новее цвета берутся из обоев, на старых — ваши")
        right.addWidget(self.follow)
        right.addWidget(self.dynamic)
        for w in (android_head, self.follow, self.dynamic):
            w.setVisible(self.android)
        right.addWidget(label("Текущий экран: светлая и тёмная версии", "H2"))
        prev = QHBoxLayout()
        self.light_view, self.dark_view = QLabel(), QLabel()
        for v in (self.light_view, self.dark_view):
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.setMinimumSize(170, 340)
            prev.addWidget(v)
        right.addLayout(prev, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Применить ко всему проекту")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        root.addLayout(right, 2)
        self._loading = True
        self.set_appearance(self.old)
        self._loading = False
        for w in (self.theme, self.font, self.shape, self.material):
            w.currentIndexChanged.connect(self.refresh)
        self.font.editTextChanged.connect(self.refresh)
        self.refresh()

    def set_appearance(self, ap: Appearance) -> None:
        self.accent.set_value(ap.accent)
        self.theme.setCurrentIndex(max(0, self.theme.findData(ap.theme)))
        self.font.setCurrentText(ap.font_family)
        self.shape.setCurrentIndex(max(0, self.shape.findData(ap.corner_radius if ap.corner_radius in SHAPES
                                                              else 12)))
        self.follow.setChecked(ap.app_theme == "system")
        self.dynamic.setChecked(ap.dynamic_color)
        self.material.setCurrentIndex(max(0, self.material.findData(ap.material)))

    def appearance(self) -> Appearance:
        return replace(self.old, accent=self.accent._value or self.old.accent, theme=self.theme.currentData(),
                       font_family=self.font.currentText().strip() or self.old.font_family,
                       corner_radius=self.shape.currentData(),
                       app_theme="system" if self.follow.isChecked() else "design",
                       dynamic_color=self.dynamic.isChecked(), material=self.material.currentData() or "m3")

    def _pick(self, item, _prev=None) -> None:
        if item is None:
            return
        p = next(x for x in PRESETS if x.key == item.data(Qt.ItemDataRole.UserRole))
        self._loading = True
        self.set_appearance(replace(self.appearance(), accent=p.accent, theme=p.theme, font_family=p.font,
                                    corner_radius=p.shape))
        self._loading = False
        self.refresh()

    def refresh(self, *_) -> None:
        if self._loading:
            return
        new = self.appearance()
        dark_theme = new.theme if new.theme != "light" else "amoled"
        for view, theme in ((self.light_view, "light"), (self.dark_view, dark_theme)):
            ap = replace(new, theme=theme)
            s = restyled_copy(self.like, self.old, ap)
            pm = render_thumbnail(s, ARTBOARD_COLORS[theme], 170, 340, self.editor.doc, bg="#0B0B0B")
            view.setPixmap(pm)
            view.setToolTip("Светлая тема" if theme == "light" else "Тёмная тема")
