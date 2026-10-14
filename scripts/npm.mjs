import { spawn } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const modes = new Set(['install', 'start', 'reconfigure', 'build', 'test']);

export function commandFor(mode, platform = process.platform, project = root) {
  if (!modes.has(mode)) throw new Error('Use npm run setup, npm start, npm run configure, npm run build or npm run test:backend.');
  if (platform === 'win32') {
    return { command: 'powershell.exe', args: ['-NoProfile', '-ExecutionPolicy', 'Bypass',
      '-File', resolve(project, 'scripts/deploy_windows.ps1'), '-Mode', mode] };
  }
  if (platform === 'linux') return { command: 'bash', args: [resolve(project, 'scripts/deploy.sh'), mode] };
  throw new Error('Deployment supports Windows with WSL2, or Ubuntu/Debian Linux.');
}

export function run(mode) {
  const { command, args } = commandFor(mode);
  const child = spawn(command, args, { cwd: root, stdio: 'inherit', shell: false,
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } });
  // On Windows the console delivers Ctrl+C to PowerShell/WSL. Killing PowerShell
  // forcefully would prevent the Python supervisor from cleaning up its services.
  const forward = signal => { if (process.platform !== 'win32') child.kill(signal); };
  const interrupt = () => forward('SIGINT');
  const terminate = () => forward('SIGTERM');
  process.on('SIGINT', interrupt);
  process.on('SIGTERM', terminate);
  child.once('error', error => {
    console.error(`Cannot launch deployment (${error.code ?? 'error'}). Check Bash/WSL or Windows PowerShell installation.`);
    process.exitCode = 1;
  });
  child.once('close', (code, signal) => {
    process.removeListener('SIGINT', interrupt);
    process.removeListener('SIGTERM', terminate);
    process.exitCode = code ?? (signal === 'SIGINT' ? 130 : 1);
  });
  return child;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    if (process.argv.length !== 3) throw new Error('Choose a command through npm run.');
    run(process.argv[2]);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
