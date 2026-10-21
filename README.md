# Touchdown-File-System-Journaling-and-Crash-Recovery-Simulator
A solo Operating Systems mini-project with a light sage-and-cream interface. Create text files on a virtual disk, pause after individual persistent writes, inject a crash, and recover committed transactions from a redo journal. Everything runs locally, including the interface; no CDN, account, database, administrator access or pip packages required.

## Requirements

- Python 3.9 or newer, with its standard library.
- A modern browser (Chrome, Edge, Firefox or Safari).
- macOS, Windows or Linux.

## Start on macOS / Linux

Extract the ZIP. Open the `Touchdown` folder in VS Code, choose Terminal → New Terminal, then run:

```bash
python3 app.py
```

The app opens at **http://127.0.0.1:8000**. If it does not open automatically, paste that address into your browser. Stop the server with Ctrl+C.

Optional macOS launcher from Terminal:

```bash
bash start_mac_linux.sh
```

## Start on Windows (PowerShell)

Extract the ZIP first. Open the `Touchdown` folder in VS Code, choose Terminal → New Terminal, then run:

```powershell
py app.py
```

If `py` is unavailable but `python` works:

```powershell
python app.py
```

You can also double-click `start_windows.bat`. Python must already be installed. No execution-policy change is required.

## If port 8000 is occupied

```bash
python3 app.py --port 8001
```

Windows: use `py app.py --port 8001`. Open http://127.0.0.1:8001.

## What is included

- Create, read, edit and delete UTF-8 text files.
- 48-block virtual disk, with 32 bytes per block (1,536 bytes total).
- Metadata: filename, byte size, block pointers and SHA-256 checksum.
- Persistent redo journal with BEGIN, LOG, COMMIT and CHECKPOINT records.
- Journal-enabled and journal-disabled comparison modes.
- Step execution, run-to-completion, crash injection and explicit recovery.
- File-content/size and block-allocation consistency checks.
- Block inspection, journal viewer and event timeline.
- Recovery after an actual server restart during a staged transaction.
- JSON experiment-report export and a sandbox reset control.
- Automated failure-boundary and HTTP integration tests.
- Demo script and project explanation for review/viva.

## How to use it

1. Choose an operation and filename. For create/edit, enter text.
2. Click **Stage operation**. This prepares the plan, without changing file data.
3. Click **Next step** to execute exactly one persistent-write stage, or **Run to completion**.
4. During an operation, click **Simulate crash**. Further writes stop.
5. Click **Recover disk**. Recovery uses durable journal entries, not the saved pending plan.
6. Inspect file contents, disk health, blocks, journal and events.

The live consistency display may temporarily say “Inconsistent” between DATA and METADATA, even with journaling enabled. This is intentional: data and metadata are installed in separate simulated writes; the committed journal makes interrupted installation recoverable.

## Demo

See **DEMO_GUIDE.md** for exact click sequences and expected results. The interface also includes a short guide with example-fill buttons.

## Persistence

On first launch the app creates `data/` next to `app.py`:

- `disk.json`: virtual block contents and file metadata.
- `journal.jsonl`: append-only redo records; LOG stores the full intended after-image.
- `control.json`: interface state, pending step, settings and event history.

Refreshing the page does not reset data. Restarting Python with an unfinished transaction puts the simulator in crashed state and requires recovery. Reset sandbox clears only these simulator records. File names are virtual keys, never paths to files on your computer.

Use a different sandbox directory if wanted:

```bash
python3 app.py --data-dir my_experiment
```

Use one server process per data directory. Requests within one server are serialized. Multiple browser tabs share that same disk; refresh another tab after making changes.

## Run tests

From inside `Touchdown`:

```bash
python3 -m unittest discover -s tests -v
```

Windows:

```powershell
py -m unittest discover -s tests -v
```

The suite covers all 18 pre-completion crash boundaries across create/edit/delete, fresh-engine restart recovery, ignoring an altered pending plan, multiple recovery rounds, unjournaled inconsistency, Unicode, empty files, capacity, input validation and HTTP routes. Temporary test disks are independent of your demo data.

## Project structure

```text
Touchdown/
  app.py                   Local HTTP server and API
  engine.py                Virtual disk, transactions, journal and recovery
  static/index.html        Interface
  static/style.css         Light theme and responsive layout
  static/app.js            UI events, state rendering and export
  tests/test_recovery.py   Recovery and integration tests
  start_windows.bat        Windows launcher
  start_mac_linux.sh       macOS/Linux launcher
  README.md                Setup and usage
  DEMO_GUIDE.md            Presentation steps
  PROJECT_NOTES.md         Architecture, algorithm, scope and viva answers
```

## Scope

This is a working educational simulation, not a mounted filesystem, kernel module or host-file recovery tool. It demonstrates full data-plus-metadata redo journaling; it does not model every journaling mode used by real filesystems. Crash injection happens between completed simulated stages, not at arbitrary physical disk sectors. Files are text-only, operations run one at a time, and allocation uses a compact deterministic layout. See PROJECT_NOTES.md for the assumptions behind durability and recovery.
