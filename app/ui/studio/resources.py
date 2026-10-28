"""Страницы «Цвета» (цветовые токены проекта) и «Ресурсы» (все файлы проекта, лицензии, отсутствующие файлы)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt, Signal
from PySide6.QtGui import QColor, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.core.document import tree
from app.core.document.model import REDISTRIBUTION, Asset, ColorToken
from app.ui.studio.common import button
from app.ui.studio.icons import RED_RU
from app.ui.widgets import format_size, label, panel
from app.ui.workspace.canvas import MAX_IMAGE_SIDE, qcolor
from app.ui.workspace.panels import ColorField

ROLE = Qt.ItemDataRole.UserRole
MAX_IMAGE_BYTES = 20 * 1024 * 1024
KIND_RU = {"icon": "Иконка (SVG)", "font": "Шрифт", "image": "Изображение"}


def swatch(color: str, size: int = 22) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(qcolor(color) if color else QColor(0, 0, 0, 0))
    return pm


class ColorsPage(QWidget):
    def __init__(self, ws, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.main = ws.editor
        self._token_id: str | None = None
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        left, ll = panel()
        ll.addWidget(label("Цветовые токены", "H2"))
        ll.addWidget(label("Именованные цвета проекта. Попадают в токены AI-экспорта (styles/tokens.json).", "Muted", wrap=True))
        self.tokens = QListWidget()
        self.tokens.currentItemChanged.connect(self._select)
        ll.addWidget(self.tokens, 1)
        form = QFormLayout()
        self.name = QLineEdit()
        self.value = ColorField(allow_none=False)
        self.value.committed.connect(self.value.set_value)
        form.addRow("Имя", self.name)
        form.addRow("Цвет", self.value)
        ll.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(button("Новый", self.new_token))
        row.addWidget(button("Сохранить", self.save_token, object_name="Primary"))
        row.addWidget(button("Удалить", self.delete_token, object_name="Danger"))
        ll.addLayout(row)
        ll.addWidget(button("Схема Material 3…", self.material_scheme,
                            "Все роли цвета Material 3 (основной, контейнеры, поверхности, контуры, ошибка) "
                            "по одному цвету бренда — светлая и тёмная схемы"))
        row = QHBoxLayout()
        row.addWidget(button("Залить выделение", lambda: self._apply("fill")))
        row.addWidget(button("Цвет текста выделения", lambda: self._apply("text_color")))
        ll.addLayout(row)
        self.status = label("", "Muted", wrap=True)
        ll.addWidget(self.status)
        root.addWidget(left, 1)
        right, rl = panel()
        rl.addWidget(label("Цвета, используемые в проекте", "H2"))
        self.used = QListWidget()
        self.used.itemDoubleClicked.connect(lambda it: (self.new_token(), self.value.set_value(it.data(ROLE))))
        rl.addWidget(self.used, 1)
        rl.addWidget(label("Двойной щелчок — создать токен из цвета.", "Muted"))
        root.addWidget(right, 1)
        self.main.document_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        doc = self.main.doc
        self.tokens.blockSignals(True)
        self.tokens.clear()
        for t in doc.colors if doc else []:
            it = QListWidgetItem(f"{t.name}   {t.value}")
            it.setIcon(swatch(t.value))
            it.setData(ROLE, t.id)
            self.tokens.addItem(it)
        self.tokens.blockSignals(False)
        counts: dict[str, int] = {}
        roots = [n for s in doc.screens for n in s.nodes] + [c.root for c in doc.components] if doc else []
        for n, _, _ in tree.walk(roots):
            for c in (n.fill, n.stroke if n.stroke_width else "", n.text_color if n.type == "text" else ""):
                if c:
                    counts[c] = counts.get(c, 0) + 1
        self.used.clear()
        for c, k in sorted(counts.items(), key=lambda kv: -kv[1]):
            it = QListWidgetItem(f"{c}   ·   {k}")
            it.setIcon(swatch(c))
            it.setData(ROLE, c)
            self.used.addItem(it)

    def _select(self, *_):
        it = self.tokens.currentItem()
        t = next((c for c in self.main.doc.colors if c.id == it.data(ROLE)), None) if it else None
        if t:
            self._token_id = t.id
            self.name.setText(t.name)
            self.value.set_value(t.value)

    def new_token(self) -> None:
        self._token_id = None
        self.tokens.clearSelection()
        self.name.setText("Новый цвет")
        self.value.set_value("#2F7BFF")

    def save_token(self) -> None:
        if not self.name.text().strip() or not self.value._value:
            self.status.setText("Укажите имя и цвет")
            return
        t = ColorToken(name=self.name.text().strip(), value=self.value._value)
        if self._token_id:
            t.id = self._token_id
        if self.main.save_color(t):
            self._token_id = t.id
            self.status.setText("Сохранено")

    def delete_token(self) -> None:
        if self._token_id and self.main.delete_color(self._token_id):
            self._token_id = None

    def material_scheme(self) -> None:
        from app.ui.studio.material import MaterialSchemeDialog
        doc = self.main.doc
        if doc is None:
            return
        dlg = MaterialSchemeDialog(doc.meta.appearance.accent, doc.meta.appearance.theme != "light", self)
        if dlg.exec():
            n = self.main.add_material_colors(dlg.seed(), dlg.variants(), dlg.fidelity())
            self.status.setText(f"Создано и обновлено токенов: {n}" if n else "Схема не применена")

    def _apply(self, prop: str) -> None:
        v = self.value._value
        ok = bool(v) and self.main.apply_color(v, prop)
        self.status.setText("Применено" if ok else "Выделите элементы на рабочей области")


class ResourcesPage(QWidget):
    insert_requested = Signal()
    COLS = ["Имя", "Тип", "Размер", "Лицензия", "Распространение", "Использований", "Состояние"]

    def __init__(self, ws, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.main = ws.editor
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        box, lay = panel()
        lay.addWidget(label("Ресурсы проекта", "H1"))
        lay.addWidget(label("Все файлы проекта с SHA-256, источником и лицензией. Отсутствующие файлы и "
                            "непроверенные лицензии выделены.", "Muted", wrap=True))
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._select)
        lay.addWidget(self.table, 1)
        form = QFormLayout()
        self.f_license, self.f_source, self.f_author = QLineEdit(), QLineEdit(), QLineEdit()
        self.f_redist = QComboBox()
        for k in REDISTRIBUTION:
            self.f_redist.addItem(RED_RU[k], k)
        for t, w in (("Лицензия", self.f_license), ("Источник", self.f_source), ("Автор", self.f_author),
                     ("Распространение", self.f_redist)):
            form.addRow(t, w)
        lay.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(button("Сохранить сведения", self.save_meta, object_name="Primary"))
        row.addWidget(button("Импорт изображения…", self.import_image, "PNG, JPEG или WebP до 20 МБ и 8192 px"))
        row.addWidget(button("Вставить на экран", self.insert))
        row.addWidget(button("Удалить неиспользуемый", self.remove, object_name="Danger"))
        row.addStretch()
        lay.addLayout(row)
        self.status = label("", "Muted", wrap=True)
        lay.addWidget(self.status)
        root.addWidget(box)
        self.main.document_changed.connect(self.refresh)
        self.refresh()

    def _current(self) -> Asset | None:
        r = self.table.currentRow()
        item = self.table.item(r, 0) if r >= 0 else None
        return self.main.doc.asset(item.data(ROLE)) if item and self.main.doc else None

    def refresh(self) -> None:
        doc = self.main.doc
        assets = doc.assets if doc else []
        self.table.setRowCount(len(assets))
        for r, a in enumerate(assets):
            ok = a.id in doc.asset_data
            vals = [a.name, KIND_RU[a.kind], format_size(a.size), a.license or "не указана",
                    RED_RU[a.redistribution], str(self.main.asset_usage(a.id)),
                    "в порядке" if ok else "файл отсутствует"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 0:
                    it.setData(ROLE, a.id)
                    it.setToolTip(f"SHA-256: {a.sha256}\n{a.archive_path}")
                if (c == 6 and not ok) or (c == 4 and a.redistribution == "forbidden"):
                    it.setForeground(QColor("#E5484D"))
                elif c == 4 and a.redistribution == "unknown":
                    it.setForeground(QColor("#E0B050"))
                self.table.setItem(r, c, it)
        self.table.resizeColumnsToContents()

    def _select(self) -> None:
        a = self._current()
        if a:
            self.f_license.setText(a.license)
            self.f_source.setText(a.source)
            self.f_author.setText(a.author)
            self.f_redist.setCurrentIndex(self.f_redist.findData(a.redistribution))

    def save_meta(self) -> None:
        a = self._current()
        if a and self.main.update_asset(a.id, None, license=self.f_license.text().strip(),
                                        source=self.f_source.text().strip(), author=self.f_author.text().strip(),
                                        redistribution=self.f_redist.currentData()):
            self.status.setText("Сведения сохранены")

    def import_image(self) -> None:
        if self.main.doc is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Импорт изображения", str(Path.home()),
                                              "Изображения (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        p = Path(path)
        try:
            if p.stat().st_size > MAX_IMAGE_BYTES:
                raise ValueError("Файл больше 20 МБ")
            data = p.read_bytes()
            buf = QBuffer()
            buf.setData(QByteArray(data))
            buf.open(QIODevice.OpenModeFlag.ReadOnly)
            reader = QImageReader(buf)
            fmt = bytes(reader.format()).decode().lower()
            size = reader.size()
            if fmt not in ("png", "jpeg", "jpg", "webp"):
                raise ValueError("Формат не поддерживается (нужен PNG, JPEG или WebP)")
            if size.width() <= 0 or size.width() > MAX_IMAGE_SIDE or size.height() > MAX_IMAGE_SIDE:
                raise ValueError(f"Размер изображения должен быть до {MAX_IMAGE_SIDE} px по стороне")
            if reader.read().isNull():
                raise ValueError("Изображение повреждено")
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Импорт изображения", str(exc))
            return
        ext = {"jpeg": "jpg"}.get(fmt, fmt)
        a = Asset(kind="image", name=p.stem, ext=ext, sha256=hashlib.sha256(data).hexdigest(), size=len(data),
                  source=p.name, redistribution="unknown")
        if self.main.add_asset(a, data):
            self.status.setText(f"Добавлено: {p.name} ({size.width()}×{size.height()}). Укажите лицензию.")

    def insert(self) -> None:
        a = self._current()
        if a is None or a.kind == "font":
            self.status.setText("Выберите иконку или изображение")
            return
        if self.main.insert_image(a.id):
            self.insert_requested.emit()

    def remove(self) -> None:
        a = self._current()
        if a and QMessageBox.question(self, "Удаление ресурса", f"Удалить «{a.name}» из проекта? Удаляется только "
                                      "неиспользуемый ресурс; действие можно отменить.") \
                == QMessageBox.StandardButton.Yes:
            self.main.remove_asset(a.id)
