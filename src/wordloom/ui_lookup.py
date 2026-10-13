"""Non-modal pointer card, reusing the model and library services."""
from copy import deepcopy
import sqlite3
from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit,
                              QPushButton, QTextEdit, QVBoxLayout)
from .jobs import Job
from .library import LibraryError
from .network import Client
from .platforms.credentials import CredentialError
from .platforms.pointer import create_pointer
from .providers import ApiError


def popup_position(point, size, bounds):
    x, y = point.x() + 16, point.y() + 24
    if x + size.width() > bounds.right() + 1:
        x = point.x() - size.width() - 16
    if y + size.height() > bounds.bottom() + 1:
        y = point.y() - size.height() - 16
    return QPoint(max(bounds.left(), min(x, bounds.right() + 1 - size.width())),
                  max(bounds.top(), min(y, bounds.bottom() + 1 - size.height())))


class LookupPopup(QDialog):
    dismissed = Signal()
    translate_requested = Signal()
    save_requested = Signal()
    edit_main_requested = Signal()
    edited = Signal()

    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('指针释义 · 语笺')
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setModal(False)
        self.resize(440, 520)
        self._updating = False
        layout = QVBoxLayout(self)
        self.word = QLineEdit()
        self.word.setPlaceholderText('指针下的单词')
        self.word.textEdited.connect(self.edited)
        layout.addWidget(self.word)
        self.source = QLabel()
        self.source.setTextFormat(Qt.TextFormat.PlainText)
        self.source.setWordWrap(True)
        layout.addWidget(self.source)
        self.context = QTextEdit()
        self.context.setAcceptRichText(False)
        self.context.setPlaceholderText('原文上下文（可修正）')
        self.context.setMaximumHeight(115)
        self.context.textChanged.connect(self.context_edited)
        layout.addWidget(self.context)
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setAcceptRichText(False)
        self.result.setPlaceholderText('释义将在此显示…')
        layout.addWidget(self.result, 1)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.translate_button = QPushButton('重新释义')
        self.translate_button.clicked.connect(self.translate_requested)
        self.save_button = QPushButton('保存生词')
        self.save_button.clicked.connect(self.save_requested)
        self.copy_button = QPushButton('复制释义')
        self.copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.result.toPlainText()))
        for widget in (self.translate_button, self.save_button, self.copy_button):
            row.addWidget(widget)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.main_button = QPushButton('打开工作台 / 粘贴')
        self.main_button.clicked.connect(self.edit_main_requested)
        row.addWidget(self.main_button)
        self.close_button = QPushButton('关闭 / 取消')
        self.close_button.clicked.connect(self.close)
        row.addWidget(self.close_button)
        layout.addLayout(row)

    def context_edited(self):
        if not self._updating:
            self.edited.emit()

    def set_input(self, word='', context='', source=''):
        self._updating = True
        self.word.setText(word)
        self.context.setPlainText(context)
        self._updating = False
        self.result.clear()
        self.source.setText(source)
        self.save_button.setEnabled(False)

    def set_busy(self, busy):
        self.word.setEnabled(not busy)
        self.context.setEnabled(not busy)
        self.translate_button.setEnabled(not busy)
        self.main_button.setEnabled(not busy)
        if busy:
            self.save_button.setEnabled(False)

    def show_at(self, point):
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        bounds = screen.availableGeometry().adjusted(8, 8, -8, -8)
        self.resize(min(440, bounds.width()), min(520, bounds.height()))
        self.move(popup_position(point, self.size(), bounds))
        self.show()  # WA_ShowWithoutActivating keeps the reader's foreground window.

    def closeEvent(self, event):
        self.dismissed.emit()
        event.accept()

    def reject(self):
        # QDialog's Escape path otherwise bypasses closeEvent and leaves I/O alive.
        self.close()


class PointerController(QObject):
    def __init__(self, owner, backend=None):
        super().__init__(owner)
        self.owner = owner
        self.backend = backend or create_pointer()
        self.popup = LookupPopup(owner)
        self.capture_job = self.model_job = None
        self.target = None
        self.anchor = QPoint()
        self.snapshot = self.completion = None
        self.silent = False
        self.closed = False
        self.popup.dismissed.connect(self.stop)
        self.popup.translate_requested.connect(self.translate)
        self.popup.save_requested.connect(self.save)
        self.popup.edit_main_requested.connect(self.open_main)
        self.popup.edited.connect(self.invalidate)
        if self.backend.available:
            self.backend.warmup()

    def stop(self):
        self.silent = True
        if self.capture_job and self.capture_job.active:
            self.capture_job.cancel()
            self.backend.cancel()
        if self.model_job and self.model_job.active:
            self.model_job.cancel()
        self.silent = False
        self.popup.set_busy(False)

    def close(self):
        self.closed = True
        self.stop()
        self.backend.close()
        self.popup.hide()

    def invalidate(self):
        self.completion = None
        self.popup.save_button.setEnabled(False)
        self.popup.status.setText('内容已修改，请重新释义后保存。')

    def trigger(self):
        if self.closed:
            return
        if QApplication.instance().activeModalWidget():
            self.owner.statusBar().showMessage('请先关闭设置，再指向原文取词。')
            return
        self.stop()
        self.popup.hide()  # Never let the lookup card contaminate a local OCR capture.
        self.anchor = QCursor.pos()
        self.snapshot = self.completion = None
        self.popup.set_input()
        if not self.backend.available:
            self.fail('unsupported', self.backend.reason)
            return
        try:
            self.target = self.backend.capture_target()
        except ApiError as exc:
            self.fail(exc.code, str(exc))
            return
        target = self.target
        use_ocr = self.owner.desktop_settings.pointer_ocr
        self.popup.set_busy(True)
        self.capture_job = Job(lambda token, progress: self.backend.read(target, token, use_ocr, progress), 11, self)
        self.capture_job.progress.connect(self.popup.status.setText)
        self.capture_job.success.connect(self.captured)
        self.capture_job.failure.connect(self.fail)
        self.capture_job.start()

    def captured(self, result):
        if self.closed:
            return
        if not self.backend.is_current(self.target):
            self.fail('changed', '目标窗口已变化，本次未发送。请重新指向取词。')
            return
        label = '文本接口 · 段落上下文' if result.source == 'uia' else '本机 OCR · 邻近行上下文（可修正）；截图未上传'
        self.popup.set_input(result.word, result.context, label)
        self.popup.set_busy(False)
        self.popup.show_at(self.anchor)
        self.translate()

    def translate(self):
        if self.closed or (self.model_job and self.model_job.active):
            return
        word, context = self.popup.word.text().strip(), self.popup.context.toPlainText().strip()
        try:
            if not word or len(word) > 128 or len(context) > 4000:
                raise ValueError('请输入 1–128 字符的词语，上下文最多 4000 字符。')
            profile = deepcopy(self.owner.settings.active())
            if profile is None:
                raise ValueError('请到工作台设置文本翻译 API；已识别的单词和上下文保留在此。')
            profile.validate()
            key = self.owner.credentials.get(profile.credential_id)
        except (ValueError, CredentialError) as exc:
            self.fail('configuration', str(exc))
            return
        self.snapshot = (profile, word, context)
        self.completion = None
        self.popup.result.clear()
        self.popup.status.setText('正在结合上下文释义…关闭浮窗可取消。')
        self.popup.set_busy(True)
        self.model_job = Job(lambda token, progress: Client().complete(profile, key, word, context, 'explain',
                                        cancellation=token, on_text=progress), profile.timeout, self)
        self.model_job.progress.connect(self.popup.result.setPlainText)
        self.model_job.success.connect(self.completed)
        self.model_job.failure.connect(self.fail)
        self.model_job.start()

    def completed(self, result):
        if self.closed:
            return
        self.completion = result
        self.popup.result.setPlainText(result.text)
        self.popup.status.setText('输出达到长度上限，可能不完整。可调整配置后重试。' if result.finish_reason == 'length' else '已完成，可核对后保存到词库。')
        self.popup.set_busy(False)
        self.popup.save_button.setEnabled(True)

    def fail(self, code, message):
        if self.silent or self.closed:
            return
        self.completion = None
        self.popup.set_busy(False)
        self.popup.save_button.setEnabled(False)
        self.popup.status.setText(message)
        self.popup.show_at(self.anchor)

    def save(self):
        if not self.completion or not self.snapshot:
            return
        profile, word, context = self.snapshot
        try:
            self.owner.library.add(word, context, self.completion.text, profile.model)
        except (LibraryError, sqlite3.Error) as exc:
            self.popup.status.setText(str(exc) if isinstance(exc, LibraryError) else '词库保存失败，请检查数据目录。')
            return
        self.owner.refresh_library()
        self.owner.refresh_review()
        self.popup.save_button.setEnabled(False)
        self.popup.status.setText('已保存单词、上下文和释义，已加入复习。')

    def open_main(self):
        if (self.owner.job and self.owner.job.active) or (self.owner.selection_job and self.owner.selection_job.active):
            self.popup.status.setText('工作台正在处理请求，请先完成或取消。')
            return
        self.owner.input.setPlainText(self.popup.word.text())
        self.owner.context.setPlainText(self.popup.context.toPlainText())
        self.owner.completed_request = self.owner.last_request = None
        self.owner.result.clear()
        self.owner.save_button.setEnabled(False)
        self.owner.retry_button.setEnabled(False)
        self.owner.request_status.setText('来自指针取词；可修正文字或手动粘贴后处理。')
        self.owner.reveal_translation()
        self.popup.close()
