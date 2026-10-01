import PyInstaller.__main__
import os

if __name__ == "__main__":
    PyInstaller.__main__.run([
        'main.py',
        '--name=WaybarWin',
        '--onefile',
        '--windowed',
        '--noconsole',
        '--add-data=waguri.mp4;.',
        '--version-file=version_info.txt',
        '--clean',
        '-y'
    ])
