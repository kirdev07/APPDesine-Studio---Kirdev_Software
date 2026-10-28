"""Typography Studio: шрифты проекта (импорт TTF/OTF, лицензии), предпросмотр, покрытие символов, стили текста."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QFontComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QScrollArea, QSpinBox, QSplitter, QVBoxLayout,
    QWidget,
)

from app.core.document.model import REDISTRIBUTION, Asset, TextStyle
from app.ui.fonts import MAX_FONT_BYTES, REGISTRY, FontError, check_font_file
from app.ui.studio.common import button
from app.ui.studio.icons import RED_RU
from app.ui.widgets import label, panel
from app.ui.workspace.panels import ColorField

ROLE = Qt.ItemDataRole.UserRole
SAMPLE = "Съешь же ещё этих мягких французских булок, да выпей чаю.\nThe quick brown fox jumps over the lazy dog. 0123456789"
SIZES = (12, 14, 16, 20, 24, 32, 48)
WEIGHTS = (300, 400, 500, 600, 700)


class TypographyPage(QWidget):
    def __init__(self, ws, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.ws, self.main = ws, ws.editor
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_fonts())
        split.addWidget(self._build_preview())
        split.addWidget(self._build_styles())
        split.setSizes([280, 760, 380])
        split.setStretchFactor(1, 1)
        root.addWidget(split)
        self.main.document_changed.connect(self.refresh)
        self.refresh()

    # ---------- шрифты ----------
    def _build_fonts(self) -> QWidget:
        frame, lay = panel(margins=10)
        lay.addWidget(label("Шрифты проекта", "H2"))
        self.font_list = QListWidget()
        self.font_list.setWordWrap(True)
        self.font_list.currentItemChanged.connect(self._select_font)
        lay.addWidget(self.font_list, 1)
        lay.addWidget(button("Импорт TTF/OTF…", self.import_font))
        lay.addWidget(label("Лицензия выбранного шрифта", "H2"))
        form = QFormLayout()
        self.f_license = QLineEdit()
        self.f_license.setPlaceholderText("например OFL-1.1")
        self.f_source = QLineEdit()
        self.f_author = QLineEdit()
        self.f_redist = QComboBox()
        for k in REDISTRIBUTION:
            self.f_redist.addItem(RED_RU[k], k)
        for t, w in (("Лицензия", self.f_license), ("Источник", self.f_source), ("Автор", self.f_author),
                     ("Распространение", self.f_redist)):
            form.addRow(t, w)
        lay.addLayout(form)
        lay.addWidget(button("Сохранить сведения", self.save_license))
        lay.addWidget(label("Системные шрифты", "H2"))
        self.system = QFontComboBox()
        self.system.currentFontChanged.connect(lambda f: self.show_family(f.family()))
        lay.addWidget(self.system)
        lay.addWidget(label("Системные шрифты не встраиваются в проект и могут отсутствовать на другом компьютере "
                            "или устройстве.", "Muted", wrap=True))
        frame.setMinimumWidth(260)
        return frame

    def refresh(self) -> None:
        doc = self.main.doc
        cur = self.font_list.currentItem().data(ROLE) if self.font_list.currentItem() else None
        self.font_list.blockSignals(True)
        self.font_list.clear()
        for a in doc.assets if doc else []:
            if a.kind != "font":
                continue
            ok = a.id in doc.asset_data
            it = QListWidgetItem(f"{a.family or a.name}{'' if ok else '  (нет файла)'}\n"
                                 f"{a.name} · {RED_RU[a.redistribution]}")
            it.setData(ROLE, a.id)
            if a.redistribution != "allowed":
                it.setForeground(QColor("#E0B050"))
            self.font_list.addItem(it)
            if a.id == cur:
                self.font_list.setCurrentItem(it)
        self.font_list.blockSignals(False)
        self.refresh_styles()

    def _asset(self) -> Asset | None:
        it = self.font_list.currentItem()
        return self.main.doc.asset(it.data(ROLE)) if it and self.main.doc else None

    def _select_font(self, *_):
        a = self._asset()
        if a is None:
            return
        self.f_license.setText(a.license)
        self.f_source.setText(a.source)
        self.f_author.setText(a.author)
        self.f_redist.setCurrentIndex(self.f_redist.findData(a.redistribution))
        self.show_family(a.family)

    def import_font(self) -> None:
        if self.main.doc is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Импорт шрифта", str(Path.home()), "Шрифты (*.ttf *.otf)")
        if not path:
            return
        p = Path(path)
        try:
            if p.stat().st_size > MAX_FONT_BYTES:
                raise FontError("Файл шрифта больше 25 МБ")
            data = p.read_bytes()
            ext = check_font_file(data)
            sha = hashlib.sha256(data).hexdigest()
            families = REGISTRY.register(sha, data)
        except (FontError, OSError) as exc:
            QMessageBox.warning(self, "Импорт шрифта", str(exc))
            return
        a = Asset(kind="font", name=p.name, ext=ext, sha256=sha, size=len(data), family=families[0] if families else "",
                  source=p.name, redistribution="unknown")
        if self.main.add_asset(a, data):
            REGISTRY._by_asset[a.id] = families
            QMessageBox.information(self, "Импорт шрифта",
                                    f"Добавлено семейство «{a.family}». Укажите лицензию: распространение "
                                    "пока не проверено.")
            self.refresh()

    def save_license(self) -> None:
        a = self._asset()
        if a is not None:
            self.main.update_asset(a.id, None, license=self.f_license.text().strip(),
                                   source=self.f_source.text().strip(), author=self.f_author.text().strip(),
                                   redistribution=self.f_redist.currentData())

    # ---------- предпросмотр ----------
    def _build_preview(self) -> QWidget:
        frame, lay = panel(margins=12)
        self.family_title = label("", "H1")
        lay.addWidget(self.family_title)
        self.coverage = label("", "Muted", wrap=True)
        lay.addWidget(self.coverage)
        self.sample = QPlainTextEdit(SAMPLE)
        self.sample.setFixedHeight(64)
        self.sample.textChanged.connect(lambda: self.show_family(self._family))
        lay.addWidget(self.sample)
        self.lines = QWidget()
        self.lines_layout = QVBoxLayout(self.lines)
        scroll = QScrollArea()
        scroll.setWidget(self.lines)
        scroll.setWidgetResizable(True)
        lay.addWidget(scroll, 1)
        self._family = "Segoe UI"
        return frame

    def show_family(self, family: str) -> None:
        if not family:
            return
        self._family = family
        self.family_title.setText(family)
        cov = REGISTRY.coverage(family)
        avail = REGISTRY.available(family)
        parts = [f"{k}: {a}/{t} {'✓' if a == t else '⚠'}" for k, (a, t) in cov.items()]
        self.coverage.setText(("Покрытие символов — " + ", ".join(parts)) if avail else
                              f"Шрифт «{family}» недоступен на этом компьютере — будет показана замена")
        while self.lines_layout.count():
            w = self.lines_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        text = self.sample.toPlainText().splitlines()[0] if self.sample.toPlainText() else "Аа"
        for size in SIZES:
            lbl = QLabel(f"{size} px — {text}")
            f = QFont(family)
            f.setPixelSize(size)
            lbl.setFont(f)
            lbl.setStyleSheet(f"font-family:'{family}'; font-size:{size}px")
            self.lines_layout.addWidget(lbl)
        for weight in WEIGHTS:
            lbl = QLabel(f"{weight} — Насыщенность / Weight")
            f = QFont(family)
            f.setPixelSize(20)
            f.setWeight(QFont.Weight(weight))
            lbl.setFont(f)
            lbl.setStyleSheet(f"font-family:'{family}'; font-size:20px; font-weight:{weight}")
            self.lines_layout.addWidget(lbl)
        self.lines_layout.addStretch()

    # ---------- стили ----------
    def _build_styles(self) -> QWidget:
        frame, lay = panel(margins=10)
        lay.addWidget(label("Стили текста", "H2"))
        lay.addWidget(label("Стиль связан с текстами: изменение стиля обновляет все связанные тексты, "
                            "включая мастер-компоненты и их экземпляры.", "Muted", wrap=True))
        self.style_list = QListWidget()
        self.style_list.setWordWrap(True)
        self.style_list.currentItemChanged.connect(self._select_style)
        lay.addWidget(self.style_list, 1)
        form = QFormLayout()
        self.s_name = QLineEdit()
        self.s_family = QFontComboBox()
        self.s_size = QDoubleSpinBox()
        self.s_size.setRange(1, 1000)
        self.s_size.setValue(16)
        self.s_weight = QSpinBox()
        self.s_weight.setRange(100, 900)
        self.s_weight.setSingleStep(100)
        self.s_weight.setValue(400)
        self.s_color = ColorField()
        self.s_color.committed.connect(lambda v: self.s_color.set_value(v))
        for t, w in (("Имя", self.s_name), ("Шрифт", self.s_family), ("Размер, px", self.s_size),
                     ("Насыщенность", self.s_weight), ("Цвет", self.s_color)):
            form.addRow(t, w)
        lay.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(button("Новый", self.new_style))
        row.addWidget(button("Сохранить", self.save_style, object_name="Primary"))
        row.addWidget(button("Удалить", self.delete_style, object_name="Danger"))
        lay.addLayout(row)
        lay.addWidget(button("Применить к выделенному тексту", self.apply_style,
                             "Связать выделенные на рабочей области тексты со стилем"))
        lay.addWidget(button("Типографика Material 3", self.material_typography,
                             "15 стилей шкалы Material 3 (Display, Headline, Title, Body, Label) — в Android-"
                             "проекте становятся Typography темы"))
        self.s_status = label("", "Muted", wrap=True)
        lay.addWidget(self.s_status)
        frame.setMinimumWidth(320)
        self._style_id: str | None = None
        return frame

    def material_typography(self) -> None:
        n = self.main.add_material_typography()
        self.s_status.setText(f"Стили Material 3: {n} (имена начинаются с «M3 · »)" if n else
                              "Стили не добавлены")

    def refresh_styles(self) -> None:
        doc = self.main.doc
        self.style_list.blockSignals(True)
        self.style_list.clear()
        for st in doc.text_styles if doc else []:
            it = QListWidgetItem(f"{st.name}\n{st.font_family} · {st.font_size:g} px · {st.font_weight}")
            it.setData(ROLE, st.id)
            self.style_list.addItem(it)
            if st.id == self._style_id:
                self.style_list.setCurrentItem(it)
        self.style_list.blockSignals(False)

    def _select_style(self, *_):
        it = self.style_list.currentItem()
        st = self.main.doc.text_style(it.data(ROLE)) if it else None
        if st is None:
            return
        self._style_id = st.id
        self.s_name.setText(st.name)
        self.s_family.setCurrentFont(QFont(st.font_family))
        self.s_size.setValue(st.font_size)
        self.s_weight.setValue(st.font_weight)
        self.s_color.set_value(st.text_color)

    def new_style(self) -> None:
        self._style_id = None
        self.style_list.clearSelection()
        self.s_name.setText("Новый стиль")
        self.s_family.setCurrentFont(QFont(self._family))

    def save_style(self) -> None:
        name = self.s_name.text().strip()
        if not name or self.main.doc is None:
            self.s_status.setText("Укажите имя стиля")
            return
        weight = int(round(self.s_weight.value() / 100) * 100)
        st = TextStyle(name=name, font_family=self.s_family.currentFont().family(), font_size=self.s_size.value(),
                       font_weight=weight, text_color=self.s_color._value)
        if self._style_id:
            st.id = self._style_id
        if self.main.save_text_style(st):
            self._style_id = st.id
            self.s_status.setText(f"Стиль «{name}» сохранён")
            self.refresh_styles()

    def delete_style(self) -> None:
        if self._style_id and QMessageBox.question(
                self, "Стиль текста", "Удалить стиль? Тексты сохранят своё оформление, связь со стилем снимется.") \
                == QMessageBox.StandardButton.Yes and self.main.delete_text_style(self._style_id):
            self._style_id = None
            self.refresh_styles()

    def apply_style(self) -> None:
        if not self._style_id:
            self.s_status.setText("Выберите или сохраните стиль")
            return
        ok = self.main.apply_text_style_to_selection(self._style_id)
        self.s_status.setText("Стиль применён" if ok else "На рабочей области не выделено ни одного текста")
