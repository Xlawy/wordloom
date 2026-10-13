from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QScrollArea
from wordloom.config import ConfigStore, Settings
from wordloom.platforms.credentials import Credentials
from wordloom.theme import Theme
from wordloom.ui_settings import SettingsDialog


def luminance(color):
    rgb = [v / 255 for v in (color.red(), color.green(), color.blue())]
    rgb = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
    return sum(v * w for v, w in zip(rgb, (.2126, .7152, .0722)))


class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.theme = Theme(cls.app)

    def test_api_dialog_light_dark_and_live_switch(self):
        with TemporaryDirectory() as directory:
            dialog = SettingsDialog(ConfigStore(Path(directory)), Settings(), Credentials())
            dialog.show()
            try:
                for mode in ('dark', 'light', 'dark'):
                    self.theme.apply(mode)
                    self.app.processEvents()
                    scroll = dialog.findChild(QScrollArea)
                    for widget, bg, fg in [(scroll.widget(), QPalette.Window, QPalette.WindowText),
                                           (dialog.url, QPalette.Base, QPalette.Text),
                                           (dialog.model.view(), QPalette.Base, QPalette.Text),
                                           (dialog.list, QPalette.Base, QPalette.Text)]:
                        for group in (QPalette.Active, QPalette.Inactive):
                            colors = [luminance(widget.palette().color(group, role)) for role in (bg, fg)]
                            self.assertGreater((max(colors) + .05) / (min(colors) + .05), 4.5)
                    self.assertEqual(scroll.widget().palette().color(QPalette.Window).lightness() < 128, mode == 'dark')
                    self.assertFalse(dialog.grab().isNull())
            finally:
                dialog.dirty = False
                dialog.close()
                self.theme.apply('system')
