import os
import shutil
from pathlib import Path

# Скрипт для зачистки временных конфигураций покрытия

ROOT = Path(__file__).resolve().parent

# Удаляем файл .coverage
for p in ROOT.glob(".coverage"):
    try:
        p.unlink()
    except FileNotFoundError:
        pass

# Удаляем htmlcov
htmlcov = ROOT / "htmlcov"
if htmlcov.is_dir():
    shutil.rmtree(htmlcov)

