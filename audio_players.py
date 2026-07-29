"""Audio player classes for CapsQual."""
import time
import logging
from PyQt5.QtCore import QThread, pyqtSignal, QTimer

logger = logging.getLogger(__name__)


class VlcAudioPlayer(QThread):
    """Audio player using VLC media player"""
    playback_started = pyqtSignal()
    playback_paused = pyqtSignal()
    playback_stopped = pyqtSignal()
    position_changed = pyqtSignal(float)  # Position in seconds
    end_reached = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.vlc_available = False
        self.instance = None
        self.player = None
        self.media = None
        self.is_playing = False
        self.duration = 0.0
        self.current_position = 0.0
        self.playback_speed = 1.0
        self.audio_file_path = None

        # Try to import VLC and create instance
        try:
            import vlc
            print("VLC module imported successfully")
            self.vlc = vlc
            self.instance = self.vlc.Instance()
            print("VLC instance created")
            self.player = self.instance.media_player_new()
            print("VLC player created")
            self.vlc_available = True

            # Timer for position updates
            self.position_timer = QTimer()
            self.position_timer.timeout.connect(self.update_position)
            self.position_timer.start(100)  # Update every 100ms

            # Event manager for VLC events
            self.event_manager = self.player.event_manager()
            self.event_manager.event_attach(self.vlc.EventType.MediaPlayerEndReached, self._on_end_reached)

        except ImportError as e:
            print(f"VLC import failed: {e}")
            self.vlc_available = False
        except Exception as e:
            print(f"VLC init failed: {e}")
            self.vlc_available = False

    def load_file(self, audio_path):
        """Load audio file"""
        if not self.vlc_available:
            logger.error("VLC not available, cannot load file")
            return False

        try:
            self.audio_file_path = audio_path
            self.media = self.instance.media_new(audio_path)
            self.player.set_media(self.media)

            # Get duration
            self.media.parse()
            time.sleep(0.1)  # Give VLC time to parse
            self.duration = self.media.get_duration() / 1000.0  # Convert ms to seconds

            # Set initial speed
            self.player.set_rate(1.0)
            self.playback_speed = 1.0

            logger.info(f"Audio loaded: {audio_path}, duration: {self.duration:.2f}s")
            return True

        except Exception as e:
            logger.error(f"Failed to load audio with VLC: {e}")
            return False

    def play(self):
        """Start playback"""
        if not self.vlc_available or not self.player:
            return
        if self.player.play() == 0:
            self.is_playing = True
            self.playback_started.emit()
            logger.info("Playback started")
        else:
            logger.error("Failed to start playback")

    def pause(self):
        """Pause playback"""
        if not self.vlc_available or not self.player:
            return
        self.player.pause()
        self.is_playing = False
        self.playback_paused.emit()
        logger.info("Playback paused")

    def stop(self):
        """Stop playback"""
        if not self.vlc_available or not self.player:
            return
        self.player.stop()
        self.is_playing = False
        self.current_position = 0.0
        self.playback_stopped.emit()
        logger.info("Playback stopped")

    def seek(self, position_seconds):
        """Seek to position in seconds"""
        if not self.vlc_available or not self.player:
            return
        try:
            position_ms = int(position_seconds * 1000)
            self.player.set_time(position_ms)
            self.current_position = position_seconds
            self.position_changed.emit(position_seconds)
            logger.debug(f"Seeked to {position_seconds:.2f}s")
        except Exception as e:
            logger.error(f"Error seeking: {e}")

    def set_speed(self, speed):
        """Set playback speed (0.5 to 2.0)"""
        if not self.vlc_available or not self.player:
            return False
        try:
            speed = max(0.25, min(4.0, speed))
            self.player.set_rate(speed)
            self.playback_speed = speed
            logger.info(f"Playback speed set to {speed:.1f}x")
            return True
        except Exception as e:
            logger.error(f"Error setting playback speed: {e}")
            return False

    def get_position(self):
        """Get current position in seconds"""
        if not self.vlc_available or not self.player:
            return self.current_position
        try:
            time_ms = self.player.get_time()
            if time_ms >= 0:
                self.current_position = time_ms / 1000.0
            return self.current_position
        except:
            return self.current_position

    def get_state(self):
        """Get current player state"""
        if not self.vlc_available or not self.player:
            return None
        return self.player.get_state()

    def update_position(self):
        """Update and emit current position"""
        if self.is_playing:
            pos = self.get_position()
            if pos >= 0:
                self.position_changed.emit(pos)

                # Check if we've reached the end
                if self.duration > 0 and pos >= self.duration - 0.1:
                    self.stop()

    def _on_end_reached(self, event):
        """Handle end of media"""
        self.is_playing = False
        self.end_reached.emit()
        logger.info("End of media reached")

    def cleanup(self):
        """Clean up resources"""
        if hasattr(self, 'position_timer'):
            self.position_timer.stop()
        self.stop()
        if self.player:
            self.player.release()
        if self.instance:
            self.instance.release()
