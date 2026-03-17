"""Syntax highlighting for formatting markers in transcript text."""
import re
from PyQt5.QtGui import QColor, QTextCharFormat, QFont, QSyntaxHighlighter


class FormattingMarkerHighlighter(QSyntaxHighlighter):
    """Highlights formatting markers and applies bold/italic/underline to enclosed text."""
    def __init__(self, parent=None):
        super().__init__(parent)
        # Define formats for markers (nearly invisible)
        self.marker_format = QTextCharFormat()
        self.marker_format.setForeground(QColor(200, 200, 200))
        self.marker_format.setFontPointSize(1)

        # Formats for text inside markers
        self.bold_format = QTextCharFormat()
        self.bold_format.setFontWeight(QFont.Bold)

        self.italic_format = QTextCharFormat()
        self.italic_format.setFontItalic(True)

        self.underline_format = QTextCharFormat()
        self.underline_format.setFontUnderline(True)

    def highlightBlock(self, text):
        pattern = re.compile(r'(#@[BIU]|#@/[BIU])')
        pos = 0
        stack = []  # list of (marker_type, start_pos)
        while True:
            m = pattern.search(text, pos)
            if not m:
                break
            marker = m.group()
            start, end = m.span()
            self.setFormat(start, end - start, self.marker_format)

            if marker in ('#@B', '#@I', '#@U'):  # opening
                stack.append((marker, end))
            else:  # closing
                if stack and stack[-1][0] == marker.replace('/', ''):
                    open_marker, text_start = stack.pop()
                    fmt = None
                    if open_marker == '#@B':
                        fmt = self.bold_format
                    elif open_marker == '#@I':
                        fmt = self.italic_format
                    elif open_marker == '#@U':
                        fmt = self.underline_format
                    if fmt:
                        self.setFormat(text_start, start - text_start, fmt)
            pos = end
