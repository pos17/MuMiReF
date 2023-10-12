from . import mp_context, tools


# ################# #
#  ! DO NOT EDIT !  #
# ################# #



IS_RUNNING = mp_context.Event()
"""If the application is running and rendering audio at the moment. This needs to be set after
all rendering clients have started up. This can also be used to globally interrupt rendering and
output of all clients. """

LOGGING_LEVEL = "INFO"

LOGGING_FORMAT = "%(name)-@s  %(levelname)-8s  %(message)s"
"""Format of messages being printed to the log, see `process_logger`."""

LOGGING_PATH = "log/"
"""Path of log messages being saved to, see `process_logger`."""

CLIENT_MAX_DELAY_SEC = 1
"""Input buffer delay limitation in s for all renderers."""