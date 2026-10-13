"""One complete palette for every window, including dialogs and popup views."""
from pathlib import Path
from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QColor, QPalette


STYLE = """
QWidget { font-size: 14px; }
QLabel#brand { font-size: 25px; font-weight: 700; }
QLabel#subtitle { color: palette(placeholder-text); }
QPushButton { background: palette(button); color: palette(button-text); border: 1px solid palette(mid); padding: 8px 15px; border-radius: 6px; }
QPushButton:hover { border: 1px solid palette(highlight); }
QPushButton:disabled { color: palette(mid); }
QPushButton#primary { color: palette(highlighted-text); background: palette(highlight); font-weight: 600; }
QPushButton#primary:disabled { background: palette(button); color: palette(mid); }
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QAbstractItemView {
 background: palette(base); color: palette(text); border: 1px solid palette(mid); border-radius: 5px; padding: 6px;
 selection-background-color: palette(highlight); selection-color: palette(highlighted-text);
}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled { color: palette(placeholder-text); }
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 12px 26px; margin: 3px; border-radius: 5px; background: palette(button); color: palette(button-text); }
QTabBar::tab:selected { background: palette(highlight); color: palette(highlighted-text); }
QHeaderView::section { background: palette(button); color: palette(button-text); border: 0; padding: 8px; }
QToolTip { background: palette(tool-tip-base); color: palette(tool-tip-text); border: 1px solid palette(mid); }
"""


def palette_for(dark):
    p = QPalette()
    colors = {
        'Window': '#202725' if dark else '#f4f6f5',
        'WindowText': '#edf4f1' if dark else '#1c343c',
        'Base': '#141c19' if dark else '#ffffff',
        'AlternateBase': '#29332e' if dark else '#edf3f0',
        'Text': '#edf4f1' if dark else '#1c343c',
        'Button': '#34443b' if dark else '#e7eeec',
        'ButtonText': '#edf4f1' if dark else '#1c343c',
        'Highlight': '#90d5b5' if dark else '#246657',
        'HighlightedText': '#10281e' if dark else '#ffffff',
        'ToolTipBase': '#34443b' if dark else '#ffffff',
        'ToolTipText': '#edf4f1' if dark else '#1c343c',
        'PlaceholderText': '#b1c2b8' if dark else '#52676e',
        'Link': '#90d5b5' if dark else '#246657',
        'LinkVisited': '#ceafea' if dark else '#704080',
        'Light': '#56675e' if dark else '#ffffff',
        'Midlight': '#45574c' if dark else '#eef3f0',
        'Mid': '#718478' if dark else '#9bab9f',
        'Dark': '#0e1511' if dark else '#5c7064',
        'Shadow': '#000000',
        'BrightText': '#ffffff',
        'Accent': '#90d5b5' if dark else '#246657',
    }
    for role, color in colors.items():
        for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
            p.setColor(group, getattr(QPalette.ColorRole, role), QColor(color))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(colors['PlaceholderText']))
    return p


class Theme(QObject):
    def __init__(self, app, mode='system'):
        super().__init__(app)
        self.app, self.mode = app, mode
        app.wordloom_theme = self
        app.setStyle('Fusion')
        app.styleHints().colorSchemeChanged.connect(self.system_changed)
        self.apply(mode)

    def system_changed(self, scheme):
        # Qt emits before its own palette update. Reapply after that update.
        if self.mode == 'system':
            QTimer.singleShot(0, lambda: self.apply(self.mode))

    def apply(self, mode):
        if mode not in ('system', 'light', 'dark'):
            raise ValueError('未知外观模式')
        self.mode = mode
        dark = mode == 'dark' or (mode == 'system' and self.app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
        self.app.setPalette(palette_for(dark))
        resources = Path(__file__).with_name('resources')
        mode_name = 'dark' if dark else 'light'
        extra = "QSpinBox, QDoubleSpinBox { padding-right: 24px; }"
        for direction, position in [('up', 'top'), ('down', 'bottom')]:
            url = (resources / f'{direction}-{mode_name}.svg').as_posix()
            extra += f"QSpinBox::{direction}-button, QDoubleSpinBox::{direction}-button {{ subcontrol-origin: border; subcontrol-position: {position} right; width: 22px; background: palette(button); border: 1px solid palette(mid); }}"
            extra += f"QSpinBox::{direction}-arrow, QDoubleSpinBox::{direction}-arrow {{ image: url(\"{url}\"); width: 12px; height: 11px; }}"
        self.app.setStyleSheet(STYLE + extra)
