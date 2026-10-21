# Touchdown: File System Journaling and Crash Recovery Simulator

## Abstract

Interrupted file operations can leave file data and metadata inconsistent. Touchdown is an interactive simulator that demonstrates this problem and a redo-journaling solution. It models a block-based virtual disk, records intended changes in a persistent journal, allows interruption between write stages, and replays committed transactions during recovery. A browser dashboard displays the disk, files, journal and consistency checks. Journal-enabled and journal-disabled executions provide a controlled comparison for an Operating Systems demonstration.

## Problem statement

A file operation may require multiple writes. If execution stops after data blocks change but before metadata is updated, a restart alone cannot always infer the intended state. The project demonstrates how a write-ahead journal preserves enough information to complete committed operations.

## Objectives

1. Model files, block allocation and filesystem metadata.
2. Implement write-ahead, full data-and-metadata redo journaling.
3. Inject crashes at deterministic transaction boundaries.
4. Recover committed operations while discarding incomplete transactions.
5. Visualize the difference between journaled and unjournaled execution.
6. Verify contents and allocation after recovery.

## Architecture

| Component | Responsibility |
|---|---|
| Browser UI | Forms, step controls, disk visualization, logs and report download |
| Python HTTP server | Local routes, input handling and serialized engine access |
| Virtual filesystem engine | File operations, allocation, checksums, transaction stages and recovery |
| disk.json | Persistent disk image: block array and metadata map |
| journal.jsonl | Durable append-only redo records |
| control.json | Pending UI state, settings, counters and event history |

Only the disk image and redo journal determine the recovered filesystem contents. The control file determines whether the UI should offer recovery; its pending after-image is not replayed.

## Data model

The disk has 48 blocks of 32 bytes each. Block contents are stored as hex-encoded UTF-8 bytes in JSON. A file metadata record contains its name (dictionary key), byte size, ordered block IDs and SHA-256 hash. Empty files use zero blocks. Each operation builds a complete after-image using a compact, filename-sorted layout. This simplified allocator can move other files; every affected block and metadata record is included in the same logged after-image.

Checks detect missing blocks, duplicate ownership, orphan allocated blocks, size differences and checksum differences. A check may report temporary inconsistency while data installation has completed but metadata installation has not.

## Journaled transaction stages

| Stage | Persistent action | If a crash follows |
|---|---|---|
| BEGIN | Append transaction ID and start marker | Discard incomplete transaction |
| LOG | Append full intended disk after-image | Discard; current disk unchanged |
| COMMIT | Append and flush commit marker | Replay after-image |
| DATA | Install new block contents | Replay after-image |
| METADATA | Install file metadata | Replay is safe and idempotent |
| CHECKPOINT | Mark completed disk installation | Skip already completed transaction |

Without journaling, the stages are DATA, METADATA and FINISH. A crash after DATA can leave an inconsistent disk. A crash before any write leaves the old state; a crash after both disk writes can leave a healthy state even without a journal. Journaling protects the vulnerable interval; it does not mean every unjournaled crash necessarily corrupts data.

## Recovery algorithm

1. Read journal records in append order.
2. Group records by transaction ID, retaining transaction order.
3. Skip checkpointed or previously discarded transactions.
4. If a complete LOG and COMMIT exist, replace the disk image with the logged after-image and save it, then append CHECKPOINT.
5. Otherwise append DISCARD, leaving the disk unchanged.
6. Clear the pending operation and crashed flag, then check consistency.

No undo log is needed: the engine does not install uncommitted data. Replaying an after-image twice has the same filesystem result as replaying it once. A checkpoint is appended only after both disk components are installed. Recovery does not use the pending plan stored in control.json.

## Persistence and crash assumptions

Journal appends flush Python buffers and call fsync. Disk and control writes use a temporary JSON file, flush plus fsync, and atomic replacement. This is sufficient for the modeled, stage-boundary crashes and the tested Python process restarts. It does not claim protection against all host power failures: directory-entry durability, device write caches, torn-sector behavior, arbitrary external JSON corruption, and hardware barriers are not modeled. There is no automatic repair for an unjournaled inconsistency; reset is the explicit way to restore the sandbox.

The journal retains completed history for teaching. It is not compacted, so long-running use can grow the log. Run one server process per sandbox directory. The HTTP server binds only to 127.0.0.1 and serializes mutation requests inside that process. This is a local teaching application rather than a public production service.

## OS concepts demonstrated

- File systems and file metadata.
- Block allocation and free-space tracking.
- Persistent versus transient state.
- Write-ahead logging and redo recovery.
- Transaction commit boundaries and atomic recovery behavior.
- Crash consistency and idempotence.

This is full data-plus-metadata journaling. Do not describe it as an implementation of ext4, NTFS or their exact journaling policies.

## Testing

Run `python3 -m unittest discover -s tests -v` (Windows: `py -m unittest discover -s tests -v`). Tests exercise all 18 unfinished-stage boundaries across create/edit/delete, restart persistence, recovery independent of pending after-images, repeated recovery cycles, missing-journal inconsistency, Unicode/empty files, disk capacity, virtual filename validation and HTTP routing. Test disks are created in temporary folders.

## Limitations

- Educational virtual disk; not mounted and not usable as a host-file recovery utility.
- Small fixed capacity and text-only files; no directory hierarchy or permissions.
- One operation at a time; no concurrent filesystem transactions.
- Full after-image logging favors clarity over efficiency.
- Crashes are modeled between complete stage writes.
- SHA-256 verifies simulated content consistency; it is not an error-correcting mechanism.
- No disk scheduling, page replacement or CPU scheduling component.

## Possible future work

Incremental block journaling, checkpoint compaction, metadata-only journaling comparison, directory support, measured write-amplification counters, and crash injection during partial record writes.

## Short viva answers

**What is journaling?** Recording planned filesystem updates in a durable log so interrupted operations can be resolved after a crash.

**What is write-ahead logging?** Flushing the required log records before the corresponding changes are installed on the disk.

**What does COMMIT mean here?** The logged transaction should survive a crash and can be replayed, even if the main disk image has not yet been updated.

**What is a checkpoint?** A record that confirms the transaction has been fully installed on the disk; recovery can skip it.

**Does journaling prevent crashes?** No. It provides a way to restore a consistent committed state after a crash.

**Why use checksums?** A file may still have block pointers while its data no longer matches the metadata. A hash detects changed contents; size checks detect extra or missing bytes.

**Why Python instead of C?** The project focuses on modeling and demonstrating filesystem recovery semantics. Python provides portable persistence and local UI support without kernel privileges.
