MODULE = "ui_printing"
TITLE = "web interface, screens of module 29 (step 27)"

import importlib.util as _u
from pathlib import Path as _P

_spec = _u.spec_from_file_location("ui_core_spec", _P(__file__).with_name("ui_core.py"))
_core = _u.module_from_spec(_spec)
_spec.loader.exec_module(_core)
HEADER = _core.HEADER
smoke = _core.smoke

# (screen code, screen name, role that opens it) for every screen with a route (LIB-UI-GEN-03)
SCREENS = [
    ("PRT-01", "Print", "member"),
    ("PRT-02", "My printing", "member"),
    ("PRT-03", "Printers", "member"),
    ("PRT-04", "Print desk", "librarian"),
    ("PRT-05", "Printing report", "librarian"),
]

CASES = [smoke(*s) for s in SCREENS]
