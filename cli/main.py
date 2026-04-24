#!/usr/bin/env python3
"""NeoSwarm CLI entry point.

Install as:
    pip install -e .
    neoswarm --help
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli import cli

if __name__ == "__main__":
    cli()
