"""
Local run shim for development.

For production use, install the package and run via:
    uvx caffeine-curfew-mcp
or
    python -m caffeine_curfew.server
"""

from caffeine_curfew.server import main

if __name__ == "__main__":
    main()
