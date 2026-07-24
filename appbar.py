import ctypes
import ctypes.wintypes
from typing import Optional

# Windows API constants
ABM_NEW = 0x00000000
ABM_REMOVE = 0x00000001
ABM_QUERYPOS = 0x00000002
ABM_SETPOS = 0x00000003
ABM_GETSTATE = 0x00000004
ABM_GETTASKBARPOS = 0x00000005
ABM_ACTIVATE = 0x00000006
ABM_GETAUTOHIDEBAR = 0x00000007
ABM_SETAUTOHIDEBAR = 0x00000008
ABM_WINDOWPOSCHANGED = 0x00000009
ABM_SETSTATE = 0x0000000A

ABE_LEFT = 0
ABE_TOP = 1
ABE_RIGHT = 2
ABE_BOTTOM = 3

class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("hWnd", ctypes.wintypes.HWND),
        ("uCallbackMessage", ctypes.wintypes.UINT),
        ("uEdge", ctypes.wintypes.UINT),
        ("rc", ctypes.wintypes.RECT),
        ("lParam", ctypes.wintypes.LPARAM),
    ]

shell32 = ctypes.windll.shell32
user32 = ctypes.windll.user32

class AppBar:
    def __init__(self, hwnd: int, x: int, y: int, width: int, height: int, edge: int = ABE_TOP):
        self.hwnd = hwnd
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.edge = edge
        self.registered = False

    def register(self):
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = self.hwnd
        
        # Register the appbar
        if not shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd)):
            print("Failed to register AppBar")
            return False
            
        self.registered = True
        self.set_pos()
        return True

    def set_pos(self):
        if not self.registered:
            return

        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = self.hwnd
        abd.uEdge = self.edge

        # Set the bounding rect for the edge
        if self.edge == ABE_TOP:
            abd.rc.left = self.x
            abd.rc.top = self.y
            abd.rc.right = self.x + self.width
            abd.rc.bottom = self.y + self.height
        # Add logic for other edges if needed

        # Query the system to adjust the rectangle to avoid overlapping
        shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))

        # Update the rect after query
        if self.edge == ABE_TOP:
            abd.rc.bottom = abd.rc.top + self.height

        # Set the new position
        shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))

        # Actually move the window
        user32.MoveWindow(self.hwnd, abd.rc.left, abd.rc.top, abd.rc.right - abd.rc.left, abd.rc.bottom - abd.rc.top, True)

    def unregister(self):
        if not self.registered:
            return

        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = self.hwnd
        shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd))
        self.registered = False
