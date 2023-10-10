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
