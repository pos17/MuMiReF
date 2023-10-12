import os
import sys
from time import sleep


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