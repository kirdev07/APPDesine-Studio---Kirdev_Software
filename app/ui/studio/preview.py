"""Interactive Preview: прототип на устройствах — профили, плотность, ориентация, безопасные области, ввод,
сравнение устройств, проверки экрана и тестовые сценарии.

Без сборки APK/EXE: экран перестраивается под устройство движком раскладки студии и рисуется в рамке
устройства. Ограничения симуляции показаны на странице (devices.SIMULATION_LIMITS).
"""

from __future__ import annotations

import hashlib
import json

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFormLayout, QGraphicsScene, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from app.core.document.model import PLATFORM_ANDROID
from app.engines.logic.engine import Interpreter, format_value
from app.engines.preview import checks, scenarios
from app.engines.preview.devices import (
    ANDROID_DENSITIES, KIND_RU, SIMULATION_LIMITS, WINDOWS_SCALES, PreviewProfile, ViewSpec, custom_profile,
    profiles_for,
)
from app.ui.studio.common import button
from app.ui.studio.prototype import PrototypePlayer, frame_rect, paint_device
from app.ui.widgets import label, panel
from app.ui.workspace.canvas import asset_lookup, build_scene

ROLE = Qt.ItemDataRole.UserRole
COMPARE = {PLATFORM_ANDROID: ("phone_compact", "phone", "foldable", "tablet"), "windows": ("win_1280", "win_1920")}


def render_device(screen, spec: ViewSpec, artboard: str, title: str, doc, max_w: int, max_h: int) -> QPixmap:
    """Миниатюра экрана в рамке устройства."""
    rect = frame_rect(screen, spec)
    k = min(max_w / rect.width(), max_h / rect.height())
    pm = QPixmap(max(1, int(rect.width() * k)), max(1, int(rect.height() * k)))
    pm.fill(Qt.GlobalColor.transparent)
    scene = QGraphicsScene()
    build_scene(scene, screen, artboard, asset_lookup(doc))
    p = QPainter(pm)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
    p.scale(k, k)
    p.translate(-rect.x(), -rect.y())
    target = QRectF(0, 0, screen.width, screen.height)
    scene.render(p, target, target)
    paint_device(p, screen, spec, artboard, title)
    p.end()
    return pm


class PreviewPage(QWidget):
    """Страница предпросмотра. Сеанс (проигрыватель) создаётся заново при изменении документа."""

    def __init__(self, ws, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.main = ws.editor
        self.player: PrototypePlayer | None = None
        self._doc_hash = ""
        self._loading = False
        self.script: list | None = None
        self.script_digest = ""
        self.results: dict[str, scenarios.ScenarioResult] = {}
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        split = QSplitter(Qt.Orientation.Horizontal)
        from PySide6.QtWidgets import QFrame as _QFrame
        left = QScrollArea()
        left.setWidgetResizable(True)
        left.setFrameShape(_QFrame.Shape.NoFrame)
        left.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left.setWidget(self._build_devices())
        left.setMinimumWidth(240)
        split.addWidget(left)
        split.addWidget(self._build_center())
        split.addWidget(self._build_right())
        split.setSizes([270, 760, 380])
        root.addWidget(split)

    # ---------- левая колонка: устройство ----------
    def _build_devices(self) -> QWidget:
        frame, lay = panel(margins=10)
        lay.addWidget(label("Устройство", "H2"))
        self.platform_label = label("", "Muted")
        lay.addWidget(self.platform_label)
        self.devices = QListWidget()
        self.devices.setMinimumHeight(220)
        self.devices.setWordWrap(True)
        self.devices.currentItemChanged.connect(self._pick_device)
        lay.addWidget(self.devices, 1)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)  # подпись над полями: колонка узкая (1280 px)
        self.c_w, self.c_h, self.c_dpi = QSpinBox(), QSpinBox(), QSpinBox()
        for sp, lo, hi in ((self.c_w, 200, 8000), (self.c_h, 200, 8000), (self.c_dpi, 72, 800)):
            sp.setRange(lo, hi)
        row = QHBoxLayout()
        row.addWidget(self.c_w)
        row.addWidget(QLabel("×"))
        row.addWidget(self.c_h)
        form.addRow("Свой размер, px", row)
        form.addRow("Плотность, dpi", self.c_dpi)
        lay.addLayout(form)
        lay.addWidget(button("Применить свой размер", self.apply_custom))
        lay.addWidget(label("Ориентация и плотность", "H2"))
        row = QHBoxLayout()
        self.orient = QButtonGroup(self)
        self.b_portrait, self.b_landscape = QPushButton("Портрет"), QPushButton("Альбом")
        for i, b in enumerate((self.b_portrait, self.b_landscape)):
            b.setCheckable(True)
            self.orient.addButton(b, i)
            row.addWidget(b)
        self.orient.idClicked.connect(lambda i: self._update_spec(orientation=("portrait", "landscape")[i]))
        lay.addLayout(row)
        self.density = QComboBox()
        self.density.currentIndexChanged.connect(self._pick_density)
        lay.addWidget(self.density)
        self.spec_info = label("", "Muted", wrap=True)
        lay.addWidget(self.spec_info)
        lay.addWidget(label("Режим просмотра", "H2"))
        self.o_safe = QCheckBox("Показывать безопасные области")
        self.o_touch = QCheckBox("Касание вместо мыши")
        self.o_touch.setToolTip("Нет наведения, видно место касания; свайп — перетаскиванием")
        self.reduced = QCheckBox("Уменьшить движение")
        self.reduced.setToolTip("Анимации и переходы показываются сразу конечным состоянием")
        for cb, name in ((self.o_safe, "show_safe"), (self.o_touch, "touch_mode"), (self.reduced, "reduced_motion")):
            cb.toggled.connect(lambda v, n=name: self.player and self.player.set_option(n, v))
            lay.addWidget(cb)
        return frame

    # ---------- центр: устройство и сравнение ----------
    def _build_center(self) -> QWidget:
        frame, lay = panel(margins=6)
        self.tabs = QTabWidget()
        self.stage = QWidget()
        self.stage_lay = QVBoxLayout(self.stage)
        self.stage_lay.setContentsMargins(0, 0, 0, 0)
        self.tabs.addTab(self.stage, "Интерактивный")
        self.compare = QWidget()
        self.compare_lay = QHBoxLayout(self.compare)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.compare)
        self.tabs.addTab(scroll, "Сравнение устройств")
        self.tabs.currentChanged.connect(lambda _: self.refresh_compare())
        lay.addWidget(self.tabs, 1)
        row = QHBoxLayout()
        row.addWidget(button("◀ Назад", lambda: self.player and self.player.system_back(),
                             "Системная кнопка «Назад» (Esc)"))
        row.addWidget(button("⟲ Сначала", self.restart, "Начать сеанс заново с текущего экрана"))
        self.b_rotate = button("⟳ Повернуть", self.rotate, "Портрет ↔ альбом")
        row.addWidget(self.b_rotate)
        self.b_limits = button("ℹ Ограничения", lambda: self.limits.setVisible(not self.limits.isVisible()),
                               "Что симулируется приближённо")
        row.addWidget(self.b_limits)
        row.addStretch()
        lay.addLayout(row)
        self.screen_label = label("", "Muted")
        from PySide6.QtWidgets import QSizePolicy
        self.screen_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay.addWidget(self.screen_label)
        self.limits = label("Ограничения симуляции: " + " ".join(SIMULATION_LIMITS), "Muted", wrap=True)
        self.limits.setVisible(False)  # по кнопке: место — устройству
        self.b_limits.setToolTip(chr(10).join(SIMULATION_LIMITS))
        lay.addWidget(self.limits)
        return frame

    # ---------- правая колонка: состояние, проверки, сценарии ----------
    def _build_right(self) -> QWidget:
        frame, lay = panel(margins=8)
        tabs = QTabWidget()
        st = QWidget()
        sl = QVBoxLayout(st)
        sl.addWidget(label("Переменные", "H2"))
        self.vars = QTableWidget(0, 2)
        self.vars.setHorizontalHeaderLabels(["Имя", "Значение"])
        self.vars.horizontalHeader().setStretchLastSection(True)
        self.vars.verticalHeader().setVisible(False)
        self.vars.setFixedHeight(140)
        sl.addWidget(self.vars)
        sl.addWidget(label("Журнал событий", "H2"))
        self.log = QListWidget()
        sl.addWidget(self.log, 1)
        sl.addWidget(label("Запись действий", "H2"))
        self.script_info = label("", "Muted", wrap=True)
        sl.addWidget(self.script_info)
        row = QHBoxLayout()
        row.addWidget(button("Запомнить", self.remember, "Запомнить действия с начала сеанса"))
        row.addWidget(button("Повторить", self.replay, "Проиграть запомненное с начала и сравнить итог"))
        sl.addLayout(row)
        sl.addWidget(button("Сохранить как тест…", self.save_scenario,
                            "Сохранить действия сеанса в проект как тестовый сценарий"))
        self.replay_result = label("", "Muted", wrap=True)
        sl.addWidget(self.replay_result)
        tabs.addTab(st, "Сеанс")
        ch = QWidget()
        cl = QVBoxLayout(ch)
        cl.addWidget(label("Проверка экрана на устройстве", "H2"))
        self.checks = QListWidget()
        self.checks.setWordWrap(True)
        cl.addWidget(self.checks, 1)
        tabs.addTab(ch, "Проверки")
        sc = QWidget()
        scl = QVBoxLayout(sc)
        scl.addWidget(label("Тестовые сценарии проекта", "H2"))
        self.sc_list = QListWidget()
        self.sc_list.setWordWrap(True)
        self.sc_list.currentItemChanged.connect(lambda *_: self._show_result())
        scl.addWidget(self.sc_list, 1)
        row = QHBoxLayout()
        row.addWidget(button("▶ Проверить", self.run_selected))
        row.addWidget(button("Проверить все", self.run_all))
        scl.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(button("Показать", self.show_selected, "Проиграть сценарий в устройстве"))
        row.addWidget(button("Удалить", self.delete_selected, object_name="Danger"))
        scl.addLayout(row)
        self.sc_result = label("", "Muted", wrap=True)
        scl.addWidget(self.sc_result)
        tabs.addTab(sc, "Сценарии")
        self.right_tabs = tabs
        lay.addWidget(tabs)
        return frame

    # ---------- сеанс ----------
    def _hash(self) -> str:
        doc = self.main.doc
        return hashlib.sha256(json.dumps(doc.to_dict(), sort_keys=True, ensure_ascii=False).encode()).hexdigest() \
            if doc else ""

    def start(self, screen_id: str | None = None) -> None:
        """Новый сеанс с экрана screen_id (по умолчанию — текущего в редакторе)."""
        if self.player is not None:
            specs = dict(self.player.specs)
            self.player.stop_clock()
            self.player.setParent(None)
            self.player.deleteLater()
        else:
            specs = {}
        self.player = None
        if self.main.doc is None:
            return
        self.player = PrototypePlayer(self.main, start_screen_id=screen_id or self.main.screen_id)
        self.player.specs = specs
        for cb, name in ((self.o_safe, "show_safe"), (self.o_touch, "touch_mode"), (self.reduced, "reduced_motion")):
            setattr(self.player, name, cb.isChecked())
        self.stage_lay.addWidget(self.player)
        self.player.changed.connect(self.refresh)
        self._doc_hash = self._hash()
        self.script, self.script_digest = None, ""
        self.replay_result.setText("")
        self.player.render(fit=True)
        self.refresh_devices()
        self.refresh_scenarios()
        if self.isVisible():
            self.player.start_clock()

    def activate(self) -> None:
        """Страница открыта: продолжить сеанс или начать новый, если документ изменился."""
        if self.player is None or self._doc_hash != self._hash() or self.player.doc is not self.main.doc:
            self.start()
        else:
            self.refresh_devices()
            self.refresh_scenarios()
        if self.player is not None:
            self.player.start_clock()

    def deactivate(self) -> None:
        if self.player is not None:
            self.player.stop_clock()

    def restart(self) -> None:
        if self.player is not None:
            self.player.restart()
            self.refresh()

    # ---------- устройство ----------
    def _platform(self) -> str:
        p = self.player
        src = p.interp.screen() if p else None
        return src.platform if src else PLATFORM_ANDROID

    def refresh_devices(self) -> None:
        if self.player is None:
            return
        self._loading = True
        spec = self.player.effective_spec()
        plat = self._platform()
        self.platform_label.setText("Android — симуляция устройства" if plat == PLATFORM_ANDROID
                                    else "Windows — окно приложения")
        self.devices.clear()
        kind = None
        for prof in profiles_for(plat):
            if prof.kind != kind:
                kind = prof.kind
                head = QListWidgetItem(KIND_RU[kind])
                head.setFlags(Qt.ItemFlag.NoItemFlags)
                self.devices.addItem(head)
            it = QListWidgetItem(f"   {prof.name}\n   {prof.width} × {prof.height} · {prof.dpi} dpi")
            it.setData(ROLE, prof.id)
            it.setSizeHint(QSize(0, 46))  # рамка выбранного пункта не должна обрезать вторую строку
            self.devices.addItem(it)
            if spec is not None and prof == spec.profile:
                self.devices.setCurrentItem(it)
        if spec is not None:
            self.c_w.setValue(spec.profile.width)
            self.c_h.setValue(spec.profile.height)
            self.c_dpi.setValue(spec.density)
            self.b_portrait.setEnabled(spec.rotatable)
            self.b_landscape.setEnabled(spec.rotatable)
            self.b_rotate.setEnabled(spec.rotatable)
            self.b_rotate.setToolTip("Портрет ↔ альбом" if spec.rotatable else "Окно Windows не поворачивается")
            (self.b_landscape if spec.orientation == "landscape" else self.b_portrait).setChecked(True)
            self.density.clear()
            if plat == PLATFORM_ANDROID:
                for dpi, name in ANDROID_DENSITIES:
                    self.density.addItem(f"{name} · {dpi} dpi · ×{dpi / 160:g}", dpi)
            else:
                for sc in WINDOWS_SCALES:
                    self.density.addItem(f"Масштаб {sc} %", round(96 * sc / 100))
            i = self.density.findData(spec.density)
            if i < 0:
                self.density.addItem(f"{spec.density} dpi", spec.density)
                i = self.density.count() - 1
            self.density.setCurrentIndex(i)
            self.spec_info.setText(spec.describe())
        self._loading = False

    def _pick_device(self, item, _prev=None) -> None:
        if self._loading or item is None or self.player is None or not item.data(ROLE):
            return
        prof = next(p for p in profiles_for(self._platform()) if p.id == item.data(ROLE))
        self.set_profile(prof)

    def set_profile(self, prof: PreviewProfile, orientation: str = "portrait") -> None:
        if self.player is None:
            return
        self.player.set_spec(ViewSpec(prof, orientation if prof.kind != "window" else "portrait"))
        self.refresh_devices()
        self.refresh()

    def apply_custom(self) -> None:
        self.set_profile(custom_profile(self._platform(), self.c_w.value(), self.c_h.value(), self.c_dpi.value()))

    def _update_spec(self, **kw) -> None:
        if self._loading or self.player is None:
            return
        spec = self.player.effective_spec()
        if spec is None:
            return
        self.player.set_spec(spec.with_(**kw))
        self.refresh_devices()
        self.refresh()

    def _pick_density(self, _i) -> None:
        if not self._loading and self.density.currentData():
            self._update_spec(dpi=int(self.density.currentData()))

    def rotate(self) -> None:
        spec = self.player.effective_spec() if self.player else None
        if spec is not None and spec.rotatable:
            self._update_spec(orientation="portrait" if spec.orientation == "landscape" else "landscape")

    # ---------- обновление ----------
    def refresh(self) -> None:
        p = self.player
        if p is None:
            return
        doc, st = p.doc, p.interp.state
        self.vars.setRowCount(len(doc.variables))
        for r, v in enumerate(doc.variables):
            self.vars.setItem(r, 0, QTableWidgetItem(v.name))
            self.vars.setItem(r, 1, QTableWidgetItem(format_value(st.variables.get(v.id, v.default))))
        if self.log.count() != len(p.effect_log):
            self.log.clear()
            self.log.addItems(p.effect_log)
            self.log.scrollToBottom()
        n = len(p.interp.log)
        self.script_info.setText(f"Действий в сеансе: {n}" + (f" · запомнено: {len(self.script)}"
                                                              if self.script is not None else ""))
        src = p.interp.screen()
        spec = p.spec
        text = f"Экран «{src.name}»" if src else "Нет экрана"
        if spec is not None:
            text += f" · {spec.profile.name} · {spec.describe()}"
        if p.focus_id:
            text += " · ввод текста: набирайте на клавиатуре, Enter — готово"
        self.screen_label.setText(text)
        self.screen_label.setToolTip(text)
        self.refresh_checks()
        if self.tabs.currentIndex() == 1:
            self.refresh_compare()

    def refresh_checks(self) -> None:
        p = self.player
        self.checks.clear()
        if p is None or p.screen is None or p.spec is None:
            return
        diags = checks.check(p.doc, p.interp.state.screen_id, p.screen, p.spec)
        diags += [d for d in p.layout_diags if d.severity == "warning"]
        if not diags:
            self.checks.addItem("✓ На этом устройстве замечаний нет")
        for d in diags:
            self.checks.addItem(("⚠ " if d.severity == "warning" else "ℹ ") + d.message)

    def refresh_compare(self) -> None:
        while self.compare_lay.count():
            w = self.compare_lay.takeAt(0).widget()
            if w is not None:
                w.hide()  # иначе старая миниатюра видна до удаления и перекрывает новую
                w.deleteLater()
        p = self.player
        if p is None or self.tabs.currentIndex() != 1:
            return
        plat = self._platform()
        for pid in COMPARE.get(plat, ()):
            prof = next(x for x in profiles_for(plat) if x.id == pid)
            spec = ViewSpec(prof)
            screen, layout_diags = p.static_screen(spec)
            if screen is None:
                continue
            n = len(checks.check(p.doc, p.interp.state.screen_id, screen, spec)) + \
                len([d for d in layout_diags if d.severity == "warning"])
            col = QWidget()
            cl = QVBoxLayout(col)
            cl.setContentsMargins(4, 4, 4, 4)
            pic = QLabel()
            pm = render_device(screen, spec, p.editor.artboard_color(), p.doc.meta.title, p.doc,
                               320 if prof.kind == "window" else 220, 420)
            pic.setPixmap(pm)
            pic.setFixedSize(pm.size())
            col.setFixedWidth(max(pm.width(), 180) + 8)
            cl.addWidget(pic)
            cl.addWidget(label(f"{prof.name}\n{spec.describe()}", "Muted", wrap=True))
            cl.addWidget(label("✓ без замечаний" if not n else f"⚠ замечаний: {n}", "Muted"))
            cl.addWidget(button("Открыть", lambda _=False, pr=prof: (self.set_profile(pr), self.tabs.setCurrentIndex(0))))
            cl.addStretch()
            self.compare_lay.addWidget(col)
        self.compare_lay.addStretch()
        # минимальная ширина по колонкам: при нехватке места — прокрутка, а не наложение миниатюр
        cols = [self.compare_lay.itemAt(i).widget() for i in range(self.compare_lay.count())]
        self.compare.setMinimumWidth(sum(c.minimumWidth() + 8 for c in cols if c is not None) + 20)

    # ---------- запись и повтор сеанса ----------
    def remember(self) -> None:
        if self.player is None:
            return
        self.script = [list(s) for s in self.player.interp.log]
        self.script_digest = self.player.interp.state.digest()
        self.replay_result.setText("Действия запомнены. «Повторить» проиграет их с начала.")
        self.refresh()

    def replay(self) -> None:
        if self.player is None:
            return
        if self.script is None:
            self.replay_result.setText("Сначала пройдите сценарий и нажмите «Запомнить».")
            return
        digest, _ = Interpreter(self.player.doc, self.player.interp.start).replay(self.script)
        self.player.play_steps(self.script)
        same = digest == self.script_digest == self.player.interp.state.digest()
        self.replay_result.setText("✓ Итоговое состояние совпадает с записанным (повтор детерминирован)" if same
                                   else "⚠ Итог отличается от записи")
        self.refresh()

    def save_scenario(self, name: str | None = None) -> bool:
        p = self.player
        if p is None:
            return False
        if not p.interp.log:
            self.replay_result.setText("В сеансе ещё нет действий — пройдите сценарий в устройстве.")
            return False
        if not name:
            name, ok = QInputDialog.getText(self, "Тестовый сценарий", "Название сценария:",
                                            text=f"Сценарий {len(self.main.doc.scenarios) + 1}")
            if not ok or not name.strip():
                return False
        sc = scenarios.record(p.interp, name.strip()[:128])
        if not self.main.patch("Тестовый сценарий", lambda doc: doc.scenarios.append(sc)):
            return False
        self._doc_hash = self._hash()  # сценарий не меняет экраны — сеанс продолжается
        self.replay_result.setText(f"Сценарий «{sc.name}» сохранён в проект: {len(sc.steps)} действий.")
        self.refresh_scenarios()
        return True

    # ---------- тестовые сценарии ----------
    def refresh_scenarios(self) -> None:
        cur = self.sc_list.currentItem().data(ROLE) if self.sc_list.currentItem() else None
        self.sc_list.clear()
        doc = self.main.doc
        if doc is None:
            return
        names = {s.id: s.name for s in doc.screens}
        for sc in doc.scenarios:
            r = self.results.get(sc.id)
            mark = "○" if r is None else ("✓" if r.ok else "✗")
            it = QListWidgetItem(f"{mark} {sc.name}\n   с экрана «{names.get(sc.start_screen_id, 'удалён')}» · "
                                 f"действий: {len(sc.steps)}")
            it.setData(ROLE, sc.id)
            self.sc_list.addItem(it)
            if sc.id == cur:
                self.sc_list.setCurrentItem(it)
        if not doc.scenarios:
            self.sc_result.setText("Сценариев нет. Пройдите действия в устройстве и нажмите «Сохранить как тест…» "
                                   "на вкладке «Сеанс».")
        self._show_result()

    def _selected(self):
        it = self.sc_list.currentItem()
        return self.main.doc.scenario(it.data(ROLE)) if it is not None and self.main.doc else None

    def _show_result(self) -> None:
        sc = self._selected()
        if sc is None:
            return
        r = self.results.get(sc.id)
        self.sc_result.setText("Ещё не проверялся." if r is None else "\n".join(r.messages))

    def run_selected(self) -> None:
        sc = self._selected()
        if sc is not None:
            self.results[sc.id] = scenarios.run(self.main.doc, sc)
            self.refresh_scenarios()

    def run_all(self) -> tuple[int, int]:
        doc = self.main.doc
        if doc is None:
            return 0, 0
        for sc in doc.scenarios:
            self.results[sc.id] = scenarios.run(doc, sc)
        self.refresh_scenarios()
        ok = sum(1 for sc in doc.scenarios if self.results[sc.id].ok)
        text = f"Пройдено {ok} из {len(doc.scenarios)}"
        failed = next((sc for sc in doc.scenarios if not self.results[sc.id].ok), None)
        if failed is not None:  # первая причина сразу видна, остальные — по выбору сценария
            text += f"\n✗ «{failed.name}»: " + "; ".join(self.results[failed.id].messages)
        self.sc_result.setText(text)
        return ok, len(doc.scenarios)

    def show_selected(self) -> None:
        sc = self._selected()
        if sc is None or self.player is None:
            return
        if self.player.interp.start != sc.start_screen_id:
            self.start(sc.start_screen_id)
        self.player.play_steps(sc.steps)
        self.tabs.setCurrentIndex(0)
        self.refresh()

    def delete_selected(self) -> None:
        sc = self._selected()
        if sc is None:
            return
        if QMessageBox.question(self, "Удаление сценария", f"Удалить сценарий «{sc.name}» из проекта? "
                                "Действие можно отменить (Ctrl+Z).") != QMessageBox.StandardButton.Yes:
            return
        sid = sc.id
        if self.main.patch("Удалить сценарий", lambda doc: doc.scenarios.remove(doc.scenario(sid))):
            self.results.pop(sid, None)
            self._doc_hash = self._hash()
            self.refresh_scenarios()


__all__ = ["PreviewPage", "render_device"]
