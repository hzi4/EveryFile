import sys
import os
import json
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QPushButton, QFrame, QListWidget,
                               QFileDialog, QMessageBox, QProgressBar, QRadioButton,
                               QSlider, QButtonGroup, QGraphicsOpacityEffect, QDialog,
                               QComboBox)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, Signal, QPoint, QThread
from PySide6.QtGui import QColor, QFont, QPainter, QLinearGradient, QBrush, QPen, QPixmap

# Библиотеки для конвертации
import pymupdf as fitz
from PIL import Image


# --- Поток для конвертации ---
class ConverterThread(QThread):
    progress_signal = Signal(int, str)
    finished_signal = Signal(bool, str)

    def __init__(self, files, mode, quality, out_dir):
        super().__init__()
        self.files = files
        self.mode = mode
        self.quality = quality
        self.out_dir = Path(out_dir)

    def run(self):
        total = len(self.files)
        if total == 0:
            self.finished_signal.emit(False, "Список файлов пуст.")
            return

        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            for idx, file in enumerate(self.files, 1):
                fname = Path(file)
                self.progress_signal.emit(int((idx - 1) / total * 100), f"Обработка: {fname.name}")

                try:
                    if self.mode == "PDF → JPG":
                        self.convert_pdf(fname)
                    elif self.mode == "JPG → PDF":
                        self.convert_jpg(fname)
                    elif self.mode == "Картинки (IMG → IMG)":
                        self.convert_img(fname)
                    elif self.mode == "Извлечь текст (OCR)":
                        self.convert_text(fname)
                    elif self.mode == "Видео → Аудио (MP3)":
                        self.convert_video(fname)
                except Exception as inner_e:
                    self.progress_signal.emit(int(idx / total * 100), f"Ошибка в {fname.name}: {inner_e}")
                    continue

                self.progress_signal.emit(int(idx / total * 100), f"Готово: {fname.name}")
            self.finished_signal.emit(True, "Все файлы обработаны!")
        except Exception as e:
            self.finished_signal.emit(False, f"Критическая ошибка: {str(e)}")

    def convert_pdf(self, pdf_path):
        matrix = fitz.Matrix(self.quality / 72, self.quality / 72)
        with fitz.open(pdf_path) as doc:
            for i, page in enumerate(doc, start=1):
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                out_file = self.out_dir / f"{pdf_path.stem}_page_{i:03d}.jpg"
                pix.save(str(out_file), jpg_quality=95)

    def convert_jpg(self, img_path):
        img = Image.open(img_path).convert("RGB")
        out_file = self.out_dir / f"{img_path.stem}.pdf"
        img.save(out_file, "PDF", resolution=100.0)

    def convert_img(self, img_path):
        img = Image.open(img_path)
        out_file = self.out_dir / f"{img_path.stem}.png"
        img.save(out_file, "PNG")

    def convert_text(self, file_path):
        try:
            import pytesseract
            if file_path.suffix.lower() == ".pdf":
                with fitz.open(file_path) as doc:
                    text = "\n".join(page.get_text() for page in doc)
            else:
                img = Image.open(file_path)
                text = pytesseract.image_to_string(img, lang="rus+eng")
            out_file = self.out_dir / f"{file_path.stem}.txt"
            out_file.write_text(text, encoding="utf-8")
        except ImportError:
            raise Exception("Библиотека pytesseract не установлена. Установите её: pip install pytesseract")
        except Exception as e:
            raise Exception(f"Ошибка OCR: {e}")

    def convert_video(self, video_path):
        try:
            from moviepy.editor import VideoFileClip
            video = VideoFileClip(str(video_path))
            out_file = self.out_dir / f"{video_path.stem}.mp3"
            video.audio.write_audiofile(str(out_file), logger=None)
            video.close()
        except ImportError:
            raise Exception("Библиотека moviepy не установлена. Установите её: pip install moviepy")
        except Exception as e:
            raise Exception(f"Ошибка конвертации видео: {e}")


# --- Экран загрузки ---
class SplashScreen(QWidget):
    def __init__(self, on_complete):
        super().__init__()
        self.on_complete = on_complete
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(450, 300)

        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)

        self.progress_val = 0.0
        self.status_text = "Инициализация..."
        self.angle = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(20)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self.opacity_effect)

        self.fade_in_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_in_anim.setDuration(400)
        self.fade_in_anim.setStartValue(0.0)
        self.fade_in_anim.setEndValue(1.0)
        self.fade_in_anim.start()

        self.show()

    def animate(self):
        self.angle = (self.angle - 6) % 360
        if self.progress_val < 0.9:
            self.progress_val += 0.005
        self.update()

    def set_progress(self, val, text):
        self.progress_val = val
        self.status_text = text
        self.update()

    def finish(self):
        self.timer.stop()
        self.fade_out_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_out_anim.setDuration(400)
        self.fade_out_anim.setStartValue(1.0)
        self.fade_out_anim.setEndValue(0.0)
        self.fade_out_anim.finished.connect(self.on_complete)
        self.fade_out_anim.finished.connect(self.close)
        self.fade_out_anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QColor("#110b18"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 20, 20)

        pen = QPen(QColor("#8a2be2"), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 20, 20)

        painter.setPen(QColor("#e0d4eb"))
        painter.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        painter.drawText(self.rect().adjusted(0, 40, 0, 0), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                         "EveryFile Converter")

        painter.setPen(QColor("#a085b8"))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(self.rect().adjusted(0, -20, 0, 0),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, self.status_text)

        cx, cy = self.width() // 2, self.height() // 2
        r = 30
        pen = QPen(QColor("#1a1124"), 6)
        painter.setPen(pen)
        painter.drawArc(cx - r, cy - r, r * 2, r * 2, 0, 360 * 16)

        pen = QPen(QColor("#8a2be2"), 6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(cx - r, cy - r, r * 2, r * 2, self.angle * 16, 90 * 16)

        bar_w, bar_h = 300, 6
        bar_x, bar_y = (self.width() - bar_w) // 2, self.height() - 60
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1a1124"))
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 3, 3)

        painter.setBrush(QColor("#8a2be2"))
        fill_w = int(bar_w * self.progress_val)
        if fill_w > 0:
            painter.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 3, 3)


# --- Градиентный фон с поддержкой тем и картинок ---
class BackgroundWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.gradient_colors = ("#110b18", "#2d1b3d", "#5c1a9e")
        self.pixmap = None

    def set_theme_colors(self, c1, c2, c3):
        self.gradient_colors = (c1, c2, c3)
        self.update()

    def set_pixmap(self, pixmap):
        self.pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.pixmap:
            painter.drawPixmap(self.rect(), self.pixmap)
        else:
            gradient = QLinearGradient(0, 0, self.width(), self.height())
            gradient.setColorAt(0.0, QColor(self.gradient_colors[0]))
            gradient.setColorAt(0.5, QColor(self.gradient_colors[1]))
            gradient.setColorAt(1.0, QColor(self.gradient_colors[2]))
            painter.fillRect(self.rect(), QBrush(gradient))


# --- Диалог настроек ---
class SettingsDialog(QDialog):
    def __init__(self, parent, current_theme, bg_image_path):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setFixedSize(450, 380)
        self.parent_app = parent
        self.current_theme = current_theme
        self.bg_image_path = bg_image_path

        self.setStyleSheet("""
            QDialog { background-color: #1a1124; color: #e0d4eb; }
            QLabel { color: #e0d4eb; font-size: 14px; }
            QComboBox { background-color: #2d1b3d; color: #e0d4eb; border: 1px solid #8a2be2; border-radius: 5px; padding: 8px; font-size: 14px; }
            QPushButton { background-color: #2d1b3d; color: #e0d4eb; border: 1px solid #8a2be2; border-radius: 5px; padding: 10px; font-size: 14px; }
            QPushButton:hover { background-color: #8a2be2; color: white; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)

        title = QLabel("🎨 НАСТРОЙКИ ВНЕШНЕГО ВИДА")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #8a2be2;")
        layout.addWidget(title)

        layout.addWidget(QLabel("Цветовая тема:"))

        self.combo = QComboBox()
        self.combo.addItems(["Фиолетовая", "Синяя", "Темная"])
        self.combo.setCurrentText(current_theme)
        layout.addWidget(self.combo)

        layout.addWidget(QLabel("Фоновое изображение:"))

        btn_bg = QPushButton("📂 Загрузить картинку")
        btn_bg.clicked.connect(self.load_bg)
        layout.addWidget(btn_bg)

        btn_reset = QPushButton("❌ Убрать обои")
        btn_reset.clicked.connect(self.reset_bg)
        layout.addWidget(btn_reset)

        layout.addStretch()

        btn_save = QPushButton("Применить")
        btn_save.setStyleSheet("background-color: #8a2be2; color: white; font-weight: bold; padding: 12px;")
        btn_save.clicked.connect(self.apply_settings)
        layout.addWidget(btn_save)

    def load_bg(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите изображение", "", "Изображения (*.jpg *.png *.jpeg)")
        if file_path:
            self.bg_image_path = file_path

    def reset_bg(self):
        self.bg_image_path = None

    def apply_settings(self):
        new_theme = self.combo.currentText()
        self.parent_app.update_settings(new_theme, self.bg_image_path)
        self.accept()


# --- Главное окно ---
class MegaConverterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EveryFile Converter")
        self.setGeometry(100, 100, 1000, 750)
        self.setMinimumSize(850, 650)

        self.setWindowOpacity(0.0)
        self.files_to_process = []
        self.base_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
        self.output_dir = str(self.base_dir / "output")
        self.thread = None

        self.config_file = self.base_dir / "settings.json"
        self.current_theme = "Фиолетовая"
        self.bg_image_path = None
        self.load_settings()

        self.theme_colors = {
            "Фиолетовая": {
                "gradient": ("#110b18", "#2d1b3d", "#5c1a9e"),
                "card": "rgba(45, 27, 61, 230)", "accent": "#8a2be2",
                "text": "#e0d4eb", "text_dim": "#a085b8", "slider_bg": "#1a1124"
            },
            "Синяя": {
                "gradient": ("#0a111f", "#1d2d44", "#1e5b99"),
                "card": "rgba(29, 45, 68, 230)", "accent": "#3e92cc",
                "text": "#e0eaf5", "text_dim": "#88a3c2", "slider_bg": "#0d1b2a"
            },
            "Темная": {
                "gradient": ("#0f0f0f", "#1e1e1e", "#4a2c80"),
                "card": "rgba(30, 30, 30, 230)", "accent": "#bb86fc",
                "text": "#f0f0f0", "text_dim": "#aaaaaa", "slider_bg": "#1a1a1a"
            }
        }
        self.colors = self.theme_colors[self.current_theme]

        self.init_ui()

    def load_settings(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.current_theme = config.get("theme", "Фиолетовая")
                    bg_path = config.get("bg_image", "")
                    if bg_path and Path(bg_path).exists():
                        self.bg_image_path = bg_path
            except Exception as e:
                print(f"Ошибка загрузки конфига: {e}")

    def save_settings(self):
        config = {
            "theme": self.current_theme,
            "bg_image": str(self.bg_image_path) if self.bg_image_path else ""
        }
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Ошибка сохранения конфига: {e}")

    def update_settings(self, new_theme, new_bg):
        self.current_theme = new_theme
        self.bg_image_path = new_bg
        self.save_settings()

        self.colors = self.theme_colors[self.current_theme]
        self.apply_theme()
        self.update_background()

    def apply_theme(self):
        c = self.colors

        g = c["gradient"]
        self.bg.set_theme_colors(g[0], g[1], g[2])

        self.left_panel.setStyleSheet(
            f"QFrame {{ background-color: {c['card']}; border-radius: 15px; border: 1px solid {c['accent']}; }}")
        self.right_panel.setStyleSheet(
            f"QFrame {{ background-color: {c['card']}; border-radius: 15px; border: 1px solid {c['accent']}; }}")

        self.btn_settings.setStyleSheet(
            f"QPushButton {{ background-color: {c['card']}; color: white; border: 1px solid {c['accent']}; border-radius: 10px; font-size: 20px; }} QPushButton:hover {{ background-color: {c['accent']}; border-color: #ffffff; }}")
        self.btn_fullscreen.setStyleSheet(
            f"QPushButton {{ background-color: {c['card']}; color: white; border: 1px solid {c['accent']}; border-radius: 10px; font-size: 20px; }} QPushButton:hover {{ background-color: {c['accent']}; border-color: #ffffff; }}")

        # ИСПРАВЛЕНО: используем slider_bg для отключенной кнопки
        self.btn_convert.setStyleSheet(f"""
            QPushButton {{ background-color: {c['card']}; color: {c['text']}; border: 2px solid {c['accent']}; border-radius: 10px; font-size: 15px; font-weight: bold; }}
            QPushButton:hover {{ background-color: {c['accent']}; color: white; }}
            QPushButton:disabled {{ background-color: {c['slider_bg']}; border-color: {c['slider_bg']}; color: #555; }}
        """)

        self.title_label.setStyleSheet(f"color: {c['text']}; font-size: 28px; font-weight: bold;")
        self.lbl_dpi.setStyleSheet(f"color: {c['text_dim']}; font-size: 12px;")
        self.status_label.setStyleSheet(f"color: {c['text_dim']}; font-size: 12px;")
        self.drop_zone.setStyleSheet(
            f"color: {c['text_dim']}; font-size: 16px; border: 2px dashed {c['accent']}; border-radius: 10px; padding: 30px;")

        self.list_widget.setStyleSheet(f"""
            QListWidget {{ background-color: {c['slider_bg']}; color: {c['text']}; border: 1px solid {c['accent']}; border-radius: 10px; padding: 5px; font-family: Consolas; font-size: 13px; }}
            QListWidget::item:selected {{ background-color: {c['accent']}; color: white; }}
        """)

        self.slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 6px; background: {c['slider_bg']}; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: {c['accent']}; width: 16px; margin: -5px 0; border-radius: 8px; }}
            QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 3px; }}
        """)

        self.progress.setStyleSheet(f"""
            QProgressBar {{ border: none; background-color: {c['slider_bg']}; border-radius: 5px; height: 10px; text-align: center; color: transparent; }}
            QProgressBar::chunk {{ background-color: {c['accent']}; border-radius: 5px; }}
        """)

        self.lbl_mode.setStyleSheet(f"color: {c['accent']}; font-weight: bold; font-size: 12px;")
        self.lbl_quality.setStyleSheet(f"color: {c['accent']}; font-weight: bold; font-size: 12px;")

        for rb in self.btn_group.buttons():
            rb.setStyleSheet(f"color: {c['text']}; font-size: 14px; padding: 5px;")

    def update_background(self):
        if self.bg_image_path:
            pixmap = QPixmap(self.bg_image_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(self.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                painter = QPainter(scaled)
                painter.fillRect(scaled.rect(), QColor(0, 0, 0, 180))
                painter.end()
                self.bg.set_pixmap(scaled)
            else:
                self.bg.set_pixmap(None)
        else:
            self.bg.set_pixmap(None)

    def init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.bg = BackgroundWidget(self.central_widget)
        self.bg.resize(self.size())
        self.bg.lower()

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(25, 25, 25, 25)
        self.main_layout.setSpacing(15)

        # Верхняя панель
        self.top_frame = QWidget()
        top_layout = QHBoxLayout(self.top_frame)
        top_layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel(self.get_greeting())
        top_layout.addWidget(self.title_label)
        top_layout.addStretch()

        self.btn_settings = QPushButton("⚙️")
        self.btn_settings.setFixedSize(45, 45)
        self.btn_settings.clicked.connect(self.open_settings)
        top_layout.addWidget(self.btn_settings)

        self.btn_fullscreen = QPushButton("⛶")
        self.btn_fullscreen.setFixedSize(45, 45)
        self.btn_fullscreen.clicked.connect(self.toggle_fullscreen)
        top_layout.addWidget(self.btn_fullscreen)

        self.main_layout.addWidget(self.top_frame)

        # Контент
        self.content_frame = QWidget()
        content_layout = QHBoxLayout(self.content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(15)

        # Левая панель
        self.left_panel = QFrame()
        self.left_panel.setFixedWidth(280)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(20, 20, 20, 20)

        self.lbl_mode = QLabel("РЕЖИМ РАБОТЫ")
        left_layout.addWidget(self.lbl_mode)

        self.btn_group = QButtonGroup(self)
        self.modes = ["PDF → JPG", "JPG → PDF", "Картинки (IMG → IMG)", "Извлечь текст (OCR)", "Видео → Аудио (MP3)"]
        for mode in self.modes:
            rb = QRadioButton(mode)
            if mode == "PDF → JPG": rb.setChecked(True)
            self.btn_group.addButton(rb)
            left_layout.addWidget(rb)

        left_layout.addSpacing(20)
        self.lbl_quality = QLabel("КАЧЕСТВО / DPI")
        left_layout.addWidget(self.lbl_quality)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(10, 300)
        self.slider.setValue(90)
        left_layout.addWidget(self.slider)

        self.lbl_dpi = QLabel("90 DPI")
        self.lbl_dpi.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.slider.valueChanged.connect(lambda v: self.lbl_dpi.setText(f"{v} DPI"))
        left_layout.addWidget(self.lbl_dpi)

        left_layout.addStretch()
        content_layout.addWidget(self.left_panel)

        # Правая панель
        self.right_panel = QFrame()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(25, 25, 25, 25)

        self.drop_zone = QLabel("📥 Нажмите или перетащите файлы сюда")
        self.drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.drop_zone)

        list_ctrl = QHBoxLayout()

        btn_remove = QPushButton("🗑 Удалить")
        btn_remove.setStyleSheet(
            "QPushButton { color: #ff4d4d; border: 1px solid #ff4d4d; border-radius: 5px; padding: 5px 10px; background: transparent; } QPushButton:hover { background: #551111; }")
        btn_remove.clicked.connect(self.remove_selected)
        list_ctrl.addWidget(btn_remove)

        btn_clear = QPushButton("❌ Очистить")
        btn_clear.setStyleSheet(
            "QPushButton { color: #a085b8; border: 1px solid #a085b8; border-radius: 5px; padding: 5px 10px; background: transparent; } QPushButton:hover { background: #333333; }")
        btn_clear.clicked.connect(self.clear_all)
        list_ctrl.addWidget(btn_clear)
        list_ctrl.addStretch()

        right_layout.addLayout(list_ctrl)

        self.list_widget = QListWidget()
        self.list_widget.setAcceptDrops(True)
        right_layout.addWidget(self.list_widget)

        content_layout.addWidget(self.right_panel)
        self.main_layout.addWidget(self.content_frame)

        # Нижняя панель
        self.bottom_frame = QWidget()
        bottom_layout = QHBoxLayout(self.bottom_frame)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        bottom_layout.addWidget(self.progress)

        self.status_label = QLabel("Система готова к работе")
        bottom_layout.addWidget(self.status_label)

        self.btn_convert = QPushButton("🚀 КОНВЕРТИРОВАТЬ")
        self.btn_convert.setFixedSize(250, 48)
        self.btn_convert.clicked.connect(self.start_conversion)
        bottom_layout.addWidget(self.btn_convert)

        self.main_layout.addWidget(self.bottom_frame)

        self.setAcceptDrops(True)

        self.apply_theme()
        self.update_background()

    def get_greeting(self):
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "Доброе утро! ☀️"
        elif 12 <= hour < 18:
            return "Добрый день! 🌤️"
        elif 18 <= hour < 23:
            return "Добрый вечер! 🌙"
        else:
            return "Доброй ночи! 🌌"

    def open_settings(self):
        dialog = SettingsDialog(self, self.current_theme, self.bg_image_path)
        if dialog.exec():
            self.update_background()

    def start_show_animation(self):
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(800)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade_anim.start()

        self.slide_anim = QPropertyAnimation(self.top_frame, b"pos")
        self.slide_anim.setDuration(1000)
        start_pos = self.top_frame.pos() - QPoint(0, 40)
        self.slide_anim.setStartValue(start_pos)
        self.slide_anim.setEndValue(self.top_frame.pos())
        self.slide_anim.setEasingCurve(QEasingCurve.Type.OutBounce)
        self.slide_anim.start()

    def resizeEvent(self, event):
        self.bg.resize(self.size())
        if self.bg_image_path:
            self.update_background()
        super().resizeEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.isfile(file_path) and file_path not in self.files_to_process:
                self.files_to_process.append(file_path)
        self.update_list()

    def update_list(self):
        self.list_widget.clear()
        for f in self.files_to_process:
            self.list_widget.addItem(f"  📄 {os.path.basename(f)}")
        self.drop_zone.setText(f"📦 Выбрано файлов: {len(self.files_to_process)}\n(Перетащите еще, если нужно)")

    def remove_selected(self):
        for item in self.list_widget.selectedItems():
            row = self.list_widget.row(item)
            del self.files_to_process[row]
        self.update_list()

    def clear_all(self):
        self.files_to_process.clear()
        self.update_list()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def start_conversion(self):
        if not self.files_to_process:
            QMessageBox.warning(self, "Внимание", "Сначала добавьте файлы!")
            return

        mode = self.btn_group.checkedButton().text()
        quality = self.slider.value()

        self.btn_convert.setEnabled(False)
        self.progress.setValue(0)
        self.status_label.setText("Инициализация процесса...")

        self.thread = ConverterThread(self.files_to_process, mode, quality, self.output_dir)
        self.thread.progress_signal.connect(self.update_progress)
        self.thread.finished_signal.connect(self.conversion_finished)
        self.thread.start()

    def update_progress(self, percent, text):
        self.progress.setValue(percent)
        self.status_label.setText(text)

    def conversion_finished(self, success, message):
        self.btn_convert.setEnabled(True)
        if success:
            self.status_label.setText("✅ Успешно завершено!")
            QMessageBox.information(self, "Успех", f"{message}\nФайлы лежат в папке 'output'.")
        else:
            self.status_label.setText("❌ Ошибка!")
            QMessageBox.critical(self, "Ошибка", message)

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            if not self.thread.wait(2000):
                self.thread.terminate()
                self.thread.wait()
        event.accept()


# --- Точка входа ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))

    window = MegaConverterApp()

    splash = SplashScreen(on_complete=lambda: None)

    step = [0]


    def update_splash():
        step[0] += 1
        if step[0] == 2:
            splash.set_progress(0.3, "Загрузка настроек...")
        elif step[0] == 4:
            splash.set_progress(0.6, "Подготовка интерфейса...")
        elif step[0] == 6:
            splash.set_progress(0.9, "Почти готово...")
        elif step[0] == 8:
            splash.set_progress(1.0, "Готово!")
            splash_timer.stop()
            splash.finish()
            window.show()
            window.start_show_animation()


    splash_timer = QTimer()
    splash_timer.timeout.connect(update_splash)
    splash_timer.start(300)

    sys.exit(app.exec())