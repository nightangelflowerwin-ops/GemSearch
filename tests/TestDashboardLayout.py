import unittest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from desktop import TokenTable, TokenTableModel


class DashboardLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_full_names_and_single_scroll_view_at_window_sizes(self):
        table = TokenTable()
        table.setModel(TokenTableModel(['Token', 'Chain', 'Price', 'Market cap', 'Vol 24h', 'Vol 5m', 'Net 5m', 'Buys', 'Liquidity', 'Sells', 'Time'], table))
        table.configure_market()
        name = 'Price Obsessed Agent With A Complete Unabridged Token Name'
        records = [{'name': name, 'address': str(i)} for i in range(100)]
        table.model().replace(records, lambda row: [row['name'], 'SOLANA', '$0.001', '$141K', '$1.1M', '$20K', '$3K', '123', '$28K', '45', '12:00'])
        table.show()
        for width in (790, 1110, 1710):
            with self.subTest(width=width):
                table.resize(width, 500)
                self.app.processEvents()
                table.resizeRowsToContents()
                self.assertGreaterEqual(table.columnWidth(0), 240)
                if width < 1200:
                    self.assertGreater(table.rowHeight(0), 42)
                self.assertEqual(table.model().data(table.model().index(0, 0)), name)
                self.assertEqual(table.textElideMode(), Qt.TextElideMode.ElideNone)
                self.assertGreater(table.verticalScrollBar().maximum(), 0)
                table.scrollToBottom()
                self.assertEqual(table.verticalScrollBar().value(), table.verticalScrollBar().maximum())
        table.close()
