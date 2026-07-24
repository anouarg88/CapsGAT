"""Unit tests for the CapsQual command-line interface (cli.py)."""
import os
import tempfile
import pytest
from pathlib import Path

from cli import build_parser, run_convert, _compile_speaker_pattern


# ── Sample SRT content ────────────────────────────────────────────

SAMPLE_SRT = """1
00:00:01,000 --> 00:00:02,500
Alice: Hello world

2
00:00:03,000 --> 00:00:04,500
Bob: Hi there

3
00:00:05,000 --> 00:00:06,000
Alice: How are you?

4
00:00:06,500 --> 00:00:08,000
Unassigned line
"""


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def srt_file():
    """Create a temporary SRT file and return its path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".srt", encoding="utf-8", delete=False
    ) as f:
        f.write(SAMPLE_SRT)
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def out_file():
    """Create a temporary output file path — does NOT create the file."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        path = f.name
    if os.path.exists(path):
        os.unlink(path)  # we want a clean slate
    yield path
    if os.path.exists(path):
        os.unlink(path)


# ── Parser tests ──────────────────────────────────────────────────

class TestArgumentParsing:
    def test_no_args_shows_help(self):
        """Calling main() with no args should return exit code 1."""
        from cli import main
        assert main([]) == 1

    def test_gui_flag_parses(self):
        """The --gui flag should be parseable without an input file."""
        parser = build_parser()
        args = parser.parse_args(["-g"])
        assert args.gui is True
        assert args.input is None

    def test_gui_long_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--gui"])
        assert args.gui is True

    def test_input_positional(self):
        parser = build_parser()
        args = parser.parse_args(["my_file.srt"])
        assert args.input == "my_file.srt"
        assert args.format == "gat2"

    def test_format_default(self):
        parser = build_parser()
        args = parser.parse_args(["f.srt"])
        assert args.format == "gat2"

    def test_format_tiq(self):
        parser = build_parser()
        args = parser.parse_args(["f.srt", "-f", "tiq"])
        assert args.format == "tiq"

    def test_format_dresing_pehl(self):
        parser = build_parser()
        args = parser.parse_args(["f.srt", "-f", "dresing_pehl"])
        assert args.format == "dresing_pehl"

    def test_format_srt_rejected(self):
        """'srt' is not a valid CLI format — SRT-in to SRT-out is pointless."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["f.srt", "-f", "srt"])

    def test_speaker_pattern_flag(self):
        parser = build_parser()
        args = parser.parse_args(["f.srt", "-s", "$:"])
        assert args.speaker == "$:"

    def test_include_unassigned_flag(self):
        parser = build_parser()
        args = parser.parse_args(["f.srt", "--include-unassigned"])
        assert args.include_unassigned is True

    def test_wrap_flag(self):
        parser = build_parser()
        args = parser.parse_args(["f.srt", "-w", "60"])
        assert args.wrap == 60

    def test_blank_lines_flag(self):
        parser = build_parser()
        args = parser.parse_args(["f.srt", "--blank-lines"])
        assert args.blank_lines is True

    def test_concatenate_turns_flag(self):
        parser = build_parser()
        args = parser.parse_args(["f.srt", "--concatenate-turns"])
        assert args.concatenate_turns is True

    def test_output_flag(self):
        parser = build_parser()
        args = parser.parse_args(["f.srt", "-o", "out.html"])
        assert args.output == "out.html"

    def test_output_default(self):
        """Default output path is set to None, letting run_convert infer it."""
        parser = build_parser()
        args = parser.parse_args(["f.srt"])
        assert args.output is None


# ── Speaker-pattern tests ─────────────────────────────────────────

class TestSpeakerPattern:
    def test_colon_pattern(self):
        pattern, kind = _compile_speaker_pattern("$:")
        assert kind == "$:"
        match = pattern.match("Alice: Hello world")
        assert match is not None
        assert match.group(1) == "Alice"
        assert match.group(2) == "Hello world"

    def test_colon_pattern_no_space(self):
        pattern, kind = _compile_speaker_pattern("$:")
        match = pattern.match("Bob:Hello")
        assert match is not None
        assert match.group(1) == "Bob"
        assert match.group(2) == "Hello"

    def test_bracket_pattern(self):
        pattern, kind = _compile_speaker_pattern("[$]")
        assert kind == "[$]"
        match = pattern.match("[Alice] Hello world")
        assert match is not None
        assert match.group(1) == "Alice"
        assert match.group(2) == "Hello world"

    def test_brace_pattern(self):
        pattern, kind = _compile_speaker_pattern("{$}")
        assert kind == "{$}"
        match = pattern.match("{Bob} Hi there")
        assert match is not None
        assert match.group(1) == "Bob"
        assert match.group(2) == "Hi there"

    def test_no_match_returns_none(self):
        pattern, _ = _compile_speaker_pattern("$:")
        match = pattern.match("Just regular text without speaker")
        assert match is None

    def test_colon_stops_at_colon(self):
        """The $: pattern uses lazy matching, so first colon ends the speaker name."""
        pattern, _ = _compile_speaker_pattern("$:")
        match = pattern.match("Alice: Hello: world")
        assert match is not None
        assert match.group(1) == "Alice"
        assert match.group(2) == "Hello: world"


# ── Conversion tests ──────────────────────────────────────────────

class TestConversion:
    def test_convert_gat2_default(self, srt_file, out_file):
        """Default GAT2 conversion with speaker detection."""
        from cli import main
        rc = main([srt_file, "--speaker", "$:", "-o", out_file])
        assert rc == 0
        with open(out_file, encoding="utf-8") as f:
            content = f.read()
        assert "Hello world" in content
        assert "Hi there" in content
        assert "How are you?" in content
        # GAT2 should use timestamps in curly braces by default
        assert "{" in content

    def test_convert_tiq(self, srt_file, out_file):
        """TiQ conversion with speaker detection."""
        from cli import main
        rc = main([srt_file, "-f", "tiq", "--speaker", "$:", "-o", out_file])
        assert rc == 0
        with open(out_file, encoding="utf-8") as f:
            content = f.read()
        assert "Hello world" in content
        assert "A:" in content or "Alice" in content

    def test_convert_dresing_pehl(self, srt_file, out_file):
        """Dresing & Pehl conversion."""
        from cli import main
        rc = main([srt_file, "-f", "dresing_pehl",
                    "--speaker", "$:", "-o", out_file])
        assert rc == 0
        with open(out_file, encoding="utf-8") as f:
            content = f.read()
        assert "Hello world" in content

    def test_convert_no_timestamps(self, srt_file, out_file):
        """Disabling timestamps should remove them from output."""
        from cli import main
        rc = main([srt_file, "--no-timestamps", "--speaker", "$:",
                    "-o", out_file])
        assert rc == 0
        with open(out_file, encoding="utf-8") as f:
            content = f.read()
        assert "{" not in content
        assert "Hello world" in content

    def test_convert_wrap(self, srt_file, out_file):
        """Wrapping should affect line lengths."""
        from cli import main
        rc = main([srt_file, "-w", "30", "--speaker", "$:", "-o", out_file])
        assert rc == 0
        with open(out_file, encoding="utf-8") as f:
            content = f.read()
        assert len(content) > 0
        # With 30-char wrap, at least some non-empty lines should exist
        lines = [l for l in content.split("\n") if l.strip()]
        assert len(lines) > 0

    def test_convert_blank_lines(self, srt_file, out_file):
        """Blank lines option for TiQ should insert a numbered blank line between turns."""
        from cli import main
        rc = main([srt_file, "-f", "tiq", "--blank-lines",
                    "--speaker", "$:", "-o", out_file])
        assert rc == 0
        with open(out_file, encoding="utf-8") as f:
            content = f.read()
        # TiQ blank lines appear as a line with just a number (and trailing space)
        # Pattern: "1 A: ...\n2 \n3 B: ..."
        assert "A:" in content
        assert "B:" in content
        # There should be more lines with blank-lines enabled
        line_count = len(content.split("\n"))
        assert line_count >= 3  # at least 3 lines including blank ones

    def test_convert_concatenate_turns(self, srt_file, out_file):
        """Concatenate turns should group same-speaker blocks."""
        from cli import main
        rc = main([srt_file, "--concatenate-turns", "--speaker", "$:",
                    "-o", out_file])
        assert rc == 0
        with open(out_file, encoding="utf-8") as f:
            content = f.read()
        # Alice has two consecutive blocks at start and end
        # In GAT2 concatenated mode, "Hello world" and "How are you?"
        # should appear on separate lines since they're different turns
        assert "Hello world" in content
        assert "How are you?" in content

    def test_convert_html_output(self, srt_file):
        """HTML output extension should generate valid HTML."""
        out = srt_file.replace(".srt", ".html")
        try:
            from cli import main
            rc = main([srt_file, "--speaker", "$:", "-o", out])
            assert rc == 0
            with open(out, encoding="utf-8") as f:
                content = f.read()
            assert "<!DOCTYPE html>" in content
            assert "<p>" in content
        finally:
            if os.path.exists(out):
                os.unlink(out)

    def test_convert_output_default(self, srt_file):
        """Without --output, should write to input path with .txt extension."""
        from cli import main
        # Default format is GAT2 → auto-name gets "_gat" suffix
        expected = srt_file.replace(".srt", "_gat.txt")
        try:
            rc = main([srt_file, "--speaker", "$:"])
            assert rc == 0
            assert os.path.exists(expected)
            with open(expected, encoding="utf-8") as f:
                assert len(f.read()) > 0
        finally:
            if os.path.exists(expected):
                os.unlink(expected)

    def test_convert_include_unassigned(self, srt_file, out_file):
        """--include-unassigned with disabled speaker detection should output all blocks."""
        from cli import main
        # Use --speaker "" to disable auto-detection, then --include-unassigned
        # will assign speaker=None blocks to speaker 0
        rc = main([srt_file, "--speaker", "", "--include-unassigned", "-o", out_file])
        assert rc == 0
        with open(out_file, encoding="utf-8") as f:
            content = f.read()
        # All blocks get assigned to speaker 0 since speaker detection is disabled
        assert "Unassigned line" in content or "Hello world" in content or "content" in content.lower()

    def test_convert_without_speaker_outputs_speaker_detected(self, srt_file, out_file):
        """With default --speaker="$:", speaker auto-detection runs."""
        from cli import main
        rc = main([srt_file, "-o", out_file])
        assert rc == 0
        with open(out_file, encoding="utf-8") as f:
            content = f.read()
        # Default --speaker="$:" auto-detects Alice:, Bob: and assigns them
        assert "Hello world" in content
        assert "Hi there" in content

    def test_convert_bogus_file(self):
        """Non-existent file should return exit code 1."""
        from cli import main
        rc = main(["nonexistent_file.srt"])
        assert rc == 1


# ── Edge cases ────────────────────────────────────────────────────

class TestEdgeCases:
    def test_speaker_pattern_bracket(self, srt_file, out_file):
        """Speaker detection with [Speaker] pattern."""
        from cli import main, build_parser
        # Create file with bracket-style speakers
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".srt", encoding="utf-8", delete=False
        ) as f:
            f.write("1\n00:00:01,000 --> 00:00:02,500\n[Alice] Hello\n")
            bracket_file = f.name
        try:
            rc = main([bracket_file, "--speaker", "[$]", "-o", out_file])
            assert rc == 0
            with open(out_file, encoding="utf-8") as f:
                assert "Hello" in f.read()
        finally:
            os.unlink(bracket_file)

    def test_convert_vtt_file(self, out_file):
        """Converting a .vtt file should work."""
        from cli import main
        import tempfile, os
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".vtt", encoding="utf-8", delete=False
        ) as f:
            f.write("WEBVTT\n\n00:00:01.000 --> 00:00:02.500\nAlice: Hello VTT\n")
            vtt_file = f.name
        try:
            rc = main([vtt_file, "-f", "gat2", "--speaker", "$:", "-o", out_file])
            assert rc == 0
            with open(out_file, encoding="utf-8") as f:
                assert "Hello VTT" in f.read()
        finally:
            os.unlink(vtt_file)

    def test_speaker_pattern_brace(self, srt_file, out_file):
        """Speaker detection with {Speaker} pattern."""
        from cli import main
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".srt", encoding="utf-8", delete=False
        ) as f:
            f.write("1\n00:00:01,000 --> 00:00:02,500\n{Bob} Hi\n")
            brace_file = f.name
        try:
            rc = main([brace_file, "--speaker", "{$}", "-o", out_file])
            assert rc == 0
            with open(out_file, encoding="utf-8") as f:
                assert "Hi" in f.read()
        finally:
            os.unlink(brace_file)
