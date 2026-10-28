"""Диалог «Схема Material 3»: цвет бренда → тональные палитры и роли цвета светлой и тёмной схем."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QLabel, QScrollArea, QVBoxLayout,
    QWidget,
)

from app.engines.material.color import ROLE_RU, contrast, scheme, tonal_table
from app.ui.widgets import label
from app.ui.workspace.panels import ColorField

# роли для образца: (роль фона, роль текста на нём)
SAMPLE = (("primary", "onPrimary"), ("primaryContainer", "onPrimaryContainer"),
          ("secondaryContainer", "onSecondaryContainer"), ("tertiaryContainer", "onTertiaryContainer"),
          ("errorContainer", "onErrorContainer"), ("surfaceContainerHighest", "onSurface"),
          ("surface", "onSurfaceVariant"), ("inverseSurface", "inverseOnSurface"))


class _Swatch(QLabel):
    def __init__(self, bg: str, fg: str, text: str, tip: str):
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(44, 30)
        self.setToolTip(tip)
        self.setStyleSheet(f"background:{bg};color:{fg};border-radius:4px;padding:2px 4px;font-size:11px")


class _Strip(QWidget):
    """Тоны одной палитры полосой."""

    def __init__(self, tones: list[tuple[int, str]]):
        super().__init__()
        self.tones = tones
        self.setMinimumHeight(22)
        self.setToolTip("  ".join(f"{t}: {c}" for t, c in tones))

    def paintEvent(self, _):
        p = QPainter(self)
        w = self.width() / len(self.tones)
        for i, (_, c) in enumerate(self.tones):
            p.fillRect(int(i * w), 0, int(w + 1), self.height(), QColor(c))
        p.end()


class MaterialSchemeDialog(QDialog):
    def __init__(self, seed: str, dark: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Схема Material 3")
        self.resize(640, 640)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Material 3 строит пять тональных палитр по одному цвету бренда и назначает тоны ролям: "
                            "основной цвет, контейнеры, поверхности, контуры, ошибка. Роли становятся цветовыми "
                            "токенами проекта; в Android-проекте тема уже содержит обе схемы.", "Muted", wrap=True))
        form = QFormLayout()
        self.seed_field = ColorField(allow_none=False)
        self.seed_field.set_value(seed)
        self.seed_field.committed.connect(lambda v: (self.seed_field.set_value(v), self.refresh()))
        form.addRow("Цвет бренда", self.seed_field)
        self.which = QComboBox()
        for text, data in ((f"Тема проекта ({'тёмная' if dark else 'светлая'})", ("dark",) if dark else ("light",)),
                           ("Светлая и тёмная", ("light", "dark")), ("Только светлая", ("light",)),
                           ("Только тёмная", ("dark",))):
            self.which.addItem(text, data)
        self.which.currentIndexChanged.connect(self.refresh)
        form.addRow("Схемы", self.which)
        self.keep = QCheckBox("Основной цвет — точно цвет бренда (иначе тон 40 / 80 по правилам Material)")
        self.keep.setChecked(True)
        self.keep.toggled.connect(self.refresh)
        form.addRow(self.keep)
        lay.addLayout(form)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.body = QWidget()
        self.grid = QVBoxLayout(self.body)
        scroll.setWidget(self.body)
        lay.addWidget(scroll, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Создать токены")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.refresh()

    def seed(self) -> str:
        return self.seed_field._value or "#2F7BFF"

    def variants(self) -> tuple[str, ...]:
        return self.which.currentData()

    def fidelity(self) -> bool:
        return self.keep.isChecked()

    def refresh(self) -> None:
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w is not None:
                w.hide()  # до удаления виджет ещё виден и перекрывает новые образцы
                w.deleteLater()
        self.grid.addWidget(label("Тональные палитры (тоны 0 → 100)", "H2"))
        for name, tones in tonal_table(self.seed()).items():
            self.grid.addWidget(label(name, "Muted"))
            self.grid.addWidget(_Strip(tones))
        for variant in self.variants():
            sch = scheme(self.seed(), variant == "dark", self.fidelity())
            self.grid.addWidget(label(f"Схема: {'тёмная' if variant == 'dark' else 'светлая'}", "H2"))
            box = QWidget()
            g = QGridLayout(box)
            g.setSpacing(4)
            for i, (bg, fg) in enumerate(SAMPLE):
                ratio = contrast(sch[bg], sch[fg])
                tip = f"{ROLE_RU[bg]} {sch[bg]} / {ROLE_RU[fg]} {sch[fg]} — контраст {ratio:.1f}:1"
                g.addWidget(_Swatch(sch[bg], sch[fg], ROLE_RU[bg], tip), i // 4, i % 4)
            self.grid.addWidget(box)
        self.grid.addStretch(1)
