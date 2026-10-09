import datetime
import html
import json
import re
import sys
import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QTextDocument, QShortcut, QKeySequence
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QTextBrowser, QDialog, QFormLayout, QLineEdit, QCheckBox, QDialogButtonBox, QComboBox, QSpinBox, QDateEdit
from DesktopCredentials import load_key, save_key
from FinancialDatasets import FinancialClient, DATASETS
from MiroResearch import ResearchEngine, endpoint


class ResearchWorkspace(QWidget):
    completed = Signal(object)
    failed = Signal(object)
    progress = Signal(object)

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.history = store.get('research_history', [])[-40:]
        self.generation = 0
        self.cancel = threading.Event()
        self.busy = False
        self.pending_question = ''
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 8, 16, 16)
        header = QHBoxLayout()
        self.state = QLabel('Connect a model to begin')
        self.state.setObjectName('status')
        header.addWidget(self.state)
        header.addStretch()
        fresh = QPushButton('New chat')
        fresh.clicked.connect(self.new_chat)
        header.addWidget(fresh)
        connections = QPushButton('Connections')
        connections.clicked.connect(self.connections)
        header.addWidget(connections)
        box.addLayout(header)
        self.transcript = QTextBrowser()
        self.transcript.setObjectName('researchConversation')
        self.transcript.setOpenExternalLinks(False)
        self.transcript.anchorClicked.connect(self.open_source)
        box.addWidget(self.transcript, 1)
        self.question = QPlainTextEdit()
        self.question.setPlaceholderText('Ask a question about a token, company or market')
        self.question.setMaximumHeight(100)
        self.question.setAccessibleName('Research question')
        box.addWidget(self.question)
        actions = QHBoxLayout()
        self.notice = QLabel('Local history. Requests go to your connected model.')
        self.notice.setObjectName('status')
        actions.addWidget(self.notice, 1)
        self.stop_button = QPushButton('Stop')
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_request)
        actions.addWidget(self.stop_button)
        self.send_button = QPushButton('Ask')
        self.send_button.setObjectName('primary')
        self.send_button.clicked.connect(self.ask)
        self.send_shortcut = QShortcut(QKeySequence('Ctrl+Return'), self)
        self.send_shortcut.activated.connect(self.ask)
        actions.addWidget(self.send_button)
        box.addLayout(actions)
        self.completed.connect(self.accept_result, Qt.ConnectionType.QueuedConnection)
        self.failed.connect(self.accept_error, Qt.ConnectionType.QueuedConnection)
        self.progress.connect(self.accept_progress, Qt.ConnectionType.QueuedConnection)
        self.render()
        self.update_connection()

    def update_connection(self):
        configured = bool(self.store.get('research_connection', {}).get('endpoint'))
        self.state.setText('Ready to connect' if configured else 'Connect a model to begin')
        self.send_button.setEnabled(configured and not self.busy)

    def render(self):
        if not self.history:
            self.transcript.setHtml('<h2>Research your markets</h2><p>Ask questions, review evidence and keep the conversation in this workspace.</p><p>Use Connections to add a MiroThinker model endpoint and a Financial Datasets key.</p>')
            return
        parts = []
        for row in self.history:
            label = 'You' if row['role'] == 'user' else 'GemSearch'
            text = html.escape(row['content']).replace('\n', '<br>')
            if row['role'] == 'assistant':
                document = QTextDocument()
                document.setMarkdown(re.sub(r'!\[[^\]]*\]\([^)]*\)', '', row['content']))
                body = re.search(r'<body[^>]*>(.*?)</body>', document.toHtml(), re.S)
                if body:
                    text = body.group(1)
            sources = ''.join('<p><a href="' + html.escape(url, quote=True) + '">Financial Datasets source</a></p>' for url in row.get('sources', []) if url.startswith('https://api.financialdatasets.ai/'))
            parts.append('<h3>' + label + '</h3><p>' + text + '</p>' + sources)
        self.transcript.setHtml(''.join(parts))
        self.transcript.verticalScrollBar().setValue(self.transcript.verticalScrollBar().maximum())

    def open_source(self, url):
        if url.scheme() in ('https', 'http'):
            QDesktopServices.openUrl(url)

    def new_chat(self):
        self.stop_request()
        self.history = []
        self.store.set('research_history', [])
        self.question.clear()
        self.render()

    def stop_request(self):
        self.cancel.set()
        self.generation += 1
        self.busy = False
        self.pending_question = ''
        self.stop_button.setEnabled(False)
        self.update_connection()
        self.state.setText('Stopped')

    def work(self, operation, kind='answer'):
        if self.busy:
            return
        self.generation += 1
        generation = self.generation
        self.cancel = threading.Event()
        cancelled = self.cancel
        self.busy = True
        self.send_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.state.setText('Connecting' if kind == 'probe' else 'Researching')
        def run():
            try:
                result = operation(cancelled, lambda text: self.progress.emit({'generation': generation, 'text': text}))
                if not cancelled.is_set():
                    self.completed.emit({'generation': generation, 'kind': kind, 'result': result})
            except Exception as error:
                if not cancelled.is_set():
                    message = str(error) if isinstance(error, ValueError) else 'The research request could not be completed. Check Connections and try again.'
                    self.failed.emit({'generation': generation, 'message': message})
        threading.Thread(target=run, daemon=True).start()

    def ask(self):
        question = self.question.toPlainText().strip()
        if self.busy or not question:
            return
        if len(question) > 16000:
            self.state.setText('Keep your question under 16,000 characters.')
            return
        config = self.store.get('research_connection', {})
        if not config.get('endpoint'):
            self.connections()
            return
        previous = list(self.history)
        self.pending_question = question
        self.history.append({'role': 'user', 'content': question})
        self.history = self.history[-40:]
        self.store.set('research_history', self.history)
        self.question.clear()
        self.render()
        engine = ResearchEngine(self.store.directory, config, load_key(self.store.directory, 'miro'))
        self.work(lambda cancelled, progress: engine.run(question, previous, cancelled, progress))

    def accept_progress(self, event):
        if event['generation'] == self.generation:
            self.state.setText(event['text'])

    def finish(self):
        self.busy = False
        self.stop_button.setEnabled(False)
        self.pending_question = ''
        self.update_connection()

    def accept_result(self, event):
        if event['generation'] != self.generation:
            return
        self.finish()
        result = event['result']
        if event['kind'] == 'probe':
            self.state.setText('Connected to ' + result['model'])
            return
        self.history.append({'role': 'assistant', 'content': result['answer'], 'sources': result['sources']})
        self.history = self.history[-40:]
        self.store.set('research_history', self.history)
        self.state.setText('Complete')
        self.render()

    def accept_error(self, event):
        if event['generation'] != self.generation:
            return
        self.finish()
        self.state.setText(event['message'])
        self.state.setWordWrap(True)

    def connections(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Research connections')
        dialog.resize(640, 460)
        form = QFormLayout(dialog)
        config = self.store.get('research_connection', {})
        base = QLineEdit(config.get('endpoint', 'http://127.0.0.1:61002/v1'))
        model = QLineEdit(config.get('model', 'mirothinker'))
        miro_key = QLineEdit()
        finance_key = QLineEdit()
        for field, provider in ((miro_key, 'miro'), (finance_key, 'financial')):
            field.setEchoMode(QLineEdit.EchoMode.Password)
            field.setPlaceholderText('Saved locally; leave blank to keep' if load_key(self.store.directory, provider) else 'Enter key locally')
        form.addRow('Model server', base)
        form.addRow('Model name', model)
        form.addRow('Model key', miro_key)
        form.addRow('Financial Datasets key', finance_key)
        share = QCheckBox('Allow this model to read GemSearch token, wallet and alert data')
        share.setChecked(config.get('share_local', False))
        form.addRow(share)
        info = QLabel('MiroThinker needs a running model endpoint. Remote inference and financial data may be billed by their providers. Keys are saved locally using Windows protection. No purchase or automatic reload is enabled.')
        info.setWordWrap(True)
        form.addRow(info)
        signup = QPushButton('Get a Financial Datasets key')
        signup.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://www.financialdatasets.ai/register')))
        form.addRow(signup)
        copy = QPushButton('Copy financial MCP connection')
        copy.clicked.connect(self.copy_financial_mcp)
        form.addRow(copy)
        clear = QPushButton('Remove saved research keys')
        def remove_keys():
            self.stop_request()
            for provider in ('miro', 'financial'):
                save_key(self.store.directory, '', provider)
            miro_key.clear()
            finance_key.clear()
            info.setText('Saved research keys removed. Environment keys, if configured, remain available.')
        clear.clicked.connect(remove_keys)
        form.addRow(clear)
        errors = QLabel()
        errors.setWordWrap(True)
        form.addRow(errors)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        test = QPushButton('Save and test model')
        buttons.addButton(test, QDialogButtonBox.ButtonRole.ActionRole)
        form.addRow(buttons)
        def save(test_model=False):
            try:
                value = endpoint(base.text())
                if not model.text().strip() or len(model.text()) > 200:
                    raise ValueError('Enter a model name.')
                for field, provider in ((miro_key, 'miro'), (finance_key, 'financial')):
                    if field.text().strip():
                        save_key(self.store.directory, field.text().strip(), provider)
                saved = {'endpoint': value, 'model': model.text().strip(), 'share_local': share.isChecked()}
                if config.get('endpoint') and config.get('endpoint') != value:
                    self.new_chat()
                self.store.set('research_connection', saved)
                self.update_connection()
                dialog.accept()
                if test_model:
                    engine = ResearchEngine(self.store.directory, saved, load_key(self.store.directory, 'miro'))
                    self.work(lambda cancelled, progress: engine.probe(), 'probe')
            except ValueError as error:
                errors.setText(str(error))
        buttons.accepted.connect(lambda: save(False))
        buttons.rejected.connect(dialog.reject)
        test.clicked.connect(lambda: save(True))
        dialog.exec()

    def copy_financial_mcp(self):
        from PySide6.QtWidgets import QApplication
        args = ['--financial-mcp', '--data-dir', str(self.store.directory.resolve())]
        if not getattr(sys, 'frozen', False):
            args.insert(0, str(Path(__file__).with_name('desktop.py')))
        value = {'mcpServers': {'gemsearch-financial': {'command': sys.executable, 'args': args}}}
        QApplication.clipboard().setText(json.dumps(value, indent=2))


class FinancialWorkspace(QWidget):
    completed = Signal(object)

    def __init__(self, store, research):
        super().__init__()
        self.store = store
        self.generation = 0
        self.busy = False
        self.research = research
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 8, 16, 16)
        controls = QHBoxLayout()
        self.ticker = QLineEdit()
        self.ticker.setPlaceholderText('Company ticker or crypto pair, such as AAPL or BTC-USD')
        controls.addWidget(self.ticker, 1)
        self.dataset = QComboBox()
        for key, (label, route, result) in DATASETS.items():
            self.dataset.addItem(label, key)
        self.dataset.setCurrentIndex(self.dataset.findData('stock'))
        self.dataset.currentIndexChanged.connect(self.update_fields)
        controls.addWidget(self.dataset)
        self.load_button = QPushButton('Look up')
        self.load_button.setObjectName('primary')
        self.load_button.clicked.connect(self.lookup)
        controls.addWidget(self.load_button)
        connections = QPushButton('Connections')
        connections.clicked.connect(research.connections)
        controls.addWidget(connections)
        box.addLayout(controls)
        options = QHBoxLayout()
        self.period = QComboBox()
        for label, value in [('Annual', 'annual'), ('Quarterly', 'quarterly'), ('Trailing twelve months', 'ttm')]:
            self.period.addItem(label, value)
        options.addWidget(self.period)
        self.limit = QSpinBox()
        self.limit.setRange(1, 100)
        self.limit.setValue(4)
        self.limit.setPrefix('Records: ')
        options.addWidget(self.limit)
        self.start = QDateEdit()
        self.end = QDateEdit()
        self.start.setDate(datetime.date.today() - datetime.timedelta(days=180))
        self.end.setDate(datetime.date.today())
        for field in (self.start, self.end):
            field.setCalendarPopup(True)
            field.setDisplayFormat('yyyy-MM-dd')
            options.addWidget(field)
        self.start.setAccessibleName('History start date')
        self.end.setAccessibleName('History end date')
        options.addStretch()
        box.addLayout(options)
        self.state = QLabel('Browse the free crypto directory, or connect a key to request financial data. Data requests may consume paid credits.')
        self.state.setWordWrap(True)
        self.state.setObjectName('status')
        box.addWidget(self.state)
        self.results = QTextBrowser()
        self.results.setObjectName('researchConversation')
        self.results.setOpenExternalLinks(True)
        self.results.setHtml('<h2>Company and crypto data</h2><p>Choose a dataset and look up a ticker. Prices, statements, news and filings come from Financial Datasets.</p>')
        box.addWidget(self.results, 1)
        self.completed.connect(self.accept_result, Qt.ConnectionType.QueuedConnection)
        self.update_fields()

    def update_fields(self):
        dataset = self.dataset.currentData()
        self.period.setVisible(dataset in ('income', 'balance', 'cashflow'))
        self.limit.setVisible(dataset in ('income', 'balance', 'cashflow', 'news', 'filings'))
        for field in (self.start, self.end):
            field.setVisible(dataset in ('stockhistory', 'cryptohistory'))
        self.ticker.setEnabled(dataset != 'tickers')

    def lookup(self):
        if self.busy:
            return
        self.generation += 1
        generation = self.generation
        args = {'dataset': self.dataset.currentData(), 'ticker': self.ticker.text(), 'period': self.period.currentData(), 'limit': self.limit.value(), 'start_date': self.start.date().toString('yyyy-MM-dd'), 'end_date': self.end.date().toString('yyyy-MM-dd')}
        key = load_key(self.store.directory, 'financial')
        self.busy = True
        self.load_button.setEnabled(False)
        self.state.setText('Loading data')
        self.results.clear()
        def run():
            try:
                result = FinancialClient(key).query(**args)
                event = {'generation': generation, 'result': result}
            except Exception as error:
                event = {'generation': generation, 'error': str(error) if isinstance(error, ValueError) else 'Could not load this dataset. Try again later.'}
            self.completed.emit(event)
        threading.Thread(target=run, daemon=True).start()

    def accept_result(self, event):
        if event['generation'] != self.generation:
            return
        self.busy = False
        self.load_button.setEnabled(True)
        if event.get('error'):
            self.state.setText(event['error'])
            return
        result = event['result']
        data = result['data']
        rows = data if isinstance(data, list) else [data]
        parts = ['<h2>' + html.escape(result['dataset'] + (' : ' + result['ticker'] if result['ticker'] else '')) + '</h2>']
        for row in rows[:100]:
            if isinstance(row, dict):
                parts.append('<table cellspacing="10">')
                for key, value in row.items():
                    if isinstance(value, (list, dict)):
                        value = json.dumps(value, ensure_ascii=False)
                    if value is None:
                        value = 'Not available'
                    label = key.replace('_', ' ').capitalize()
                    parts.append('<tr><td><b>' + html.escape(label) + '</b></td><td>' + html.escape(str(value)) + '</td></tr>')
                parts.append('</table><hr>')
            else:
                parts.append('<p>' + html.escape(str(row)) + '</p>')
        if not rows:
            parts.append('<p>No records were returned for this query.</p>')
        if len(rows) > 100 or result['has_more']:
            parts.append('<p>More records are available. Narrow your query to review a specific period.</p>')
        parts.append('<p><a href="' + html.escape(result['source'], quote=True) + '">Financial Datasets</a></p>')
        self.results.setHtml(''.join(parts))
        self.state.setText('Updated ' + result['sampled_at'][:19].replace('T', ' ') + ' UTC')
