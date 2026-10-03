import sys
import ctypes
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase
from bar import WaybarWindow

from config import load_config

class WindowManager:
    def __init__(self, app):
        self.app = app
        self.windows = {}
        self.config = load_config()
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
            if name == primary_name or name in self.config.get("displays", {}).get("enabled_monitors", []):
                self.spawn_window(screen)
                
    def spawn_window(self, screen):
        name = screen.name()
        if name in self.windows:
            return
            
        win = WaybarWindow(screen_name=name)
        # Position on the correct screen
        geom = screen.geometry()
        
        position = self.config.get("general", {}).get("position", "top").lower()
        if position == "left":
            # Vertical layout with rotated text forces a minimum width of ~54px
            actual_width = 54
            win.setGeometry(geom.x(), geom.y(), actual_width, geom.height())
            from appbar import AppBar, ABE_LEFT
            if not win.appbar:
                win.appbar = AppBar(int(win.winId()), geom.x(), geom.y(), actual_width, geom.height(), ABE_LEFT)
                win.appbar.register()
        else: # top
            win.setGeometry(geom.x(), geom.y(), geom.width(), win.bar_height)
            from appbar import AppBar, ABE_TOP
            if not win.appbar:
                win.appbar = AppBar(int(win.winId()), geom.x(), geom.y(), geom.width(), win.bar_height, ABE_TOP)
                win.appbar.register()
            
        win.display_toggled.connect(self.on_display_toggled)
        win.show()
        self.windows[name] = win
        
    def destroy_window(self, name):
        if name in self.windows:
            win = self.windows.pop(name)
            
            # Unregister from Windows Desktop Appbar
            if hasattr(win, 'appbar') and win.appbar:
                win.appbar.unregister()
                
            # Stop timers and animations
            if hasattr(win, 'fs_timer'):
                win.fs_timer.stop()
            if hasattr(win, 'bar_anim'):
                win.bar_anim.stop()
                
            # Close corners which might be floating top-level tool windows
            if hasattr(win, 'left_corner'):
                win.left_corner.close()
            if hasattr(win, 'right_corner'):
                win.right_corner.close()
                
            win.close()
            win.deleteLater()
            
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