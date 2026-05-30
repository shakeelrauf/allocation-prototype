#!/usr/bin/env python3
"""Backward-compatible entrypoint: ``python cli.py`` or ``python -m newton3.cli``."""

from newton3.cli import main

if __name__ == "__main__":
    main()
