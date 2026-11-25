#!/bin/sh
# Keep the managed interpreter alongside the kernel venv: otherwise the venv
# survives recreation in the project volume but points to a missing Python.
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$HOME/.prime/python}"
exec /opt/prime-agent/prime-agent "$@"
