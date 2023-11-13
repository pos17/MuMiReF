from . import mp_context, tools


BLOCK_LENGTH = None

# ########################## #
#  ! PERFORMANCE SETTINGS !  #
# ########################## #

IS_SINGLE_PRECISION = True
"""If all signal generation and processing should be done in single precision (`numpy32` and
`complex64`) instead of double precision (`float64` and `complex128`). """


IS_PYFFTW_MODE = True  # True leads to the best performance so far
"""If `pyfftw` package (wrapper for FFTW library) should be used instead of `numpy` for all
real-time DFT operations. In case `pyfftw` is not used, all related tasks like loading/saving and
pre-calculating FFTW wisdom will be skipped. """

## SH_COMPENSATION_TYPE = "SPHERICAL_HARMONICS_TAPERING+SPHERICAL_HEAD_FILTER"
## SH_COMPENSATION_TYPE = "SPHERICAL_HARMONICS_TAPERING+SPHERICAL_HEAD_FILTER+SECTORIAL_DEGREE_SELECTION"

# ################# #
#  ! DO NOT EDIT !  #
# ################# #



IS_DEBUG_MODE = tools.get_is_debug()
"""If the application is run in a debugging mode. When execution is paused this is used so
certain processes relying on real time execution do not raise errors. Also this is used to make
use of breakpoints in certain functions before they get released in a separate process. """

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

ARIR_RADIAL_AMP = 18
"""Maximum amplification limit in dB when generating modal radial filters, see `FilterSet`."""


if "TRACKER_TYPE" not in locals():
    TRACKER_TYPE = None
if "TRACKER_PORT" not in locals():
    TRACKER_PORT = None
if "ARIR_RADIAL_AMP" not in locals():
    ARIR_RADIAL_AMP = 0
if "SH_COMPENSATION_TYPE" not in locals():
    SH_COMPENSATION_TYPE = None

