"""Custom widgets for CapsQual."""
import math
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect
from PyQt5.QtGui import QPainter, QPen, QColor


class SpeedKnob(QWidget):
    valueChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 1.0  # Default 1.0x speed
        self.min_value = 0.5
        self.max_value = 2.0
        self.step = 0.1
        self.is_dragging = False
        self.last_mouse_pos = None
        self.setMinimumSize(60, 60)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw knob background
        center = QPoint(self.width() // 2, self.height() // 2)
        radius = min(self.width(), self.height()) // 2 - 5

        # Outer circle
        painter.setBrush(QColor(240, 240, 240))
        painter.setPen(QPen(QColor(180, 180, 180), 2))
        painter.drawEllipse(center, radius, radius)

        # Value indicator
        angle = 142 + (self.value - self.min_value) / (self.max_value - self.min_value) * 270
        angle_rad = math.radians(angle)

        indicator_length = radius - 5
        end_x = center.x() + indicator_length * math.cos(angle_rad)
        end_y = center.y() + indicator_length * math.sin(angle_rad)

        painter.setPen(QPen(QColor(0, 120, 215), 2))
        painter.drawLine(center, QPoint(int(end_x), int(end_y)))

        # Draw center dot
        painter.setBrush(QColor(0, 120, 215))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, 4, 4)

        # Draw value text
        painter.setPen(QColor(50, 50, 50))
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        value_text = f"{self.value:.1f}x"
        text_rect = QRect(center.x() - 30, center.y() - -2, 60, 20)
        painter.drawText(text_rect, Qt.AlignCenter, value_text)

        # Draw min/max labels
        font.setPointSize(7)
        painter.setFont(font)
        painter.drawText(center.x() - 40, center.y() - radius + 50, "0.5x")
        painter.drawText(center.x() + 27, center.y() - radius + 50, "2.0x")

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
