"""Basic UI and non‑UI tests for CapsQual – focuses on initialisation and core logic without GUI."""
import sys
import pytest
from unittest.mock import patch, Mock, MagicMock, PropertyMock
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout
from PyQt5.QtGui import QColor
from PyQt5.QtCore import QEvent, Qt
from editor import SRTEditor
from generators import (
    format_timestamp, time_to_seconds, time_to_ms, _ms_to_time as ms_to_time
)

# ── helpers ───────────────────────────────────────────────────────

def _make_mock_layout(name="mock_layout"):
    """Return a MagicMock that quacks like a QLayout with count()/itemAt()."""
    layout = MagicMock()
    layout.count.return_value = 0
    return layout

# ── fixtures ─────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app():
    """Create a QApplication instance (required for any Qt object)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app

@pytest.fixture
def editor(app):
    """Create an SRTEditor instance with the UI initialisation mocked."""
    with patch.object(SRTEditor, 'init_ui'):
        editor = SRTEditor()
        # Provide minimal UI-like attributes for methods that assume widgets exist.
        editor.speaker_count_label = Mock()
        editor.speaker_count_label.setText = Mock()
        editor.btn_add_speaker = Mock()
        editor.btn_remove_speaker = Mock()
        editor.create_speaker_widgets = Mock()
        editor.setup_shortcuts = Mock()
        editor.update_display = Mock()
        editor.update_speaker_buttons = Mock()
        editor.speaker_colors = [QColor(200, 200, 200)]
        yield editor
        editor.has_unsaved_changes = False
        editor.close()

# ── initialisation tests ─────────────────────────────────────────

def test_initial_attributes(editor):
    """Check that basic attributes are set correctly before init_ui."""
    assert editor.srt_blocks == []
    assert editor.speakers == ["A", "B", "C", "D"]
    assert editor.current_block_index == 0
    assert editor.file_has_timestamps is True
    assert editor.project_name == ""
    assert editor.project_memo == ""
    assert editor.cjk_mode is False

# ── speaker management tests ─────────────────────────────────────

def test_speaker_management(editor):
    """Test speaker count adjustment and renaming (no UI needed)."""
    # Initial speaker count
    assert len(editor.speakers) == 4
    # Increase
    editor.increase_speaker_count()
    assert len(editor.speakers) == 5
    assert editor.speakers[4] == "E"   # next letter
    # Decrease (but need to handle assigned blocks – none assigned)
    editor.decrease_speaker_count()
    assert len(editor.speakers) == 4

def test_update_speaker_count_increases(editor):
    """update_speaker_count should add new speakers and update UI."""
    editor.update_speaker_count(6)
    assert len(editor.speakers) == 6
    assert editor.speakers[4] == "E"
    assert editor.speakers[5] == "F"
    editor.create_speaker_widgets.assert_called_once()
    editor.setup_shortcuts.assert_called_once()
    editor.update_display.assert_called_once()
    editor.speaker_count_label.setText.assert_called_with("6")
    editor.update_speaker_buttons.assert_called()

def test_update_speaker_count_decreases(editor):
    """update_speaker_count should pop speakers when decreasing."""
    editor.update_speaker_count(2)
    assert len(editor.speakers) == 2
    assert editor.speakers == ["A", "B"]

def test_count_blocks_for_speaker(editor):
    """count_blocks_for_speaker should count blocks assigned to a speaker index."""
    editor.srt_blocks = [
        {'speaker': 0, 'text': 'A1'},
        {'speaker': 0, 'text': 'A2'},
        {'speaker': 1, 'text': 'B1'},
        {'speaker': None, 'text': 'unassigned'},
    ]
    assert editor.count_blocks_for_speaker(0) == 2
    assert editor.count_blocks_for_speaker(1) == 1
    assert editor.count_blocks_for_speaker(2) == 0

def test_rename_speaker(editor):
    """rename_speaker should update the speaker name."""
    # Set up speaker_widgets with mock name edits
    mock_edit = Mock()
    mock_edit.text.return_value = "Alice"
    editor.speaker_widgets = [{'name_edit': mock_edit}]
    editor.push_undo = Mock()
    editor.rename_speaker(0)
    assert editor.speakers[0] == "Alice"
    editor.push_undo.assert_called_once()
    editor.update_display.assert_called()

# ── undo/redo tests ──────────────────────────────────────────────

def test_undo_redo_basic(editor):
    """Test undo/redo stack operations."""
    editor.srt_blocks = [{'text': 'Original', 'speaker': None}]
    editor.push_undo()
    editor.srt_blocks[0]['text'] = 'Modified'
    editor.undo()
    assert editor.srt_blocks[0]['text'] == 'Original'
    editor.redo()
    assert editor.srt_blocks[0]['text'] == 'Modified'

# ── unsaved changes tests ────────────────────────────────────────

def test_mark_unsaved_changes(editor):
    """Test the unsaved changes flag and window title."""
    editor.project_name = "Test"
    editor.mark_unsaved_changes()
    assert editor.has_unsaved_changes is True
    assert "*" in editor.windowTitle()
    editor.clear_unsaved_changes()
    assert editor.has_unsaved_changes is False
    assert "*" not in editor.windowTitle()

# ── load_file tests ──────────────────────────────────────────────

def test_load_file_returns_when_unsaved_cancelled(editor):
    """load_file should return early if check_unsaved_changes is cancelled."""
    editor.check_unsaved_changes = Mock(return_value=False)
    with patch('editor.QFileDialog') as mock_fd:
        result = editor.load_file()
        assert result is None
        mock_fd.getOpenFileName.assert_not_called()

# ── old-format overlap detection tests ───────────────────────────

INDENT_PL = '\u2423'  # ␣ placeholder character

def test_detect_old_overlap_blocks_gat2(editor):
    """Detect blocks with old-format GAT2 overlap markers."""
    editor.srt_blocks = [
        {'raw_text': f'some text{INDENT_PL}{INDENT_PL}[overlap]', 'overlap_info': None},
        {'raw_text': 'normal block', 'overlap_info': None},
    ]
    result = editor._detect_old_overlap_blocks()
    assert len(result) == 1
    assert result[0][0] == 0

def test_detect_old_overlap_blocks_tiq(editor):
    """Detect blocks with old-format TiQ overlap markers."""
    editor.srt_blocks = [
        {'raw_text': f'some text{INDENT_PL}{INDENT_PL}└overlap', 'overlap_info': None},
    ]
    result = editor._detect_old_overlap_blocks()
    assert len(result) == 1

def test_detect_old_overlap_blocks_skips_new_format(editor):
    """Blocks with overlap_info already set should not be detected as old-format."""
    editor.srt_blocks = [
        {'raw_text': f'some text{INDENT_PL}{INDENT_PL}[overlap]',
         'overlap_info': {'indent': 2, 'overlap_text': '[overlap]'}},
    ]
    result = editor._detect_old_overlap_blocks()
    assert len(result) == 0

def test_detect_old_overlap_blocks_skips_empty(editor):
    """Empty raw_text should not cause errors."""
    editor.srt_blocks = [
        {'raw_text': ''},
        {'raw_text': None},
    ]
    result = editor._detect_old_overlap_blocks()
    assert len(result) == 0

# ── upgrade old-format tests ─────────────────────────────────────

def test_upgrade_old_overlap_format_tiq(editor):
    """Upgrade TiQ-format blocks to overlap_info."""
    editor.srt_blocks = [
        {'raw_text': 'first line', 'speaker': 0, 'is_turn_start': True},
        {'raw_text': f'some text{INDENT_PL}{INDENT_PL}└overlap more',
         'speaker': 1, 'is_turn_start': True, 'overlap_info': None},
    ]
    old_blocks = editor._detect_old_overlap_blocks()
    count = editor._upgrade_old_overlap_format(old_blocks)
    assert count == 1
    info = editor.srt_blocks[1]['overlap_info']
    assert info is not None
    assert info['convention'] == 'tiq'
    assert info['indent'] == 2
    assert '└overlap' in info['overlap_text']

def test_upgrade_old_overlap_format_gat2(editor):
    """Upgrade GAT2-format blocks to overlap_info."""
    editor.srt_blocks = [
        {'raw_text': 'first line', 'speaker': 0, 'is_turn_start': True},
        {'raw_text': f'some text{INDENT_PL}{INDENT_PL}{INDENT_PL}[overlap]after',
         'speaker': 1, 'is_turn_start': True, 'overlap_info': None},
    ]
    old_blocks = editor._detect_old_overlap_blocks()
    count = editor._upgrade_old_overlap_format(old_blocks)
    assert count == 1
    info = editor.srt_blocks[1]['overlap_info']
    assert info is not None
    assert info['convention'] == 'gat2'
    assert info['indent'] == 3
    assert info['overlap_text'] == '[overlap]'
    assert info['text_after'] == 'after'

# ── create_speaker_widgets smoke test ────────────────────────────

def test_create_speaker_widgets_needs_layout(editor):
    """create_speaker_widgets requires speaker_layout — verify method exists."""
    assert hasattr(editor, 'create_speaker_widgets')
    assert callable(editor.create_speaker_widgets)



# ── waveform audio lifecycle tests ───────────────────────────────

def test_clear_waveform_audio_no_viewer(editor):
    """_clear_waveform_audio should not crash when waveform_viewer doesn't exist."""
    if hasattr(editor, 'waveform_viewer'):
        del editor.waveform_viewer
    # Should not raise
    editor._clear_waveform_audio()

def test_clear_waveform_audio_with_viewer(editor):
    """_clear_waveform_audio should call clear_audio on the waveform viewer."""
    mock_viewer = MagicMock()
    editor.waveform_viewer = mock_viewer
    editor._clear_waveform_audio()
    mock_viewer.clear_audio.assert_called_once()

def test_load_waveform_audio_delegates(editor):
    """_load_waveform_audio should delegate to waveform viewer."""
    mock_viewer = MagicMock()
    editor.waveform_viewer = mock_viewer
    editor._load_waveform_audio("/fake/path.wav")
    mock_viewer.load_audio.assert_called_once_with("/fake/path.wav")

def test_waveform_drag_pushes_undo_once_per_drag(editor):
    """A single waveform handle drag pushes exactly ONE undo snapshot.

    Regression: previously every mouse-move during a drag emitted
    segment_start_changed/segment_end_changed, and each emission called
    push_undo(). That flooded the undo stack with micro-steps, so undo
    only nudged the boundary by a few milliseconds instead of reverting
    the whole drag. The drag_started signal now captures the pre-drag
    state once, so one undo restores the entire drag.
    """
    from widgets import WaveformViewer

    viewer = WaveformViewer()
    viewer.end_time = 20.0
    viewer.set_segment = Mock()
    editor.waveform_viewer = viewer
    editor.srt_blocks = [{
        'text': 'X', 'raw_text': 'X',
        'start_time': '00:00:10,000', 'end_time': '00:00:20,000',
    }]
    editor.current_block_index = 0
    editor._seconds_to_srt = Mock(side_effect=lambda s: f"00:00:{int(s):02d},000")
    editor.mark_unsaved_changes = Mock()

    viewer.drag_started.connect(editor._on_waveform_drag_started)
    viewer.segment_start_changed.connect(editor._on_waveform_start_changed)

    # Simulate one drag gesture: handle press + several mouse moves
    viewer.drag_started.emit()
    for i in range(1, 6):
        viewer.segment_start_changed.emit(10.0 + i)  # 11, 12, 13, 14, 15

    # Exactly one undo entry for the whole gesture
    assert len(editor.undo_stack) == 1

    editor.undo()
    assert editor.srt_blocks[0]['start_time'] == '00:00:10,000'

    editor.redo()
    assert editor.srt_blocks[0]['start_time'] == '00:00:15,000'

def test_waveform_end_drag_pushes_undo_once_per_drag(editor):
    """The end-handle drag has the same once-per-gesture undo behaviour."""
    from widgets import WaveformViewer

    viewer = WaveformViewer()
    viewer.start_time = 10.0
    viewer.set_segment = Mock()
    editor.waveform_viewer = viewer
    editor.srt_blocks = [{
        'text': 'X', 'raw_text': 'X',
        'start_time': '00:00:10,000', 'end_time': '00:00:20,000',
    }]
    editor.current_block_index = 0
    editor._seconds_to_srt = Mock(side_effect=lambda s: f"00:00:{int(s):02d},000")
    editor.mark_unsaved_changes = Mock()

    viewer.drag_started.connect(editor._on_waveform_drag_started)
    viewer.segment_end_changed.connect(editor._on_waveform_end_changed)

    viewer.drag_started.emit()
    for i in range(1, 6):
        viewer.segment_end_changed.emit(20.0 + i)  # 21, 22, 23, 24, 25

    assert len(editor.undo_stack) == 1

    editor.undo()
    assert editor.srt_blocks[0]['end_time'] == '00:00:20,000'

    editor.redo()
    assert editor.srt_blocks[0]['end_time'] == '00:00:25,000'

# ── waveform keyboard-control tests ───────────────────────────────

def _key_event(key, modifiers, autorep=False):
    """Build a synthetic QKeyEvent for driving the waveform viewer's keyboard handling."""
    from PyQt5.QtGui import QKeyEvent
    return QKeyEvent(QEvent.KeyPress, key, modifiers, "", autorep)

def _make_viewer():
    from widgets import WaveformViewer
    viewer = WaveformViewer()
    viewer.duration = 30.0
    viewer.view_start, viewer.view_end = 0.0, 30.0
    viewer.start_time, viewer.end_time = 10.0, 20.0
    return viewer

def test_waveform_keyboard_nudge_start_marker(app):
    """Ctrl+Left/Right nudges the start marker by one step."""
    viewer = _make_viewer()
    changed, started = [], []
    viewer.segment_start_changed.connect(changed.append)
    viewer.drag_started.connect(lambda: started.append(1))

    viewer.keyPressEvent(_key_event(Qt.Key_Left, Qt.ControlModifier))
    assert viewer.start_time == 9.9
    assert changed == [9.9]
    assert len(started) == 1  # one undo snapshot per press

    viewer.keyPressEvent(_key_event(Qt.Key_Right, Qt.ControlModifier))
    assert viewer.start_time == 10.0

def test_waveform_keyboard_nudge_end_marker(app):
    """Ctrl+Shift+Left/Right nudges the end marker by one step."""
    viewer = _make_viewer()
    changed = []
    viewer.segment_end_changed.connect(changed.append)

    viewer.keyPressEvent(_key_event(Qt.Key_Right, Qt.ControlModifier | Qt.ShiftModifier))
    assert viewer.end_time == 20.1
    assert changed == [20.1]

    viewer.keyPressEvent(_key_event(Qt.Key_Left, Qt.ControlModifier | Qt.ShiftModifier))
    assert viewer.end_time == 20.0

def test_waveform_keyboard_set_markers_to_playhead(app):
    """Ctrl+Shift+Alt+Left/Right snaps a marker to the current playhead."""
    viewer = _make_viewer()
    viewer.playback_position = 15.0
    started = []
    viewer.drag_started.connect(lambda: started.append(1))

    viewer.keyPressEvent(_key_event(
        Qt.Key_Left, Qt.ControlModifier | Qt.ShiftModifier | Qt.AltModifier))
    assert viewer.start_time == 15.0
    assert len(started) == 1

    viewer.start_time = 10.0
    viewer.keyPressEvent(_key_event(
        Qt.Key_Right, Qt.ControlModifier | Qt.ShiftModifier | Qt.AltModifier))
    assert viewer.end_time == 15.0

def test_waveform_keyboard_nudge_keeps_segment_valid(app):
    """Nudging start right cannot push it past the end marker."""
    viewer = _make_viewer()
    viewer.start_time, viewer.end_time = 10.0, 10.5
    for _ in range(20):
        viewer.keyPressEvent(_key_event(Qt.Key_Right, Qt.ControlModifier))
    assert viewer.start_time == pytest.approx(10.5 - 0.001)

def test_waveform_keyboard_nudge_undo_integration(editor):
    """A keyboard nudge creates ONE undo entry; auto-repeat doesn't add more."""
    from widgets import WaveformViewer
    viewer = _make_viewer()
    viewer.set_segment = Mock()
    editor.waveform_viewer = viewer
    editor.srt_blocks = [{
        'text': 'X', 'raw_text': 'X',
        'start_time': '00:00:10,000', 'end_time': '00:00:20,000',
    }]
    editor.current_block_index = 0
    editor._seconds_to_srt = Mock(side_effect=lambda s: (
        f"00:00:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"))
    editor.mark_unsaved_changes = Mock()

    viewer.drag_started.connect(editor._on_waveform_drag_started)
    viewer.segment_start_changed.connect(editor._on_waveform_start_changed)

    # A real keypress nudges start to 9.9 and pushes one undo snapshot
    viewer.keyPressEvent(_key_event(Qt.Key_Left, Qt.ControlModifier))
    assert len(editor.undo_stack) == 1
    assert editor.srt_blocks[0]['start_time'] == '00:00:09,900'

    # Auto-repeat (held key) keeps moving but must NOT push another snapshot
    viewer.keyPressEvent(_key_event(Qt.Key_Left, Qt.ControlModifier, autorep=True))
    assert len(editor.undo_stack) == 1
    assert editor.srt_blocks[0]['start_time'] == '00:00:09,800'

    editor.undo()
    assert editor.srt_blocks[0]['start_time'] == '00:00:10,000'

    editor.redo()
    assert editor.srt_blocks[0]['start_time'] == '00:00:09,800'

def test_waveform_keyboard_shortcuts_work_without_waveform_focus(editor):
    """The editor routes waveform shortcuts globally, no waveform click needed."""
    from widgets import WaveformViewer
    viewer = _make_viewer()
    viewer.set_segment = Mock()
    editor.waveform_viewer = viewer
    editor.srt_blocks = [{
        'text': 'X', 'raw_text': 'X',
        'start_time': '00:00:10,000', 'end_time': '00:00:20,000',
    }]
    editor.current_block_index = 0
    editor._seconds_to_srt = Mock(side_effect=lambda s: (
        f"00:00:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"))
    editor.mark_unsaved_changes = Mock()
    viewer.drag_started.connect(editor._on_waveform_drag_started)
    viewer.segment_start_changed.connect(editor._on_waveform_start_changed)
    viewer.segment_end_changed.connect(editor._on_waveform_end_changed)

    # Ctrl+Right handled by the editor's global shortcut router
    handled = editor._handle_waveform_shortcut(
        _key_event(Qt.Key_Right, Qt.ControlModifier))
    assert handled is True
    assert editor.srt_blocks[0]['start_time'] == '00:00:10,100'
    assert len(editor.undo_stack) == 1

    # Ctrl+Shift+Right nudges the end marker
    handled = editor._handle_waveform_shortcut(
        _key_event(Qt.Key_Right, Qt.ControlModifier | Qt.ShiftModifier))
    assert handled is True
    assert editor.srt_blocks[0]['end_time'] == '00:00:20,100'

    # Unrelated keys pass through (not consumed)
    handled = editor._handle_waveform_shortcut(_key_event(Qt.Key_A, Qt.ControlModifier))
    assert handled is False

def test_waveform_shortcut_text_input_guard(editor):
    """Editable text fields keep Ctrl+arrows; read-only displays don't block them."""
    from widgets import WaveformViewer
    from editor import _is_editable_text_widget
    from PyQt5.QtWidgets import QTextEdit, QLineEdit

    viewer = _make_viewer()
    editor.waveform_viewer = viewer

    # Read-only transcript (the app's main display) must NOT be protected
    ro_display = QTextEdit()
    ro_display.setReadOnly(True)
    assert _is_editable_text_widget(ro_display) is False

    # A truly editable text area must be protected (Ctrl+arrow = word nav)
    editable = QTextEdit()
    assert _is_editable_text_widget(editable) is True
    line_edit = QLineEdit()
    assert _is_editable_text_widget(line_edit) is True

    # Non-text widgets are never protected
    assert _is_editable_text_widget(viewer) is False

# ── shortcuts dialog tests ───────────────────────────────────────

def test_shortcuts_dialog_fits_small_screen(app):
    """The F1 shortcuts dialog must fit an 800x600 screen (scrollable, capped)."""
    from dialogs import ShortcutsDialog
    dlg = ShortcutsDialog()
    try:
        assert dlg.width() <= 800
        assert dlg.height() <= 600
    finally:
        dlg.close()

def test_shortcuts_dialog_lists_all_sections(app):
    """Every documented shortcut category is present in the dialog tree."""
    from dialogs import ShortcutsDialog, SHORTCUT_SECTIONS
    dlg = ShortcutsDialog()
    try:
        assert dlg.tree.topLevelItemCount() == len(SHORTCUT_SECTIONS)
        for i, (name, entries) in enumerate(SHORTCUT_SECTIONS):
            item = dlg.tree.topLevelItem(i)
            assert item.text(0) == name
            assert item.childCount() == len(entries)
    finally:
        dlg.close()

def test_shortcuts_dialog_filter(app):
    """Typing in the filter narrows the list to matching categories."""
    from dialogs import ShortcutsDialog
    dlg = ShortcutsDialog()
    try:
        dlg.filter_edit.setText("waveform")
        visible = [i for i in range(dlg.tree.topLevelItemCount())
                   if not dlg.tree.topLevelItem(i).isHidden()]
        assert len(visible) == 1
        assert dlg.tree.topLevelItem(visible[0]).text(0) == "Waveform Viewer"

        dlg.filter_edit.setText("ctrl+z")
        visible = [i for i in range(dlg.tree.topLevelItemCount())
                   if not dlg.tree.topLevelItem(i).isHidden()]
        assert visible == []

        dlg.filter_edit.setText("")
        visible = [i for i in range(dlg.tree.topLevelItemCount())
                   if not dlg.tree.topLevelItem(i).isHidden()]
        assert len(visible) == dlg.tree.topLevelItemCount()
    finally:
        dlg.close()

# ── format & time conversion tests ───────────────────────────────

def test_format_timestamp(editor):
    """Test timestamp formatting."""
    assert format_timestamp(90.5, "curly") == "{00:01:30}"
    assert format_timestamp(90.5, "hash") == "#00:01:30-5#"
    assert format_timestamp(90.5, "bracket") == "[00:01:30]"

def test_time_conversion(editor):
    """Test helper methods for time conversion."""
    assert time_to_seconds("00:01:30,500") == 90.5
    assert time_to_ms("00:01:30,500") == 90500
    assert ms_to_time(90500) == "00:01:30,500"
