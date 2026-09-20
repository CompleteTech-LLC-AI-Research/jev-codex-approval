"""Append-only metadata records. Raw prompts, commands, tokens and paths are omitted."""
from __future__ import annotations
from pathlib import Path
import os
import stat
from .schema import canonical, ContractError

def append_record(path: str, record: dict) -> None:
    if not path:
        raise ContractError('audit_not_configured')
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ContractError('audit_path_not_absolute')
    # The owner supplies the directory; do not create arbitrary trees from a tool request.
    parent = p.parent
    st = parent.stat()
    if os.name == 'posix' and (st.st_mode & 0o022 or st.st_uid not in (0, os.getuid())):
        raise ContractError('audit_directory_permissions_unsafe')
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(p, flags, 0o600)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ContractError('audit_not_regular')
        if os.name == 'posix' and (st.st_mode & 0o077 or st.st_uid != os.getuid()):
            raise ContractError('audit_file_permissions_unsafe')
        data = canonical(record) + b'\n'
        # A single append write prevents interleaving in ordinary local filesystem use.
        if os.write(fd, data) != len(data):
            raise ContractError('audit_short_write')
    finally:
        os.close(fd)
