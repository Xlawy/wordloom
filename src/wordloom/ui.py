from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QSplitter,
    QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget, QComboBox,
    QFileDialog, QAbstractItemView)

from .config import ConfigStore, Settings
from .jobs import Job
from .library import Entry, Library, LibraryError
from .network import Client
from .platforms.credentials import CredentialError, Credentials
from .ui_settings import SettingsDialog
from .desktop import DesktopStore, DesktopSettings, DesktopError, HotkeyController
from .platforms.hotkeys import create_hotkeys
from .theme import Theme
from .ui_desktop import DesktopDialog





def text_edit(placeholder="", readonly=False):
    edit = QTextEdit()
    edit.setAcceptRichText(False)
    edit.setReadOnly(readonly)
    edit.setPlaceholderText(placeholder)
    return edit


class EntryEditor(QDialog):
    def __init__(self, entry: Entry, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑词条")
        self.resize(630, 600)
        form = QFormLayout(self)
        self.text = text_edit()
        self.context = text_edit()
        self.meaning = text_edit()
        for name, edit, value in [("词语 / 原文", self.text, entry.text), ("上下文", self.context, entry.context), ("释义", self.meaning, entry.meaning)]:
            edit.setPlainText(value)
            form.addRow(name, edit)
        self.error = QLabel()
        self.error.setWordWrap(True)
        form.addRow(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def accept(self):
        from .library import validate_text
        try:
            validate_text(self.text.toPlainText(), self.context.toPlainText(), self.meaning.toPlainText())
        except LibraryError as exc:
            self.error.setText(str(exc))
            return
        super().accept()


class MainWindow(QMainWindow):
    def __init__(self, store: ConfigStore, settings: Settings, library: Library, credentials: Credentials):
        super().__init__()
        self.store, self.settings, self.library, self.credentials = store, settings, library, credentials
        self.job = None
        self.last_request = None
        self.completed_request = None
        self.review_card = None
        self.setWindowTitle("语笺 WordLoom")
        self.resize(1100, 800)
        self.setMinimumSize(820, 600)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 18, 24, 18)
        self.setCentralWidget(root)
        header = QHBoxLayout()
        title = QLabel("语笺  WordLoom")
        title.setObjectName("brand")
        header.addWidget(title)
        header.addStretch()
        self.desktop_button = QPushButton("外观与快捷键")
        self.desktop_button.clicked.connect(self.open_desktop_settings)
        header.addWidget(self.desktop_button)
        self.settings_button = QPushButton("模型与 API 设置")
        self.settings_button.clicked.connect(self.open_settings)
        header.addWidget(self.settings_button)
        layout.addLayout(header)
        subtitle = QLabel("把阅读中的发现，留下来慢慢学。  ·  本地词库 / 自选模型")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.make_translate_page()
        self.make_library_page()
        self.make_review_page()
        self.tabs.currentChanged.connect(self.tab_changed)
        self.statusBar().showMessage("词库保存在本机。仅点击请求时，将输入发送到您选择的模型服务。")
        self.shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.shortcut.activated.connect(self.translate)
        self.refresh_profiles()
        self.refresh_library()
        self.refresh_review()
        self.setup_desktop()

    def setup_desktop(self):
        app = QApplication.instance()
        self.theme = getattr(app, 'wordloom_theme', None) or Theme(app)
        self.desktop_store = DesktopStore(self.store.path.parent)
        load_error = ''
        try:
            self.desktop_settings = self.desktop_store.load()
        except (DesktopError, OSError):
            self.desktop_settings = DesktopSettings(hotkey_enabled=False)
            load_error = '外观/快捷键配置无法读取，原文件已保留；请打开外观与快捷键设置检查。'
        self.theme.apply(self.desktop_settings.theme)
        self.hotkeys = HotkeyController(create_hotkeys(), self.toggle_window)
        app.aboutToQuit.connect(self.hotkeys.close)
        try:
            if self.hotkeys.backend.available:
                self.hotkeys.configure(self.desktop_settings)
            self.hotkey_status()
        except DesktopError as exc:
            self.statusBar().showMessage(str(exc))
        if load_error:
            self.statusBar().showMessage(load_error)

    def hotkey_status(self):
        if self.hotkeys.current:
            self.statusBar().showMessage('全局快捷键：' + self.hotkeys.current[1] + ' · 前台隐藏，否则唤起；关闭窗口退出。')
        elif not self.hotkeys.backend.available:
            self.statusBar().showMessage(self.hotkeys.backend.reason)
        else:
            self.statusBar().showMessage('全局快捷键未启用。可在“外观与快捷键”中设置。')

    def open_desktop_settings(self):
        DesktopDialog(self).exec()

    def toggle_window(self):
        app = QApplication.instance()
        modal = app.activeModalWidget()
        if modal:
            modal.show()
            modal.raise_()
            modal.activateWindow()
            return
        if self.isVisible() and not self.isMinimized() and self.isActiveWindow():
            self.hide()
            return
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()
        if self.hotkeys.backend.available:
            self.hotkeys.backend.api.foreground(int(self.winId()))
        self.tabs.setCurrentIndex(0)
        self.input.setFocus()

    def make_translate_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        top = QHBoxLayout()
        top.addWidget(QLabel("翻译配置"))
        self.profiles = QComboBox()
        self.profiles.setMinimumWidth(200)
        self.profiles.currentIndexChanged.connect(self.select_profile)
        top.addWidget(self.profiles, 1)
        self.mode = QComboBox()
        for title, value in [("翻译", "translate"), ("释义与用法", "explain"), ("生成例句", "examples")]:
            self.mode.addItem(title, value)
        top.addWidget(self.mode)
        layout.addLayout(top)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        input_box, output_box = QWidget(), QWidget()
        left, right = QVBoxLayout(input_box), QVBoxLayout(output_box)
        left.addWidget(QLabel("原文"))
        self.input = text_edit("输入或粘贴单词、句子或短文…")
        self.input.setObjectName("sourceText")
        left.addWidget(self.input, 3)
        left.addWidget(QLabel("上下文（可选）"))
        self.context = text_edit("原文所在的句子或阅读背景，有助于模型判断含义。")
        self.context.setObjectName("sourceContext")
        left.addWidget(self.context, 2)
        paste = QPushButton("粘贴剪贴板文本")
        paste.clicked.connect(lambda: self.input.setPlainText(QApplication.clipboard().text()))
        left.addWidget(paste)
        right.addWidget(QLabel("模型结果"))
        self.result = text_edit("配置好 API 后即可开始。词库和复习无需联网。", True)
        self.result.setObjectName("modelResult")
        right.addWidget(self.result, 1)
        self.result_info = QLabel("结果由您选择的模型生成，请核对后收藏。")
        self.result_info.setWordWrap(True)
        right.addWidget(self.result_info)
        copy = QPushButton("复制结果")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.result.toPlainText()))
        right.addWidget(copy)
        splitter.addWidget(input_box)
        splitter.addWidget(output_box)
        splitter.setSizes([450, 500])
        layout.addWidget(splitter, 1)
        actions = QHBoxLayout()
        self.translate_button = QPushButton("开始处理  Ctrl+Enter")
        self.translate_button.setObjectName("primary")
        self.translate_button.clicked.connect(self.translate)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.cancel_request)
        self.cancel_button.setEnabled(False)
        self.retry_button = QPushButton("重试上次请求")
        self.retry_button.setEnabled(False)
        self.retry_button.clicked.connect(lambda: self.translate(retry=True))
        for b in (self.translate_button, self.cancel_button, self.retry_button):
            actions.addWidget(b)
        layout.addLayout(actions)
        self.request_status = QLabel("尚未发送请求。")
        self.request_status.setObjectName("requestStatus")
        self.request_status.setWordWrap(True)
        layout.addWidget(self.request_status)
        save_row = QHBoxLayout()
        save_row.addWidget(QLabel("收藏词语 / 原文"))
        self.save_text = QLineEdit()
        self.save_text.setPlaceholderText("可将短文中的一个词作为词条；完整原文保留在上下文中")
        save_row.addWidget(self.save_text, 1)
        self.save_button = QPushButton("保存到词库")
        self.save_button.setObjectName("saveEntry")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_entry)
        save_row.addWidget(self.save_button)
        layout.addLayout(save_row)
        self.tabs.addTab(page, "翻译工作台")

    def refresh_profiles(self):
        self.profiles.blockSignals(True)
        self.profiles.clear()
        for p in self.settings.profiles:
            if p.purpose == "translation":
                self.profiles.addItem(f"{p.name} · {p.model}", p.id)
        active = self.settings.active()
        if active:
            self.profiles.setCurrentIndex(self.profiles.findData(active.id))
        self.profiles.blockSignals(False)
        if self.profiles.count() == 0:
            self.request_status.setText("先打开“模型与 API 设置”创建翻译配置。您仍可离线浏览和复习词库。")

    def select_profile(self, index):
        if index < 0:
            return
        old = self.settings.active_translation
        self.settings.active_translation = self.profiles.itemData(index)
        try:
            self.store.save(self.settings)
        except (OSError, ValueError):
            self.settings.active_translation = old
            self.refresh_profiles()
            self.request_status.setText("当前配置选择未能保存，请检查数据目录。")

    def open_settings(self):
        dialog = SettingsDialog(self.store, self.settings, self.credentials, self)
        dialog.exec()
        if dialog.saved:
            self.settings = dialog.settings
            self.refresh_profiles()

    def translate(self, checked=False, *, retry=False):
        if self.job and self.job.active:
            return
        try:
            if retry and self.last_request:
                profile, text, context, mode = deepcopy(self.last_request)
            else:
                profile = self.settings.active()
                if profile is None:
                    self.request_status.setText("请先创建并选择一个文本翻译配置。")
                    return
                profile = deepcopy(profile)
                text, context, mode = self.input.toPlainText().strip(), self.context.toPlainText().strip(), self.mode.currentData()
            profile.validate()
            if not text:
                self.request_status.setText("请输入原文。")
                return
            key = self.credentials.get(profile.credential_id)
        except (CredentialError, ValueError) as exc:
            self.request_status.setText(str(exc))
            return
        self.last_request = (profile, text, context, mode)
        self.completed_request = None
        self.result.clear()
        self.save_text.setText(text)
        self.save_button.setEnabled(False)
        self.request_status.setText("正在请求模型…可随时取消。")
        self.result_info.setText(f"{profile.name} / {profile.model} · 请求中")
        self.set_request_busy(True)
        self.job = Job(lambda token, progress: Client().complete(profile, key, text, context, mode,
                       cancellation=token, on_text=progress), profile.timeout, self)
        self.job.progress.connect(self.result.setPlainText)
        self.job.success.connect(self.translation_done)
        self.job.failure.connect(self.translation_failed)
        self.job.start()

    def set_request_busy(self, busy):
        for widget in (self.input, self.context, self.profiles, self.mode, self.settings_button, self.translate_button):
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.retry_button.setEnabled(not busy and self.last_request is not None)

    def translation_done(self, completion):
        self.set_request_busy(False)
        self.result.setPlainText(completion.text)
        self.completed_request = deepcopy(self.last_request)
        profile = self.completed_request[0]
        self.result_info.setText(f"{profile.name} / {profile.model} · 已完成")
        self.request_status.setText("结果达到输出长度上限，可能不完整。可调整参数后重新请求。" if completion.finish_reason == "length" else "已完成。核对释义后可保存到本地词库。")
        self.save_button.setEnabled(True)

    def translation_failed(self, code, message):
        self.set_request_busy(False)
        self.completed_request = None
        self.save_button.setEnabled(False)
        self.request_status.setText(message)
        self.result_info.setText("未完成 · 部分内容仅供查看，未保存")

    def cancel_request(self):
        if self.job and self.job.active:
            self.job.cancel()

    def save_entry(self):
        if self.completed_request is None:
            return
        profile, original, context, mode = self.completed_request
        text = self.save_text.text().strip()
        if text != original:
            context = original + ("\n\n" + context if context else "")
        try:
            self.library.add(text, context, self.result.toPlainText(), profile.model)
            self.request_status.setText("已保存到词库，已加入到期复习。")
            self.save_button.setEnabled(False)
            self.refresh_library()
            self.refresh_review()
        except (LibraryError, sqlite3.Error) as exc:
            self.request_status.setText(str(exc) if isinstance(exc, LibraryError) else "词库写入失败，请检查数据目录权限和磁盘空间。")

    def make_library_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("librarySearch")
        self.search.setPlaceholderText("搜索原文、上下文或释义…")
        self.search.textChanged.connect(self.refresh_library)
        row.addWidget(self.search, 1)
        for title, callback in [("导入", self.import_library), ("导出", self.export_library)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.table = QTableWidget(0, 4)
        self.table.setObjectName("libraryTable")
        self.table.setHorizontalHeaderLabels(["词语 / 原文", "释义预览", "下次复习", "已练习"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(2, 155)
        self.table.itemSelectionChanged.connect(self.show_selected_entry)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit_entry())
        layout.addWidget(self.table, 2)
        self.entry_detail = text_edit("选择一个词条查看完整原文、上下文和释义。", True)
        layout.addWidget(self.entry_detail, 1)
        row = QHBoxLayout()
        self.library_status = QLabel()
        row.addWidget(self.library_status, 1)
        for title, callback in [("编辑", self.edit_entry), ("删除", self.delete_entry)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.tabs.addTab(page, "我的词库")

    def refresh_library(self, *_):
        try:
            rows = self.library.search(self.search.text())
        except sqlite3.Error:
            self.library_status.setText("词库读取失败。")
            return
        self.table.setRowCount(0)
        self.entry_detail.clear()
        for e in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, text in enumerate((e.text.replace("\n", " ")[:120], e.meaning.replace("\n", " ")[:140], format_time(e.due), str(e.repetitions))):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, e.id)
                self.table.setItem(row, col, item)
        self.library_status.setText(f"{len(rows)} 个词条 · 双击编辑")

    def selected_entry(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return self.library.get(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def show_selected_entry(self):
        e = self.selected_entry()
        if e:
            self.entry_detail.setPlainText(f"{e.text}\n\n上下文\n{e.context or '（无）'}\n\n释义\n{e.meaning}\n\n模型：{e.model or '手动导入'}")

    def edit_entry(self):
        entry = self.selected_entry()
        if not entry:
            self.library_status.setText("请先选择词条。")
            return
        dialog = EntryEditor(entry, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.library.update(entry.id, dialog.text.toPlainText(), dialog.context.toPlainText(), dialog.meaning.toPlainText(), expected_revision=entry.revision)
                self.refresh_library()
                self.refresh_review()
            except (LibraryError, sqlite3.Error) as exc:
                self.library_status.setText(str(exc) if isinstance(exc, LibraryError) else "词条修改失败。")

    def delete_entry(self):
        entry = self.selected_entry()
        if not entry:
            return
        if QMessageBox.question(self, "删除词条", "删除所选词条及其复习记录？") == QMessageBox.StandardButton.Yes:
            try:
                self.library.delete(entry.id)
                self.refresh_library()
                self.refresh_review()
            except sqlite3.Error:
                self.library_status.setText("删除失败，请检查词库。")

    def import_library(self):
        name, _ = QFileDialog.getOpenFileName(self, "导入 WordLoom 词库", "", "词库 (*.json *.csv)")
        if name:
            try:
                added, skipped = self.library.import_file(Path(name))
                self.refresh_library()
                self.refresh_review()
                self.library_status.setText(f"导入 {added} 条，跳过 {skipped} 条重复记录。")
            except (LibraryError, OSError, sqlite3.Error) as exc:
                self.library_status.setText(str(exc) if isinstance(exc, LibraryError) else "文件读取或词库写入失败。")

    def export_library(self):
        name, selected = QFileDialog.getSaveFileName(self, "导出全部词库", "wordloom-library.json", "JSON 含复习进度 (*.json);;CSV 仅词条 (*.csv)")
        if name:
            path = Path(name)
            if not path.suffix:
                path = path.with_suffix(".csv" if selected.startswith("CSV") else ".json")
            try:
                count = self.library.export_file(path)
                self.library_status.setText(f"已导出全部 {count} 个词条。模型配置和密钥不包含在导出中。")
            except (LibraryError, OSError, sqlite3.Error) as exc:
                self.library_status.setText(str(exc) if isinstance(exc, LibraryError) else "导出写入失败。")

    def make_review_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.review_status = QLabel()
        layout.addWidget(self.review_status)
        self.question = text_edit("还没有到期词条。先翻译并保存一些单词。", True)
        self.question.setObjectName("reviewQuestion")
        layout.addWidget(self.question, 1)
        self.answer = text_edit("先回想含义，再显示答案。", True)
        self.answer.setObjectName("reviewAnswer")
        layout.addWidget(self.answer, 1)
        self.reveal_button = QPushButton("显示答案")
        self.reveal_button.setObjectName("revealAnswer")
        self.reveal_button.clicked.connect(self.reveal)
        layout.addWidget(self.reveal_button)
        row = QHBoxLayout()
        self.grade_buttons = []
        for title, grade in [("没记住 · 10 分钟后", "again"), ("有点难 · 较短间隔", "hard"), ("记住了 · 延长间隔", "good")]:
            button = QPushButton(title)
            button.setObjectName("grade_" + grade)
            button.clicked.connect(lambda checked=False, g=grade: self.rate(g))
            self.grade_buttons.append(button)
            row.addWidget(button)
        layout.addLayout(row)
        refresh = QPushButton("刷新到期列表")
        refresh.clicked.connect(self.refresh_review)
        layout.addWidget(refresh)
        note = QLabel("每次评分即时保存在本机。简单间隔算法：首次记住 1 天，之后约 ×2.2；有点难约 ×1.2；没记住 10 分钟。")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs.addTab(page, "每日复习")

    def refresh_review(self):
        try:
            cards = self.library.due_entries()
        except sqlite3.Error:
            self.review_status.setText("复习列表读取失败。")
            return
        self.review_card = cards[0] if cards else None
        self.review_status.setText(f"当前到期 {len(cards)} 个词条。" if cards else "当前已完成，稍后可刷新查看新到期的词条。")
        self.answer.clear()
        for button in self.grade_buttons:
            button.setEnabled(False)
        self.reveal_button.setEnabled(bool(cards))
        self.question.setPlainText((self.review_card.text + "\n\n" + self.review_card.context) if cards else "暂时没有到期词条。词库始终可以离线查看。")

    def reveal(self):
        if self.review_card:
            self.answer.setPlainText(self.review_card.meaning)
            for button in self.grade_buttons:
                button.setEnabled(True)

    def rate(self, grade):
        if not self.review_card or not self.answer.toPlainText():
            return
        card = self.review_card
        try:
            self.library.review(card.id, grade, expected_revision=card.revision)
            self.refresh_review()
            self.refresh_library()
        except (LibraryError, sqlite3.Error) as exc:
            self.refresh_review()
            self.review_status.setText(str(exc) if isinstance(exc, LibraryError) else "评分保存失败，请重试。")

    def tab_changed(self, index):
        if index == 1:
            self.refresh_library()
        elif index == 2:
            self.refresh_review()

    def closeEvent(self, event):
        self.hotkeys.close()
        self.cancel_request()
        self.credentials.clear_session()
        event.accept()


def format_time(value):
    try:
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return "远期"
