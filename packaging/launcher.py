"""Точка входа собранной программы (PyInstaller)."""

import sys

from app.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
