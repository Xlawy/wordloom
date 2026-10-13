from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from .config import ConfigError, ConfigStore, Profile, Settings
from .jobs import Job
from .network import Client
from .platforms.credentials import CredentialError, Credentials


class SettingsDialog(QDialog):
    def __init__(self, store: ConfigStore, settings: Settings, credentials: Credentials, parent=None):
        super().__init__(parent)
        self.setWindowTitle("模型与 API 设置 · 语笺")
        self.resize(900, 760)
        self.store, self.settings, self.credentials = store, deepcopy(settings), credentials
        self.current = Profile()
        self.job = None
        self.saved = False
        self.loading = False
        self.dirty = False
        layout = QVBoxLayout(self)
        note = QLabel("填写服务商提供的 Chat Completions 根地址。翻译与 OCR 分开配置；模型能力由服务商确认。")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        layout.addLayout(row, 1)
        left = QVBoxLayout()
        row.addLayout(left, 1)
        self.list = QListWidget()
        self.list.setMinimumWidth(190)
        self.list.currentRowChanged.connect(self.select_row)
        left.addWidget(self.list)
        new = QPushButton("新建配置")
        new.clicked.connect(self.new_profile)
        left.addWidget(new)
        delete = QPushButton("删除配置")
        delete.clicked.connect(self.delete_profile)
        left.addWidget(delete)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        scroll.setWidget(content)
        row.addWidget(scroll, 3)
        self.name = QLineEdit()
        self.name.setObjectName("profileName")
        self.purpose = QComboBox()
        self.purpose.addItem("文本翻译", "translation")
        self.purpose.addItem("OCR 图像识别（独立服务）", "ocr")
        self.protocol = QComboBox()
        self.protocol.addItem("OpenAI 兼容 · Chat Completions", "openai_chat")
        self.url = QLineEdit()
        self.url.setObjectName("baseUrl")
        self.url.setPlaceholderText("https://your-provider.example/v1")
        self.model = QComboBox()
        self.model.setObjectName("modelName")
        self.model.setEditable(True)
        self.model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.model.lineEdit().setPlaceholderText("手动输入模型 ID，或获取模型列表")
        self.key = QLineEdit()
        self.key.setObjectName("apiKey")
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("留空保留当前地址的密钥；新地址不会继承旧密钥")
        self.session = QCheckBox("新输入的 Key 仅本次会话使用")
        self.session.setChecked(not credentials.available)
        self.clear_key = QCheckBox("清除此配置当前地址的已保存密钥")
        self.key_status = QLabel("系统凭据库可用" if credentials.available else "当前宿主无受支持的系统凭据库；Key 仅保存在内存。")
        self.key_status.setWordWrap(True)
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 600)
        self.timeout.setSuffix(" 秒")
        self.temperature_on = QCheckBox("发送温度参数")
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0, 2)
        self.temperature.setSingleStep(0.1)
        self.tokens_on = QCheckBox("发送输出长度参数")
        self.tokens = QSpinBox()
        self.tokens.setRange(1, 131072)
        self.token_parameter = QComboBox()
        self.token_parameter.addItems(["max_tokens", "max_completion_tokens"])
        self.stream = QCheckBox("流式输出（服务不支持时关闭）")
        self.vision = QCheckBox("我已确认该 OCR 模型支持图像输入")
        self.active = QCheckBox("设为此用途的当前配置")
        for label, widget in [("配置名称", self.name), ("用途", self.purpose), ("协议", self.protocol),
            ("Base URL", self.url), ("模型", self.model), ("API Key", self.key), ("", self.session),
            ("", self.clear_key), ("", self.key_status), ("总超时", self.timeout), ("", self.temperature_on),
            ("温度", self.temperature), ("", self.tokens_on), ("输出长度", self.tokens), ("长度字段", self.token_parameter),
            ("", self.stream), ("", self.vision), ("", self.active)]:
            form.addRow(label, widget)
        tabs = QTabWidget()
        self.prompts = {}
        for key, title in [("translate", "翻译"), ("explain", "释义"), ("examples", "例句")]:
            edit = QTextEdit()
            edit.setAcceptRichText(False)
            edit.setMinimumHeight(120)
            self.prompts[key] = edit
            tabs.addTab(edit, title)
        form.addRow("提示词", tabs)
        help_text = QLabel("提示词作为 system 消息；原文和上下文单独发送。不要在提示词或普通字段中填写密钥。\n连接测试会发送少量测试文本，可能消耗服务额度；OCR 测试会发送自制测试图片。")
        help_text.setWordWrap(True)
        form.addRow(help_text)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        self.models_button = QPushButton("获取模型列表")
        self.test_button = QPushButton("测试连接")
        self.cancel_button = QPushButton("取消测试")
        self.cancel_button.setEnabled(False)
        self.save_button = QPushButton("保存配置")
        self.save_button.setObjectName("saveProfile")
        close = QPushButton("完成")
        for button in (self.models_button, self.test_button, self.cancel_button, self.save_button, close):
            buttons.addWidget(button)
        self.models_button.clicked.connect(lambda: self.request("models"))
        self.test_button.clicked.connect(lambda: self.request("test"))
        self.cancel_button.clicked.connect(self.cancel)
        self.save_button.clicked.connect(self.save_profile)
        close.clicked.connect(self.accept)
        self.temperature_on.toggled.connect(self.temperature.setEnabled)
        self.tokens_on.toggled.connect(self.tokens.setEnabled)
        for edit in (self.name, self.url, self.key):
            edit.textChanged.connect(self.mark_dirty)
        self.model.editTextChanged.connect(self.mark_dirty)
        for edit in self.prompts.values():
            edit.textChanged.connect(self.mark_dirty)
        for box in (self.purpose, self.token_parameter):
            box.currentIndexChanged.connect(self.mark_dirty)
        for box in (self.session, self.clear_key, self.temperature_on, self.tokens_on, self.stream, self.vision, self.active):
            box.toggled.connect(self.mark_dirty)
        for spin in (self.timeout, self.temperature, self.tokens):
            spin.valueChanged.connect(self.mark_dirty)
        self.refresh_list()
        if self.settings.profiles:
            self.list.setCurrentRow(0)
        else:
            self.load_profile(self.current)

    def mark_dirty(self, *_):
        if not self.loading:
            self.cancel()
            self.dirty = True

    def discard_changes(self):
        return not self.dirty or QMessageBox.question(self, "未保存的修改", "放弃当前尚未保存的配置修改？") == QMessageBox.StandardButton.Yes

    def refresh_list(self, selected=None):
        self.list.blockSignals(True)
        self.list.clear()
        for p in self.settings.profiles:
            self.list.addItem(("OCR · " if p.purpose == "ocr" else "翻译 · ") + p.name)
        if selected:
            self.list.setCurrentRow(next((i for i, p in enumerate(self.settings.profiles) if p.id == selected), -1))
        self.list.blockSignals(False)

    def load_profile(self, p):
        self.cancel()
        self.loading = True
        self.current = deepcopy(p)
        self.name.setText(p.name)
        self.purpose.setCurrentIndex(self.purpose.findData(p.purpose))
        self.url.setText(p.base_url)
        self.model.clear()
        self.model.setEditText(p.model)
        self.key.clear()
        self.clear_key.setChecked(False)
        self.timeout.setValue(int(p.timeout))
        self.temperature_on.setChecked(p.temperature is not None)
        self.temperature.setValue(p.temperature if p.temperature is not None else 0.3)
        self.temperature.setEnabled(p.temperature is not None)
        self.tokens_on.setChecked(p.max_tokens is not None)
        self.tokens.setValue(p.max_tokens or 2048)
        self.tokens.setEnabled(p.max_tokens is not None)
        self.token_parameter.setCurrentText(p.token_parameter)
        self.stream.setChecked(p.stream)
        self.vision.setChecked(p.vision)
        active = self.settings.active(p.purpose)
        self.active.setChecked(active is None or active.id == p.id)
        for name, edit in self.prompts.items():
            edit.setPlainText(p.prompts[name])
        self.status.setText("已载入配置；API Key 不在界面回显。")
        self.loading = False
        self.dirty = False

    def select_row(self, row):
        if 0 <= row < len(self.settings.profiles):
            if self.discard_changes():
                self.load_profile(self.settings.profiles[row])
            else:
                self.refresh_list(self.current.id)

    def new_profile(self):
        if self.discard_changes():
            self.refresh_list()
            self.load_profile(Profile())

    def form_profile(self, *, require_model=True):
        p = replace(self.current, name=self.name.text().strip(), purpose=self.purpose.currentData(),
            base_url=self.url.text().strip(), model=self.model.currentText().strip(), timeout=self.timeout.value(),
            temperature=self.temperature.value() if self.temperature_on.isChecked() else None,
            max_tokens=self.tokens.value() if self.tokens_on.isChecked() else None,
            token_parameter=self.token_parameter.currentText(), stream=self.stream.isChecked(), vision=self.vision.isChecked(),
            prompts={name: edit.toPlainText() for name, edit in self.prompts.items()})
        p.validate(require_model=require_model)
        return p

    def request_key(self, p):
        if self.clear_key.isChecked():
            return ""
        return self.key.text().strip() or self.credentials.get(p.credential_id)

    def save_profile(self):
        try:
            p = self.form_profile()
            key = self.request_key(p)
            if key and key in json.dumps(asdict(p), ensure_ascii=False):
                raise ConfigError("普通字段中包含当前 API Key，请移除后保存。")
            candidate = deepcopy(self.settings)
            candidate.upsert(p)
            if self.active.isChecked():
                setattr(candidate, "active_" + p.purpose, p.id)
            if self.clear_key.isChecked():
                self.credentials.delete(p.credential_id)
            elif self.key.text().strip():
                self.credentials.set(p.credential_id, key, session_only=self.session.isChecked())
            self.store.save(candidate)
            # Old origin credentials never migrate automatically to a changed endpoint.
            self.settings = candidate
            self.saved = True
            self.refresh_list(p.id)
            self.load_profile(p)
            self.status.setText("配置已保存。" + ("新 Key 仅在本次会话可用。" if key and self.session.isChecked() else ""))
            return True
        except (ConfigError, CredentialError, OSError) as exc:
            self.status.setText(str(exc) if not isinstance(exc, OSError) else "配置文件写入失败，请检查数据目录权限。")
            return False

    def delete_profile(self):
        old = next((p for p in self.settings.profiles if p.id == self.current.id), None)
        if old is None:
            return
        if QMessageBox.question(self, "删除配置", f"删除“{old.name}”及其当前地址的凭据？词库不会删除。") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.cancel()
            self.credentials.delete(old.credential_id)
            candidate = deepcopy(self.settings)
            candidate.remove(old.id)
            self.store.save(candidate)
            self.settings, self.saved = candidate, True
            self.dirty = False
            self.refresh_list()
            if candidate.profiles:
                self.list.setCurrentRow(0)
            else:
                self.load_profile(Profile())
        except (CredentialError, ConfigError, OSError):
            self.status.setText("删除未完成，请检查凭据库或数据目录后重试。")

    def request(self, kind):
        self.cancel()
        try:
            p = self.form_profile(require_model=kind != "models")
            key = self.request_key(p)
            if kind == "test" and p.purpose == "ocr" and not p.vision:
                raise ConfigError("OCR 测试前请确认模型支持图像。")
        except (ConfigError, CredentialError) as exc:
            self.status.setText(str(exc))
            return
        client = Client()
        if kind == "models":
            function = lambda token, progress: client.models(p, key, cancellation=token)
        elif p.purpose == "ocr":
            from PySide6.QtCore import QBuffer, QIODevice
            from PySide6.QtGui import QImage, QPainter, QColor
            image = QImage(160, 60, QImage.Format.Format_RGB32)
            image.fill(QColor("white"))
            painter = QPainter(image)
            painter.setPen(QColor("black"))
            painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, "WordLoom OCR 123")
            painter.end()
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buffer, "PNG")
            pixels = bytes(buffer.data())
            function = lambda token, progress: client.complete(p, key, "", image=pixels, cancellation=token)
        else:
            probe = replace(p, stream=False, max_tokens=min(p.max_tokens or 64, 64))
            function = lambda token, progress: client.complete(probe, key, "Hello", cancellation=token)
        self.status.setText("正在获取模型…" if kind == "models" else "正在发送连接测试…")
        self.set_busy(True)
        self.job = Job(function, p.timeout, self)
        self.job.success.connect(lambda result: self.request_done(kind, result))
        self.job.failure.connect(lambda code, message: self.request_failed(message))
        self.job.start()

    def set_busy(self, busy):
        for button in (self.models_button, self.test_button, self.save_button):
            button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    def request_done(self, kind, result):
        self.set_busy(False)
        if kind == "models":
            current = self.model.currentText()
            self.model.clear()
            self.model.addItems(result)
            if current:
                self.model.setEditText(current)
            self.status.setText(f"获取到 {len(result)} 个模型；列表不代表每个模型均支持图片或当前参数。")
        else:
            self.status.setText("连接成功：收到有效模型文本。请用实际任务确认质量与能力。")

    def request_failed(self, message):
        self.set_busy(False)
        self.status.setText(message)

    def cancel(self):
        if self.job and self.job.active:
            self.job.cancel()

    def done(self, result):
        if self.dirty and not self.discard_changes():
            return
        self.cancel()
        self.key.clear()
        super().done(result)
