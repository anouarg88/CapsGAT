"""Audio player classes for CapsQual."""
import threading
import time
import logging
from PyQt5.QtCore import QThread, pyqtSignal, QTimer

logger = logging.getLogger(__name__)

# Lazy import detection for audio libraries
_HAS_PYAUDIO = None

def has_pyaudio():
    """Return True if pyaudio and soundfile are available, else False."""
    global _HAS_PYAUDIO
    if _HAS_PYAUDIO is None:
        try:
            import pyaudio
            import soundfile as sf
            _HAS_PYAUDIO = True
        except ImportError:
            _HAS_PYAUDIO = False
            logger.warning("PyAudio or soundfile not installed. Fallback audio will not work.")
    return _HAS_PYAUDIO


class SimpleAudioPlayer(QThread):
    """Simple fallback audio player using PyAudio (no speed control)"""
    playback_started = pyqtSignal()
    playback_stopped = pyqtSignal()
    position_changed = pyqtSignal(float)  # Position in seconds

    def __init__(self):
        super().__init__()
        self.audio_path = None
        self.is_playing = False
        self.is_paused = False
        self.stop_flag = False
        self.current_position = 0.0
        self.duration = 0.0
        self.sample_rate = 44100
        self.channels = 1
        self.pyaudio = None
        self.stream = None
        self.audio_data = None
        self.lock = threading.Lock()

    def load_file(self, audio_path):
        """Load audio file"""
        try:
            import numpy as np
            import soundfile as sf

            self.audio_path = audio_path

            # Load audio data
            audio_data, self.sample_rate = sf.read(audio_path)

            # Convert to mono if needed
            if len(audio_data.shape) > 1:
                audio_data = audio_data.mean(axis=1)

            # Convert to int16
            if audio_data.dtype != np.int16:
                audio_data = (audio_data * 32767).astype(np.int16)

            self.audio_data = audio_data.tobytes()
            self.duration = len(audio_data) / self.sample_rate
            self.channels = 1

            logger.info(f"Simple audio loaded: {self.duration:.2f}s")
            return True

        except Exception as e:
            logger.error(f"Failed to load audio for fallback: {e}")
            return False

    def play(self):
        """Start playback"""
        with self.lock:
            if not has_pyaudio():
                logger.error("PyAudio not available for fallback")
                return

            # Stop any existing playback
            self._stop_playback()

            self.is_playing = True
            self.is_paused = False
            self.stop_flag = False

            if not self.isRunning():
                self.start()

            self.playback_started.emit()

    def pause(self):
        """Pause playback"""
        with self.lock:
            self.is_playing = False
            self.is_paused = True

    def stop(self):
        """Stop playback"""
        with self.lock:
            self.stop_flag = True
            self.is_playing = False
            self.is_paused = False
            self.current_position = 0.0

            self._stop_playback()

            self.playback_stopped.emit()

    def _stop_playback(self):
        """Safely stop audio playback"""
        try:
            if self.stream:
                if self.stream.is_active():
                    self.stream.stop_stream()
                self.stream.close()
                self.stream = None
        except Exception as e:
            logger.debug(f"Error stopping stream: {e}")
            self.stream = None

        # Give time for stream to close
        time.sleep(0.05)

    def seek(self, position_seconds):
        """Seek to position"""
        with self.lock:
            new_position = max(0, min(self.duration, position_seconds))
            self.current_position = new_position

            # If currently playing, restart from new position
            if self.is_playing and not self.is_paused:
                # Signal the thread to restart
                self.stop_flag = True

                # Wait a bit for thread to respond
                time.sleep(0.05)

                # Reset and restart
                self.stop_flag = False
                self.is_paused = False

                # Clear stream
                self._stop_playback()

    def get_position(self):
        """Get current position"""
        return self.current_position

    def run(self):
        """Main playback thread"""
        if not has_pyaudio() or not self.audio_data:
            logger.error("Fallback player: No PyAudio or audio data")
            return

        try:
            import numpy as np
            import pyaudio

            with self.lock:
                self.pyaudio = pyaudio.PyAudio()

            while not self.stop_flag:
                # Check if we should play
                if not self.is_playing or self.is_paused:
                    time.sleep(0.01)
                    continue

                # Calculate start position in bytes
                start_byte = int(self.current_position * self.sample_rate * 2)

                with self.lock:
                    # Create new stream
                    self.stream = self.pyaudio.open(
                        format=pyaudio.paInt16,
                        channels=self.channels,
                        rate=self.sample_rate,
                        output=True,
                        frames_per_buffer=2048
                    )

                # Play from current position
                chunk_size = 4096
                data_bytes = len(self.audio_data)

                for i in range(start_byte, data_bytes, chunk_size):
                    if self.stop_flag:
                        break

                    if not self.is_playing or self.is_paused:
                        break

                    chunk = self.audio_data[i:i+chunk_size]
                    if chunk:
                        try:
                            if self.stream:
                                self.stream.write(chunk)
                        except Exception as e:
                            logger.warning(f"Error writing to stream: {e}")
                            break

                        # Update position
                        self.current_position = i / (self.sample_rate * 2)
                        self.position_changed.emit(self.current_position)

                        # Check if at end
                        if i + chunk_size >= data_bytes:
                            self.stop()
                            break

                    # Small sleep to prevent CPU overuse
                    time.sleep(chunk_size / (self.sample_rate * 2) * 0.9)

                # Clean up stream
                with self.lock:
                    self._stop_playback()

                # If we broke out of loop but still supposed to be playing,
                # we were seeking or paused
                if self.is_playing and not self.is_paused and not self.stop_flag:
                    # Continue from current position
                    continue
                else:
                    break

        except Exception as e:
            logger.error(f"Error in fallback player: {e}")
        finally:
            with self.lock:
                self._stop_playback()
                if self.pyaudio:
                    try:
                        self.pyaudio.terminate()
                    except:
                        pass
                    self.pyaudio = None

    def cleanup(self):
        """Clean up resources"""
        self.stop()
        if self.isRunning():
            self.quit()
            self.wait(1000)  # Wait up to 1 second


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