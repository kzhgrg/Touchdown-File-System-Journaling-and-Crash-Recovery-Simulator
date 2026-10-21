"""Educational redo-journal filesystem. Only files inside data_dir are touched."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
from datetime import datetime, timezone

BLOCKS = 48
BLOCK_SIZE = 32


def atomic_json(path, obj):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class FileSystem:
    def __init__(self, data_dir):
        self.root = Path(data_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.disk_path = self.root / 'disk.json'
        self.wal_path = self.root / 'journal.jsonl'
        self.control_path = self.root / 'control.json'
        if not self.disk_path.exists():
            self.reset()
        self.disk = json.loads(self.disk_path.read_text(encoding='utf-8'))
        self.control = json.loads(self.control_path.read_text(encoding='utf-8'))
        # A Python/server restart during a transaction is also a simulated crash.
        if self.control.get('pending'):
            self.control['crashed'] = True
            self.log('Server restarted during an operation. Recovery is required.')
            self.save_control()

    def reset(self):
        self.disk = {'blocks': [None] * BLOCKS, 'files': {}}
        self.control = {'mode': True, 'crashed': False, 'pending': None, 'events': [],
                        'stats': {'completed': 0, 'crashes': 0, 'recoveries': 0, 'replayed': 0}}
        atomic_json(self.disk_path, self.disk)
        self.wal_path.write_text('', encoding='utf-8')
        self.log('Fresh virtual disk ready. Journaling is enabled.')
        self.save_control()

    def log(self, message):
        self.control['events'].append({'time': datetime.now(timezone.utc).strftime('%H:%M:%S'), 'message': message})
        self.control['events'] = self.control['events'][-100:]

    def save_control(self):
        atomic_json(self.control_path, self.control)

    def save_disk(self):
        atomic_json(self.disk_path, self.disk)

    def journal(self):
        entries = []
        for line in self.wal_path.read_text(encoding='utf-8').splitlines():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                # Ignore an incomplete trailing log record; no COMMIT means no replay.
                break
        return entries

    def append(self, entry):
        with self.wal_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())

    def content(self, name):
        meta = self.disk['files'][name]
        return b''.join(bytes.fromhex(self.disk['blocks'][i] or '') for i in meta['blocks'])[:meta['size']]

    def check(self):
        issues, owners = [], {}
        for name, meta in self.disk['files'].items():
            raw = b''.join(bytes.fromhex(self.disk['blocks'][i] or '') for i in meta['blocks'])
            if len(raw) != meta['size'] or digest(raw) != meta['sha256']:
                issues.append(f'{name}: file contents do not match its metadata checksum/size.')
            for i in meta['blocks']:
                if i in owners:
                    issues.append(f'Block {i} is shared by {owners[i]} and {name}.')
                owners[i] = name
                if self.disk['blocks'][i] is None:
                    issues.append(f'{name}: referenced block {i} is empty.')
        for i, value in enumerate(self.disk['blocks']):
            if value is not None and i not in owners:
                issues.append(f'Block {i} is allocated but has no file owner (orphan).')
        return issues

    def plan(self, op, name, content):
        if op not in ('create', 'edit', 'delete'):
            raise ValueError('Choose create, edit, or delete.')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,39}', name):
            raise ValueError('Use a filename of 1–40 letters, digits, dots, underscores or hyphens; start with a letter or digit.')
        if op == 'create' and name in self.disk['files']:
            raise ValueError('That file already exists.')
        if op != 'create' and name not in self.disk['files']:
            raise ValueError('That file does not exist.')
        if not isinstance(content, str):
            raise ValueError('File contents must be text.')
        files = {n: self.content(n) for n in self.disk['files']}
        if op == 'delete':
            del files[name]
        else:
            files[name] = content.encode('utf-8')
        # A compact deterministic layout keeps the block visualization easy to follow.
        after = {'blocks': [None] * BLOCKS, 'files': {}}
        cursor = 0
        for n, raw in sorted(files.items()):
            chunks = [raw[i:i + BLOCK_SIZE] for i in range(0, len(raw), BLOCK_SIZE)]
            if cursor + len(chunks) > BLOCKS:
                raise ValueError(f'Virtual disk full. Capacity is {BLOCKS * BLOCK_SIZE} bytes, in {BLOCK_SIZE}-byte blocks.')
            ids = list(range(cursor, cursor + len(chunks)))
            after['files'][n] = {'blocks': ids, 'size': len(raw), 'sha256': digest(raw)}
            for i, chunk in zip(ids, chunks):
                after['blocks'][i] = chunk.hex()
            cursor += len(chunks)
        return after

    def start(self, op, name, content=''):
        self.require_ready()
        if self.check():
            raise ValueError('Disk is inconsistent. Reset the sandbox before starting another operation.')
        after = self.plan(op, name, content)
        stages = (['BEGIN', 'LOG', 'COMMIT', 'DATA', 'METADATA', 'CHECKPOINT']
                  if self.control['mode'] else ['DATA', 'METADATA', 'FINISH'])
        self.control['pending'] = {'id': uuid.uuid4().hex[:12], 'op': op, 'name': name,
                                   'after': after, 'index': 0, 'stages': stages, 'journaled': self.control['mode']}
        self.log(f'Staged {op} for {name}. Use Next step, or Run to completion.')
        self.save_control()

    def require_ready(self):
        if self.control['crashed']:
            raise ValueError('Recover the crashed disk first.')
        if self.control['pending']:
            raise ValueError('Finish or crash the current operation first.')

    def step(self):
        if self.control['crashed']:
            raise ValueError('Recover the crashed disk first.')
        p = self.control['pending']
        if not p:
            raise ValueError('Stage an operation first.')
        stage = p['stages'][p['index']]
        tx = {'tx': p['id'], 'type': stage}
        if stage == 'LOG':
            tx['after'] = p['after']
        if stage in ('BEGIN', 'LOG', 'COMMIT', 'CHECKPOINT'):
            self.append(tx)
        if stage == 'DATA':
            self.disk['blocks'] = copy.deepcopy(p['after']['blocks'])
            self.save_disk()
        elif stage == 'METADATA':
            self.disk['files'] = copy.deepcopy(p['after']['files'])
            self.save_disk()
        explanations = {'BEGIN': 'Transaction start saved to journal.',
                        'LOG': 'Complete data + metadata after-image flushed to journal.',
                        'COMMIT': 'Commit record flushed. Recovery can now replay this operation.',
                        'DATA': 'New data blocks written to the virtual disk.',
                        'METADATA': 'File names, block pointers, sizes and checksums updated.',
                        'CHECKPOINT': 'Disk installation finished; checkpoint recorded.',
                        'FINISH': 'Operation finished without a journal.'}
        self.log(f'{stage}: {explanations[stage]}')
        p['index'] += 1
        if p['index'] == len(p['stages']):
            self.control['pending'] = None
            self.control['stats']['completed'] += 1
        self.save_control()

    def run(self):
        if not self.control['pending']:
            raise ValueError('Stage an operation first.')
        while self.control['pending']:
            self.step()

    def crash(self):
        if self.control['crashed']:
            raise ValueError('The simulator is already crashed.')
        if not self.control['pending']:
            raise ValueError('Stage an operation before simulating a crash.')
        self.control['crashed'] = True
        self.control['stats']['crashes'] += 1
        self.log('CRASH: execution stopped. Disk and journal bytes are preserved.')
        self.save_control()

    def recover(self):
        if not self.control['crashed']:
            raise ValueError('Simulate a crash before recovery.')
        # Recovery intentionally does not use pending.after: only durable journal records.
        entries = self.journal()
        order, groups = [], {}
        for e in entries:
            txid = e['tx']
            if txid not in groups:
                groups[txid] = []
                order.append(txid)
            groups[txid].append(e)
        for txid in order:
            records = groups[txid]
            types = [r['type'] for r in records]
            if 'CHECKPOINT' in types or 'DISCARD' in types:
                continue
            logged = next((r for r in records if r['type'] == 'LOG'), None)
            if 'COMMIT' in types and logged:
                self.disk = copy.deepcopy(logged['after'])
                self.save_disk()
                self.append({'tx': txid, 'type': 'CHECKPOINT'})
                self.control['stats']['replayed'] += 1
                self.log(f'REDO {txid}: committed after-image replayed; checkpoint recorded.')
            else:
                self.append({'tx': txid, 'type': 'DISCARD'})
                self.log(f'DISCARD {txid}: no complete committed transaction; old disk retained.')
        p = self.control.get('pending')
        if p and not p['journaled']:
            self.log('No journal for this operation. Restart cannot reconstruct its intended changes.')
        self.control['pending'] = None
        self.control['crashed'] = False
        self.control['stats']['recoveries'] += 1
        issues = self.check()
        self.log('Recovery finished. ' + (f'{len(issues)} consistency issue(s) remain.' if issues else 'Disk consistency check passed.'))
        self.save_control()

    def set_mode(self, enabled):
        self.require_ready()
        if not isinstance(enabled, bool):
            raise ValueError('Journaling mode must be true or false.')
        self.control['mode'] = enabled
        self.log('Journaling ' + ('enabled.' if enabled else 'disabled.'))
        self.save_control()

    def state(self):
        owners = {i: name for name, m in self.disk['files'].items() for i in m['blocks']}
        p = copy.deepcopy(self.control['pending'])
        if p:
            p.pop('after')
        entries = [{k: v for k, v in e.items() if k != 'after'} for e in self.journal()]
        return {'mode': self.control['mode'], 'crashed': self.control['crashed'], 'pending': p,
                'files': [{'name': n, **m, 'content': self.content(n).decode('utf-8', errors='replace')}
                          for n, m in sorted(self.disk['files'].items())],
                'blocks': [{'id': i, 'allocated': b is not None, 'owner': owners.get(i),
                            'text': bytes.fromhex(b or '').decode('utf-8', errors='replace')}
                           for i, b in enumerate(self.disk['blocks'])],
                'issues': self.check(), 'events': self.control['events'], 'journal': entries,
                'stats': self.control['stats'], 'capacity': BLOCKS * BLOCK_SIZE, 'block_size': BLOCK_SIZE,
                'used': sum(b is not None for b in self.disk['blocks'])}
