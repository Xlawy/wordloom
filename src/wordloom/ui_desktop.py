from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                              QFormLayout, QLabel, QLineEdit)
from .desktop import DesktopError, DesktopSettings


class DesktopDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle('外观与快捷键 · 语笺')
        self.resize(560, 300)
        form = QFormLayout(self)
        self.theme = QComboBox()
        for name, value in [('跟随系统', 'system'), ('浅色', 'light'), ('深色', 'dark')]:
            self.theme.addItem(name, value)
        self.theme.setCurrentIndex(self.theme.findData(owner.desktop_settings.theme))
        self.enabled = QCheckBox('启用 Windows 全局快捷键')
        supported = owner.hotkeys.backend.available
        self.enabled.setChecked(owner.desktop_settings.hotkey_enabled and supported)
        self.enabled.setEnabled(supported)
        self.shortcut = QLineEdit(owner.desktop_settings.toggle_hotkey)
        self.shortcut.setEnabled(supported)
        self.shortcut.setPlaceholderText('Ctrl+Alt+W')
        form.addRow('外观', self.theme)
        form.addRow(self.enabled)
        form.addRow('唤起 / 隐藏', self.shortcut)
        self.selection_enabled = QCheckBox('启用选词翻译快捷键')
        self.selection_enabled.setChecked(owner.desktop_settings.selection_enabled and supported and owner.selection_backend.available)
        self.selection_enabled.setEnabled(supported and owner.selection_backend.available)
        self.selection_shortcut = QLineEdit(owner.desktop_settings.selection_hotkey)
        self.selection_shortcut.setEnabled(supported and owner.selection_backend.available)
        form.addRow(self.selection_enabled)
        form.addRow('选中文字后翻译', self.selection_shortcut)
        selection_note = QLabel('选词使用 Windows UI Automation，不改变剪贴板。触发后把所选文字发送到当前翻译模型；不支持的控件请手动复制粘贴。')
        selection_note.setWordWrap(True)
        form.addRow(selection_note)
        hint = QLabel('前台主窗口按快捷键隐藏；隐藏、最小化或在后台时唤起。\n支持 Ctrl/Alt/Shift/Win + 字母、数字或功能键；关闭窗口仍退出程序。'
                      if supported else owner.hotkeys.backend.reason)
        hint.setWordWrap(True)
        form.addRow(hint)
        self.error = QLabel()
        self.error.setWordWrap(True)
        form.addRow(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def save(self):
        settings = DesktopSettings(self.theme.currentData(), self.enabled.isChecked(), self.shortcut.text(),
                                   self.selection_enabled.isChecked(), self.selection_shortcut.text())
        try:
            self.owner.hotkeys.configure(settings, lambda: self.owner.desktop_store.save(settings))
        except (DesktopError, OSError) as exc:
            self.error.setText(str(exc) if isinstance(exc, DesktopError) else '设置无法保存，请检查数据目录权限；原快捷键仍有效。')
            return
        self.owner.desktop_settings = settings
        self.owner.theme.apply(settings.theme)
        self.owner.hotkey_status()
        self.accept()
