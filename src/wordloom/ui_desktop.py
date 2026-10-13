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
        self.selection_enabled = QCheckBox('启用取词快捷键')
        self.selection_enabled.setChecked(owner.desktop_settings.selection_enabled and supported and (owner.selection_backend.available or owner.pointer_lookup.backend.available))
        self.selection_enabled.setEnabled(supported and (owner.selection_backend.available or owner.pointer_lookup.backend.available))
        self.selection_shortcut = QLineEdit(owner.desktop_settings.selection_hotkey)
        self.selection_shortcut.setEnabled(supported and (owner.selection_backend.available or owner.pointer_lookup.backend.available))
        form.addRow(self.selection_enabled)
        form.addRow('取词快捷键', self.selection_shortcut)
        self.lookup_mode = QComboBox()
        self.lookup_mode.addItem('鼠标指向单词后按快捷键（无需选中，浮窗显示）', 'pointer')
        self.lookup_mode.addItem('读取已选择的文字（旧方式）', 'selection')
        self.lookup_mode.setCurrentIndex(self.lookup_mode.findData(owner.desktop_settings.lookup_mode))
        self.pointer_ocr = QCheckBox('文字接口失败时使用 Windows 本机 OCR（不上传截图）')
        self.pointer_ocr.setChecked(owner.desktop_settings.pointer_ocr)
        self.pointer_ocr.setEnabled(owner.pointer_lookup.backend.available)
        form.addRow('取词方式', self.lookup_mode)
        form.addRow(self.pointer_ocr)
        selection_note = QLabel('指针方式读取鼠标下单词与上下文，在旁边浮窗释义，可修正并保存。按快捷键才取词；不需要先选中，不会改动剪贴板。识别后的文字发送到当前翻译模型。')
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
                                   self.selection_enabled.isChecked(), self.selection_shortcut.text(),
                                   self.lookup_mode.currentData(), self.pointer_ocr.isChecked())
        try:
            self.owner.hotkeys.configure(settings, lambda: self.owner.desktop_store.save(settings))
        except (DesktopError, OSError) as exc:
            self.error.setText(str(exc) if isinstance(exc, DesktopError) else '设置无法保存，请检查数据目录权限；原快捷键仍有效。')
            return
        self.owner.desktop_settings = settings
        self.owner.theme.apply(settings.theme)
        self.owner.hotkey_status()
        self.accept()
