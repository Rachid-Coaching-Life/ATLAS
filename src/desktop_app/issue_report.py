"""Local report composition and review before opening GitHub."""
from __future__ import annotations

from collections.abc import Mapping

from PyQt6.QtGui import QTextOption
from html import escape
import urllib.parse
import webbrowser

from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QStackedWidget, QTextBrowser,
    QSizePolicy, QVBoxLayout, QWidget,
)

from jarvis.debug import debug_log
from jarvis.utils.redact import scrub_secrets
from desktop_app.themes import JARVIS_THEME_STYLESHEET

_ISSUE_URL = 'https://github.com/Rachid-Coaching-Life/ATLAS/issues/new'
_URL_LIMIT = 8000


class IssueReportDialog(QDialog):
    """Describe a problem in plain language, then review its public report."""

    def __init__(self, logs: str, *, version: tuple[str, str],
                 metadata: Mapping[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle('ATLAS — Signaler un problème')
        self.setStyleSheet(JARVIS_THEME_STYLESHEET)
        screen = self.screen().availableGeometry()
        self.resize(min(660, screen.width()), min(640, screen.height()))
        self._logs = scrub_secrets(logs).replace('```', '`` `')
        self._version = f'{version[0]} ({version[1]})'
        self._metadata = dict(metadata)
        layout = QVBoxLayout(self)
        self.pages = QStackedWidget()
        # Both pages may contain very long, unbroken report text.  Do not
        # let their size hints silently force the top-level window wider.
        self.pages.setMinimumWidth(0)
        self.pages.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.pages, 1)

        form_scroll, form = self._scroll_page()
        heading = QLabel('Décrivez le problème rencontré')
        heading.setStyleSheet('font-size: 20px; font-weight: 600; color: #fbbf24;')
        form.addWidget(heading)
        intro = QLabel('Décrivez ce qui s’est passé. Vous pourrez vérifier le rapport avant son ouverture sur GitHub.')
        intro.setWordWrap(True)
        form.addWidget(intro)
        self.problem_input = self._add_field(form, 'Que s’est-il passé ?',
            'Que faisiez-vous lorsque le problème est apparu ?', 'problem')
        self.expected_input = self._add_field(form, 'Quel résultat attendiez-vous ? (facultatif)',
            'Que souhaitiez-vous demander à ATLAS ?', 'expected')
        extra = QCheckBox('Ajouter des détails (facultatif)')
        extra.setObjectName('add_details')
        form.addWidget(extra)
        self.extra_fields = QWidget()
        extra_layout = QVBoxLayout(self.extra_fields)
        extra_layout.setContentsMargins(0, 0, 0, 0)
        self.title_input = QLineEdit()
        self.title_input.setMaxLength(200)
        self.title_input.setPlaceholderText('Laissez vide pour utiliser la première ligne de votre description')
        extra_layout.addWidget(QLabel('Résumé (facultatif)'))
        extra_layout.addWidget(self.title_input)
        self.steps_input = self._add_field(extra_layout, 'Comment reproduire le problème ? (facultatif)',
            'Indiquez vos paroles ou les clics effectués', 'steps')
        self.extra_fields.hide()
        extra.toggled.connect(self.extra_fields.setVisible)
        form.addWidget(self.extra_fields)
        form.addStretch()
        self.pages.addWidget(form_scroll)

        review_scroll, review = self._scroll_page()
        heading = QLabel('Vérifiez votre rapport')
        heading.setStyleSheet('font-size: 20px; font-weight: 600; color: #fbbf24;')
        review.addWidget(heading)
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        self.preview.setOpenLinks(False)
        self.preview.setMinimumHeight(200)
        self.preview.setAccessibleName('Votre rapport')
        self.preview.setMinimumWidth(0)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.preview.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        review.addWidget(self.preview, 1)
        self.include_logs = QCheckBox('Joindre les informations techniques au rapport')
        self.include_logs.setChecked(True)
        review.addWidget(self.include_logs)
        privacy = QLabel('Ces informations comprennent les réglages et le journal d’activité, qui peuvent contenir '
                         'des paroles adressées à ATLAS. Vous pouvez les consulter ou ne pas les joindre.')
        privacy.setWordWrap(True)
        review.addWidget(privacy)
        self.details_button = QPushButton('Afficher les informations techniques')
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self._show_diagnostics)
        review.addWidget(self.details_button)
        self.technical_preview = QPlainTextEdit()
        self.technical_preview.setReadOnly(True)
        self.technical_preview.setMinimumHeight(160)
        self.technical_preview.setAccessibleName('Informations techniques')
        self.technical_preview.setMinimumWidth(0)
        self.technical_preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.technical_preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.technical_preview.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        self.technical_preview.hide()
        review.addWidget(self.technical_preview)
        self.pages.addWidget(review_scroll)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        # French action labels and the long-report button cannot fit beside
        # Cancel/Back on a 440px window. Keep the two groups in separate
        # compact rows instead of allowing Qt to enlarge the dialog.
        buttons = QVBoxLayout()
        navigation = QHBoxLayout()
        cancel = QPushButton('Annuler')
        cancel.clicked.connect(self.reject)
        navigation.addWidget(cancel)
        self.back_button = QPushButton('Retour')
        self.back_button.clicked.connect(lambda: self._show_page(0))
        navigation.addWidget(self.back_button)
        navigation.addStretch()
        buttons.addLayout(navigation)

        actions = QHBoxLayout()
        actions.addStretch()
        self.review_button = QPushButton('Vérifier le rapport')
        self.review_button.setObjectName('review_report')
        self.review_button.clicked.connect(lambda: self._show_page(1))
        actions.addWidget(self.review_button)
        self.copy_button = QPushButton('Copier')
        self.copy_button.setToolTip('Copier le rapport vérifié')
        self.copy_button.clicked.connect(self._copy_report)
        actions.addWidget(self.copy_button)
        self.open_button = QPushButton('Ouvrir GitHub')
        self.open_button.setObjectName('open_github')
        self.open_button.clicked.connect(self._open_github)
        actions.addWidget(self.open_button)
        buttons.addLayout(actions)
        layout.addLayout(buttons)
        self.title_input.textChanged.connect(self._update_preview)
        for field in (self.problem_input, self.expected_input, self.steps_input):
            field.textChanged.connect(self._update_preview)
        self.include_logs.toggled.connect(self._update_preview)
        self._show_page(0)

    @staticmethod
    def _scroll_page():
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setMinimumWidth(0)
        scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        content = QWidget()
        form = QVBoxLayout(content)
        scroll.setWidget(content)
        return scroll, form

    def _show_page(self, index):
        if index == 1 and not self._valid():
            return
        self.pages.setCurrentIndex(index)
        self.back_button.setVisible(index == 1)
        self.copy_button.setVisible(index == 1)
        self.open_button.setVisible(index == 1)
        self.review_button.setVisible(index == 0)
        self._update_preview()

    def _show_diagnostics(self, visible):
        self.technical_preview.setVisible(visible and self.include_logs.isChecked())
        self.details_button.setText('Masquer les informations techniques' if visible
                                    else 'Afficher les informations techniques')

    @staticmethod
    def _add_field(form, label, placeholder, name):
        field = QPlainTextEdit()
        field.setObjectName(name)
        field.setPlaceholderText(placeholder)
        field.setAccessibleName(label)
        field.setMinimumHeight(80)
        field.setMaximumHeight(110)
        field_label = QLabel(label)
        field_label.setWordWrap(True)
        form.addWidget(field_label)
        form.addWidget(field)
        return field

    def _title(self):
        description = self.problem_input.toPlainText().strip()
        first_line = description.splitlines()[0][:160] if description else ''
        return scrub_secrets(self.title_input.text().strip() or first_line)

    def _sections(self):
        return [(heading, scrub_secrets(field.toPlainText().strip())) for heading, field in (
            ('What happened', self.problem_input),
            ('What should have happened', self.expected_input),
            ('How to make it happen again', self.steps_input),
        ) if field.toPlainText().strip()]

    def _diagnostics_text(self):
        parts = [f'ATLAS version: {self._version}']
        parts.extend(f'{key}: {value}' for key, value in self._metadata.items())
        parts.extend(['', 'Activity log', self._logs or 'Aucun journal disponible.'])
        return scrub_secrets('\n'.join(parts))

    def _report_body(self):
        parts = [f'## {self._title()}', f'**Version:** {self._version}']
        for heading, value in self._sections():
            parts.extend(['', f'### {heading}', value])
        if self.include_logs.isChecked():
            parts.extend(['', '<details>', '<summary>📋 Troubleshooting details</summary>', '',
                          '```', self._diagnostics_text(), '```', '', '</details>'])
        else:
            parts.extend(['', 'Troubleshooting details omitted by the reporter.'])
        return scrub_secrets('\n'.join(parts))

    def _report_url(self, body):
        return _ISSUE_URL + '?' + urllib.parse.urlencode({
            'title': self._title(), 'body': body, 'labels': 'bug',
        })

    def _valid(self):
        return bool(self.problem_input.toPlainText().strip())

    def _update_preview(self):
        self._prepared_report = self._report_body()
        # User text is escaped, so it cannot introduce images, links or HTML.
        parts = [f'<h2>{escape(self._title())}</h2>']
        for heading, value in self._sections():
            text = escape(value).replace('\n', '<br>')
            parts.extend([f'<h3>{escape(heading)}</h3>', f'<p>{text}</p>'])
        self.preview.setHtml(''.join(parts))
        self.technical_preview.setPlainText(self._diagnostics_text())
        included = self.include_logs.isChecked()
        self.details_button.setEnabled(included)
        if not included:
            self.details_button.setChecked(False)
        self.technical_preview.setVisible(included and self.details_button.isChecked())
        valid = self._valid()
        reviewing = self.pages.currentIndex() == 1
        self.review_button.setEnabled(valid)
        self.open_button.setEnabled(valid and reviewing)
        self.copy_button.setEnabled(valid and reviewing)
        long_report = len(self._report_url(self._prepared_report)) > _URL_LIMIT
        self.open_button.setText('Copier + GitHub' if long_report else 'Ouvrir GitHub')
        self.status.setText('Ce rapport est trop long pour être ouvert directement. Il sera copié afin que vous puissiez '
                            'le coller dans GitHub avant de l’envoyer.' if long_report and reviewing else '')

    def _copy_report(self):
        if not self._valid() or self.pages.currentIndex() != 1:
            return False
        try:
            QApplication.clipboard().setText(self._prepared_report)
        except Exception as exc:
            debug_log(f'Issue report clipboard failed: {type(exc).__name__}', 'desktop')
            self.status.setText('Copie impossible. Copiez le contenu depuis l’aperçu.')
            return False
        self.status.setText('Rapport copié. Vous pouvez le coller dans GitHub.')
        debug_log('Issue report copied after local review', 'desktop')
        return True

    def _open_github(self):
        if not self._valid() or self.pages.currentIndex() != 1:
            return
        url = self._report_url(self._prepared_report)
        if len(url) > _URL_LIMIT:
            if not self._copy_report():
                return
            url = _ISSUE_URL + '?' + urllib.parse.urlencode({'title': self._title(), 'labels': 'bug'})
        try:
            opened = webbrowser.open(url)
        except Exception as exc:
            debug_log(f'Issue report browser failed: {type(exc).__name__}', 'desktop')
            opened = False
        if not opened:
            self.status.setText('Impossible d’ouvrir le navigateur. Copiez le rapport et ouvrez '
                                'github.com/Rachid-Coaching-Life/ATLAS/issues/new manuellement.')
            return
        debug_log('Issue report opened for user submission on GitHub', 'desktop')
        self.accept()
