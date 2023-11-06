
import os 
import sound_field_analysis as sfa
import numpy as np
import pyfftw
from . import system_config, tools
from .jack_client import JackClient
from mics_process.system_config import IS_SINGLE_PRECISION




class JackAmbisonicEncoder(JackClient):

    
    
    def __init__(
        self,
        name,
        OSC_port,
        block_length,
        file_name,
        sh_max_order,
        sh_is_enforce_pinv,
        *args,
        **kwargs,
    ):
        # variables to be initialized from init
        self._ERROR_MSG_FD = "blocks in frequency domain have not been calculated yet."
        self._ERROR_MSG_NM = "blocks in spherical harmonics domain have not been calculated yet."
        self._is_passthrough = True
        ## self._blocks_fd = None
        ## self._input_block_td = None
        self._file_name = None
        self._sh_max_order = None
        self._sh_is_enforce_pinv = False
        self._block_length = None
       
        #variables to be initialized from load
        self._sh_bases_weighted = None
        self._fs = None
        self._irs_grid = None
        self._dirac_td = None
        self._dirac_blocks_fd = None
        self._input_block_td = None 

        super().__init__(name=name,OSC_port=OSC_port, block_length=block_length, *args, **kwargs)


        self._file_name = file_name
        self._sh_is_enforce_pinv = sh_is_enforce_pinv
        self._block_length = block_length
        

        self._sh_max_order = sh_max_order
        self._is_passthrough = False

    def load_config_file(self,is_single_precision):
        
        self._load(dtype=np.float32 if is_single_precision else np.float64)

         # generate dirac impulse
        ## self._dirac_td = np.zeros(self._block_length.shape[-2:], dtype=self._irs_td.dtype)
        ## self._dirac_td[:, 0] = 1.0
        ## self._dirac_blocks_fd = np.zeros()

        # prevent running debugging help function in case of `AdjustableShConvolver` (needs to be
        # invoked after `AdjustableShConvolver.prepare_renderer_sh_processing()` instead!)
        if system_config.IS_DEBUG_MODE:
            # noinspection PyTypeChecker
            self._debug_filter_block(
                len(source_positions) if source_positions else 0
            )

    def start(self, client_connect_target_ports=True):
        """
        Extends the `JackClient` function to `start()` the process. Here also the function
        concerning the JACK output ports suitable for binaural rendering is called.

        Parameters
        ----------
        client_connect_target_ports : jack.Ports or bool, optional
            see `_client_register_and_connect_outputs()` for documentation
        """
        super().start()

        # run after `AdjustableShConvolver.prepare_renderer_sh_processing()` was run
        ## self._convolver.init_fft_optimize(self._logger)

        self._logger.debug("activating JACK client ...")
        self._client.activate()
        self._client_register_and_connect_outputs(client_connect_target_ports)
        self._event_ready.set()

    def get_dirac_td(self):
        """
        Returns
        -------
        numpy.ndarray
            dirac impulse in time domain of identical size like `get_filter_td()`
        """
        return self._dirac_td


    def get_dirac_blocks_fd(self):
        """
        Returns
        -------
        numpy.ndarray
            block-wise one-sided complex frequency spectra of dirac impulses of identical size like
            `get_filter_blocks_fd()`

        Raises
        ------
        RuntimeError
            in case requested blocks have not been calculated yet
        """
        if self._dirac_blocks_fd is None:
            raise RuntimeError(self._ERROR_MSG_FD)
        return self._dirac_blocks_fd

    def _load(self, dtype):
        if not isinstance(self._file_name, str):
            raise TypeError(f'unknown parameter type "{type(self._file_name)}".')

        array_signal = sfa.io.read_miro_struct(self._file_name,transducer_type = "cardioid")

        # save needed attributes and adjust dtype
        self._arir_config = sfa.io.ArrayConfiguration(
            *(
                a.astype(dtype) if isinstance(a, np.ndarray) else a
                for a in array_signal.configuration
            )
        )

        # save needed attributes and adjust dtype
        self._fs = int(array_signal.signal.fs)
        self._irs_grid = sfa.io.SphericalGrid(
            *(
                g.astype(dtype) if isinstance(g, np.ndarray) else g
                for g in array_signal.grid
            )
        )

        sh_bases = sfa.sph.sph_harm_all(
            nMax=self._sh_max_order,
            az=self._irs_grid.azimuth,
            co=self._irs_grid.colatitude,
        ).astype(dtype)

        with np.errstate(under="ignore"):
            if self._sh_is_enforce_pinv or self._irs_grid.weight is None:
                # calculate pseudo inverse since no grid weights are given
                sh_bases_weighted = np.linalg.pinv(sh_bases)
            else:
                # apply given grid weights
                sh_bases_weighted = np.conj(sh_bases).T * (
                    4 * np.pi * self._irs_grid.weight
                )
        self._sh_bases_weighted = sh_bases_weighted




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

        ## self._blocks_fd[0, 0] = input_block_nm 
        

        # transform back into time domain
        output_in_block_td = self._filter_block_shift_and_convert_result(
            input_block_nm= input_block_nm
        )

        return output_in_block_td


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
        ## self._input_block_td[:, : input_block_td.shape[1]] = self._input_block_td[
        ##    :, input_block_td.shape[1] :
        ##]
        ##self._input_block_td[:, input_block_td.shape[1] :] = input_block_td
        ## self._input_block_td = input_block_td
        # transform stored blocks into frequency domain
        buffer_block_fd = (
            self._rfft(input_block_td)
            if system_config.IS_PYFFTW_MODE
            else np.fft.rfft(input_block_td)
        )

        return buffer_block_fd


    def init_fft_optimize(self, logger=None):
        """
        Initialize `pyfftw` objects with given `config` parameters, for most efficient real-time
        DFT.

        Parameters
        ----------
        logger : logging.Logger, optional
            instance to provide identical logging behaviour as the parent process
        """
        log_str = (
            "initializing FFTW DFT optimization ..."
            if system_config.IS_PYFFTW_MODE
            else "skipping FFTW DFT optimization."
        )
        logger.info(log_str) if logger else print(log_str)

        if not system_config.IS_PYFFTW_MODE:
            return

        self._rfft = pyfftw.builders.rfft(
            np.zeros_like(self.get_dirac_td()), overwrite_input=True
        )
        self._irfft = pyfftw.builders.irfft(
            np.zeros_like(self._filter.get_dirac_blocks_fd()[0]), overwrite_input=False
        )
    
    def _filter_block_shift_and_convert_result(self, input_block_nm):
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
        ## buffer_blocks_fd = self._blocks_fd
        ## is_last_block = False
        
        # transform first block back into time domain
        output_block_td = (
            self._irfft(input_block_nm)
            if system_config.IS_PYFFTW_MODE
            else np.fft.irfft(input_block_nm)
        )

        # check if partitioned convolution was done
        ##if buffer_blocks_fd.shape[0] > 1:
            # shift blocks forwards
        ##    buffer_blocks_fd = np.roll(buffer_blocks_fd, -1, axis=0)
            # since `buffer_blocks_fd` is assigned a new copy of an ndarray, it needs to be returned

        # set last block to zero
        ##buffer_blocks_fd[-1] = 0.0

        # store result back to current or last block reference
        ##if is_last_block:
        ##    self._last_blocks_fd = buffer_blocks_fd
        ##else:
        ##    self._blocks_fd = buffer_blocks_fd

        # remove 1st singular dimension and return relevant second half of the time domain data
        return output_block_td[0, :, int(output_block_td.shape[-1] / 2) :]
        # half of 1st block is not in C-order, but copy() did not have a performance impact



    def _debug_filter_block(self, input_count, is_generate_noise=False):
        """
        Provides debugging possibilities the `filter_block()` function before running the
        `Convolver` as a separate process, where breakpoints do not work anymore. Arbitrary audio
        blocks can be send into the array, here some white noise in the shape to be expected from
        a `JackRenderer` input is generated.

        Parameters
        ----------
        input_count : int or None
            number of input channels expected
        is_generate_noise : bool, optional
            if white noise should be generated to test convolution, otherwise a dirac impulse will
            be used

        Returns
        -------
        numpy.ndarray
            filtered output blocks in time domain of size [number of output channels;
            `_block_length`]
        """
        # catch up with optimizing DFT, if had not been done yet
        if not self._rfft or not self._irfft:
            self.init_fft_optimize()

        # generate input blocks
        if not input_count:  # 0 or None
            input_count = (
                self._rfft.input_shape[-2]
                if system_config.IS_PYFFTW_MODE
                else self.get_dirac_td().shape[-2]
            )

        # noinspection PyUnresolvedReferences
        # do not replace with `isinstance()` because of inheritance!
        block_length = (
            self._rfft.input_shape[-1]
            if (system_config.IS_PYFFTW_MODE)
            else self._block_length
        )
        if is_generate_noise:
            ip = tools.generate_noise(
                (input_count, block_length), dtype=self._filter.get_dirac_td().dtype
            )  # white
        else:
            ip = np.zeros(
                (input_count, block_length), dtype=self._filter.get_dirac_td().dtype
            )
            ip[:, 0] = 1  # dirac impulse

        # calculate filtered blocks
        op = self.filter_block(ip)

        # potentially check output blocks
        return op
