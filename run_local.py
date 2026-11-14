"""Start the local demo with one Flask server; run from any working directory."""
import argparse
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

def persistent_secret(directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / '.local-secret'
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text().strip()
    value = secrets.token_hex(32)
    with os.fdopen(fd, 'w') as handle:
        handle.write(value)
    return value

def main():
    parser = argparse.ArgumentParser(description='Локальный запуск HackFlow без Docker')
    parser.add_argument('--port', type=int, default=5050)
    parser.add_argument('--skip-build', action='store_true', help='Использовать уже собранный frontend')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Порт должен быть от 1 до 65535')
    if not args.skip_build:
        npm = shutil.which('npm')
        if not npm:
            parser.exit(1, 'Установите Node.js 22 LTS, затем снова запустите команду.\n')
        if not (ROOT / 'frontend/node_modules').exists():
            subprocess.run([npm, 'ci'], cwd=ROOT / 'frontend', check=True)
        subprocess.run([npm, 'run', 'build'], cwd=ROOT / 'frontend', check=True)
    if not (ROOT / 'frontend/dist/index.html').is_file():
        parser.exit(1, 'Сборка frontend не найдена. Запустите без --skip-build.\n')
    os.environ.setdefault('SECRET_KEY', persistent_secret(ROOT / 'backend/instance'))
    os.environ.setdefault('DATABASE_URL', 'sqlite:///hackflow.db')
    os.environ.setdefault('FRONTEND_ORIGIN', f'http://localhost:{args.port}')
    sys.path.insert(0, str(ROOT / 'backend'))
    try:
        from app import create_app, seed_data
        from flask_migrate import upgrade
    except ImportError:
        parser.exit(1, 'Активируйте .venv и выполните pip install -r backend/requirements.txt\n')
    app = create_app()
    with app.app_context():
        upgrade(directory=str(ROOT / 'backend/migrations'))
        seed_data()
    print(f'\nHackFlow: http://localhost:{args.port}', flush=True)
    print('Капитан: captain@hackflow.local / HackFlow2026!', flush=True)
    print('Новые аккаунты должны получить допуск у организатора.\n', flush=True)
    app.run(host='127.0.0.1', port=args.port, debug=False)

if __name__ == '__main__':
    main()
