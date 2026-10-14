"""Build a shareable archive from an explicit source allowlist."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
FILES = ['package.json', 'package-lock.json', 'scripts/npm.mjs', 'tests/npm.test.mjs', 'LICENSE', 'README.md', 'README.zh-CN.md', 'docs/OPERATIONS.md', 'docs/TUTORIAL.zh-CN.md', 'docs/TUTORIAL.en.md',
         '.env.example', '.gitignore', 'requirements.txt', 'requirements-test.txt',
         'pyproject.toml', 'manage.py', 'auto_setup.py', 'deploy_print3d.bat',
         'scripts/deploy.sh', 'scripts/deploy_windows.ps1',
         'scripts/install_dependencies.sh', 'scripts/config_helpers.py',
         'scripts/run_local.py', 'scripts/build_release.py',
         'deploy/print3d.service', 'tests/test_system.py', 'tests/test_autodeploy.py']
FILES += [str(p.relative_to(ROOT)) for p in sorted((ROOT / 'app').glob('*.py'))]


def build():
    target = ROOT / 'dist/print3d-autodeploy.zip'
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, 'print3d/' + name)
    with ZipFile(target) as archive:
        assert archive.testzip() is None
        for name in archive.namelist():
            path = Path(name)
            assert path.name != '.env' and path.suffix not in {'.sqlite3', '.db', '.log', '.pyc'}
            assert path.name != 'ConfigurePrint3D.gs'
    print(f'Created {target.name}: {len(FILES)} source files; private runtime files excluded.')
    return target


if __name__ == '__main__':
    build()
