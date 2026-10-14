import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';
import { commandFor, root } from '../scripts/npm.mjs';

test('Windows deployment passes paths and modes as separate PowerShell arguments', () => {
  const project = resolve('/tmp/print3d project');
  const result = commandFor('reconfigure', 'win32', project);
  assert.equal(result.command, 'powershell.exe');
  assert.deepEqual(result.args.slice(-4), ['-File', resolve(project, 'scripts/deploy_windows.ps1'), '-Mode', 'reconfigure']);
});

test('Linux deployment supports setup/start/configure/build/backend tests', () => {
  for (const mode of ['install', 'start', 'reconfigure', 'build', 'test']) {
    assert.deepEqual(commandFor(mode, 'linux'), {
      command: 'bash', args: [resolve(root, 'scripts/deploy.sh'), mode]
    });
  }
});

test('Unsupported modes and operating systems fail before spawning services', () => {
  assert.throws(() => commandFor('start; echo unsafe', 'linux'), /Use npm/);
  assert.throws(() => commandFor('start', 'darwin'), /supports Windows/);
});

test('CLI rejects missing or unexpected arguments', () => {
  for (const args of [[], ['invalid'], ['start', 'unexpected']]) {
    const result = spawnSync(process.execPath, ['scripts/npm.mjs', ...args], { cwd: root, encoding: 'utf8' });
    assert.equal(result.status, 1);
    assert.ok(result.stderr.length > 0);
  }
});
