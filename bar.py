import sys
import os
import time
import subprocess
import ctypes
from ctypes import wintypes
import psutil
import threading
import winreg
import asyncio

from config import load_config
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QFrame, QGraphicsDropShadowEffect,
    QSlider, QListWidget, QListWidgetItem, QLineEdit, QMenu, QGridLayout,
    QSpacerItem, QSizePolicy,
)
from PyQt6.QtCore import (
    Qt, QTimer, QTime, QDate, pyqtSignal, QThread, QByteArray,
    QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QRect, QUrl,
)
from PyQt6.QtGui import QColor, QPixmap, QRegion, QImage
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

try:
    from pyvda import get_virtual_desktops, VirtualDesktop
    PYVDA_OK = True
except Exception:
    PYVDA_OK = False

try:
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    )
    from winsdk.windows.storage.streams import Buffer, InputStreamOptions
    WINSDK_OK = True
except Exception:
    WINSDK_OK = False

from theme import get_theme, hex_to_qcolor, DARK_PALETTE, DARK_PALETTE
palette, _ = get_theme()

SEG = "font-family: 'Segoe MDL2 Assets';"

import struct

def enable_acrylic_blur(hwnd, is_light=False, force=False):
    try:
        # Round the window corners natively in DWM (Windows 11)
        import ctypes
        from config import load_config
        
        val = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(int(hwnd), 33, ctypes.byref(val), ctypes.sizeof(val))
        
        if not force:
            config = load_config()
            style = config.get("style", {}).get("popup_style", "popup")
            if style in ["edgeBox", "edgeCurve"]:
                import struct
                # ACCENT_DISABLED = 0
                policy = struct.pack("IIII", 0, 0, 0, 0)
                attrib_data = struct.pack("IPI", 19, ctypes.cast(ctypes.c_char_p(policy), ctypes.c_void_p).value, len(policy))
                ctypes.windll.user32.SetWindowCompositionAttribute(int(hwnd), attrib_data)
                return # Disable blur globally for this mode!

        # ACCENT_ENABLE_BLURBEHIND = 3 (Aero blur)
        import struct
        policy = struct.pack("IIII", 3, 0, 0, 0)
        attrib_data = struct.pack("IPI", 19, ctypes.cast(ctypes.c_char_p(policy), ctypes.c_void_p).value, len(policy))
        ctypes.windll.user32.SetWindowCompositionAttribute(int(hwnd), attrib_data)
    except Exception as e:
        print(f"Error enabling blur: {e}")


# ─── Virtual Desktop Workspaces ───────────────────────────────────────────────

class WorkspacesWidget(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("workspaces")
        self._layout = QHBoxLayout()
        self._layout.setContentsMargins(5, 0, 5, 0)
        self._layout.setSpacing(5)
        self.setLayout(self._layout)

        self.buttons = []
        self.current_desktop = 1

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_workspaces)
        self.timer.start(500)
        self.update_workspaces()

    def update_workspaces(self):
        if not PYVDA_OK:
            if not self.buttons:
                for i in range(1, 6):
                    btn = QPushButton()
                    btn.setCheckable(True)
                    if i == 1:
                        btn.setChecked(True)
                    self._layout.addWidget(btn)
                    self.buttons.append(btn)
            return
        try:
            desktops = get_virtual_desktops()
            current = VirtualDesktop.current().number

            if len(desktops) != len(self.buttons):
                for btn in self.buttons:
                    self._layout.removeWidget(btn)
                    btn.deleteLater()
                self.buttons.clear()

                for i in range(1, len(desktops) + 1):
                    btn = QPushButton()
                    btn.setCheckable(True)
                    btn.clicked.connect(lambda checked, idx=i: self.switch_desktop(idx))
                    self._layout.addWidget(btn)
                    self.buttons.append(btn)

            if self.current_desktop != current:
                self.current_desktop = current
                for idx, btn in enumerate(self.buttons):
                    btn.setChecked((idx + 1) == self.current_desktop)

        except Exception as e:
            print(f"Workspace error: {e}")

    def switch_desktop(self, index):
        if not PYVDA_OK:
            return
        try:
            VirtualDesktop(index).go()
        except Exception as e:
            print(f"Failed to switch desktop: {e}")


# ─── System Monitor ───────────────────────────────────────────────────────────

class SystemMonitorWidget(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("sys-monitor")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        self.lbl = QLabel("CPU: 0%  RAM: 0%")
        layout.addWidget(self.lbl)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(2000)

    def update_stats(self):
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        self.lbl.setText(f"CPU: {cpu:.0f}%  RAM: {ram:.0f}%")


# ─── Calendar Popup + Clock ───────────────────────────────────────────────────

class CircularVideoWidget(QVideoWidget):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        region = QRegion(self.rect(), QRegion.RegionType.Ellipse)
        self.setMask(region)


class CalendarPopupWidget(QWidget):
    def __init__(self, owner=None):
        super().__init__()
        self.owner = owner
        self.setWindowFlags(
            Qt.WindowType.ToolTip |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("calendar-popup")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(25)

        self.month_label = QLabel()
        self.month_label.setStyleSheet(
            f"font-size: 24px; font-weight: bold; color: {palette['text']};"
        )
        layout.addWidget(self.month_label)

        self.week_layout = QHBoxLayout()
        self.week_layout.setSpacing(15)
        self.day_labels = []

        for _ in range(7):
            vbox = QVBoxLayout()
            vbox.setSpacing(5)
            day_name = QLabel()
            day_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            day_num = QLabel()
            day_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vbox.addWidget(day_name)
            vbox.addWidget(day_num)
            self.week_layout.addLayout(vbox)
            self.day_labels.append((day_name, day_num))

        layout.addLayout(self.week_layout)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setStyleSheet(f"background-color: {palette['separator']}; max-width: 1px;")
        layout.addWidget(separator)

        # Circular video player
        self.video_container = QWidget()
        self.video_container.setFixedSize(90, 90)
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)

        self.video_widget = CircularVideoWidget()
        video_layout.addWidget(self.video_widget)

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(0.0)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)

        if hasattr(sys, '_MEIPASS'):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        video_path = os.path.join(base_dir, "waguri.mp4")
        if os.path.exists(video_path):
            self.player.setSource(QUrl.fromLocalFile(video_path))
            self.player.setLoops(-1)
            self.player.play()

        layout.addWidget(self.video_container)

        self.update_calendar()

    def leaveEvent(self, event):
        if self.owner and hasattr(self.owner, 'check_hide_popup'):
            QTimer.singleShot(100, self.owner.check_hide_popup)
        super().leaveEvent(event)

    def showEvent(self, event):
        is_light = (palette.get("name") == "Light")
        enable_acrylic_blur(self.winId(), is_light)
        super().showEvent(event)

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QPainterPath
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(0, 0, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r.x(), r.y(), r.width(), r.height(), 12, 12)
        painter.fillPath(path, hex_to_qcolor(palette['capsule_bg']))

    def update_calendar(self):
        today = QDate.currentDate()
        self.month_label.setText(today.toString("MMM"))
        start_day = today.addDays(-3)
        for i in range(7):
            current_day = start_day.addDays(i)
            name_lbl, num_lbl = self.day_labels[i]
            name_lbl.setText(current_day.toString("ddd").upper())
            num_lbl.setText(current_day.toString("dd"))
            if current_day == today:
                name_lbl.setStyleSheet(
                    f"font-size: 10px; font-weight: bold; color: {palette['text']};"
                )
                num_lbl.setStyleSheet(
                    f"font-size: 14px; font-weight: bold; color: {palette['text']};"
                )
            else:
                name_lbl.setStyleSheet(
                    f"font-size: 10px; font-weight: bold; color: {palette['text_muted']};"
                )
                num_lbl.setStyleSheet(
                    f"font-size: 14px; font-weight: bold; color: {palette['text_muted']};"
                )


class ClockWidget(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("clock")
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 0, 10, 0)
        self.label = QLabel()
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.popup = CalendarPopupWidget(owner=self)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.update_time()

    def update_time(self):
        current_time = QTime.currentTime().toString("h:mm AP")
        current_date = QDate.currentDate().toString("ddd, MMM d")
        self.label.setText(f"{current_time}  {current_date}")
        if QTime.currentTime().second() == 0:
            self.popup.update_calendar()

    def enterEvent(self, event):
        from PyQt6.QtGui import QCursor
        mouse_pos = QCursor.pos()
        current_screen = QApplication.screenAt(mouse_pos)
        if not current_screen:
            current_screen = QApplication.primaryScreen()
        screen_geo = current_screen.availableGeometry()

        self.popup.adjustSize()
        popup_w = self.popup.sizeHint().width() if hasattr(self.popup, 'sizeHint') else self.popup.width()
        popup_h = self.popup.sizeHint().height() if hasattr(self.popup, 'sizeHint') else self.popup.height()

        from config import load_config
        config = load_config()
        position = config.get("general", {}).get("position", "top").lower()

        if position == "left":
            target_x = screen_geo.left() + 8
            target_y = mouse_pos.y() - (popup_h // 2)
            start_x = target_x - 15
            start_y = target_y
        elif position == "right":
            target_x = screen_geo.right() - 8 - popup_w
            target_y = mouse_pos.y() - (popup_h // 2)
            start_x = target_x + 15
            start_y = target_y
        elif position == "bottom":
            target_y = screen_geo.bottom() - 8 - popup_h
            target_x = mouse_pos.x() - (popup_w // 2)
            start_y = target_y + 15
            start_x = target_x
        else:
            target_y = screen_geo.top() + 8
            target_x = mouse_pos.x() - (popup_w // 2)
            start_y = target_y - 15
            start_x = target_x

        if target_x + popup_w > screen_geo.right() - 10:
            target_x = screen_geo.right() - popup_w - 10
        if target_x < screen_geo.left() + 10:
            target_x = screen_geo.left() + 10
        if target_y + popup_h > screen_geo.bottom() - 10:
            target_y = screen_geo.bottom() - popup_h - 10
        if target_y < screen_geo.top() + 10:
            target_y = screen_geo.top() + 10
            
        if position in ["left", "right"]:
            start_y = target_y
        else:
            start_x = target_x

        self.popup.show()

        self.anim_group = QParallelAnimationGroup()

        geom_anim = QPropertyAnimation(self.popup, b"geometry")
        geom_anim.setDuration(200)
        geom_anim.setStartValue(QRect(start_x, start_y, popup_w, popup_h))
        geom_anim.setEndValue(QRect(target_x, target_y, popup_w, popup_h))
        geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        opacity_anim = QPropertyAnimation(self.popup, b"windowOpacity")
        opacity_anim.setDuration(200)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)

        self.anim_group.addAnimation(geom_anim)
        self.anim_group.addAnimation(opacity_anim)
        self.anim_group.start()

        super().enterEvent(event)

    def leaveEvent(self, event):
        QTimer.singleShot(100, self.check_hide_popup)
        super().leaveEvent(event)

    def check_hide_popup(self):
        if not self.underMouse() and not self.popup.underMouse():
            self.popup.hide()


# ─── SMTC Media (winsdk) ─────────────────────────────────────────────────────

class MediaFetcherThread(QThread):
    title_updated = pyqtSignal(str)
    thumbnail_updated = pyqtSignal(QByteArray)
    playback_updated = pyqtSignal(int)
    time_updated = pyqtSignal(float, float)

    def __init__(self):
        super().__init__()
        self.running = True
        self.action_queue = []

    def run(self):
        asyncio.run(self._loop())

    def do_action(self, action):
        self.action_queue.append(action)

    def do_seek(self, position_seconds):
        self.action_queue.append(("seek", position_seconds))

    def stop(self):
        self.running = False

    async def _read_thumbnail(self, stream_ref):
        thumb_buffer = Buffer(5_000_000)
        readable_stream = await stream_ref.open_read_async()
        await readable_stream.read_async(
            thumb_buffer, thumb_buffer.capacity, InputStreamOptions.READ_AHEAD
        )
        if thumb_buffer.length == 0:
            return None
        return QByteArray(bytes(thumb_buffer))

    async def _loop(self):
        last_title = None
        last_thumb_key = None
        while self.running:
            try:
                if WINSDK_OK:
                    sessions = await MediaManager.request_async()
                    current_session = sessions.get_current_session()

                    if current_session:
                        while self.action_queue:
                            action = self.action_queue.pop(0)
                            if action == "prev":
                                await current_session.try_skip_previous_async()
                            elif action == "next":
                                await current_session.try_skip_next_async()
                            elif action == "play_pause":
                                info = current_session.get_playback_info()
                                if info.playback_status == 4:
                                    await current_session.try_pause_async()
                                else:
                                    await current_session.try_play_async()
                            elif isinstance(action, tuple) and action[0] == "seek":
                                try:
                                    target_secs = action[1]
                                    ticks = int(target_secs * 10_000_000)
                                    await current_session.try_change_playback_position_async(ticks)
                                except Exception:
                                    pass

                        info = current_session.get_playback_info()
                        if info:
                            self.playback_updated.emit(info.playback_status)

                        timeline = current_session.get_timeline_properties()
                        if timeline:
                            pos = timeline.position.total_seconds()
                            end = timeline.end_time.total_seconds()
                            self.time_updated.emit(pos, end)

                        props = await current_session.try_get_media_properties_async()
                        if props:
                            title = props.title or ""
                            if props.artist:
                                title += f" - {props.artist}"
                            self.title_updated.emit(title or "No media")

                            thumb_key = f"{props.title}|{props.artist}|{props.album_title}"
                            if props.thumbnail and thumb_key != last_thumb_key:
                                try:
                                    qba = await self._read_thumbnail(props.thumbnail)
                                    if qba and len(qba) > 0:
                                        last_thumb_key = thumb_key
                                        self.thumbnail_updated.emit(qba)
                                except Exception:
                                    pass
                            elif title != last_title and not props.thumbnail:
                                last_thumb_key = None

                            last_title = title
                    else:
                        self.title_updated.emit("No media")
            except Exception:
                pass
            await asyncio.sleep(0.5)


class WaveSeekBar(QWidget):
    """Seek bar that draws an animated sine wave for played portion, flat line for unplayed, and an interactive draggable knob handle."""
    seeked = pyqtSignal(float)            # Emitted when drag released (0.0 – 1.0)
    dragging_progress = pyqtSignal(float)  # Emitted live while dragging

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setMouseTracking(True)
        self._progress = 0.0
        self._dragging = False
        self._hovered = False
        self._phase = 0.0
        self._playing = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_playing(self, playing):
        self._playing = playing

    def _tick(self):
        if self._playing:
            self._phase += 0.20
            self.update()

    def set_progress(self, fraction):
        if not self._dragging:
            self._progress = max(0.0, min(1.0, fraction))
            self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        import math
        from PyQt6.QtGui import QPainter, QPen, QPainterPath, QColor
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mid = h / 2

        dot_r = 7 if (self._dragging or self._hovered) else 5
        margin = dot_r + 2
        usable_w = max(w - margin * 2, 1)
        split = int(margin + usable_w * self._progress)

        # Played section — animated sine wave (~20px wavelength)
        if split > margin:
            pen = QPen(QColor(137, 180, 250, 240) if (self._dragging or self._hovered) else QColor(255, 255, 255, 230), 2.2)
            p.setPen(pen)
            path = QPainterPath()
            wavelength = 20.0
            for x in range(int(margin), split + 1):
                t = ((x - margin) / wavelength) * 2 * math.pi
                y = mid + math.sin(t + self._phase) * (h * 0.30)
                if x == int(margin):
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.drawPath(path)

        # Unplayed section — flat dim line
        if split < w - margin:
            p.setPen(QPen(QColor(255, 255, 255, 60), 2.0))
            p.drawLine(split, int(mid), int(w - margin), int(mid))

        # Handle dot with glow halo when hovered/dragged
        dot_x = split
        if self._dragging or self._hovered:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(137, 180, 250, 90))
            p.drawEllipse(dot_x - (dot_r + 3), int(mid) - (dot_r + 3), (dot_r + 3) * 2, (dot_r + 3) * 2)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 255))
        p.drawEllipse(dot_x - dot_r, int(mid) - dot_r, dot_r * 2, dot_r * 2)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._update_from_mouse(event.position().x())

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._update_from_mouse(event.position().x())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self._update_from_mouse(event.position().x())
            self.seeked.emit(self._progress)
            self.update()

    def _update_from_mouse(self, x):
        dot_r = 7
        margin = dot_r + 2
        usable_w = max(self.width() - margin * 2, 1)
        rel_x = x - margin
        self._progress = max(0.0, min(1.0, rel_x / usable_w))
        self.dragging_progress.emit(self._progress)
        self.update()


def draw_popup_background(widget, painter):
    from PyQt6.QtGui import QPainterPath, QRadialGradient, QColor, QPen
    from config import load_config
    from theme import get_windows_accent_color, hex_to_qcolor
    global palette
    
    r = widget.rect().adjusted(0, 0, -1, -1)
    path = QPainterPath()
    path.addRoundedRect(r.x(), r.y(), r.width(), r.height(), 12, 12)
    
    config = load_config()
    style = config.get("style", {}).get("popup_style", "popup")
    
    if style in ["edgeBox", "edgeCurve"]:
        painter.fillPath(path, hex_to_qcolor(palette['capsule_bg'])) # Opaque black base
        
        r_c, g_c, b_c = get_windows_accent_color()
        progress = getattr(widget, '_glow_progress', 1.0)
        max_radius = r.width() * 0.6
        current_radius = max_radius * progress
        
        if current_radius > 0:
            grad = QRadialGradient(r.width() / 2.0, 0, current_radius)
            grad.setColorAt(0, QColor(r_c, g_c, b_c, int(100 * progress))) # Procedural top glow
            grad.setColorAt(1, QColor(r_c, g_c, b_c, 0))  # Fade to fully transparent
            painter.fillPath(path, grad)
            
        painter.setPen(QPen(QColor(45, 45, 45, 255), 1))
        painter.drawPath(path)
    else:
        # We need to access global palette but it's not passed. 
        # Since this function is in bar.py, we can access the global variable directly.
        painter.fillPath(path, hex_to_qcolor(palette['capsule_bg']))

class MediaPopupWidget(QWidget):
    def __init__(self, owner=None):
        super().__init__()
        self.owner = owner
        self._raw_pixmap = None

        self.setWindowFlags(
            Qt.WindowType.ToolTip |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(340)

        # Shadow frame (invisible, just for effect)
        self.shadow_caster = QFrame(self)


        # Transparent card (content drawn over paintEvent background)
        self.card = QWidget(self)
        self.card.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        pad = 12
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(pad, pad, pad, pad)
        card_layout.setSpacing(10)

        # Album art — left column, square with equal inset from capsule edges
        self.album_art = QLabel()
        self.album_art.setFixedSize(56, 56)
        self.album_art.setScaledContents(False)
        self.album_art.setStyleSheet(
            "background: rgba(255,255,255,15); border-radius: 8px;"
        )
        card_layout.addWidget(self.album_art, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Right column: title/time/controls
        content_col = QVBoxLayout()
        content_col.setSpacing(8)
        content_col.setContentsMargins(0, 0, 0, 0)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.setContentsMargins(0, 0, 0, 0)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        info_col.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel("No media")
        self.title_label.setWordWrap(False)
        self.title_label.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #ffffff; background: transparent;"
        )
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setStyleSheet(
            "font-size: 10px; color: rgba(255,255,255,150); background: transparent;"
        )
        info_col.addWidget(self.title_label)
        info_col.addWidget(self.time_label)
        top_row.addLayout(info_col, stretch=1)

        self.play_btn = QPushButton("\uE768")
        self.play_btn.setFixedSize(32, 32)
        self.play_btn.setStyleSheet("""
            QPushButton {
                font-family: 'Segoe MDL2 Assets'; font-size: 16px;
                background: rgba(255,255,255,20); color: #ffffff;
                border: none; border-radius: 16px;
            }
            QPushButton:hover { background: rgba(255,255,255,35); }
            QPushButton:pressed { background: rgba(137,180,250,80); }
        """)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        top_row.addWidget(self.play_btn, alignment=Qt.AlignmentFlag.AlignTop)

        content_col.addLayout(top_row)

        # Seek row: prev | wave-seek | next
        seek_row = QHBoxLayout()
        seek_row.setSpacing(6)
        seek_row.setContentsMargins(0, 0, 0, 0)

        def _skip_btn(glyph):
            b = QPushButton(glyph)
            b.setFixedSize(26, 26)
            b.setStyleSheet("""
                QPushButton {
                    font-family: 'Segoe MDL2 Assets'; font-size: 13px;
                    background: transparent; color: rgba(255,255,255,180);
                    border: none;
                }
                QPushButton:hover { color: #ffffff; }
                QPushButton:pressed { color: #89b4fa; }
            """)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            return b

        self.prev_btn = _skip_btn("\uE892")
        self.next_btn = _skip_btn("\uE893")
        self.seek_bar = WaveSeekBar()

        seek_row.addWidget(self.prev_btn)
        seek_row.addWidget(self.seek_bar, stretch=1)
        seek_row.addWidget(self.next_btn)
        content_col.addLayout(seek_row)

        card_layout.addLayout(content_col, stretch=1)

        # Wire up
        self.play_btn.clicked.connect(self.play_pause)
        self.prev_btn.clicked.connect(self.prev_track)
        self.next_btn.clicked.connect(self.next_track)
        self.seek_bar.seeked.connect(self._on_seeked)
        self.seek_bar.dragging_progress.connect(self._on_dragging_seek)

        # Outer layout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(5, 5, 5, 5)
        outer.addWidget(self.card)

    def paintEvent(self, event):
        import math
        from PyQt6.QtGui import QPainter, QPainterPath, QColor, QPen
        from config import load_config
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        m = 5
        r = self.rect().adjusted(m, m, -m, -m)
        path = QPainterPath()
        
        config = load_config()
        popup_style = config.get("style", {}).get("popup_style", "popup")
        
        path.addRoundedRect(r.x(), r.y(), r.width(), r.height(), 12, 12)
            
        painter.setClipPath(path)
        if popup_style not in ["edgeBox", "edgeCurve"] and hasattr(self, '_blurred_bg') and self._blurred_bg and not self._blurred_bg.isNull():
            scaled = self._blurred_bg.scaled(
                r.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            dx = (r.width() - scaled.width()) // 2
            dy = (r.height() - scaled.height()) // 2
            painter.drawPixmap(r.x() + dx, r.y() + dy, scaled)
            painter.fillRect(r, QColor(10, 12, 22, 100))
        else:
            if popup_style in ["edgeBox", "edgeCurve"]:
                painter.fillRect(r, hex_to_qcolor(palette['capsule_bg']))
            else:
                painter.fillRect(r, QColor(28, 30, 42, 235))
        
        if popup_style in ["edgeBox", "edgeCurve"]:
            painter.setPen(QPen(QColor(45, 45, 45, 255), 1))
            painter.drawPath(path)

    def _on_dragging_seek(self, fraction):
        if hasattr(self, '_end') and self._end > 0:
            current_secs = fraction * self._end
            def fmt(s):
                return f"{int(s//60)}:{int(s%60):02d}"
            self.time_label.setText(f"{fmt(current_secs)} / {fmt(self._end)}")

    def _on_seeked(self, fraction):
        if hasattr(self, '_end') and self._end > 0 and self.owner and self.owner.fetcher_thread:
            target_secs = fraction * self._end
            self.owner.fetcher_thread.do_seek(target_secs)

    def on_time_updated(self, pos, end):
        self._pos = pos
        self._end = end
        def fmt(s):
            return f"{int(s//60)}:{int(s%60):02d}"
        if not self.seek_bar._dragging:
            self.time_label.setText(f"{fmt(pos)} / {fmt(end)}")
        if end > 0:
            self.seek_bar.set_progress(pos / end)

    def on_playback_updated(self, status):
        playing = status == 4
        self.play_btn.setText("\uE769" if playing else "\uE768")
        self.seek_bar.set_playing(playing)

    def on_title_updated(self, title):
        fm = self.title_label.fontMetrics()
        max_w = max(self.card.width() - 130, 120)
        elided = fm.elidedText(title, Qt.TextElideMode.ElideRight, max_w)
        self.title_label.setText(elided)

    def _make_rounded_art(self, pixmap, size):
        rounded = QPixmap(size)
        rounded.fill(QColor(0, 0, 0, 0))
        from PyQt6.QtGui import QPainter, QPainterPath
        p = QPainter(rounded)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(0, 0, size.width(), size.height(), 8, 8)
        p.setClipPath(clip)
        p.drawPixmap(0, 0, pixmap.scaled(
            size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        ))
        p.end()
        return rounded

    def on_thumbnail_updated(self, q_bytes):
        pixmap = QPixmap()
        if not pixmap.loadFromData(q_bytes):
            image = QImage.fromData(q_bytes)
            if image.isNull():
                return
            pixmap = QPixmap.fromImage(image)
        self._raw_pixmap = pixmap
        
        # Pre-compute a high-quality, creamy Gaussian Blur and cache it!
        try:
            from PyQt6.QtWidgets import QGraphicsBlurEffect, QGraphicsScene, QGraphicsPixmapItem
            from PyQt6.QtGui import QPainter
            # Scale down slightly for performance, but not enough to pixelate
            scaled_for_blur = pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            
            scene = QGraphicsScene()
            item = QGraphicsPixmapItem(scaled_for_blur)
            blur = QGraphicsBlurEffect()
            blur.setBlurRadius(40) # Strong, silky Gaussian blur
            item.setGraphicsEffect(blur)
            scene.addItem(item)
            
            self._blurred_bg = QPixmap(scaled_for_blur.size())
            self._blurred_bg.fill(Qt.GlobalColor.transparent)
            ptr = QPainter(self._blurred_bg)
            ptr.setRenderHint(QPainter.RenderHint.Antialiasing)
            scene.render(ptr)
            ptr.end()
        except Exception:
            self._blurred_bg = None
            
        self.album_art.setPixmap(self._make_rounded_art(pixmap, self.album_art.size()))
        self.update()

    def prev_track(self):
        if self.owner and self.owner.fetcher_thread:
            self.owner.fetcher_thread.do_action("prev")

    def next_track(self):
        if self.owner and self.owner.fetcher_thread:
            self.owner.fetcher_thread.do_action("next")

    def play_pause(self):
        if self.owner and self.owner.fetcher_thread:
            self.owner.fetcher_thread.do_action("play_pause")

    def leaveEvent(self, event):
        QTimer.singleShot(100, self.check_hide)

    def check_hide(self):
        if not self.underMouse() and self.owner and not self.owner.underMouse():
            self.hide()



class MediaWidget(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("media")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        self.label = QLabel(f'<span style="{SEG}">&#xE8D6;</span> No media')
        layout.addWidget(self.label)

        self.popup = MediaPopupWidget(owner=self)
        self.fetcher_thread = MediaFetcherThread()
        self.fetcher_thread.title_updated.connect(self.on_title_updated)
        self.fetcher_thread.title_updated.connect(self.popup.on_title_updated)
        self.fetcher_thread.playback_updated.connect(self.popup.on_playback_updated)
        self.fetcher_thread.time_updated.connect(self.popup.on_time_updated)
        self.fetcher_thread.thumbnail_updated.connect(self.popup.on_thumbnail_updated)
        self.fetcher_thread.start()

    def on_title_updated(self, title):
        icon = f'<span style="{SEG}">&#xE8D6;</span>'
        fm = self.label.fontMetrics()
        elided = fm.elidedText(title, Qt.TextElideMode.ElideRight, 150)
        self.label.setText(f"{icon} {elided}")

    def enterEvent(self, event):
        from PyQt6.QtGui import QCursor
        mouse_pos = QCursor.pos()
        current_screen = QApplication.screenAt(mouse_pos)
        if not current_screen:
            current_screen = QApplication.primaryScreen()
        screen_geo = current_screen.availableGeometry()

        self.popup.adjustSize()
        popup_w = self.popup.sizeHint().width() if hasattr(self.popup, 'sizeHint') else self.popup.width()
        popup_h = self.popup.sizeHint().height() if hasattr(self.popup, 'sizeHint') else self.popup.height()

        from config import load_config
        config = load_config()
        position = config.get("general", {}).get("position", "top").lower()

        if position == "left":
            target_x = screen_geo.left() + 8
            target_y = mouse_pos.y() - (popup_h // 2)
            start_x = target_x - 15
            start_y = target_y
        elif position == "right":
            target_x = screen_geo.right() - 8 - popup_w
            target_y = mouse_pos.y() - (popup_h // 2)
            start_x = target_x + 15
            start_y = target_y
        elif position == "bottom":
            target_y = screen_geo.bottom() - 8 - popup_h
            target_x = mouse_pos.x() - (popup_w // 2)
            start_y = target_y + 15
            start_x = target_x
        else:
            target_y = screen_geo.top() + 8
            target_x = mouse_pos.x() - (popup_w // 2)
            start_y = target_y - 15
            start_x = target_x

        if target_x + popup_w > screen_geo.right() - 10:
            target_x = screen_geo.right() - popup_w - 10
        if target_x < screen_geo.left() + 10:
            target_x = screen_geo.left() + 10
        if target_y + popup_h > screen_geo.bottom() - 10:
            target_y = screen_geo.bottom() - popup_h - 10
        if target_y < screen_geo.top() + 10:
            target_y = screen_geo.top() + 10
            
        if position in ["left", "right"]:
            start_y = target_y
        else:
            start_x = target_x

        self.popup.show()
        self.popup.raise_()

        if hasattr(self, '_anim_group') and self._anim_group:
            self._anim_group.stop()
        self._anim_group = QParallelAnimationGroup()

        geom_anim = QPropertyAnimation(self.popup, b"geometry")
        geom_anim.setDuration(200)
        geom_anim.setStartValue(QRect(start_x, start_y, popup_w, popup_h))
        geom_anim.setEndValue(QRect(target_x, target_y, popup_w, popup_h))
        geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        opacity_anim = QPropertyAnimation(self.popup, b"windowOpacity")
        opacity_anim.setDuration(200)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)

        from PyQt6.QtCore import QVariantAnimation
        glow_anim = QVariantAnimation(self.popup)
        glow_anim.setDuration(400)
        glow_anim.setStartValue(0.0)
        glow_anim.setEndValue(1.0)
        
        # Keep reference to avoid garbage collection
        self.popup._glow_anim = glow_anim
        def update_glow(val):
            self.popup._glow_progress = val
            self.popup.update()
        glow_anim.valueChanged.connect(update_glow)

        self._anim_group.addAnimation(geom_anim)
        self._anim_group.addAnimation(opacity_anim)
        self._anim_group.addAnimation(glow_anim)
        self._anim_group.start()

    def leaveEvent(self, event):
        QTimer.singleShot(100, self._check_hide)

    def _check_hide(self):
        if not self.underMouse() and not self.popup.underMouse():
            self.popup.hide()


# ─── Network ──────────────────────────────────────────────────────────────────

class NetworkFetcherThread(QThread):
    stats_updated = pyqtSignal(str, float, float)

    def run(self):
        last_io = psutil.net_io_counters()
        ssid = "Unknown"
        try:
            output = subprocess.check_output(
                "netsh wlan show interfaces",
                shell=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            for line in output.split('\n'):
                if ' SSID ' in line and 'BSSID' not in line:
                    ssid = line.split(':', 1)[1].strip()
                    break
        except Exception:
            ssid = "Ethernet"

        counter = 0
        while True:
            time.sleep(1)
            current_io = psutil.net_io_counters()
            down = (current_io.bytes_recv - last_io.bytes_recv) / 1024.0
            up = (current_io.bytes_sent - last_io.bytes_sent) / 1024.0
            last_io = current_io
            counter += 1
            if counter > 10:
                counter = 0
                try:
                    output = subprocess.check_output(
                        "netsh wlan show interfaces",
                        shell=True, text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    for line in output.split('\n'):
                        if ' SSID ' in line and 'BSSID' not in line:
                            ssid = line.split(':', 1)[1].strip()
                            break
                except Exception:
                    pass
            self.stats_updated.emit(ssid, down, up)


class NetworkPopupWidget(QWidget):
    def __init__(self, owner=None):
        super().__init__()
        self.owner = owner
        self.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        self.ssid_label = QLabel("SSID: Unknown")
        self.ssid_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.ssid_label)
        self.down_label = QLabel("Down: 0.0 KB/s")
        self.up_label = QLabel("Up: 0.0 KB/s")
        layout.addWidget(self.down_label)
        layout.addWidget(self.up_label)

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter
        draw_popup_background(self, QPainter(self))

    def showEvent(self, event):
        is_light = (palette.get("name") == "Light")
        enable_acrylic_blur(self.winId(), is_light)
        super().showEvent(event)


class NetworkWidget(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("network")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.icon = QLabel(f'<span style="{SEG}">&#xE701;</span>')
        layout.addWidget(self.icon)

        self.popup = NetworkPopupWidget(self)
        self.thread = NetworkFetcherThread()
        self.thread.stats_updated.connect(self.update_stats)
        self.thread.start()

    def update_stats(self, ssid, down, up):
        self.popup.ssid_label.setText(f"SSID: {ssid}")
        self.popup.down_label.setText(f"Down: {down:.1f} KB/s")
        self.popup.up_label.setText(f"Up: {up:.1f} KB/s")

    def enterEvent(self, event):
        from PyQt6.QtGui import QCursor
        mouse_pos = QCursor.pos()
        current_screen = QApplication.screenAt(mouse_pos)
        if not current_screen:
            current_screen = QApplication.primaryScreen()
        screen_geo = current_screen.availableGeometry()

        self.popup.adjustSize()
        popup_w = self.popup.sizeHint().width() if hasattr(self.popup, 'sizeHint') else self.popup.width()
        popup_h = self.popup.sizeHint().height() if hasattr(self.popup, 'sizeHint') else self.popup.height()

        from config import load_config
        config = load_config()
        position = config.get("general", {}).get("position", "top").lower()

        if position == "left":
            target_x = screen_geo.left() + 8
            target_y = mouse_pos.y() - (popup_h // 2)
            start_x = target_x - 15
            start_y = target_y
        elif position == "right":
            target_x = screen_geo.right() - 8 - popup_w
            target_y = mouse_pos.y() - (popup_h // 2)
            start_x = target_x + 15
            start_y = target_y
        elif position == "bottom":
            target_y = screen_geo.bottom() - 8 - popup_h
            target_x = mouse_pos.x() - (popup_w // 2)
            start_y = target_y + 15
            start_x = target_x
        else:
            target_y = screen_geo.top() + 8
            target_x = mouse_pos.x() - (popup_w // 2)
            start_y = target_y - 15
            start_x = target_x

        if target_x + popup_w > screen_geo.right() - 10:
            target_x = screen_geo.right() - popup_w - 10
        if target_x < screen_geo.left() + 10:
            target_x = screen_geo.left() + 10
        if target_y + popup_h > screen_geo.bottom() - 10:
            target_y = screen_geo.bottom() - popup_h - 10
        if target_y < screen_geo.top() + 10:
            target_y = screen_geo.top() + 10
            
        if position in ["left", "right"]:
            start_y = target_y
        else:
            start_x = target_x

        self.popup.show()
        self.popup.raise_()

        if hasattr(self, '_anim_group') and self._anim_group:
            self._anim_group.stop()
        self._anim_group = QParallelAnimationGroup()

        geom_anim = QPropertyAnimation(self.popup, b"geometry")
        geom_anim.setDuration(200)
        geom_anim.setStartValue(QRect(start_x, start_y, popup_w, popup_h))
        geom_anim.setEndValue(QRect(target_x, target_y, popup_w, popup_h))
        geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        opacity_anim = QPropertyAnimation(self.popup, b"windowOpacity")
        opacity_anim.setDuration(200)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)

        from PyQt6.QtCore import QVariantAnimation
        glow_anim = QVariantAnimation(self.popup)
        glow_anim.setDuration(400)
        glow_anim.setStartValue(0.0)
        glow_anim.setEndValue(1.0)
        
        # Keep reference to avoid garbage collection
        self.popup._glow_anim = glow_anim
        def update_glow(val):
            self.popup._glow_progress = val
            self.popup.update()
        glow_anim.valueChanged.connect(update_glow)

        self._anim_group.addAnimation(geom_anim)
        self._anim_group.addAnimation(opacity_anim)
        self._anim_group.addAnimation(glow_anim)
        self._anim_group.start()

    def leaveEvent(self, event):
        self.popup.hide()


# ─── Bluetooth ────────────────────────────────────────────────────────────────

class BluetoothFetcherThread(QThread):
    devices_updated = pyqtSignal(list)

    def run(self):
        while True:
            try:
                cmd = (
                    'powershell -NoProfile -Command "'
                    'Get-PnpDevice -Class Bluetooth '
                    "| Where-Object { $_.Status -eq 'OK' -and $_.Present -eq $true } "
                    '| Select-Object -Property FriendlyName"'
                )
                output = subprocess.check_output(
                    cmd, shell=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                devices = [
                    l.strip() for l in output.split('\n')
                    if l.strip() and 'FriendlyName' not in l and '----' not in l
                ]
                self.devices_updated.emit(devices)
            except Exception:
                pass
            time.sleep(15)


class BluetoothPopupWidget(QWidget):
    def __init__(self, owner=None):
        super().__init__()
        self.owner = owner
        self.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 15, 20, 15)
        self.title = QLabel("Bluetooth Devices")
        self.title.setStyleSheet("font-weight: bold;")
        self._layout.addWidget(self.title)
        self.device_layout = QVBoxLayout()
        self._layout.addLayout(self.device_layout)

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter
        draw_popup_background(self, QPainter(self))

    def showEvent(self, event):
        is_light = (palette.get("name") == "Light")
        enable_acrylic_blur(self.winId(), is_light)
        super().showEvent(event)


NOISE_BT = {
    "Microsoft Bluetooth LE Enumerator",
    "Microsoft Bluetooth Enumerator",
    "Realtek Bluetooth Adapter",
    "Bluetooth Device (Personal Area Network)",
}


class BluetoothWidget(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("bluetooth")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.icon = QLabel(f'<span style="{SEG}">&#xE702;</span>')
        layout.addWidget(self.icon)

        self.popup = BluetoothPopupWidget(self)
        self.thread = BluetoothFetcherThread()
        self.thread.devices_updated.connect(self.update_devices)
        self.thread.start()

    def update_devices(self, devices):
        while self.popup.device_layout.count():
            child = self.popup.device_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        filtered = [d for d in dict.fromkeys(devices) if d not in NOISE_BT]
        if not filtered:
            self.popup.device_layout.addWidget(QLabel("No devices connected"))
        else:
            for dev in filtered:
                self.popup.device_layout.addWidget(QLabel(f"\u2022 {dev}"))
        self.popup.adjustSize()

    def enterEvent(self, event):
        from PyQt6.QtGui import QCursor
        mouse_pos = QCursor.pos()
        current_screen = QApplication.screenAt(mouse_pos)
        if not current_screen:
            current_screen = QApplication.primaryScreen()
        screen_geo = current_screen.availableGeometry()

        self.popup.adjustSize()
        popup_w = self.popup.sizeHint().width() if hasattr(self.popup, 'sizeHint') else self.popup.width()
        popup_h = self.popup.sizeHint().height() if hasattr(self.popup, 'sizeHint') else self.popup.height()

        from config import load_config
        config = load_config()
        position = config.get("general", {}).get("position", "top").lower()

        if position == "left":
            target_x = screen_geo.left() + 8
            target_y = mouse_pos.y() - (popup_h // 2)
            start_x = target_x - 15
            start_y = target_y
        elif position == "right":
            target_x = screen_geo.right() - 8 - popup_w
            target_y = mouse_pos.y() - (popup_h // 2)
            start_x = target_x + 15
            start_y = target_y
        elif position == "bottom":
            target_y = screen_geo.bottom() - 8 - popup_h
            target_x = mouse_pos.x() - (popup_w // 2)
            start_y = target_y + 15
            start_x = target_x
        else:
            target_y = screen_geo.top() + 8
            target_x = mouse_pos.x() - (popup_w // 2)
            start_y = target_y - 15
            start_x = target_x

        if target_x + popup_w > screen_geo.right() - 10:
            target_x = screen_geo.right() - popup_w - 10
        if target_x < screen_geo.left() + 10:
            target_x = screen_geo.left() + 10
        if target_y + popup_h > screen_geo.bottom() - 10:
            target_y = screen_geo.bottom() - popup_h - 10
        if target_y < screen_geo.top() + 10:
            target_y = screen_geo.top() + 10
            
        if position in ["left", "right"]:
            start_y = target_y
        else:
            start_x = target_x

        self.popup.show()
        self.popup.raise_()

        if hasattr(self, '_anim_group') and self._anim_group:
            self._anim_group.stop()
        self._anim_group = QParallelAnimationGroup()

        geom_anim = QPropertyAnimation(self.popup, b"geometry")
        geom_anim.setDuration(200)
        geom_anim.setStartValue(QRect(start_x, start_y, popup_w, popup_h))
        geom_anim.setEndValue(QRect(target_x, target_y, popup_w, popup_h))
        geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        opacity_anim = QPropertyAnimation(self.popup, b"windowOpacity")
        opacity_anim.setDuration(200)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)

        from PyQt6.QtCore import QVariantAnimation
        glow_anim = QVariantAnimation(self.popup)
        glow_anim.setDuration(400)
        glow_anim.setStartValue(0.0)
        glow_anim.setEndValue(1.0)
        
        # Keep reference to avoid garbage collection
        self.popup._glow_anim = glow_anim
        def update_glow(val):
            self.popup._glow_progress = val
            self.popup.update()
        glow_anim.valueChanged.connect(update_glow)

        self._anim_group.addAnimation(geom_anim)
        self._anim_group.addAnimation(opacity_anim)
        self._anim_group.addAnimation(glow_anim)
        self._anim_group.start()

    def leaveEvent(self, event):
        self.popup.hide()


# ─── App Launcher (Rofi-style) ────────────────────────────────────────────────

class SmoothScrollBar(object):
    def __init__(self, scrollbar):
        self.scrollbar = scrollbar
        self.target = scrollbar.value()
        self.anim = QPropertyAnimation(self.scrollbar, b"value")
        self.anim.setDuration(150)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def scroll_to(self, delta):
        self.anim.stop()
        offset = int(delta * 0.4)
        self.target = max(self.scrollbar.minimum(), min(self.scrollbar.maximum(), self.target - offset))
        self.anim.setStartValue(self.scrollbar.value())
        self.anim.setEndValue(self.target)
        self.anim.start()

class AppLauncherWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(600, 450)

        self.shadow_caster = QFrame(self)
        self.shadow_caster.setStyleSheet(
            "background-color: transparent;"
        )


        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search apps or calculate...")
        self.search_bar.setStyleSheet(f"""
            QLineEdit {{
                background-color: {palette['capsule_bg']};
                color: {palette['text']};
                border: 1px solid {palette['bg_transparent']};
                border-radius: 8px;
                padding: 10px;
                font-size: 16px;
            }}
        """)
        self.search_bar.textChanged.connect(self.on_search)
        self.search_bar.returnPressed.connect(self.launch_selected)
        layout.addWidget(self.search_bar)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                color: {palette['text']};
                font-size: 14px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px;
                border-radius: 5px;
                margin-right: 8px;
            }}
            QListWidget::item:selected {{
                background-color: {palette['accent']};
                color: {palette['bg']};
            }}
            QScrollBar:vertical {{
                width: 6px;
                background: transparent;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(128, 128, 128, 0.35);
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)
        self.list_widget.itemDoubleClicked.connect(self.launch_selected)
        from PyQt6.QtCore import QSize
        self.list_widget.setIconSize(QSize(24, 24))
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.smooth_scroll = SmoothScrollBar(self.list_widget.verticalScrollBar())
        self.list_widget.wheelEvent = self.list_widget_wheel_event
        layout.addWidget(self.list_widget)

        self.apps = []
        self.pinned_apps = []
        threading.Thread(target=self.load_apps, daemon=True).start()
        QApplication.instance().installEventFilter(self)

    def paintEvent(self, event):
        self.shadow_caster.setGeometry(0, 0, self.width(), self.height())
        from PyQt6.QtGui import QPainter, QPainterPath, QColor, QPen, QRadialGradient
        from config import load_config
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw to window boundaries to match system DWM rounded borders exactly
        r = self.rect().adjusted(0, 0, -1, -1)
        
        config = load_config()
        style = config.get("style", {}).get("popup_style", "popup")
        is_light = (palette.get("name") == "Light")
        
        path = QPainterPath()
        path.addRoundedRect(r.x(), r.y(), r.width(), r.height(), 12, 12)
        
        if style in ["edgeBox", "edgeCurve"]:
            painter.fillPath(path, hex_to_qcolor(palette['capsule_bg'])) # Opaque base
            
            from theme import get_windows_accent_color
            r_c, g_c, b_c = get_windows_accent_color()
            progress = getattr(self, '_glow_progress', 1.0)
            max_radius = r.width() * 0.6
            current_radius = max_radius * progress
            if current_radius > 0:
                bg_color = QRadialGradient(r.width() / 2.0, 0, current_radius)
                bg_color.setColorAt(0, QColor(r_c, g_c, b_c, int(100 * progress)))
                bg_color.setColorAt(1, QColor(r_c, g_c, b_c, 0))
                painter.fillPath(path, bg_color)
                
            border_color = QColor(45, 45, 45, 255)
        else:
            if is_light:
                bg_color = QColor(240, 240, 240, 130) # Soft tint to blend the blur
                border_color = QColor(0, 0, 0, 30)
            else:
                bg_color = QColor(20, 20, 20, 130) # Soft tint to blend the blur
                border_color = QColor(255, 255, 255, 25)
            painter.fillPath(path, bg_color)
            
        # Draw subtle border
        painter.setPen(QPen(border_color, 1))
        painter.drawPath(path)

    def changeEvent(self, event):
        from PyQt6.QtCore import QEvent
        if event.type() in (QEvent.Type.WindowDeactivate, QEvent.Type.ActivationChange):
            if not self.isActiveWindow():
                self.hide()
        super().changeEvent(event)

    def eventFilter(self, obj, event):
        try:
            from PyQt6.QtCore import QEvent
            if event.type() == QEvent.Type.MouseButtonPress:
                if self.isVisible():
                    if hasattr(event, "globalPosition"):
                        gp = event.globalPosition().toPoint()
                        if not self.geometry().contains(gp):
                            self.hide()
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def load_apps(self):
        paths = [
            os.path.join(os.environ.get('PROGRAMDATA', ''), r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get('APPDATA', ''), r"Microsoft\Windows\Start Menu\Programs"),
        ]
        pinned_kw = {"chrome", "edge", "explorer", "terminal", "code", "steam", "spotify", "discord"}
        for p in paths:
            if not os.path.isdir(p):
                continue
            for root, _, files in os.walk(p):
                for f in files:
                    if f.lower().endswith(".lnk"):
                        app = {"name": f[:-4], "path": os.path.join(root, f)}
                        self.apps.append(app)
                        if any(kw in f.lower() for kw in pinned_kw):
                            self.pinned_apps.append(app)

    def showEvent(self, event):
        self.search_bar.clear()
        self.search_bar.setFocus()
        self.on_search("")
        
        is_light = (palette.get("name") == "Light")
        enable_acrylic_blur(self.winId(), is_light, force=True)

        from PyQt6.QtCore import QVariantAnimation
        self._glow_anim = QVariantAnimation(self)
        self._glow_anim.setDuration(400)
        self._glow_anim.setStartValue(0.0)
        self._glow_anim.setEndValue(1.0)
        self._glow_anim.valueChanged.connect(self._update_glow)
        self._glow_anim.start()

    def _update_glow(self, val):
        self._glow_progress = val
        self.update()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.hide()
        elif key == Qt.Key.Key_Down:
            row = self.list_widget.currentRow()
            self.list_widget.setCurrentRow(min(row + 1, self.list_widget.count() - 1))
        elif key == Qt.Key.Key_Up:
            row = self.list_widget.currentRow()
            self.list_widget.setCurrentRow(max(row - 1, 0))
        else:
            super().keyPressEvent(event)

    def on_search(self, text):
        self.smooth_scroll.target = 0
        self.list_widget.clear()
        t = text.strip()
        t_lower = t.lower()

        # Command shortcuts check
        if t_lower.startswith(":"):
            show_any = False
            if t_lower == ":l":
                item = QListWidgetItem("🔒  Lock Windows")
                item.setData(Qt.ItemDataRole.UserRole, "CMD_LOCK")
                self.list_widget.addItem(item)
                show_any = True
            elif t_lower == ":sl":
                item = QListWidgetItem("🌙  Sleep PC")
                item.setData(Qt.ItemDataRole.UserRole, "CMD_SLEEP")
                self.list_widget.addItem(item)
                show_any = True
            elif t_lower == ":s":
                item = QListWidgetItem("🛑  Shutdown PC")
                item.setData(Qt.ItemDataRole.UserRole, "CMD_SHUTDOWN")
                self.list_widget.addItem(item)
                show_any = True
            elif t_lower == ":c":
                item = QListWidgetItem("🧮  Launch Calculator")
                item.setData(Qt.ItemDataRole.UserRole, "CMD_CALC")
                self.list_widget.addItem(item)
                show_any = True
            
            if show_any:
                if self.list_widget.count():
                    self.list_widget.setCurrentRow(0)
                return

        if t and all(c in "0123456789+-*/()., " for c in t):
            try:
                result = eval(t)  # noqa
                item = QListWidgetItem(f"= {result}")
                item.setData(Qt.ItemDataRole.UserRole, "CALC")
                self.list_widget.addItem(item)
            except Exception:
                pass

        source = self.apps if t else self.pinned_apps
        term = t.lower()
        from PyQt6.QtWidgets import QFileIconProvider
        from PyQt6.QtCore import QFileInfo
        provider = None

        for app in source:
            if not t or term in app["name"].lower():
                if "icon" not in app:
                    if provider is None:
                        provider = QFileIconProvider()
                    app["icon"] = provider.icon(QFileInfo(app["path"]))
                item = QListWidgetItem(app["icon"], app["name"])
                item.setData(Qt.ItemDataRole.UserRole, app["path"])
                self.list_widget.addItem(item)

    def list_widget_wheel_event(self, event):
        self.smooth_scroll.scroll_to(event.angleDelta().y())

        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)

    def launch_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if path == "CALC":
            self.hide()
            return
        if path == "CMD_LOCK":
            self.hide()
            try:
                os.system("rundll32.exe user32.dll,LockWorkStation")
            except Exception as e:
                print(f"Lock error: {e}")
            return
        if path == "CMD_SLEEP":
            self.hide()
            try:
                os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            except Exception as e:
                print(f"Sleep error: {e}")
            return
        if path == "CMD_SHUTDOWN":
            self.hide()
            try:
                os.system("shutdown /s /t 0")
            except Exception as e:
                print(f"Shutdown error: {e}")
            return
        if path == "CMD_CALC":
            self.hide()
            try:
                os.startfile("calc.exe")
            except Exception as e:
                print(f"Calc error: {e}")
            return
        if path:
            try:
                os.startfile(path)
            except Exception as e:
                print(f"Failed to launch: {e}")
            self.hide()

    def hideEvent(self, event):
        self.search_bar.clear()


class AppLauncherTriggerWidget(QFrame):
    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        self.setObjectName("launcher-trigger")
        self.setStyleSheet(f"""
            #launcher-trigger {{
                color: {palette['text']};
            }}
            #launcher-trigger:hover {{
                color: {palette['accent']};
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        self.icon = QLabel(f'<span style="{SEG}">&#xE721;</span>')
        layout.addWidget(self.icon)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if self.launcher.isVisible():
            self.launcher.hide()
        else:
            screen = self.window().screen().availableGeometry()
            w, h = self.launcher.width(), self.launcher.height()

            from config import load_config
            config = load_config()
            position = config.get("general", {}).get("position", "top").lower()

            if position == "left":
                target_x = screen.left() + 8
                target_y = screen.y() + (screen.height() - h) // 2
                start_x = target_x - 15
                start_y = target_y
            elif position == "right":
                target_x = screen.right() - 8 - w
                target_y = screen.y() + (screen.height() - h) // 2
                start_x = target_x + 15
                start_y = target_y
            elif position == "bottom":
                target_y = screen.bottom() - 8 - h
                target_x = screen.x() + (screen.width() - w) // 2
                start_y = target_y + 15
                start_x = target_x
            else:
                target_y = screen.top() + 8
                target_x = screen.x() + (screen.width() - w) // 2
                start_y = target_y - 15
                start_x = target_x

            if target_x + w > screen.right() - 10:
                target_x = screen.right() - w - 10
            if target_x < screen.left() + 10:
                target_x = screen.left() + 10
            if target_y + h > screen.bottom() - 10:
                target_y = screen.bottom() - h - 10
            if target_y < screen.top() + 10:
                target_y = screen.top() + 10
            
            if position in ["left", "right"]:
                start_y = target_y
            else:
                start_x = target_x

            self.launcher.setWindowOpacity(0.0)
            self.launcher.setGeometry(start_x, start_y, w, h)
            self.launcher.show()
            self.launcher.raise_()
            self.launcher.activateWindow()

            if hasattr(self.launcher, '_anim_group') and self.launcher._anim_group:
                self.launcher._anim_group.stop()

            self.launcher._anim_group = QParallelAnimationGroup()

            geom_anim = QPropertyAnimation(self.launcher, b"geometry")
            geom_anim.setDuration(250)
            geom_anim.setStartValue(QRect(start_x, start_y, w, h))
            geom_anim.setEndValue(QRect(target_x, target_y, w, h))
            geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            opacity_anim = QPropertyAnimation(self.launcher, b"windowOpacity")
            opacity_anim.setDuration(250)
            opacity_anim.setStartValue(0.0)
            opacity_anim.setEndValue(1.0)

            self.launcher._anim_group.addAnimation(geom_anim)
            self.launcher._anim_group.addAnimation(opacity_anim)
            self.launcher._anim_group.start()


# ─── Right modules group ──────────────────────────────────────────────────────

class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, text=""):
        super().__init__(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ModulesRightWidget(QFrame):
    sig_vol_updated = pyqtSignal(bool, float)

    def __init__(self):
        super().__init__()
        self.setObjectName("modules-right")
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(10)

        self.screenshot_btn = QPushButton("\uE8C6")
        self.screenshot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.screenshot_btn.clicked.connect(self.take_screenshot)

        self.network = NetworkWidget()
        self.bluetooth = BluetoothWidget()

        self.wifi = ClickableLabel(f'<span style="{SEG}">&#xE701;</span>')
        self.vol = ClickableLabel(f'<span style="{SEG}">&#xE767;</span>')
        self.vol.clicked.connect(self.toggle_mute)
        self.sig_vol_updated.connect(self.on_volume_updated)
        self.bat = QLabel(f'<span style="{SEG}">&#xE83F;</span> 100%')

        layout.addWidget(self.screenshot_btn)
        layout.addWidget(self.network)
        layout.addWidget(self.bluetooth)
        layout.addWidget(self.vol)
        layout.addWidget(self.bat)
        self.setLayout(layout)

        self.bat_timer = QTimer(self)
        self.bat_timer.timeout.connect(self.update_battery)
        self.bat_timer.start(30000)
        self.update_battery()

        self.vol_timer = QTimer(self)
        self.vol_timer.timeout.connect(self.update_volume_status)
        self.vol_timer.start(2000)
        self.update_volume_status()

    def update_battery(self):
        bat = psutil.sensors_battery()
        if bat:
            pct = int(bat.percent)
            icon = "&#xE83F;" if bat.power_plugged else "&#xE850;"
            self.bat.setText(f'<span style="{SEG}">{icon}</span> {pct}%')

    def take_screenshot(self):
        try:
            os.startfile("ms-screenclip:")
        except Exception as e:
            print(f"Snipping tool launch error: {e}")

    def toggle_mute(self):
        VK_VOLUME_MUTE = 0xAD
        ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)
        QTimer.singleShot(150, self.update_volume_status)

    def update_volume_status(self):
        def check():
            try:
                from pycaw.pycaw import AudioUtilities
                
                ctypes.windll.ole32.CoInitialize(None)
                try:
                    dev = AudioUtilities.GetSpeakers()
                    vol = dev.EndpointVolume
                    muted = vol.GetMute() == 1
                    level = vol.GetMasterVolumeLevelScalar()
                    self.sig_vol_updated.emit(muted, level)
                finally:
                    ctypes.windll.ole32.CoUninitialize()
            except Exception as e:
                print(f"Volume check error: {e}")
        threading.Thread(target=check, daemon=True).start()

    def on_volume_updated(self, muted, level):
        if muted:
            icon = "&#xE74F;"
        else:
            pct = int(level * 100)
            if pct == 0:
                icon = "&#xE74F;"
            elif pct < 33:
                icon = "&#xE765;"
            elif pct < 66:
                icon = "&#xE766;"
            else:
                icon = "&#xE767;"
        self.vol.setText(f'<span style="{SEG}">{icon}</span>')


def is_any_window_maximized_on_screen(self_hwnd):
    import ctypes
    from ctypes import wintypes
    
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    
    # MONITOR_DEFAULTTONEAREST = 2
    target_monitor = user32.MonitorFromWindow(int(self_hwnd), 2)
    if not target_monitor:
        return False
        
    maximized = [False]
    
    def enum_callback(hwnd, lParam):
        if not user32.IsWindowVisible(hwnd):
            return True
            
        cloaked = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(ctypes.c_int))
        if cloaked.value != 0:
            return True
            
        buf = ctypes.create_string_buffer(256)
        user32.GetClassNameA(hwnd, buf, 256)
        class_name = buf.value.decode("utf-8")
        if class_name in ("Progman", "WorkerW", "Shell_TrayWnd", "Qt630QWindowIcon"):
            return True
            
        if user32.IsZoomed(hwnd):
            # MONITOR_DEFAULTTONULL = 0
            win_monitor = user32.MonitorFromWindow(hwnd, 0)
            if win_monitor == target_monitor:
                maximized[0] = True
                return False
        return True
        
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    user32.EnumWindows(EnumWindowsProc(enum_callback), 0)
    return maximized[0]


# ─── Main Window ──────────────────────────────────────────────────────────────


class RotatedLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.angle = 90
        
    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter
        painter = QPainter(self)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self.angle)
        painter.translate(-self.height() / 2, -self.width() / 2)
        # We need to draw the text manually because standard QLabel paintEvent doesn't respect painter transforms
        painter.drawText(self.rect().transposed(), Qt.AlignmentFlag.AlignCenter, self.text())
        painter.end()
        
    def sizeHint(self):
        s = super().sizeHint()
        from PyQt6.QtCore import QSize
        return QSize(s.height(), s.width())
        
    def minimumSizeHint(self):
        s = super().minimumSizeHint()
        from PyQt6.QtCore import QSize
        return QSize(s.height(), s.width())

class CornerWidget(QWidget):
    def __init__(self, parent=None, mode="tl"):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.mode = mode
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(12, 12)
        
    def set_mode(self, mode):
        self.mode = mode
        self.update()
    
    def showEvent(self, event):
        import ctypes, struct
        hwnd = int(self.winId())
        # Match bar's DWM treatment: disable accent and round corners
        val = ctypes.c_int(1)  # DWMWCP_DONOTROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(val), ctypes.sizeof(val))
        # ACCENT_DISABLED = 0
        policy = struct.pack("IIII", 0, 0, 0, 0)
        attrib_data = struct.pack("IPI", 19, ctypes.cast(ctypes.c_char_p(policy), ctypes.c_void_p).value, len(policy))
        ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, attrib_data)
        super().showEvent(event)
        
    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QPainterPath, QColor
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw solid square
        painter.fillRect(0, 0, 12, 12, hex_to_qcolor(palette['bg']))
        
        # Punch out circle
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        
        from PyQt6.QtCore import Qt
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(hex_to_qcolor(palette['bg']))
        
        if self.mode == "tl":
            painter.drawEllipse(0, 0, 24, 24)
        elif self.mode == "tr":
            painter.drawEllipse(-12, 0, 24, 24)
        elif self.mode == "bl":
            painter.drawEllipse(0, -12, 24, 24)
        elif self.mode == "br":
            painter.drawEllipse(-12, -12, 24, 24) # Center at (0, 12)

class WaybarWindow(QMainWindow):
    display_toggled = pyqtSignal(str, bool)

    def __init__(self, screen_name=None):
        super().__init__()
        self.bar_height = 37
        self.screen_name = screen_name
        self.appbar = None
        self.is_hidden_for_fullscreen = False
        self.current_brightness = 50
        self._last_max_state = None
        
        self.left_corner = CornerWidget(self, mode="tl")
        self.right_corner = CornerWidget(self, mode="tr")
        
        self.bar_anim = QPropertyAnimation(self, b"geometry")
        self.bar_anim.setDuration(250)
        self.bar_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        threading.Thread(target=self._init_brightness, daemon=True).start()
        self.init_ui()

        self.fs_timer = QTimer(self)
        self.fs_timer.timeout.connect(self.check_fullscreen)
        self.fs_timer.start(500)
        QTimer.singleShot(0, self.check_fullscreen)

    def _init_brightness(self):
        try:
            out = subprocess.check_output(
                "powershell -NoProfile -Command \"(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness\"",
                shell=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            ).strip()
            if out.isdigit():
                self.current_brightness = int(out)
        except Exception:
            pass

    def check_fullscreen(self):
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        geo = self.screen().geometry()
        
        # Check if any window is maximized on this screen
        is_maximized = is_any_window_maximized_on_screen(self.winId())
        
        from config import load_config
        config = load_config()
        popup_style = config.get("style", {}).get("popup_style", "popup")
        
        if popup_style in ["edgeBox", "edgeCurve"]:
            is_maximized = True

        
        is_fs = False
        if hwnd:
            rect = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            is_fs = (
                rect.left <= geo.left() and
                rect.top <= geo.top() and
                rect.right >= geo.right() and
                rect.bottom >= geo.bottom()
            )
            buf = ctypes.create_string_buffer(256)
            ctypes.windll.user32.GetClassNameA(hwnd, buf, 256)
            class_name = buf.value.decode("utf-8")
            if class_name in ("Progman", "WorkerW"):
                is_fs = False
                
            title_buf = ctypes.create_string_buffer(512)
            ctypes.windll.user32.GetWindowTextA(hwnd, title_buf, 512)
            title_name = title_buf.value.decode("utf-8", errors="ignore")
                
            # Snipping Tool cloaks underlying windows, causing false floating state. Freeze state!
            is_snipping = False
            if class_name in ("ScreenClippingHostWindow", "SnippingTool", "Windows.UI.Core.CoreWindow"):
                is_snipping = True
            elif "Snipping Tool" in title_name or "Screen Snipping" in title_name or "Screen clipping" in title_name:
                is_snipping = True
                
            if is_snipping:
                is_fs = False
                self._snipping_active = True
                if hasattr(self, '_last_max_state') and self._last_max_state is not None:
                    is_maximized = self._last_max_state
            else:
                if getattr(self, '_snipping_active', False):
                    self._snipping_active = False
                    self._last_max_state = None # Force a hard refresh of geometry and DWM attributes!
                    
        if is_fs and not self.is_hidden_for_fullscreen:
            self.hide()
            self.is_hidden_for_fullscreen = True
            return
        elif not is_fs and self.is_hidden_for_fullscreen:
            self.show()
            self.is_hidden_for_fullscreen = False
            # Force a hard refresh of DWM attributes because Windows 11 ruins them on show()
            self._last_max_state = None
            
        self.set_maximized_style(is_maximized)

    def set_maximized_style(self, is_maximized):
        if not self.appbar:
            return
            
        geo = self.screen().geometry()
            
        if hasattr(self, '_last_max_state') and self._last_max_state == is_maximized:
            # Failsafe: Windows or interrupted animations might leave a 1px gap. Enforce it!
            from config import load_config
            config = load_config()
            position = config.get("general", {}).get("position", "top").lower()
            
            if is_maximized:
                if position == "left":
                    expected_geo = QRect(geo.x(), geo.y(), 54, geo.height())
                else:
                    expected_geo = QRect(geo.x(), geo.y(), geo.width(), self.bar_height)
                    
                if self.geometry() != expected_geo:
                    self.setGeometry(expected_geo)
            else:
                gap_x = 10
                gap_y = 6
                if position == "left":
                    expected_geo = QRect(geo.x() + gap_x, geo.y() + gap_y, 54, geo.height() - (gap_y * 2))
                else:
                    expected_geo = QRect(geo.x() + gap_x, geo.y() + gap_y, geo.width() - (gap_x * 2), self.bar_height)
                    
                if self.geometry() != expected_geo:
                    self.setGeometry(expected_geo)
            return
            
        self.bar_anim.stop()
        first_run = (self._last_max_state is None)
        self._last_max_state = is_maximized
        
        from config import load_config
        config = load_config()
        position = config.get("general", {}).get("position", "top").lower()
        is_vertical = position in ["left", "right"]

        if is_maximized:
            # Touch edges (no gap)
            if position == "left":
                target_x = geo.x()
                target_y = geo.y()
                target_w = self.bar_height
                target_h = geo.height()
            elif position == "right":
                target_x = geo.x() + geo.width() - self.bar_height
                target_y = geo.y()
                target_w = self.bar_height
                target_h = geo.height()
            else:
                target_x = geo.x()
                target_y = geo.y()
                target_w = geo.width()
                target_h = self.bar_height
            
            # Corner radius 0 (DWMWCP_DONOTROUND = 1)
            val = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 33, ctypes.byref(val), ctypes.sizeof(val))
            
            self.appbar.height = self.bar_height # Width is used in ABE_LEFT/RIGHT internally as height in AppBar API
            self.appbar.set_pos()
            
            popup_style = config.get("style", {}).get("popup_style", "popup")
            
            if popup_style == "edgeCurve":
                if self.position == "top":
                    self.left_corner.set_mode("tl")
                    self.right_corner.set_mode("tr")
                    self.left_corner.setGeometry(target_x, target_y + target_h, 12, 12)
                    self.right_corner.setGeometry(target_x + target_w - 12, target_y + target_h, 12, 12)
                elif self.position == "bottom":
                    self.left_corner.set_mode("bl")
                    self.right_corner.set_mode("br")
                    self.left_corner.setGeometry(target_x, target_y - 12, 12, 12)
                    self.right_corner.setGeometry(target_x + target_w - 12, target_y - 12, 12, 12)
                elif self.position == "left":
                    self.left_corner.set_mode("tl")
                    self.right_corner.set_mode("bl")
                    actual_w = self.geometry().width()
                    self.left_corner.setGeometry(target_x + actual_w, target_y, 12, 12)
                    self.right_corner.setGeometry(target_x + actual_w, target_y + target_h - 12, 12, 12)
                elif self.position == "right":
                    self.left_corner.set_mode("tr")
                    self.right_corner.set_mode("br")
                    actual_w = self.geometry().width()
                    actual_x = self.geometry().x()
                    self.left_corner.setGeometry(actual_x - 12, target_y, 12, 12)
                    self.right_corner.setGeometry(actual_x - 12, target_y + target_h - 12, 12, 12)
                
                self.left_corner.show()
                self.right_corner.show()
                self.left_corner.raise_()
                self.right_corner.raise_()
            else:
                self.left_corner.hide()
                self.right_corner.hide()
            
            if first_run:
                self.setGeometry(target_x, target_y, target_w, target_h)
            else:
                self.bar_anim.setStartValue(self.geometry())
                self.bar_anim.setEndValue(QRect(target_x, target_y, target_w, target_h))
                self.bar_anim.start()
        else:
            # Floating form (maintain gap)
            self.left_corner.hide()
            self.right_corner.hide()
            
            gap_x = 10
            gap_y = 6
            if position == "left":
                target_x = geo.x() + gap_x
                target_y = geo.y() + gap_y
                target_w = self.bar_height
                target_h = geo.height() - (gap_y * 2)
            elif position == "right":
                target_x = geo.x() + geo.width() - self.bar_height - gap_x
                target_y = geo.y() + gap_y
                target_w = self.bar_height
                target_h = geo.height() - (gap_y * 2)
            else:
                target_x = geo.x() + gap_x
                target_y = geo.y() + gap_y
                target_w = geo.width() - (gap_x * 2)
                target_h = self.bar_height
            
            # Corner radius rounded (DWMWCP_ROUND = 2)
            val = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 33, ctypes.byref(val), ctypes.sizeof(val))
            
            self.appbar.height = self.bar_height
            self.appbar.set_pos()
            
            if first_run:
                self.setGeometry(target_x, target_y, target_w, target_h)
            else:
                self.bar_anim.setStartValue(self.geometry())
                self.bar_anim.setEndValue(QRect(target_x, target_y, target_w, target_h))
                self.bar_anim.start()

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        central = QWidget()
        central.setObjectName("main-window")
        self.setCentralWidget(central)

        config = load_config()
        self.position = config.get("general", {}).get("position", "top").lower()
        self.is_vertical = self.position in ["left", "right"]
        
        # We use a graphics view to rotate the entire bar if vertical
        if self.is_vertical:
            from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsProxyWidget
            self.view = QGraphicsView(central)
            self.view.setFrameShape(QFrame.Shape.NoFrame)
            self.view.setStyleSheet("background: transparent;")
            self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.scene = QGraphicsScene(self.view)
            self.view.setScene(self.scene)
            
            # The actual content widget
            self.content_widget = QWidget()
            self.proxy = self.scene.addWidget(self.content_widget)
            
            # Rotate proxy
            if self.position == "left":
                self.proxy.setRotation(-90)
            elif self.position == "right":
                self.proxy.setRotation(90)
                
            self.main_layout = QGridLayout(self.content_widget)
            
            view_layout = QVBoxLayout(central)
            view_layout.setContentsMargins(0, 0, 0, 0)
            view_layout.addWidget(self.view)
        else:
            self.main_layout = QGridLayout(central)
            self.content_widget = central

        self.main_layout.setContentsMargins(5, 0, 5, 0)

        # Widget mapping
        # Note: AppLauncher requires a bit of special handling because it has a trigger widget.
        self.app_launcher = AppLauncherWidget()
        
        from taskbar import TaskbarTriggerWidget
        WIDGET_MAP = {
            "clock": ClockWidget,
            "workspaces": WorkspacesWidget,
            "launcher": lambda: AppLauncherTriggerWidget(self.app_launcher),
            "media": MediaWidget,
            "system-monitor": SystemMonitorWidget,
            "modules-right": ModulesRightWidget,
            "taskbar": TaskbarTriggerWidget
        }

        # Dynamically load modules function
        def populate_layout(layout, module_list):
            for mod_name in module_list:
                if self.is_vertical and mod_name == "taskbar":
                    continue
                if mod_name in WIDGET_MAP:
                    widget_instance = WIDGET_MAP[mod_name]()
                    # Save reference dynamically so things like `self.modules_right.update_volume_status()` still work if it exists
                    var_name = mod_name.replace("-", "_")
                    setattr(self, var_name, widget_instance)
                    layout.addWidget(widget_instance)

        # Left modules
        left_container = QWidget()
        left_layout = QHBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(15)
        populate_layout(left_layout, config.get("layout", {}).get("modules-left", []))
        left_layout.addStretch()
        self.main_layout.addWidget(left_container, 0, 0, alignment=Qt.AlignmentFlag.AlignLeft)

        # Center modules
        center_container = QWidget()
        center_layout = QHBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(5)
        populate_layout(center_layout, config.get("layout", {}).get("modules-center", []))
        self.main_layout.addWidget(center_container, 0, 1, alignment=Qt.AlignmentFlag.AlignCenter)

        # Right modules
        right_container = QWidget()
        right_layout = QHBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        populate_layout(right_layout, config.get("layout", {}).get("modules-right", []))
        self.main_layout.addWidget(right_container, 0, 2, alignment=Qt.AlignmentFlag.AlignRight)

    def contextMenuEvent(self, event):
        from config import load_config, save_config
        config = load_config()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {palette['bg']};
                color: {palette['text']};
                border: 1px solid {palette['separator']};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 24px 6px 16px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {palette['accent_hover']};
            }}
            QMenu::separator {{
                height: 1px;
                background: {palette['separator']};
                margin: 4px 8px;
            }}
        """)

        displays_menu = menu.addMenu("Displays")
        primary_name = QApplication.primaryScreen().name()
        display_actions = []
        for screen in QApplication.screens():
            name = screen.name()
            act = displays_menu.addAction(name)
            act.setCheckable(True)
            if name == primary_name:
                act.setChecked(True)
                act.setEnabled(False)
            else:
                act.setChecked(name in config.get("displays", {}).get("enabled_monitors", []))
            display_actions.append((act, name))

        menu.addSeparator()
        
        position_menu = menu.addMenu("Position")
        pos_top_act = position_menu.addAction("Top")
        pos_top_act.setCheckable(True)
        pos_left_act = position_menu.addAction("Left")
        pos_left_act.setCheckable(True)
        
        current_pos = config.get("general", {}).get("position", "top").title()
        if current_pos == "Left":
            pos_left_act.setChecked(True)
        else:
            pos_top_act.setChecked(True)

        style_menu = menu.addMenu("Style")
        style_popup_act = style_menu.addAction("popup")
        style_popup_act.setCheckable(True)
        style_edgebox_act = style_menu.addAction("edgeBox")
        style_edgebox_act.setCheckable(True)
        style_edgecurve_act = style_menu.addAction("edgeCurve")
        style_edgecurve_act.setCheckable(True)
        
        current_style = config.get("style", {}).get("popup_style", "popup")
        if current_style == "edgeBox":
            style_edgebox_act.setChecked(True)
        elif current_style == "edgeCurve":
            style_edgecurve_act.setChecked(True)
        else:
            style_popup_act.setChecked(True)

        menu.addSeparator()

        startup_action = menu.addAction("Launch at startup")
        startup_action.setCheckable(True)
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, "WaybarWin")
            startup_action.setChecked(True)
            winreg.CloseKey(key)
        except OSError:
            startup_action.setChecked(False)

        menu.addSeparator()
        
        open_config_action = menu.addAction("Open Configuration")
        restore_defaults_action = menu.addAction("Restore Defaults")

        menu.addSeparator()
        quit_action = menu.addAction("Quit")

        chosen = menu.exec(event.globalPos())

        if chosen in [a for a, _ in display_actions]:
            for a, name in display_actions:
                if chosen == a:
                    displays = config.setdefault("displays", {})
                    monitors = displays.setdefault("enabled_monitors", [])
                    if a.isChecked() and name not in monitors:
                        monitors.append(name)
                    elif not a.isChecked() and name in monitors:
                        monitors.remove(name)
                    save_config(config)
                    self.display_toggled.emit(name, a.isChecked())
        elif chosen == pos_top_act:
            config.setdefault("general", {})["position"] = "top"
            save_config(config)
            self.restart_app()
        elif chosen == pos_left_act:
            config.setdefault("general", {})["position"] = "left"
            save_config(config)
            self.restart_app()
        elif chosen == style_popup_act:
            config.setdefault("style", {})["popup_style"] = "popup"
            save_config(config)
            self.apply_style_live()
        elif chosen == style_edgebox_act:
            config.setdefault("style", {})["popup_style"] = "edgeBox"
            save_config(config)
            self.apply_style_live()
        elif chosen == style_edgecurve_act:
            config.setdefault("style", {})["popup_style"] = "edgeCurve"
            save_config(config)
            self.apply_style_live()
        elif chosen == startup_action:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE)
                if startup_action.isChecked():
                    if getattr(sys, "frozen", False):
                        exe = f'"{sys.executable}"'
                    else:
                        pythonw = sys.executable.replace("python.exe", "pythonw.exe")
                        exe = f'"{pythonw}" "{os.path.abspath("main.py")}"'
                    winreg.SetValueEx(key, "WaybarWin", 0, winreg.REG_SZ, exe)
                else:
                    winreg.DeleteValue(key, "WaybarWin")
                winreg.CloseKey(key)
            except OSError:
                pass
        elif chosen == open_config_action:
            from config import CONFIG_FILE
            import subprocess
            if sys.platform == "win32":
                os.startfile(CONFIG_FILE)
            else:
                subprocess.Popen(['xdg-open', CONFIG_FILE])
        elif chosen == restore_defaults_action:
            from config import restore_defaults
            restore_defaults()
            # Restart to apply defaults
            import subprocess
            if getattr(sys, "frozen", False):
                subprocess.Popen([sys.executable])
            else:
                subprocess.Popen([sys.executable] + sys.argv)
            QApplication.quit()
        elif chosen == quit_action:
            QApplication.quit()


    def restart_app(self):
        import subprocess
        import sys
        if getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable])
        else:
            subprocess.Popen([sys.executable] + sys.argv)
        QApplication.quit()

    def apply_style_live(self):
        from theme import get_theme
        global palette, theme_stylesheet
        palette, theme_stylesheet = get_theme()
        
        # Apply updated stylesheet globally
        QApplication.instance().setStyleSheet(theme_stylesheet)
        
        # Update blur and trigger repaints for all windows
        is_light = (palette.get("name") == "Light")
        for widget in QApplication.topLevelWidgets():
            # Skip corner wedges because disabling blur destroys their WA_TranslucentBackground
            if widget.inherits("CornerWidget"):
                widget.update()
                continue
                
            if hasattr(widget, 'winId'):
                # Force blur on AppLauncher
                force = widget.inherits("AppLauncherWidget")
                enable_acrylic_blur(widget.winId(), is_light, force=force)
            widget.update()
            
        # Force geometry to update (add/remove gaps and corners)
        self._last_max_state = None
        self.check_fullscreen()

    def showEvent(self, event):
        is_light = (palette.get("name") == "Light")
        enable_acrylic_blur(self.winId(), is_light)
        super().showEvent(event)
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'is_vertical') and self.is_vertical:
            if self.position == "left":
                self.content_widget.setFixedSize(self.height(), self.width())
                self.proxy.setPos(0, self.height())
            elif self.position == "right":
                self.content_widget.setFixedSize(self.height(), self.width())
                self.proxy.setPos(self.width(), 0)
            self.scene.setSceneRect(0, 0, self.width(), self.height())

    def wheelEvent(self, event):
        x = event.position().x()
        delta = event.angleDelta().y()
        if delta == 0:
            return

        if x < self.width() / 2:
            # Left side: Brightness adjust
            step = 5 if delta > 0 else -5
            self.current_brightness = max(0, min(100, self.current_brightness + step))
            val = self.current_brightness
            def run():
                subprocess.run(
                    f"powershell -NoProfile -Command \"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {val})\"",
                    shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            threading.Thread(target=run, daemon=True).start()
        else:
            # Right side: Volume adjust
            VK_VOLUME_UP = 0xAF
            VK_VOLUME_DOWN = 0xAE
            key = VK_VOLUME_UP if delta > 0 else VK_VOLUME_DOWN
            ctypes.windll.user32.keybd_event(key, 0, 0, 0)
            ctypes.windll.user32.keybd_event(key, 0, 2, 0)
            if hasattr(self, 'modules_right'):
                self.modules_right.update_volume_status()

        super().wheelEvent(event)
