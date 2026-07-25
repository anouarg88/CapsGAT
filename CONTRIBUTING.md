# Contributing to CapsQual

Thank you for your interest in contributing to CapsQual! Whether you are reporting a bug, suggesting a feature, or opening a pull request, your help is appreciated. This document outlines a straightforward workflow to keep things consistent.

---

## Table of Contents

- [How to Report Issues](#how-to-report-issues)
- [Feature Requests](#feature-requests)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Code Style](#code-style)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)

---

## How to Report Issues

Before opening an issue, please search the [existing issues](https://github.com/anouarg88/CapsQual/issues) to avoid duplicates.

### Bug Reports

When filing a bug report, please include:

- **A clear title** summarizing the problem.
- **Steps to reproduce** — what did you do, what happened, and what did you expect?
- **Your environment** — operating system and version, Python version, CapsQual version, and (if audio was involved) whether VLC is installed.
- **Log output or screenshots**, if relevant.
- **If available: a minimal example file** that triggers the bug (attach an `.srt`, `.json`, etc.).

### Feature Requests

Describe the feature you would like to see in CapsQual, why the current behaviour is insufficient, and — if possible — how you imagine it working. Mock-ups or references to similar tools are also helpful.

---

## Development Setup

### Prerequisites

- **Python 3.9 or later**
- **Git**
- **(Recommended) VLC media player** for audio playback speed control

### 1. Fork & Clone

```bash
git clone https://github.com/anouarg88/CapsQual.git
cd CapsQual
```

### 2. Create a Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```
(If this step fails see installation section in README.md)


### 4. Install Test Dependencies (optional, for running tests)

```bash
pip install pytest pytest-qt pytest-timeout
```

### 5. Run the Application

```bash
python main.py
```

---

## Making Changes

### Branch Naming

Use short, descriptive branch names prefixed by category:

| Prefix | Example |
|--------|---------|
| `fix/` | `fix/waveform-crash-on-empty` |
| `feat/` | `feat/json-import-v2` |
| `docs/` | `docs/update-readme-screenshots` |
| `refactor/` | `refactor/extract-parsers` |
| `test/` | `test/add-cli-coverage` |

### Commit Messages

Write commit messages in the **imperative present tense**:

```
Fix waveform viewer reset when unloading audio
```

Not: *"Fixed waveform viewer..."* or *"Fixes waveform viewer..."*

Keep the first line under 72 characters. Add a more detailed body after a blank line if the change needs explanation.

### Architecture Reference

Before making changes, take a moment to read [`architecture.md`](architecture.md) — it maps out every module, the data flow, and known cross-cutting risks. This will help you understand where your change fits and avoid unintended ripple effects.

---

## Code Style

- **Python**: follow [PEP 8](https://peps.python.org/pep-0008/). Use 4 spaces for indentation (no tabs).
- **Imports**: group standard library, third-party, and local imports with a blank line between groups.
- **Naming**: `snake_case` for functions and variables, `PascalCase` for classes, `UPPER_CASE` for constants.
- **Type hints**: encouraged for function signatures, especially in public APIs.
- **Qt / PyQt5**: connect signals using the new-style syntax (`signal.connect(slot)`) rather than old-style string-based connections.

When in doubt, match the style of the surrounding code.

---

## Testing

Run the full test suite from the project root:

```bash
python -m pytest tests/ -v
```

### Test Structure

| File | What it covers |
|------|----------------|
| `tests/test_export.py` | GAT2, TiQ, Dresing & Pehl, and SRT generation |
| `tests/test_parsing.py` | SRT, VTT, JSON, TSV, TXT parsing |
| `tests/test_cli.py` | Command-line workflow, speaker detection, format conversions |
| `tests/test_ui.py` | Timestamp formatting, time conversion, misc utilities |

### Before Submitting

- Add or update tests for any changed behaviour.
- Make sure the existing tests still pass.
- If you add a new feature without tests, explain why in the pull request.

---

## Pull Request Process

1. **Discuss first** — Even if it is a trivial fix, open an issue or comment on an existing one before writing code or implementing a change. This saves wasted effort.
2. **Keep it focused** — one pull request per logical change. Avoid mixing refactoring with new features.
3. **Write tests** for new functionality and ensure all tests pass.
4. **Update documentation** if you change user-facing behavior (README, architecture.md, CLI help text, etc.).
5. **Link the issue** your PR addresses in the description (e.g., `Closes #42`).
6. **Rebase** your branch onto the latest `main` before submitting to keep the history clean.
7. **Respond to review feedback** — reviewers may ask for changes before merging.

### Checklist Before Opening

- [ ] Opened or commented on issue.
- [ ] Code compiles and runs (`python main.py`)
- [ ] Tests pass (`python -m pytest tests/ -v`)
- [ ] New tests cover the changed behavior
- [ ] Documentation updated if needed (README, `architecture.md`, CLI help, etc.)
- [ ] No unrelated changes sneaked in

---

## Need Help?

If you're unsure about anything, open a [Discussion](https://github.com/anouarg88/CapsQual/discussions) or ask in an issue. No question is too small.
