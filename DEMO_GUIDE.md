# Touchdown — Demo Guide

Start the app and keep the terminal open. Use the browser interface. All resets below affect only the virtual sandbox.

## Demo 1: Normal operation (about 30 seconds)

1. Click **Reset sandbox**, then confirm.
2. Leave **Enable journaling** checked.
3. Select Create, filename `notes.txt`, contents `OS project`.
4. Click **Stage operation**, then **Run to completion**.
5. Show one allocated block, a healthy disk, and journal records BEGIN, LOG, COMMIT, CHECKPOINT.
6. Click the file to inspect its contents, or click block 00.

Say: “This text file is stored on a simulated disk. Its metadata contains the block pointers, size and checksum. The journal records the operation before the data is installed.”

## Demo 2: Crash before commit (about 40 seconds)

1. Click `notes.txt`; the form switches to Edit.
2. Change contents to `OS project completed` and click **Stage operation**.
3. Click **Next step** exactly twice: BEGIN, then LOG.
4. Click **Simulate crash**, then **Recover disk**.
5. Click the file. It still contains `OS project`.
6. Show the DISCARD journal record and recovery event.

Say: “There was no commit record, so recovery discarded the incomplete transaction. No data blocks had been modified, so the original file remains intact.”

## Demo 3: Crash after commit (about 50 seconds)

1. Edit `notes.txt` again to `OS project completed` and stage it.
2. Click **Next step** exactly four times: BEGIN, LOG, COMMIT, DATA.
3. The disk can now show a consistency issue because the old metadata has not been updated.
4. Click **Simulate crash**, then **Recover disk**.
5. Show the REDO event, checkpoint record, healthy disk, and updated contents.

Say: “The commit record made the logged after-image recoverable. Recovery replayed both the data and metadata from the journal, completing the interrupted transaction.”

## Demo 4: Compare without journaling (about 50 seconds)

1. Reset the sandbox. Uncheck **Enable journaling**.
2. Create `notes.txt` containing `OS project`, and run to completion.
3. Edit it to `OS project completed`, then stage the edit.
4. Click **Next step** exactly once: DATA.
5. Click **Simulate crash**, then **Recover disk**.
6. Show that a consistency issue remains. The journal is empty, and new operations are blocked until reset.

Say: “The data was changed but the metadata was not. Without a durable record of the intended operation, restart cannot reconstruct the correct final state.”

Note: the old file size is ten bytes, while the updated block contains twenty bytes. This makes the metadata/data mismatch visible even though both versions start with the same words. Recovery does not fabricate a fix without evidence.

## Optional: Prove persistence across a Python restart

1. Reset and create the baseline normally with journaling enabled.
2. Stage an edit; execute BEGIN, LOG, COMMIT.
3. Press Ctrl+C in the server terminal.
4. Run `python3 app.py` again (Windows: `py app.py`). Refresh the browser.
5. The simulator shows a crashed unfinished operation. Click **Recover disk**.
6. Verify the committed update is restored.

Do this only after practicing it; the crash button is enough for the core presentation.

## Export evidence

After a useful scenario, select **Export report**. It downloads JSON containing file contents and metadata, blocks, consistency findings, events, journal record types, settings and counters. Export each comparison before resetting, because Reset clears history. The exported report summarizes the journal; the full after-images remain in `data/journal.jsonl`.

## Common presentation questions

- Why not recover uncommitted changes? There is no durable promise that they should become visible.
- Is the pending plan used for recovery? No. It supports step controls only. Recovery reads the disk and committed journal records.
- Why is there temporary inconsistency? Installation has two writes: data first, metadata second. The durable journal bridges that interval.
- What if a crash occurs immediately after COMMIT, before DATA? Replay installs the complete logged result.
- Is it a real operating system filesystem? It is a persistent user-space simulator of filesystem concepts, not a kernel filesystem driver.
