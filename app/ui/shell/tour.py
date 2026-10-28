"""Короткое обучение: что делать по шагам. Показывается при первом открытии проекта, потом — из «Помощи»."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

STEPS = (
    ("Добро пожаловать!", "Здесь вы рисуете экраны приложения для Android или Windows, проверяете их как на "
     "настоящем телефоне и получаете готовый проект для Android Studio.\n\nСлева в меню — три шага: "
     "«1 · Рисую», «2 · Проверяю», «3 · Выгружаю». Редкие инструменты спрятаны под «Ещё»."),
    ("1 · Рисую: добавить элементы", "Слева во вкладке «Добавить» — картинки всех компонентов: кнопки, поля, "
     "переключатели, карточки, меню. Щёлкните картинку — компонент появится на экране, или перетащите его в нужное "
     "место.\n\nНужен целый экран сразу? Внизу «+ Экран ▾» → готовые экраны: вход, список, профиль, настройки, чат, "
     "корзина."),
    ("1 · Рисую: изменить элемент", "Щёлкните элемент на экране. Сверху появится панель:\n"
     "• «При нажатии…» — что сделает кнопка: откроет другой экран, вернётся назад, покажет окно;\n"
     "• «Заменить…» — поставить на это место другой компонент;\n• «Дублировать» и «Удалить».\n\n"
     "Справа — его текст, цвет, размер и эффекты. Кнопка «?» рядом с разделом объясняет, что он делает. "
     "Правая кнопка мыши — все действия. Ошиблись — Ctrl+Z."),
    ("2 · Проверяю", "Кнопка «▶ Просмотр» или F5 открывает экран на телефоне, планшете или в окне. Нажимайте "
     "кнопки, листайте, вводите текст — всё работает, как в приложении. Переключатели и вкладки "
     "переключаются, переходы между экранами анимированы."),
    ("3 · Выгружаю", "«3 · Выгружаю» собирает пакет: проект Android Studio (Kotlin, Jetpack Compose, Material 3), "
     "тестовый APK для телефона и задание для ИИ, чтобы доделать приложение.\n\nМасштаб холста — Ctrl + колесо мыши "
     "или кнопки в правом нижнем углу. Это обучение можно снова открыть: «Помощь → Как пользоваться»."),
)


class TourDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Как пользоваться")
        self.setMinimumWidth(520)
        self.i = 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(12)
        self.counter = QLabel()
        self.counter.setObjectName("Muted")
        lay.addWidget(self.counter)
        self.title = QLabel()
        self.title.setObjectName("H1")
        self.title.setWordWrap(True)
        lay.addWidget(self.title)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setMinimumHeight(160)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self.body, 1)
        row = QHBoxLayout()
        self.skip = QPushButton("Пропустить")
        self.skip.clicked.connect(self.accept)
        row.addWidget(self.skip)
        row.addStretch()
        self.back = QPushButton("Назад")
        self.back.clicked.connect(lambda: self.go(self.i - 1))
        row.addWidget(self.back)
        self.next = QPushButton("Дальше")
        self.next.setObjectName("Primary")
        self.next.setDefault(True)
        self.next.clicked.connect(lambda: self.go(self.i + 1) if self.i < len(STEPS) - 1 else self.accept())
        row.addWidget(self.next)
        lay.addLayout(row)
        self.go(0)

    def go(self, i: int) -> None:
        self.i = max(0, min(len(STEPS) - 1, i))
        title, body = STEPS[self.i]
        self.counter.setText(f"Шаг {self.i + 1} из {len(STEPS)}")
        self.title.setText(title)
        self.body.setText(body)
        self.back.setEnabled(self.i > 0)
        last = self.i == len(STEPS) - 1
        self.next.setText("Начать работу" if last else "Дальше")
        self.skip.setVisible(not last)
