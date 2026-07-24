import sys
import ctypes
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase
from bar import WaybarWindow

from PyQt6.QtCore import QSettings

class WindowManager:
    def __init__(self, app):
        self.app = app
        self.windows = {}
        self.settings = QSettings("WaybarWin", "Settings")
        
        # Load dynamic stylesheet
        from theme import get_theme
        self.palette, stylesheet = get_theme()
        self.app.setStyleSheet(stylesheet)
            
        self.init_windows()
        
    def init_windows(self):
        screens = self.app.screens()
        primary_name = self.app.primaryScreen().name()
        
        for screen in screens:
            name = screen.name()
            # Primary always shown. Others based on settings
            if name == primary_name or self.settings.value(f"displays/{name}", False, type=bool):
                self.spawn_window(screen)
                
    def spawn_window(self, screen):
        name = screen.name()
        if name in self.windows:
            return
            
        win = WaybarWindow(screen_name=name)
        # Position on the correct screen
        geom = screen.geometry()
        win.setGeometry(geom.x(), geom.y(), geom.width(), win.bar_height)
        
        # Register AppBar on the correct screen
        if not win.appbar:
            from appbar import AppBar, ABE_TOP
            win.appbar = AppBar(int(win.winId()), geom.x(), geom.y(), geom.width(), win.bar_height, ABE_TOP)
            win.appbar.register()
            
        win.display_toggled.connect(self.on_display_toggled)
        win.show()
        self.windows[name] = win
        
    def destroy_window(self, name):
        if name in self.windows:
            win = self.windows.pop(name)
            win.close()
            
    def on_display_toggled(self, name, is_enabled):
        if is_enabled:
            for s in self.app.screens():
                if s.name() == name:
                    self.spawn_window(s)
                    break
        else:
            self.destroy_window(name)

def main():
    app = QApplication(sys.argv)
    manager = WindowManager(app)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()