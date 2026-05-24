"""GitHub release update check and apply for RDrive."""



from rdrive.core.update.auto_update import (

    AutoUpdateOutcome,

    AutoUpdateResult,

    AutoUpdateScheduler,

    apply_pending_update,

    check_and_apply_update,

    is_auto_update_enabled,

    is_silent_auto_apply_mode,

)

from rdrive.core.update.release_notes import format_release_notes



__all__ = [

    "AutoUpdateOutcome",

    "AutoUpdateResult",

    "AutoUpdateScheduler",

    "apply_pending_update",

    "check_and_apply_update",

    "format_release_notes",

    "is_auto_update_enabled",

    "is_silent_auto_apply_mode",

]

