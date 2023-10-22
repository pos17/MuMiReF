
import logging
import os
import sys
from time import sleep


if sys.platform == "darwin":
    # prevent exception due to python not being a framework build when installed
    import matplotlib  # chosen by default not non-interactive backend 'agg' (matplotlib from conda)

    # matplotlib.use("TkAgg")  # this backend lead to complete system crashes recently on
    # matplotlib=3.1.0
    matplotlib.use("MacOSX")  # this backend seems to work fine
    del matplotlib
    import matplotlib.pyplot as plt
else:
    import matplotlib.pyplot as plt

# reset matplotlib logging level
logging.getLogger("matplotlib").setLevel(logging.INFO)


def calculate_rms(data, is_level=False):
    """
    Parameters
    ----------
    data : numpy.ndarray
        time or frequency domain data (along last axis)
    is_level : bool, optional
        if RMS value should be calculated as level in dB

    Returns
    -------
    numpy.ndarray
        root mean square values of provided data
    """
    import numpy as np

    if np.iscomplexobj(data):
        rms = np.sqrt(
            np.sum(np.square(np.abs(data)), axis=-1) / np.square(data.shape[-1])
        )
    else:
        rms = np.sqrt(np.mean(np.square(np.abs(data)), axis=-1))
    if is_level:
        rms[np.nonzero(rms == 0)] = np.nan  # prevent zeros
        rms = 20 * np.log10(rms)  # transform into level
        # rms[np.isnan(rms)] = np.NINF  # transform zeros into -infinity
        rms[np.isnan(rms)] = -200  # transform zeros into -200 dB
    return rms


def calculate_peak(data_td, is_level=False):
    """
    Parameters
    ----------
    data_td : numpy.ndarray
        time domain data (along last axis) the absolute peak value should be calculated of
    is_level : bool, optional
        if RMS value should be calculated as level in dB

    Returns
    -------
    numpy.ndarray
        absolute peak values of provided time domain data
    """
    import numpy as np

    peak = np.nanmax(np.abs(data_td), axis=-1)
    if is_level:
        peak[np.nonzero(peak == 0)] = np.nan  # prevent zeros
        peak = 20 * np.log10(peak)  # transform into level
        # peak[np.isnan(peak)] = np.NINF  # transform zeros into -infinity
        peak[np.isnan(peak)] = -200  # transform zeros into -200 dB
    return peak

def get_is_debug():
    """
    The current implementation works fine in PyCharm, but might not work from command line or
    other IDEs.

    Returns
    -------
    bool
        if the application is run in a debugging mode
    """
    return sys.gettrace() is not None


def plot_ir_and_tf(
    data_td_or_fd,
    fs,
    lgd_ch_ids=None,
    is_label_x=True,
    is_share_y=True,
    is_draw_grid=True,
    is_etc=False,
    set_td_db_y=None,
    set_fd_db_y=None,
    step_db_y=5,
    set_fd_f_x=None,
    is_draw_td=True,
    is_draw_fd=True,
    is_show_blocked=None,
):
    """
    Parameters
    ----------
    data_td_or_fd : numpy.ndarray
        time (real) or one-sided frequency domain (complex) data that should be plotted of size
        [number of channels; number of samples or bins]
    fs : int
        sampling frequency of data
    lgd_ch_ids : array_like, optional
        IDs that should be printed in the legend as individual channel names of size
        [number of channels] (range from 0 if nothing is specified)
    is_label_x : bool, optional
        if x-axis of last plot should have a label
    is_share_y : bool, optional
        if y-axis dimensions of plots for all data channels should be shared
    is_draw_grid : bool, optional
        if grid should be drawn (time domain plot visualizes current processing block length)
    is_etc : bool, optional
        if time domain plot should be done as Energy Time Curve (y-axis in dB_FS)
    set_td_db_y : float or list of float or array_like, optional
        limit of time domain plot y-axis in dB (only in case of `is_etc`)
    set_fd_db_y : float or list of float or array_like, optional
        limit of frequency domain plot y-axis in dB
    step_db_y : float, optional
        step size of frequency (and time domain in case of `is_etc`) domain plot y-axis in dB for
        minor grid and rounding of limits
    set_fd_f_x : list of float or array_like, optional
        limit of frequency domain plot x-axis in Hz
    is_draw_td : bool, optional
        if figure should contain time domain plot
    is_draw_fd : bool, optional
        if figure should contain frequency domain plot
    is_show_blocked : bool, optional
        if figure should be shown with the provided `block` status

    Returns
    -------
    matplotlib.figure.Figure
        generated plot
    """

    import numpy as np
    from matplotlib.ticker import FuncFormatter

    def _adjust_y_lim(is_fd=True):
        col = fd_col if is_fd else td_col
        set_db_y = set_fd_db_y if is_fd else set_td_db_y
        lim_y = fd_lim_y if is_fd else td_lim_y
        if set_db_y is not None and len(set_db_y) == 2:
            # return provided fixed limits
            return set_db_y
        # get current data limits
        v_min, v_max = (
            _get_y_data_lim(col)
            if is_share_y
            else axes[ch, int(col)].yaxis.get_data_interval()
        )
        # add to limits in case current data is exactly at limit
        if not v_min % step_db_y:
            v_min -= step_db_y
        if not v_max % step_db_y:
            v_max += step_db_y
        # prevent infinity
        if v_min == np.NINF or v_min == np.Inf:
            v_min = -1e12
        if v_max == np.NINF or v_max == np.Inf:
            v_max = 1e12
        # round limits
        v_max = step_db_y * np.ceil(v_max / step_db_y)
        if set_db_y is None:
            v_min = step_db_y * np.floor(v_min / step_db_y)
        else:
            # set minimum according to provided dynamic range under maximum
            v_min = v_max - set_db_y[0]
        # adjust according to and update global limit
        if is_share_y:
            if set_db_y is not None:
                v_min = min([lim_y[0], v_min])
            v_max = max([lim_y[1], v_max])
            lim_y[0] = v_min
            lim_y[1] = v_max
        # if is_fd:
        #     print(v_min, v_max)
        return v_min, v_max

    def _get_y_data_lim(_column):
        # get current data limits from all subplots
        v_min = min(
            axes[_ch, int(_column)].yaxis.get_data_interval()[0]
            for _ch in range(data_td.shape[0])
        )
        v_max = max(
            axes[_ch, int(_column)].yaxis.get_data_interval()[1]
            for _ch in range(data_td.shape[0])
        )
        return v_min, v_max

    def _check_y_db_param(_db_y):
        # check provided y-axis (time or frequency domain) limits
        if not isinstance(_db_y, list):
            _db_y = [_db_y]
        if len(_db_y) > 2:
            raise ValueError(
                f"number of Decibel axis limits ({len(_db_y)}) is greater 2."
            )
        if len(_db_y) == 1 and _db_y[0] <= 0:
            raise ValueError(
                f"value of single Decibel axis limit ({_db_y[0]}) is smaller equal 0."
            )
        return _db_y

    # check and set provided parameters
    if is_etc and set_td_db_y is not None:
        set_td_db_y = _check_y_db_param(set_td_db_y)
    if set_fd_db_y is not None:
        set_fd_db_y = _check_y_db_param(set_fd_db_y)
    if set_fd_f_x is None:
        set_fd_f_x = [20, fs / 2]
    elif len(set_fd_f_x) != 2:
        raise ValueError(
            f"number of frequency axis limits ({len(set_fd_f_x)}) is not 2."
        )
    if step_db_y <= 0:
        raise ValueError(f"step size of Decibel axis ({step_db_y}) is smaller equal 0.")

    fd_lim_y = [1e12, -1e12]  # initial values
    td_lim_y = [1e12, -1e12]  # initial values
    _TD_STEM_LIM = 8  # upper limit in samples until a plt.stem() will be used instead of plt.plot()
    _FREQS_LABELED = [1, 10, 100, 1000, 10000, 100000]  # labeled frequencies
    _FREQS_LABELED.extend(set_fd_f_x)  # add labels at upper and lower frequency limit

    td_col = 0
    fd_col = 1 if is_draw_td else 0

    # check provided data size
    data_td_or_fd = np.atleast_2d(data_td_or_fd)
    if data_td_or_fd.ndim >= 3:
        data_td_or_fd = data_td_or_fd.squeeze()
        if data_td_or_fd.ndim >= 3:
            raise ValueError(
                f"plotting of data with size {data_td_or_fd.shape} is not supported."
            )

    # check provided legend IDs
    if lgd_ch_ids is None:
        if data_td_or_fd.shape[0] > 1:
            lgd_ch_ids = range(data_td_or_fd.shape[0])
    elif not isinstance(lgd_ch_ids, (list, range, np.ndarray)):
        raise TypeError(
            f"legend channel IDs of type {type(lgd_ch_ids)} are not supported."
        )
    elif len(lgd_ch_ids) != data_td_or_fd.shape[0]:
        raise ValueError(
            f"length of legend channel IDs ({len(lgd_ch_ids)}) does not match "
            f"the size of the data ({data_td_or_fd.shape[0]})."
        )

    if np.iscomplexobj(data_td_or_fd):
        # fd data given
        data_fd = data_td_or_fd.copy()  # make copy to not alter input data
        if data_td_or_fd.shape[1] == 1:
            data_fd = np.repeat(data_fd, 2, axis=1)
        data_td = np.fft.irfft(data_fd, axis=1)
        if data_td_or_fd.shape[1] == 1:
            data_td = data_td[:, :1]
    else:
        # td data given
        data_td = data_td_or_fd.copy()  # make copy to not alter input data
        # if data_td.shape[1] == 1:
        #     data_td[:, 1] = 0
        data_fd = np.fft.rfft(data_td, axis=1)
    del data_td_or_fd

    # prevent zeros
    data_fd[np.nonzero(data_fd == 0)] = np.nan
    if is_etc:
        data_td[np.nonzero(data_td == 0)] = np.nan
        # transform td data into logarithmic scale
        data_td = 20 * np.log10(np.abs(data_td))

    fig, axes = plt.subplots(
        nrows=data_td.shape[0],
        ncols=is_draw_td + is_draw_fd,
        squeeze=False,
        sharex="col",
        sharey="col" if is_share_y else False,
    )
    for ch in range(data_td.shape[0]):
        if is_draw_td:
            # # # plot IR # # #
            length = len(data_td[ch])
            if length > _TD_STEM_LIM:
                axes[ch, td_col].plot(
                    np.arange(0, length), data_td[ch], linewidth=0.5, color="C0"
                )
            else:
                axes[ch, td_col].stem(
                    data_td[ch],
                    linefmt="C0-",
                    markerfmt="C0.",
                    basefmt="C0-",
                    use_line_collection=True,
                )
            # set limits
            if is_etc:
                # needs to be done before setting yticks
                axes[ch, td_col].set_ylim(*_adjust_y_lim(is_fd=False))
            # set ticks and grid
            axes[ch, td_col].tick_params(
                which="major",
                direction="in",
                top=True,
                bottom=True,
                left=True,
                right=True,
            )
            axes[ch, td_col].tick_params(which="minor", length=0)
            if is_draw_grid:
                from . import system_config

                length_2 = 2 ** np.ceil(np.log2(length))  # next power of 2
                if length > system_config.BLOCK_LENGTH:
                    axes[ch, td_col].set_xticks(
                        np.arange(
                            0,
                            length + 1,
                            length_2 // 4 if length_2 > length else length // 2,
                        ),
                        minor=False,
                    )
                    axes[ch, td_col].set_xticks(
                        np.arange(0, length + 1, system_config.BLOCK_LENGTH), minor=True
                    )
                    axes[ch, td_col].grid(
                        True, which="both", axis="x", color="r", alpha=0.4
                    )
                else:
                    axes[ch, td_col].set_xticks(
                        np.arange(0, length + 1, length_2 // 4 if length_2 > 4 else 2),
                        minor=False,
                    )
                    axes[ch, td_col].grid(True, which="major", axis="x", alpha=0.25)
                axes[ch, td_col].grid(True, which="both", axis="y", alpha=0.1)
                if is_etc:
                    axes[ch, td_col].set_yticks(
                        np.arange(*axes[ch, td_col].get_ylim(), step_db_y), minor=True
                    )
                else:
                    axes[ch, td_col].axhline(y=0, color="black", linewidth=0.75)
            # set limits
            if length > _TD_STEM_LIM:
                axes[ch, td_col].set_xlim(0, length)
            else:
                # overwrite ticks
                axes[ch, td_col].set_xticks(np.arange(0, length, 1), minor=False)
                axes[ch, td_col].set_xlim(-0.5, length - 0.5)
            # set labels
            if is_label_x and ch == data_td.shape[0] - 1:
                axes[ch, td_col].set_xlabel("Samples")
            # set axes in background
            axes[ch, td_col].set_zorder(-1)

        if is_draw_fd:
            # # # plot spectrum # # #
            axes[ch, fd_col].semilogx(
                np.linspace(0, fs / 2, len(data_fd[ch])),
                20 * np.log10(np.abs(data_fd[ch])),
                color="C1",
            )
            # ignore underflow FloatingPointError in `numpy.ma.power()`
            with np.errstate(under="ignore"):
                # set limits, needs to be done before setting yticks
                axes[ch, fd_col].set_ylim(*_adjust_y_lim(is_fd=True))
            # set ticks and grid
            axes[ch, fd_col].set_xticks(_FREQS_LABELED)
            axes[ch, fd_col].xaxis.set_major_formatter(
                FuncFormatter(lambda x, _: f"{x / 1000:.16g}")
            )
            axes[ch, fd_col].tick_params(
                which="major",
                direction="in",
                top=True,
                bottom=True,
                left=True,
                right=True,
            )
            axes[ch, fd_col].tick_params(which="minor", length=0)
            if is_draw_grid:
                axes[ch, fd_col].grid(True, which="major", axis="both", alpha=0.25)
                axes[ch, fd_col].grid(True, which="minor", axis="both", alpha=0.1)
                axes[ch, fd_col].set_yticks(
                    np.arange(*axes[ch, fd_col].get_ylim(), step_db_y), minor=True
                )
            # set limits, needs to be done after setting xticks
            axes[ch, fd_col].set_xlim(*set_fd_f_x)
            # set labels
            if is_label_x and ch == data_td.shape[0] - 1:
                axes[ch, fd_col].set_xlabel("Frequency / kHz")
            # set axes in background
            axes[ch, fd_col].set_zorder(-1)

        # set legend
        if (is_draw_td or is_draw_fd) and lgd_ch_ids:
            lgd_str = f'ch {lgd_ch_ids[ch]}{" (ETC)" if is_etc and is_draw_td else ""}'
            axes[ch, td_col].legend(
                labels=[lgd_str], loc="upper right", fontsize="xx-small"
            )

    # remove layout margins
    fig.tight_layout(pad=0)

    if is_show_blocked is not None:
        plt.show(block=is_show_blocked)

    return fig



def export_plot(figure, name, logger=None, file_type="png"):
    """
    Parameters
    ----------
    figure : matplotlib.figure.Figure
        plot that should be exported
    name : str
        name or path of image file being exported, in case no path is given standard logging
        directory will be used
    logger : logging.Logger, optional
        instance to provide identical logging behaviour as the calling process
    file_type : str, optional
        image file type should be exported, multiple in the form e.g. 'png,pdf' can be used
    """
    import re

    # store into logging directory if no path is given
    if os.path.sep not in os.path.relpath(name):
        from . import system_config

        if system_config.LOGGING_PATH is None:
            return
        name = os.path.join(system_config.LOGGING_PATH, name)
    # store all requested file types
    for ending in re.split(r"[,.;:|/\-+]+", file_type):
        file = f"{name}{os.path.extsep}{ending}"
        log_str = f'writing results to "{os.path.relpath(file)}" ...'
        logger.info(log_str) if logger else print(log_str)
        figure.savefig(file, dpi=300)
    # close figure
    plt.close(figure)

def transform_into_state(state, logger=None):
    """
    Parameters
    ----------
    state : bool, int, float, str or None
        state value in compatible format for which a mapping will be achieved, if an invalid value
        is given a warning will be logged and `None` returned
    logger : logging.Logger, optional
        instance to provide identical logging behaviour as the calling process

    Returns
    -------
    bool or None
        state value as either True, False or None
    """
    if state is None or isinstance(state, bool):
        return state

    # parse str
    if isinstance(state, str):
        # noinspection PyUnresolvedReferences
        return transform_str2bool(state.strip())

    # parse int and float
    if isinstance(state, (int, float)):
        state = int(state)
        if state == 1:
            return True
        if state == 0:
            return False
        if state == -1:
            return None

    # no match found
    log_str = f'unknown state "{state}"'
    logger.warning(log_str) if logger else print(log_str, file=sys.stderr)
    return None

def transform_into_type(str_or_instance, _type):
    """
    Parameters
    ----------
    str_or_instance : str, Type or None
        string or instance of type that should be transformed
    _type : type
        type that should be transformed into

    Returns
    -------
    class
        type instance

    Raises
    ------
    ValueError
        in case unknown type is given
    """

    def get_type_str():
        return f"{_type.__module__}.{_type.__name__}"

    if str_or_instance is None:
        return None
    elif isinstance(str_or_instance, str):
        if str_or_instance.upper() == "NONE":
            return None
        try:
            # transform string into enum, will fail in case an invalid type string was given
            # noinspection PyUnresolvedReferences
            return _type[str_or_instance]
        except KeyError:
            raise ValueError(
                f'unknown parameter "{str_or_instance}", see `{get_type_str()}` for reference!'
            )
    elif isinstance(str_or_instance, _type):
        return str_or_instance
    else:
        raise ValueError(
            f"unknown parameter type `{type(str_or_instance)}`, see `{get_type_str()}` for "
            f"reference!"
        )

def transform_str2bool(_str):
    """
    Parameters
    ----------
    _str : str or None
        equivalent string to be transformed into a boolean

    Returns
    -------
    bool
        boolean transformed from equivalent string

    Raises
    ------
    ValueError
        in case unknown equivalent string was given
    """
    if _str is None or _str.upper() in ("TRUE", "YES", "T", "Y", "1"):
        return True
    elif _str.upper() in ("FALSE", "NO", "F", "N", "0"):
        return False
    elif _str.upper() in ("TOGGLE", "SWITCH", "T", "S", "-1"):
        return None
    else:
        raise ValueError(f'unknown boolean equivalent string "{_str}".')


    
def _set_noise_generator():
    """
    Generate a `SFC64` number generator instance since it yields the best performance, see
    https://numpy.org/doc/1.18/reference/random/performance.html.

    Returns
    -------
    numpy.random.Generator
        Random number generator instance to be reused during rendering for best real-time
        performance
    """

    from numpy.random import Generator, SFC64

    return Generator(SFC64())

def generate_noise(shape, scale=1 / 10, dtype="float64"):
    """
    Parameters
    ----------
    shape : tuple of int
        shape of noise to generate (last axis contains normally distributed time samples)
    scale : float, optional
        numpy.random.normal scaling factor, the default value is supposed to result in amplitudes
        [-1, 1]
    dtype : str or numpy.dtype or type, optional
        numpy data type of generated array

    Returns
    -------
    numpy.ndarray
        generated white noise (normal distributed) with given shape

    Raises
    ------
    ValueError
        in case an unsupported data type is given
    """
    import numpy as np

    if np.dtype(dtype) in [np.float32, np.float64]:
        return scale * _RNG.standard_normal(size=shape, dtype=dtype)

    elif np.dtype(dtype) in [np.complex64, np.complex128]:
        return (
            scale
            * _RNG.standard_normal(
                size=(shape[0], shape[1] * 2),
                dtype=np.float32 if np.dtype(dtype) == np.complex64 else np.float64,
            ).view(dtype)
        )

    else:
        raise ValueError(f'unknown data type "{dtype}".')


def transform_into_wrapped_angles(azim, elev, tilt, is_deg=True, deg_round_precision=0):
    """
    Parameters
    ----------
    azim : float
        azimuth angle (will be wrapped to -180..180 degrees)
    elev : float
        elevation angle (will be wrapped to -90..90 degrees)
    tilt : float
        tilt angle (will be wrapped to -180..180 degrees)
    is_deg : bool, optional
        if provided and delivered values are in degrees, radians otherwise
    deg_round_precision : int, optional
        number of decimals to round to (only in case of angles in degrees)

    Returns
    -------
    list of float
        azimuth, elevation and tilt angles in degrees or radians being wrapped
    """
    if is_deg:
        _AZIM_WRAP = 360
        _ELEV_WRAP = 180
        _TILT_WRAP = 360
    else:
        import numpy as np

        _AZIM_WRAP = 2 * np.pi
        _ELEV_WRAP = np.pi
        _TILT_WRAP = 2 * np.pi

    azim = azim % _AZIM_WRAP
    elev = elev % _ELEV_WRAP
    tilt = tilt % _TILT_WRAP

    if azim > _AZIM_WRAP / 2:
        azim -= _AZIM_WRAP
    if elev > _ELEV_WRAP / 2:
        elev -= _ELEV_WRAP
    if tilt > _TILT_WRAP / 2:
        tilt -= _TILT_WRAP

    if is_deg:
        azim = round(azim, ndigits=deg_round_precision)
        elev = round(elev, ndigits=deg_round_precision)
        tilt = round(tilt, ndigits=deg_round_precision)

    return [azim, elev, tilt]







SPEED_OF_SOUND = 343
"""Speed of sound in meters per second in air."""
SEPARATOR = "-------------------------------------------------------------------------"
"""String to improve visual orientation for a clear logging behaviour."""
_RNG = _set_noise_generator()
"""Random number generator instance to be reused during rendering for best real-time performance."""
