
import os 
import sound_field_analysis as sfa
import numpy as np
from . import system_config
from .jack_client import JackClient
from srcs.mics_process.system_config import IS_SINGLE_PRECISION



class JackAmbisonicEncoder(JackClient):
    
    def __init__(
        self,
        name,
        OSC_port,
        block_length,
        *args,
        **kwargs,
    ):
        self._is_passthrough = True
        self._blocks_fd = None
        self._input_block_td = None

    def _process(self, input_td):
        """
        Process block of audio data. This implementation falls back to a straight passthrough
        behaviour if requested. Otherwise the provided `Convolver` instance will handle the
        signal processing.

        Parameters
        ----------
        input_td : numpy.ndarray
            block of audio data that was received from JACK

        Returns
        -------
        numpy.ndarray
            processed block of audio data that will be delivered to JACK
        """
        if self._is_passthrough:
            return super()._process(input_td)

        return self._ambisonic_encoding(input_td)

    def _ambisonic_encoding(self,input_td):
        
        # transform into frequency domain and sh-coefficients
        input_block_nm = sfa.process.spatFT_RT(
            data=self._filter_block_shift_and_convert_input(input_td),
            spherical_harmonic_weighted=self._sh_bases_weighted,
        )

        self._blocks_fd[0, 0] = input_block_nm 
        

        # transform back into time domain
        output_in_block_td = self._filter_block_shift_and_convert_result(
            is_last_block=False
        )


    def _filter_block_shift_and_convert_input(self, input_block_td):
        """
        Parameters
        ----------
        input_block_td : numpy.ndarray
            block of time domain input samples of size [number of input channels; `_block_length`]

        Returns
        -------
        numpy.ndarray
            block of complex one-sided input frequency spectra of size [number of input channels;
            `_block_length` (+1
            depending on even or uneven length)]
        """
        # set new input to end of stored blocks (after shifting backwards)
        self._input_block_td[:, : input_block_td.shape[1]] = self._input_block_td[
            :, input_block_td.shape[1] :
        ]
        self._input_block_td[:, input_block_td.shape[1] :] = input_block_td

        # transform stored blocks into frequency domain
        buffer_block_fd = (
            self._rfft(self._input_block_td)
            if system_config.IS_PYFFTW_MODE
            else np.fft.rfft(self._input_block_td)
        )

        return buffer_block_fd
    
    def _filter_block_shift_and_convert_result(self, is_last_block=False):
        """
        Parameters
        ----------
        is_last_block : bool, optional
            if last (just passed) block or otherwise current block should be processed

        Returns
        -------
        numpy.ndarray
            block of filtered time domain output samples of size [number of output channels;
            `_block_length`]
        """
        # select current or last block to process
        buffer_blocks_fd = self._blocks_fd
        is_last_block = False

        # transform first block back into time domain
        first_block_td = (
            self._irfft(buffer_blocks_fd[0])
            if system_config.IS_PYFFTW_MODE
            else np.fft.irfft(buffer_blocks_fd[0])
        )

        # check if partitioned convolution was done
        if buffer_blocks_fd.shape[0] > 1:
            # shift blocks forwards
            buffer_blocks_fd = np.roll(buffer_blocks_fd, -1, axis=0)
            # since `buffer_blocks_fd` is assigned a new copy of an ndarray, it needs to be returned

        # set last block to zero
        buffer_blocks_fd[-1] = 0.0

        # store result back to current or last block reference
        if is_last_block:
            self._last_blocks_fd = buffer_blocks_fd
        else:
            self._blocks_fd = buffer_blocks_fd

        # remove 1st singular dimension and return relevant second half of the time domain data
        return first_block_td[0, :, int(first_block_td.shape[-1] / 2) :]
        # half of 1st block is not in C-order, but copy() did not have a performance impact
