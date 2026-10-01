import ctypes
from ctypes import wintypes
import psutil
import time

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QFrame, QLabel, QPushButton, QScrollArea
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QFileInfo, QTimer, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QRect
from PyQt6.QtGui import QPainter, QPainterPath, QPen, QColor, QRegion
from PyQt6.QtWidgets import QFileIconProvider

from theme import get_theme, hex_to_qcolor
SEG = "font-family: 'Segoe MDL2 Assets';"

palette, _ = get_theme()
user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

class TaskbarFetcherThread(QThread):
    apps_updated = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self._is_running = True
        self._last_hwnds = set()

    def stop(self):
        self._is_running = False

    def run(self):
        while self._is_running:
            apps = []
            hwnds_this_tick = set()

            def enum_cb(hwnd, lparam):
                if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
                    ex_style = user32.GetWindowLongW(hwnd, -20) # GWL_EXSTYLE
                    # Filter out tool windows unless they are also app windows
                    if ex_style & 0x00000080 and not (ex_style & 0x00040000):
                        return True
                        
                    length = user32.GetWindowTextLengthW(hwnd)
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value
                    
                    if title in ["Program Manager", "Settings", "Microsoft Text Input Application"]:
                        return True
                        
                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    
                    try:
                        exe_path = psutil.Process(pid.value).exe()
                        if exe_path and "waybarwin.exe" not in exe_path.lower():
                            hwnds_this_tick.add(hwnd)
                            apps.append({
                                "hwnd": hwnd,
                                "title": title,
                                "exe": exe_path
                            })
                    except Exception:
                        pass
                return True

            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            
            # Deduplicate by exe path to keep it tidy, keeping the first (top-most) window
            seen_exes = set()
            unique_apps = []
            for app in apps:
                if app["exe"] not in seen_exes:
                    seen_exes.add(app["exe"])
                    unique_apps.append(app)

            current_state = [app["hwnd"] for app in unique_apps]
            if current_state != getattr(self, "_last_state", []):
                self._last_state = current_state
                self.apps_updated.emit(unique_apps)

            time.sleep(1.5)

class HorizontalScrollArea(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFrameStyle(0)
        self.setViewportMargins(0, 0, 0, 0)
        self.setStyleSheet("background: transparent; border: none; margin: 0px; padding: 0px;")
        
    def wheelEvent(self, event):
        h_bar = self.horizontalScrollBar()
        delta = event.angleDelta().y()
        
        if not hasattr(self, '_anim'):
            self._anim = QPropertyAnimation(h_bar, b"value")
            self._anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            self._anim.setDuration(250)
            
        current_target = self._anim.endValue() if self._anim.state() == QPropertyAnimation.State.Running else h_bar.value()
        target = current_target - delta
        
        # Clamp to bounds
        target = max(h_bar.minimum(), min(target, h_bar.maximum()))
        
        self._anim.stop()
        self._anim.setStartValue(h_bar.value())
        self._anim.setEndValue(target)
        self._anim.start()

class TaskbarPopupWidget(QWidget):
    def __init__(self, owner=None):
        super().__init__(owner)
        self.owner = owner
        self.setWindowFlags(
            Qt.WindowType.ToolTip | 
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 4, 12, 4)
        self.main_layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
        
        self.card = QFrame()
        self.card.setObjectName("media-popup-container") # Reuse acrylic styling
        self.card.setStyleSheet(f"""
            #media-popup-container {{
                background-color: transparent;
                border: none;
            }}
            QPushButton {{
                background-color: transparent;
                border-radius: 8px;
                padding: 4px;
            }}
            QPushButton:hover {{
                background-color: {palette['accent_hover']};
            }}
        """)
        
        self.card_layout = QHBoxLayout(self.card)
        self.card_layout.setContentsMargins(10, 4, 10, 4)
        self.card_layout.setSpacing(10)
        
        self.scroll_area = HorizontalScrollArea()
        self.scroll_area.setFixedHeight(32)
        self.scroll_area.setWidget(self.card)
        
        self.main_layout.addWidget(self.scroll_area)
        self.icon_provider = QFileIconProvider()
        
    def showEvent(self, event):
        from PyQt6.QtCore import QSettings
        settings = QSettings("WaybarWin", "Settings")
        popup_style = settings.value("popup_style", "popup", type=str)
        
        if popup_style != "edgeBox":
            try:
                from bar import enable_acrylic_blur
                enable_acrylic_blur(int(self.winId()), palette["name"] == "Light")
            except Exception:
                pass
                
        self.wave_timer = QTimer(self)
        self.wave_timer.timeout.connect(self.update_wave)
        self.wave_timer.start(16) # ~60 FPS physics tick
        
        super().showEvent(event)

    def hideEvent(self, event):
        if hasattr(self, 'wave_timer'):
            self.wave_timer.stop()
            self.wave_timer.deleteLater()
            del self.wave_timer
        super().hideEvent(event)

    def update_wave(self):
        from PyQt6.QtGui import QCursor
        from PyQt6.QtCore import QSize
        import math
        
        mouse_pos = QCursor.pos()
        card_pos = self.card.mapFromGlobal(mouse_pos)
        popup_pos = self.mapFromGlobal(mouse_pos)
        
        # Determine if mouse is near the visible dock bounds
        is_hovered = self.rect().adjusted(-30, -30, 30, 30).contains(popup_pos)
        
        for i in range(self.card_layout.count()):
            item = self.card_layout.itemAt(i)
            if not item: continue
            btn = item.widget()
            if not btn: continue
            
            target_size = 24.0
            if is_hovered:
                # Use logical, unscaled positions to prevent jitter during layout updates
                # Base button width is 24, spacing is 10, margin is 10
                logical_center_x = 10 + (i * 34) + 12 
                dist = abs(card_pos.x() - logical_center_x)
                
                if dist < 80:
                    # Apply a smooth cosine wave (max size 30px, base size 24px)
                    target_size = 24.0 + 6.0 * math.cos((dist / 80.0) * (math.pi / 2))
            
            # Physics-based smooth interpolation (spring-like easing)
            current_size = float(btn.property("curr_size") or 24.0)
            new_size = current_size + (target_size - current_size) * 0.3
            
            if abs(new_size - target_size) < 0.1:
                new_size = target_size
                
            btn.setProperty("curr_size", new_size)
            
            if int(new_size) != btn.width():
                btn.setFixedSize(int(new_size), int(new_size))
                
                # Qt QSize needs integers
                icon_size = int(new_size * 0.8)
                btn.setIconSize(QSize(icon_size, icon_size))

    def update_apps(self, apps):
        # Clear existing
        for i in reversed(range(self.card_layout.count())): 
            widget_to_remove = self.card_layout.itemAt(i).widget()
            self.card_layout.removeWidget(widget_to_remove)
            widget_to_remove.setParent(None)

        # Add new icons
        for app in apps:
            btn = QPushButton()
            btn.setFixedSize(24, 24)
            icon = self.icon_provider.icon(QFileInfo(app["exe"]))
            btn.setIcon(icon)
            btn.setIconSize(btn.size() * 0.8)
            btn.setToolTip(app["title"])
            
            hwnd = app["hwnd"]
            btn.clicked.connect(lambda checked, h=hwnd: self.focus_window(h))
            
            self.card_layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignBottom)
            
        # Calculate optimal width (show max 7 apps before scrolling)
        app_count = len(apps)
        if app_count > 0:
            visible_apps = min(app_count, 7)
            # 24px base per button + spacing + margin, PLUS 12 extra px reserved for the smaller expanded wave
            desired_width = (visible_apps * 24) + ((visible_apps - 1) * 10) + 20 + 12
            self.scroll_area.setFixedWidth(desired_width)
        else:
            self.scroll_area.setFixedWidth(44)

    def focus_window(self, hwnd):
        # Bring window to front
        user32.ShowWindow(hwnd, 9) # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        self.hide()
        
    def wheelEvent(self, event):
        # Intercept any mouse scroll anywhere on this popup pill
        # and directly forward it to the internal horizontal scroll area!
        if hasattr(self, 'scroll_area'):
            self.scroll_area.wheelEvent(event)
            event.accept()
        else:
            super().wheelEvent(event)
    def paintEvent(self, event):
        from PyQt6.QtCore import QSettings
        settings = QSettings("WaybarWin", "Settings")
        popup_style = settings.value("popup_style", "popup", type=str)
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if popup_style in ["edgeBox", "edgeCurve"]:
            bg_color = QColor(0, 0, 0, 255)
            border_color = QColor(45, 45, 45, 255)
        else:
            if palette["name"] == "Dark":
                bg_color = QColor(20, 20, 20, 130)
                border_color = QColor(255, 255, 255, 25)
            else:
                bg_color = QColor(240, 240, 240, 130)
                border_color = QColor(0, 0, 0, 30)
                
        r = self.rect().adjusted(0, 0, -1, -1)
        path = QPainterPath()
        
        path.addRoundedRect(r.x(), r.y(), r.width(), r.height(), 12, 12)
            
        painter.fillPath(path, bg_color)
        
        painter.setPen(QPen(border_color, 1))
        painter.drawPath(path)

    def leaveEvent(self, event):
        QTimer.singleShot(100, self._check_hide)
        super().leaveEvent(event)

    def _check_hide(self):
        if not self.underMouse() and (not self.owner or not self.owner.underMouse()):
            if hasattr(self.owner, 'hide_popup'):
                self.owner.hide_popup()
            else:
                self.hide()

class TaskbarTriggerWidget(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("taskbar")
        self.setFixedSize(40, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.icon_label = QLabel(f'<span style="{SEG}">&#xE71D;</span>') # App switcher / Task View icon
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)
        
        self.popup = TaskbarPopupWidget(self)
        
        self.fetcher = TaskbarFetcherThread()
        self.fetcher.apps_updated.connect(self.popup.update_apps)
        self.fetcher.start()
        
        self._anim_group = QParallelAnimationGroup(self)

    def enterEvent(self, event):
        try:
            self._anim_group.finished.disconnect()
        except TypeError:
            pass
            
        if not self.popup.isVisible():
            global_center = self.mapToGlobal(self.rect().center())
            
            # Update geometry to get actual height before animation
            self.popup.adjustSize()
            popup_w = self.popup.width()
            popup_h = self.popup.height()

            target_x = global_center.x() - (popup_w // 2)
            
            # Float it perfectly below the bar
            target_y = self.window().geometry().bottom() + 5

            self._anim_group.clear()
            geom_anim = QPropertyAnimation(self.popup, b"geometry")
            geom_anim.setDuration(250)
            
            start_y = target_y - 15
            geom_anim.setStartValue(QRect(target_x, start_y, popup_w, popup_h))
            geom_anim.setEndValue(QRect(target_x, target_y, popup_w, popup_h))
            geom_anim.setEasingCurve(QEasingCurve.Type.OutBack)
            
            opacity_anim = QPropertyAnimation(self.popup, b"windowOpacity")
            opacity_anim.setDuration(200)
            opacity_anim.setStartValue(0.0)
            opacity_anim.setEndValue(1.0)
            
            self._anim_group.addAnimation(geom_anim)
            self._anim_group.addAnimation(opacity_anim)
            
            self.popup.show()
            self._anim_group.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        QTimer.singleShot(100, self._check_hide)
        super().leaveEvent(event)

    def _check_hide(self):
        if not self.underMouse() and not self.popup.underMouse():
            self.hide_popup()

    def hide_popup(self):
        if not self.popup.isVisible():
            return
            
        self._anim_group.clear()
        current_rect = self.popup.geometry()
        
        geom_anim = QPropertyAnimation(self.popup, b"geometry")
        geom_anim.setDuration(200)
        geom_anim.setStartValue(current_rect)
        # Match Media popup by sliding up and fading out
        geom_anim.setEndValue(QRect(current_rect.x(), current_rect.y() - 15, current_rect.width(), current_rect.height()))
        geom_anim.setEasingCurve(QEasingCurve.Type.InBack)
        
        opacity_anim = QPropertyAnimation(self.popup, b"windowOpacity")
        opacity_anim.setDuration(200)
        opacity_anim.setStartValue(self.popup.windowOpacity())
        opacity_anim.setEndValue(0.0)
        
        self._anim_group.addAnimation(geom_anim)
        self._anim_group.addAnimation(opacity_anim)
        self._anim_group.finished.connect(self.popup.hide)
        self._anim_group.start()
