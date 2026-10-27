"""SVG Editor & Icon Builder: коллекция иконок проекта, импорт с санитизацией, векторное редактирование, экспорт.

Иконка — ресурс проекта типа icon (очищенный SVG). Для редактирования SVG преобразуется в векторные узлы
изолированного документа (холст = viewBox), при сохранении собирается обратно в SVG и снова проходит
санитизацию. Поддерживается подмножество SVG — см. app/engines/assets/svg.py.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from app.core.document.model import REDISTRIBUTION, Asset, Screen
from app.engines.assets.svg import MAX_SVG_BYTES, SvgError, nodes_to_svg, sanitize, svg_to_nodes
from app.ui.studio.common import ask_save, button, editor_toolbar, scratch_document
from app.ui.widgets import label, panel
from app.ui.workspace.canvas import CanvasView
from app.ui.workspace.editor import TOOL_ELLIPSE, TOOL_PEN, TOOL_RECT, TOOL_SELECT, Editor
from app.ui.workspace.panels import Inspector

ROLE = Qt.ItemDataRole.UserRole
RED_RU = {"allowed": "Разрешено", "forbidden": "Запрещено", "unknown": "Не проверено"}


def svg_pixmap(data: bytes, size: int = 48) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(QColor("#1C1C1C"))
    r = QSvgRenderer(QByteArray(data))
    if r.isValid():
        p = QPainter(pm)
        r.render(p, QRectF(4, 4, size - 8, size - 8))
        p.end()
    return pm


class ImportReport(QDialog):
    def __init__(self, name: str, report, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Импорт SVG")
        self.resize(520, 420)
        v = QVBoxLayout(self)
        v.addWidget(label(f"Файл «{name}» проверен", "H2"))
        if report.clean:
            v.addWidget(label("Небезопасного содержимого не найдено.", "Muted"))
        if report.removed:
            v.addWidget(label("Удалено:", "H2"))
            v.addWidget(label("• " + "\n• ".join(report.removed), wrap=True))
        if report.simplified:
            v.addWidget(label("Упрощено:", "H2"))
            v.addWidget(label("• " + "\n• ".join(report.simplified), wrap=True))
        form = QFormLayout()
        self.name = QLineEdit(Path(name).stem)
        self.license = QLineEdit()
        self.license.setPlaceholderText("например MIT, Apache-2.0, собственная")
        self.source = QLineEdit()
        self.author = QLineEdit()
        self.redist = QComboBox()
        for k in REDISTRIBUTION:
            self.redist.addItem(RED_RU[k], k)
        self.redist.setCurrentIndex(self.redist.findData("unknown"))
        form.addRow("Имя", self.name)
        form.addRow("Лицензия", self.license)
        form.addRow("Источник", self.source)
        form.addRow("Автор", self.author)
        form.addRow("Распространение", self.redist)
        v.addLayout(form)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("Отмена", self.reject))
        row.addWidget(button("Добавить в проект", self.accept, object_name="Primary"))
        v.addLayout(row)


class IconsPage(QWidget):
    insert_requested = Signal()

    def __init__(self, ws, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.ws, self.main = ws, ws.editor
        self.editor = Editor(self)
        self.editor.grid_size = 1
        self.asset_id: str | None = None
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_list())
        split.addWidget(self._build_center())
        split.addWidget(self._build_right())
        split.setSizes([240, 900, 360])
        split.setStretchFactor(1, 1)
        root.addWidget(split)
        self.main.document_changed.connect(self.refresh_list)
        self.editor.document_changed.connect(self._update_title)

    # ---------- коллекция ----------
    def _build_list(self) -> QWidget:
        frame, lay = panel(margins=10)
        lay.addWidget(label("Иконки проекта", "H2"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск…")
        self.search.textChanged.connect(self.refresh_list)
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setIconSize(QSize(48, 48))
        self.list.setGridSize(QSize(92, 84))
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.itemClicked.connect(lambda it: self.open_icon(it.data(ROLE)))
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(button("+ Новая", self.new_icon))
        row.addWidget(button("Импорт SVG…", self.import_svg))
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(button("Вставить", self.insert_on_screen, "Вставить иконку на текущий экран"))
        row.addWidget(button("Удалить", self.delete_icon, "Удалить неиспользуемую иконку", "Danger"))
        lay.addLayout(row)
        frame.setMinimumWidth(220)
        return frame

    def refresh_list(self) -> None:
        self.list.clear()
        doc = self.main.doc
        needle = self.search.text().strip().casefold()
        for a in doc.assets if doc else []:
            if a.kind != "icon" or (needle and needle not in a.name.casefold()):
                continue
            data = doc.asset_data.get(a.id)
            it = QListWidgetItem(a.name)
            if data:
                it.setIcon(svg_pixmap(data))
            else:
                it.setText(f"{a.name}\n(нет файла)")
            it.setData(ROLE, a.id)
            it.setToolTip(f"{a.name} · лицензия: {a.license or 'не указана'} · {RED_RU[a.redistribution]}")
            self.list.addItem(it)

    # ---------- холст ----------
    def _build_center(self) -> QWidget:
        frame, lay = panel(margins=0)
        head = QHBoxLayout()
        head.setContentsMargins(10, 8, 10, 0)
        self.title = label("Новая иконка", "H2")
        head.addWidget(self.title, 1)
        head.addWidget(label("viewBox", "Muted"))
        self.vb_w, self.vb_h = QSpinBox(), QSpinBox()
        for s in (self.vb_w, self.vb_h):
            s.setRange(1, 4096)
            s.setValue(24)
            s.setKeyboardTracking(False)
            s.valueChanged.connect(self._resize_viewbox)
            head.addWidget(s)
        lay.addLayout(head)
        lay.addWidget(editor_toolbar(self.editor, [
            (TOOL_SELECT, "➤", "Выделение"), (TOOL_PEN, "✎", "Перо: щелчки — точки, двойной щелчок или Enter — "
                                                         "открытый контур, щелчок по первой точке — замкнуть"),
            (TOOL_RECT, "▭", "Прямоугольник"), (TOOL_ELLIPSE, "◯", "Эллипс")],
            [button("Целиком", lambda: self.canvas.fit()),
             button("Объединить в группу", self.editor.group_selection)]))
        self.canvas = CanvasView(self.editor)
        lay.addWidget(self.canvas, 1)
        lay.addWidget(label("  Поддерживаются контуры, прямоугольники, эллипсы, линии, многоугольники, заливка и "
                            "обводка. Текст и растровые изображения в иконку не попадают.", "Muted", wrap=True))
        return frame

    def _build_right(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        self.inspector = Inspector(self.editor, show_document=False)
        v.addWidget(self.inspector, 1)
        meta, ml = panel(margins=10)
        ml.addWidget(label("Иконка", "H2"))
        form = QFormLayout()
        self.f_name = QLineEdit("Иконка")
        self.f_license = QLineEdit()
        self.f_source = QLineEdit()
        self.f_author = QLineEdit()
        self.f_redist = QComboBox()
        for k in REDISTRIBUTION:
            self.f_redist.addItem(RED_RU[k], k)
        for label_, wdg in (("Имя", self.f_name), ("Лицензия", self.f_license), ("Источник", self.f_source),
                            ("Автор", self.f_author), ("Распространение", self.f_redist)):
            form.addRow(label_, wdg)
        ml.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(button("Сохранить в проект", self.save_icon, object_name="Primary"))
        row.addWidget(button("Экспорт SVG…", self.export_svg))
        ml.addLayout(row)
        self.status = label("", "Muted", wrap=True)
        ml.addWidget(self.status)
        v.addWidget(meta)
        w.setMinimumWidth(330)
        return w

    def reset_for_document(self) -> None:
        """Открыт другой проект (или закрыт текущий)."""
        self.asset_id = None
        if self.main.doc is None:
            self.editor.set_document(None)
        else:
            self.new_icon(ask=False)
        self.refresh_list()

    # ---------- работа с иконкой ----------
    def is_dirty(self) -> bool:
        st = self.editor.stack
        return st is not None and not st.is_clean()

    def confirm_leave(self) -> bool:
        if not self.is_dirty():
            return True
        choice = ask_save(self, f"иконка «{self.f_name.text()}»")
        return self.save_icon() if choice == "save" else choice == "discard"

    def _load(self, nodes, vb_w: float, vb_h: float, asset: Asset | None) -> None:
        screen = Screen(name="Иконка", platform="android", width=max(1, round(vb_w)), height=max(1, round(vb_h)),
                        nodes=nodes)
        if self.main.doc is None:
            return
        self.editor.set_document(scratch_document(self.main.doc, screen))
        self.asset_id = asset.id if asset else None
        for s, v in ((self.vb_w, vb_w), (self.vb_h, vb_h)):
            s.blockSignals(True)
            s.setValue(max(1, round(v)))
            s.blockSignals(False)
        self.f_name.setText(asset.name if asset else "Иконка")
        self.f_license.setText(asset.license if asset else "")
        self.f_source.setText(asset.source if asset else "")
        self.f_author.setText(asset.author if asset else "")
        self.f_redist.setCurrentIndex(self.f_redist.findData(asset.redistribution if asset else "unknown"))
        self.canvas.fit()
        self._update_title()

    def new_icon(self, ask: bool = True) -> None:
        if ask and not self.confirm_leave():
            return
        size = 24
        if ask:
            size, ok = QInputDialog.getInt(self, "Новая иконка", "Размер viewBox (квадрат):", 24, 4, 1024)
            if not ok:
                return
        if self.main.doc is not None:
            self._load([], size, size, None)

    def open_icon(self, asset_id: str) -> None:
        if asset_id == self.asset_id or not self.confirm_leave():
            return
        doc = self.main.doc
        a = doc.asset(asset_id)
        data = doc.asset_data.get(asset_id)
        if a is None or data is None:
            QMessageBox.warning(self, "Иконка", "Файл иконки отсутствует в проекте")
            return
        try:
            clean, report = sanitize(data)
            nodes, vb = svg_to_nodes(clean, report)
        except SvgError as exc:
            QMessageBox.warning(self, "Иконка", str(exc))
            return
        self._load(nodes, vb[2], vb[3], a)
        self.status.setText("Упрощено при открытии: " + "; ".join(report.simplified) if report.simplified else "")

    def _resize_viewbox(self) -> None:
        if self.editor.screen() is not None:
            self.editor.set_screen_props({"width": self.vb_w.value(), "height": self.vb_h.value()},
                                         label="Размер viewBox")
            self.canvas.fit()

    def current_svg(self) -> bytes:
        s = self.editor.screen()
        svg = nodes_to_svg(s.nodes, s.width, s.height, self.f_name.text().strip())
        clean, _ = sanitize(svg.encode("utf-8"))
        return clean

    def save_icon(self) -> bool:
        if self.editor.screen() is None or self.main.doc is None:
            return False
        if not self.editor.screen().nodes:
            QMessageBox.information(self, "Иконка", "Иконка пустая — нарисуйте контур или фигуру")
            return False
        data = self.current_svg()
        meta = {"name": self.f_name.text().strip() or "Иконка", "license": self.f_license.text().strip(),
                "source": self.f_source.text().strip(), "author": self.f_author.text().strip(),
                "redistribution": self.f_redist.currentData()}
        if self.asset_id and self.main.doc.asset(self.asset_id):
            ok = self.main.update_asset(self.asset_id, data, **meta)
        else:
            a = Asset(kind="icon", ext="svg", sha256=hashlib.sha256(data).hexdigest(), size=len(data), **meta)
            ok = self.main.add_asset(a, data)
            if ok:
                self.asset_id = a.id
        if ok:
            self.editor.stack.set_clean()
            self.status.setText(f"Сохранено: {len(data)} байт")
            self._update_title()
        return ok

    def export_svg(self) -> None:
        if self.editor.screen() is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт SVG", str(Path.home() / f"{self.f_name.text()}.svg"),
                                              "SVG (*.svg)")
        if path:
            Path(path).write_bytes(self.current_svg())

    def import_svg(self) -> None:
        if not self.confirm_leave():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Импорт SVG", str(Path.home()), "SVG (*.svg)")
        if not path:
            return
        p = Path(path)
        if p.stat().st_size > MAX_SVG_BYTES:
            QMessageBox.warning(self, "Импорт SVG", "SVG больше 2 МБ")
            return
        try:
            clean, report = sanitize(p.read_bytes())
            nodes, vb = svg_to_nodes(clean, report)
        except (SvgError, OSError) as exc:
            QMessageBox.warning(self, "Импорт SVG", str(exc))
            return
        dlg = ImportReport(p.name, report, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        a = Asset(kind="icon", name=dlg.name.text().strip() or p.stem, ext="svg",
                  sha256=hashlib.sha256(clean).hexdigest(), size=len(clean), license=dlg.license.text().strip(),
                  source=dlg.source.text().strip() or p.name, author=dlg.author.text().strip(),
                  redistribution=dlg.redist.currentData())
        if self.main.add_asset(a, clean):
            self.asset_id = None
            self._load(nodes, vb[2], vb[3], a)

    def insert_on_screen(self) -> None:
        it = self.list.currentItem()
        aid = it.data(ROLE) if it else self.asset_id
        if aid and self.main.insert_image(aid):
            self.insert_requested.emit()

    def delete_icon(self) -> None:
        it = self.list.currentItem()
        if not it:
            return
        aid = it.data(ROLE)
        if QMessageBox.question(self, "Удаление иконки", f"Удалить иконку «{it.text()}» из проекта? "
                                "Удаляется только неиспользуемая иконка; действие можно отменить.") \
                == QMessageBox.StandardButton.Yes and self.main.remove_asset(aid) and aid == self.asset_id:
            self.new_icon(ask=False)

    def _update_title(self) -> None:
        name = self.f_name.text() if self.asset_id else "Новая иконка"
        self.title.setText(name + ("  ●" if self.is_dirty() else ""))


__all__ = ["IconsPage", "QPushButton", "QPlainTextEdit"]
