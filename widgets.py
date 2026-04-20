"""Custom widgets for CapsQual."""
import math
from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize
from PyQt5.QtGui import QPainter, QPen, QColor


class SpeedKnob(QWidget):
    valueChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 1.0
        self.min_value = 0.5
        self.max_value = 2.0
        self.step = 0.1
        self.is_dragging = False
        self.last_mouse_pos = None
        self.setMinimumSize(30, 30)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
    def sizeHint(self):
        return QSize(60, 60)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        center = QPoint(self.width() // 2, self.height() // 2)
        radius = min(self.width(), self.height()) // 2 - 5
        if radius < 5:
            return  # too small to draw anything

        # Outer circle
        painter.setBrush(QColor(240, 240, 240))
        painter.setPen(QPen(QColor(180, 180, 180), 2))
        painter.drawEllipse(center, radius, radius)

        # Value indicator
        angle = 142 + (self.value - self.min_value) / (self.max_value - self.min_value) * 270
        angle_rad = math.radians(angle)
        indicator_length = radius - 2  # stay inside circle
        end_x = center.x() + indicator_length * math.cos(angle_rad)
        end_y = center.y() + indicator_length * math.sin(angle_rad)

        painter.setPen(QPen(QColor(0, 120, 215), 2))
        painter.drawLine(center, QPoint(int(end_x), int(end_y)))

        # Center dot
        painter.setBrush(QColor(0, 120, 215))
        painter.setPen(Qt.NoPen)
        dot_radius = max(2, radius // 10)
        painter.drawEllipse(center, dot_radius, dot_radius)

        # Value text
        text_color = self.palette().text().color()
        painter.setPen(text_color)
        font = painter.font()
        font_size = max(7, radius // 4)
        font.setPointSize(font_size)
        painter.setFont(font)
        value_text = f"{self.value:.1f}x"

        value_label_x = center.x()
        value_label_y = center.y() + radius / 2

        # Compute bounding rectangle of the text and centre it on the target point
        text_rect = painter.fontMetrics().boundingRect(value_text)
        text_rect.moveCenter(QPoint(int(value_label_x), int(value_label_y)))
        painter.drawText(text_rect, Qt.AlignCenter, value_text)

      # Min/max labels (0.5 and 2.0)
        font.setPointSize(max(6, radius // 5))
        painter.setFont(font)
        label_min = "0.5x"
        label_max = "2.0x"

        # Get text bounding rectangles
        min_rect = painter.fontMetrics().boundingRect(label_min)
        max_rect = painter.fontMetrics().boundingRect(label_max)

        # Position min label to the left of the circle
        min_x = center.x() - radius - min_rect.width() - 5
        min_y = center.y() + radius // 1   # adjust vertical position as needed
        painter.drawText(min_x, min_y, label_min)

        # Position max label to the right of the circle
        max_x = center.x() + radius + 5
        max_y = center.y() + radius // 1
        painter.drawText(max_x, max_y, label_max)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.last_mouse_pos = event.pos()
            event.accept()

    def set_value_direct(self, value):
        """Set value directly"""
        new_value = max(self.min_value, min(self.max_value, value))
        if abs(new_value - self.value) > 0.01:
            self.value = new_value
            self.update()
            self.valueChanged.emit(self.value)

    def mouseMoveEvent(self, event):
        if self.is_dragging and self.last_mouse_pos:
            delta_y = self.last_mouse_pos.y() - event.y()
            delta_x = event.x() - self.last_mouse_pos.x()
            delta = delta_y + delta_x

            new_value = self.value + (delta * self.step / 30)
            new_value = max(self.min_value, min(self.max_value, new_value))

            if new_value != self.value:
                self.value = round(new_value / self.step) * self.step
                self.value = max(self.min_value, min(self.max_value, self.value))
                self.update()
                self.valueChanged.emit(self.value)

            self.last_mouse_pos = event.pos()
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False
            self.last_mouse_pos = None
            event.accept()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self.set_value_direct(self.value + self.step)
        else:
            self.set_value_direct(self.value - self.step)
        event.accept()

