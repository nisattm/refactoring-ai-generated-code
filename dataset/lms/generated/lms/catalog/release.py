"""Release of a free copy (LIB-RES-08).

Called when a copy becomes free: a returned copy (LIB-LOAN-12), a new copy (LIB-CAT-07), a
repaired copy (LIB-CAT-11), a transfer arrival (LIB-BR-07). The procedure itself belongs to the
reservation module.
"""

from lms.reservations.service import release_copy

__all__ = ["release_copy"]
