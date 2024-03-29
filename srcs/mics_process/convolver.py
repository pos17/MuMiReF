
from asyncio.log import logger
from asyncore import write
from . import Compensation, system_config, tools, HeadTracker
from copy import copy 
import pyfftw
import numpy as np
import sound_field_analysis as sfa

from .filter_set import FilterSetMultiChannel, FilterSetShConfig, FilterSetSsr


class Convolver(object):
    """
    Basic class to provide convolution of an input signal by complex multiplication in the
    frequency domain. The filter length has to be smaller or identical to the system audio block
    size.

    Attributes
    ----------
    _filter : FilterSet
        FIR filter specification with loaded filter coefficients and block-wise pre-calculated in
        frequency domain
    _is_passthrough : bool
        if signals should be passed through by processing them with the `FilterSet` dirac attributes
    _rfft : pyfftw.FFTW
        FFTW library wrapper with a pre-calculated optimal scheme for fast real-time computation of
        the 1D real DFT
    _irfft : pyfftw.FFTW
        FFTW library wrapper with a pre-calculated optimal scheme for fast real-time computation of
        the 1D inverse real DFT
    """

    @staticmethod
    def create_instance_by_filter_set(
        filter_set, 
        block_length=None, 
        source_positions=None, 
        shared_tracker_data=None,
        is_measured_encoding = False,
        filter_set_encoding = None,
        ## azim_deg = 0,
        ## elevs_deg = 0
    ):
        """
        Static method to instantiate a `Convolver` class or one if its deriving classes,
        depending on the given `FilterSet.Type`.

        Parameters
        ----------
        filter_set : FilterSet
            beforehand loaded FIR filter set with a specific `FilterSet.Type`
        block_length : int, optional
            system specific size of every audio block
        source_positions : list of int or list of float, optional
            rendered binaural source positions as list of tuple of azimuth (counterclockwise) and
            elevation in degrees, int or float values are possible
        shared_tracker_data : multiprocessing.Array, optional
            shared data array from an existing tracker instance for dynamic binaural rendering,
            see `HeadTracker`

        Returns
        -------
        Convolver, OverlapSaveConvolver, AdjustableFdConvolver or AdjustableShConvolver
            created instance according to `FilterSet.Type`
        """
        if not block_length:
            convolver = Convolver(filter_set)
        elif type(filter_set) == FilterSetMultiChannel:
            convolver = OverlapSaveConvolver(filter_set, block_length)
        elif type(filter_set) == FilterSetSsr:
            convolver = AdjustableFdConvolver(
                ##filter_set, block_length, source_positions, azim_deg=azim_deg,elevs_deg=elevs_deg ##shared_tracker_data
                filter_set, block_length, source_positions, shared_tracker_data
            )
        else:
            # isinstance(filter_set, (FilterSetMiro, FilterSetSofa))
            if filter_set.get_sh_configuration().arir_config:
                # for ARIR pre-renderer
                convolver = OverlapSaveConvolver(filter_set, block_length)
            else:
                # for HRIR renderer
                # if measured encoding filters are present
                if is_measured_encoding:
                    convolver = AdjustableShConvolverMeasuredEnc(
                        ## filter_set, block_length, source_positions, azim_deg=azim_deg,elevs_deg=elevs_deg ##shared_tracker_data
                        filter_set, block_length, source_positions, shared_tracker_data,filter_set_encoding
                    )
                else:
                    convolver = AdjustableShConvolver(
                        ## filter_set, block_length, source_positions, azim_deg=azim_deg,elevs_deg=elevs_deg ##shared_tracker_data
                        filter_set, block_length, source_positions, shared_tracker_data
                    )

        # prevent running debugging help function in case of `AdjustableShConvolver` (needs to be
        # invoked after `AdjustableShConvolver.prepare_renderer_sh_processing()` instead!)
        if system_config.IS_DEBUG_MODE and type(convolver) is not AdjustableShConvolver:
            # noinspection PyTypeChecker
            convolver._debug_filter_block(
                len(source_positions) if source_positions else 0
            )

        return convolver

    def __init__(self, filter_set):
        """
        Initialize `Convolver` instance and trigger calculation of filter coefficients in frequency
        domain. 

        Parameters
        ----------
        filter_set : FilterSet
            beforehand loaded FIR filter set
        """
        self._filter = filter_set
        self._is_passthrough = False
        self._rfft = None
        self._irfft = None
        self._fft = None
        self._ifft = None

        # do not run if called by an inheriting class
        if type(self) is Convolver:  # do not replace with `isinstance()`
            self._filter.calculate_filter_blocks_fd(None)
            

    def __copy__(self):
        _filter = copy(self._filter)
        _filter.load(
            block_length=None,
            is_prevent_logging=True,
            is_single_precision=self._filter.get_dirac_td().dtype == np.float32,
        )
        new = type(self)(_filter)
        new.__dict__.update(self.__dict__)
        return new

    def __str__(self):
        return (
            f"[ID={id(self)}, _filter={self._filter}, _is_passthrough={self._is_passthrough}, "
            f"_rfft=shape{self._rfft.input_shape}--shape{self._rfft.output_shape}, "
            f"_irfft=shape{self._irfft.input_shape}--shape{self._irfft.output_shape}]"
            f"_fft=shape{self._fft.input_shape}--shape{self._fft.output_shape}, "
            f"_ifft=shape{self._ifft.input_shape}--shape{self._ifft.output_shape}]"
        )

    def _clear_buffers(self):
         """Clear all intermediate signal block buffers, helpful to prevent artifacts when switching
        configurations."""

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
            np.zeros_like(self._filter.get_dirac_td()), overwrite_input=True
        )
        self._irfft = pyfftw.builders.irfft(
            np.zeros_like(self._filter.get_dirac_blocks_fd()[0]), overwrite_input=False
        )
        self._fft = pyfftw.builders.fft(
            np.zeros_like(self._filter.get_dirac_td()), overwrite_input=True
        )
        self._ifft = pyfftw.builders.ifft(
            np.zeros_like(self._filter.get_dirac_blocks_fd()[0]), overwrite_input=False
        )
    
    def set_passthrough(self, new_state=None):
        """
        Parameters
        ----------
        new_state : bool or None, optional
            new passthrough state if processing should be virtually bypassed by using a dirac as a
            'filter', if `None` is given this function works as a toggle between states

        Returns
        -------
        bool
            actually realized passthrough state
        """
        if new_state is None:
            self._is_passthrough = not self._is_passthrough
        else:
            self._is_passthrough = new_state
        return self._is_passthrough
    
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
        
        if not self._fft or not self._ifft:
            self.init_fft_optimize()

        # generate input blocks
        if not input_count:  # 0 or None
            input_count = (
                self._fft.input_shape[-2]
                if system_config.IS_PYFFTW_MODE
                else self._filter.get_dirac_td().shape[-2]
            )

        # noinspection PyUnresolvedReferences
        # do not replace with `isinstance()` because of inheritance!
        block_length = (
            self._fft.input_shape[-1]
            if (system_config.IS_PYFFTW_MODE and type(self) is Convolver)
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

    def filter_block(self, input_td):
        """
        Process time domain samples with the given `FilterSet` by fast convolution in frequency
        domain.

        This implementation does NOT use any input or output buffering like overlap save or
        overlap add. Due to that it is prone to produce time aliasing artifacts. Hence,
        direct use this implementation is not recommended, but provides a foundation for the
        inheriting classes.

        Parameters
        ----------
        input_td : numpy.ndarray or None
            time domain input samples of size [number of input channels; `_block_length`]

        Returns
        -------
        numpy.ndarray
            filtered time domain output samples of size [number of output channels; `_block_length`]
        """
        if input_td is None:
            if not system_config.IS_RUNNING.is_set():
                self._clear_buffers()
            return None

        # transform into frequency domain
        input_fd = (
            self._fft(input_td) if system_config.IS_PYFFTW_MODE else np.fft.fft(input_td)
        )

        # do complex multiplication
        result_fd = input_fd * self._get_current_filters_fd()

        # transform back into time domain
        return (
            self._ifft(result_fd) if system_config.IS_PYFFTW_MODE else np.fft.ifft(result_fd)
        )

    # noinspection PyProtectedMember
    def get_input_channel_count(self):
        """
        Returns
        -------
        int
            number of processed input channels
        """
        if self._filter._is_hpcf:
            return self._filter._irs_td.shape[1]
        else:
            return self._filter._irs_td.shape[0]

    def get_output_channel_count(self):
        """
        Returns
        -------
        int
            number of processed output channels
        """
        # noinspection PyProtectedMember
        return self._filter._irs_td.shape[0] * self._filter._irs_td.shape[1]

    def _get_current_filters_fd(self):
        """
        Returns ------- numpy.ndarray complex one-sided filter frequency spectra to be applied to
        the signal (based on current passthrough state and position) of size [number of blocks;
        number of output channels; block length (+1 depending on even or uneven length)]
        """
        if self._is_passthrough:
            return self._filter.get_dirac_blocks_fd()

        return self._filter.get_filter_blocks_fd()

class OverlapSaveConvolver(Convolver):
    """
    Extension of `Convolver` to allow convolution of filter lengths independent of the system
    audio block size. This is achieved by processing the complex multiplication in the frequency
    domain based on the overlap-save-algorithm.

    Attributes
    ----------
    _block_length : int
        system wide time domain audio block size
    _blocks_fd : numpy.ndarray
        complex one-sided frequency spectra contained in a shifting buffer of size [number of
        blocks; number of output channels; `_block_length` (+1 depending on even or uneven length)]
    _input_block_td : numpy.ndarray
        time domain input samples contained in a shifting buffer of size [number of input channels;
        2 * `_block_length`]
    """

    def __init__(self, filter_set, block_length):
        """
        Extends the function of `Convolver` to initialize an overlap-add-convolver by also
        allocating the necessary buffer arrays for the block-wise processing.

        Parameters
        ----------
        block_length : int
            system wide time domain audio block size
        """
        super().__init__(filter_set=filter_set)
        self._block_length = block_length
        self._input_block_td = None

        # calculate filter in frequency domain
        self._filter.calculate_filter_blocks_fd(self._block_length)
        self._blocks_fd = np.zeros_like(
            self._filter.get_dirac_blocks_fd()
        )  # also inherit dtype

        # do not run if called by an inheriting class
        if type(self) is OverlapSaveConvolver:  # do not replace with `isinstance()`
            # reserve input block buffer according to input channel count
            self._input_block_td = np.zeros(
                (self._blocks_fd.shape[-2], self._block_length * 2),
                dtype=self._filter.get_dirac_td().dtype,
            )

    def __copy__(self):
        _filter = copy(self._filter)
        _filter.load(
            block_length=self._block_length,
            is_prevent_logging=True,
            is_single_precision=self._filter.get_dirac_td().dtype == np.float32,
        )
        new = type(self)(_filter, self._block_length)
        new.__dict__.update(self.__dict__)
        return new

    def __str__(self):
        return (
            f"[{super().__str__()[1:-1]}, _block_length={self._block_length}, "
            f"_blocks_fd=shape{self._blocks_fd.shape}, "
            f"_input_block_td=shape{self._input_block_td.shape}]"
        )

    def _clear_buffers(self):
        """Clear all intermediate signal block buffers, helpful to prevent artifacts when
        switching configurations."""
        super()._clear_buffers()
        self._input_block_td.fill(0)
        self._blocks_fd.fill(0)

    def init_fft_optimize(self, logger=None):
        """
        Initialize `pyfftw` objects with given `config` parameters, for most efficient real-time
        DFT.

        Parameters
        ----------
        logger : logging.Logger, optional
            instance to provide identical logging behaviour as the parent process
        """
        super().init_fft_optimize(logger)
        if not system_config.IS_PYFFTW_MODE:
            return

        self._fft = pyfftw.builders.fft(self._input_block_td, overwrite_input=True)
        self._ifft = pyfftw.builders.ifft(self._blocks_fd[0], overwrite_input=False)

    def filter_block(self, input_block_td):
        """
        Process a block of samples with the given `FilterSet`. Steps before the complex
        multiplication are provided by `_filter_block_shift_and_convert_input()`. Steps after the
        complex multiplication are provided by `_filter_block_shift_and_convert_result()`.

        `_blocks_fd[i]` will form the output in i blocks time, so each input block is multiplied
        by `filter_block_fd[i]` and summed into `_blocks_fd[i]`. After each block this queue is
        rotated to maintain this invariant.

        `_input_block_td` first half contains the input for this block and the second half
        contains the input from the previous one. That leads to half of each block in
        `_blocks_fd` will contain the tail from the previous one.

        In passthrough mode, the signal is still shifted in the buffer and transformed to
        frequency domain to deliver a smooth transition behaviour when toggling passthrough.

        Parameters
        ----------
        input_block_td : numpy.ndarray or None
            block of time domain input samples of size [number of input channels; `_block_length`]

        Returns
        -------
        numpy.ndarray
            block of filtered time domain output samples of size [number of output channels;
            `_block_length`]
        """
        if input_block_td is None:
            return super().filter_block(input_block_td)

        # transform into frequency domain
        input_block_fd = self._filter_block_shift_and_convert_input(input_block_td)

        if self._is_passthrough:
            # discard higher inputs than there are existing outputs
            input_block_fd = input_block_fd[: self._blocks_fd.shape[-2]]
            # just override the first buffer block
            self._blocks_fd[0, 0, : input_block_fd.shape[-2]] = input_block_fd
        else:
            # block-wise complex multiplication into buffer
            self._filter_block_complex_multiply(
                self._blocks_fd, self._get_current_filters_fd(), input_block_fd
            )

        # transform back into time domain
        output_block_td = self._filter_block_shift_and_convert_result()
        return output_block_td

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
            self._fft(self._input_block_td)
            if system_config.IS_PYFFTW_MODE
            else np.fft.fft(self._input_block_td)
        )

        return buffer_block_fd

    @staticmethod
    def _filter_block_complex_multiply(
        buffer_blocks_fd, filter_blocks_fd, input_block_fd
    ):
        """
        Parameters
        ----------
        buffer_blocks_fd : numpy.ndarray
            reference to complex one-sided frequency spectra of size [number of blocks; number of
            output channels; `_block_length` (+1 depending on even or uneven length)]
        filter_blocks_fd : numpy.ndarray
            complex one-sided filter frequency spectra to be applied to the signal of size
            [number of blocks; number of input channels; number of output channels;
            block length (+1 depending on even or uneven length)]
        input_block_fd : numpy.ndarray
            block of complex one-sided input frequency spectra of size [number of input channels;
            `_block_length` (+1 depending on even or uneven length)]
        """
        # do block-wise complex multiplication
        for block_fd, filter_block_fd in zip(buffer_blocks_fd, filter_blocks_fd):
            block_fd += filter_block_fd * input_block_fd  # NOSONAR

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
        if is_last_block and type(self) is not OverlapSaveConvolver:
            # noinspection PyUnresolvedReferences
            buffer_blocks_fd = self._last_blocks_fd
        else:
            buffer_blocks_fd = self._blocks_fd
            is_last_block = False

        # transform first block back into time domain
        first_block_td = (
            self._ifft(buffer_blocks_fd[0])
            if system_config.IS_PYFFTW_MODE
            else np.fft.ifft(buffer_blocks_fd[0])
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


# TODO: properly replacing HEAD-TRACKER SYSTEM not used for this project

class AdjustableFdConvolver(OverlapSaveConvolver):
    """
    Extension of `OverlapSaveConvolver` to allow fast convolution in frequency domain with
    exchangeable impulse responses i.e., for binaural rendering (selection of a Head Related
    Impulse Response depending on the head orientation).

    Attributes
    ----------
    _tracker_deg : multiprocessing.Array
        currently received head position received from a chosen kind of tracking device, see
        `HeadTracker.DataIndex`
    _sources_deg : numpy.ndarray
        rendered binaural source positions of size [number of sources; 2] with second dimension
        being azimuth (counterclockwise) and elevation in degrees
    _is_crossfade : bool
        if output signals applying the current filter should be cross-faded with the output signals
        of the last filter (theoretically improving the perceptual appeal when exchanging filters
        i.e. of an HRIR, almost doubles the processing effort)
    _window_out_td : numpy.ndarray
        time domain window samples to fade out during a block of size [`_block_length`]
    _window_in_td : numpy.ndarray
        time domain window samples to fade in during a block of size [`_block_length`]
    _last_filters_fd : numpy.ndarray
        complex one-sided filter frequency spectra that were applied to the signal in the last
        processing frame of size like `_get_current_filters_fd()`
    _last_blocks_fd : numpy.ndarray
        complex one-sided frequency spectra that had the past last processing filters applied to
        the signal contained in a shifting buffer of size like `_blocks_fd`
    """
    ## def __init__(self, filter_set, block_length, source_positions, azim_deg = 0 , elevs_deg= 0):
       
    def __init__(self, filter_set, block_length, source_positions, shared_tracker_data):
        """
        Extends the function of `OverlapSaveConvolver` to initialize a binaural renderer by
        loading the provided positions of virtual sound sources.

        Parameters
        ----------
        source_positions : tuple of int or tuple of float
            rendered binaural source positions as list of tuple of azimuth (counterclockwise) and
            elevation in degrees, int or float values are possible
        shared_tracker_data : multiprocessing.Array
            shared data array from an existing tracker instance for dynamic binaural rendering, see
            `HeadTracker`

        Raises
        ------
        ValueError
            in case no `source_positions` are given
        """
        super().__init__(filter_set=filter_set, block_length=block_length)
        self._is_crossfade = True

        if not source_positions:
            raise ValueError(
                "no virtual source positions (according to playback file channel count) given."
            )
        self._tracker_deg = shared_tracker_data
        ## self.track_azim = azim_deg
        ## self.track_elev = elevs_deg
        self._sources_deg = np.array(source_positions, dtype=np.float16)

        # limit to amount of output channels on second dimension to 1
        self._blocks_fd = self._blocks_fd[:, :1]

        # discard higher dimensions than there are existing inputs
        self._input_block_td = np.zeros(
            (len(source_positions), self._block_length * 2),
            dtype=self._filter.get_dirac_td().dtype,
        )

        # calculate COSINE-Square cross-fade windows
        self._window_out_td = np.arange(
            self._block_length, dtype=self._input_block_td.dtype
        )
        self._window_out_td = np.square(
            np.cos(self._window_out_td * np.pi / (2 * (self._block_length - 1)))
        )
        self._window_in_td = np.flip(self._window_out_td).copy()

        # allocate space for storing buffers relevant to cross-fading
        self._last_blocks_fd = np.zeros_like(self._blocks_fd)
        self._last_filters_fd = np.zeros_like(self._get_current_filters_fd())

    def __copy__(self):
        _filter = copy(self._filter)
        _filter.load(
            block_length=self._block_length,
            is_prevent_logging=True,
            is_single_precision=self._filter.get_dirac_td().dtype == np.float32,
        )
        new = type(self)(
            ## _filter, self._block_length, tuple(self._sources_deg), self.track_azim, self.track_elev ## self._tracker_deg
            _filter, self._block_length, tuple(self._sources_deg), self._tracker_deg
        )
        new.__dict__.update(self.__dict__)
        return new

    def __str__(self):
        # noinspection PyTypeChecker
        return (
            f"[{super().__str__()[1:-1]},  _tracker_deg=len({len(self._tracker_deg)}), "
            ## f"[{super().__str__()[1:-1]},  azim_deg= {self.track_azim}, elev_deg= {self.track_elev},"
            f"_sources_deg=shape{self._sources_deg.shape}, _is_crossfade={self._is_crossfade}, "
            f"_window_td=shape{self._window_out_td.shape}]"
        )

    def _clear_buffers(self):
        """Clear all intermediate signal block buffers, helpful to prevent artifacts when
        switching configurations."""
        super()._clear_buffers()
        self._last_blocks_fd.fill(0)

    def filter_block(self, input_block_td):
        """
        Process a block of samples with the given `FilterSet`. Steps before the complex
        multiplication are provided by `_filter_block_shift_and_convert_input()`. Steps after the
        complex multiplication are provided by `_filter_block_shift_and_convert_result()`.

        In passthrough mode, the functionality of `OverlapSaveConvolver` filtering is used.

        Parameters
        ----------
        input_block_td : numpy.ndarray or None
            block of time domain input samples of size [number of input channels; `_block_length`]

        Returns
        -------
        numpy.ndarray
            block of filtered time domain output samples of size [number of output channels;
            `_block_length`]
        """
        if self._is_passthrough or input_block_td is None:
            return super().filter_block(input_block_td)

        # transform into frequency domain
        input_block_fd = self._filter_block_shift_and_convert_input(input_block_td)
        filters_blocks_fd = self._get_current_filters_fd()

        # block-wise complex multiplication into current buffer
        self._filter_block_complex_multiply(
            self._blocks_fd, filters_blocks_fd, input_block_fd
        )
        # transform back into time domain
        output_in_block_td = self._filter_block_shift_and_convert_result(
            is_last_block=False
        )

        # skip further calculations in case no crossfade in time domain should be done
        if not self._is_crossfade:
            return output_in_block_td

        # block-wise complex multiplication into last buffer
        self._filter_block_complex_multiply(
            self._last_blocks_fd, self._last_filters_fd, input_block_fd
        )
        # transform back into time domain
        output_out_block_td = self._filter_block_shift_and_convert_result(
            is_last_block=True
        )

        # store last used filters
        self._last_filters_fd = (
            filters_blocks_fd  # copy is not necessary here (ndarray was newly created)
        )

        # add in time domain after applying windows
        return (output_in_block_td * self._window_in_td) + (
            output_out_block_td * self._window_out_td
        )

    @staticmethod
    def _filter_block_complex_multiply(
        buffer_blocks_fd, filters_blocks_fd, input_block_fd
    ):
        """
        Parameters
        ----------
        buffer_blocks_fd : numpy.ndarray
            reference to complex one-sided frequency spectra of size [number of blocks; number of
            output channels; `_block_length` (+1 depending on even or uneven length)]
        filters_blocks_fd : numpy.ndarray
            complex one-sided filter frequency spectra to be applied to the signal (based on
            current passthrough state and position) of size [number of sources, number of blocks;
            number of output channels; block length (+1 depending on even or uneven length)]
        input_block_fd : numpy.ndarray
            block of complex one-sided input frequency spectra of size [number of input channels;
            `_block_length` (+1 depending on even or uneven length)]
        """
        # summation for every source
        for s in range(filters_blocks_fd.shape[0]):
            # do block-wise complex multiplication
            for block_fd, filter_block_fd in zip(
                buffer_blocks_fd, filters_blocks_fd[s]
            ):
                # division by `_sources_deg.shape[0]` is level adjustment in case multiple
                # sources are rendered
                block_fd[0] += (
                    filter_block_fd * input_block_fd[s] / filters_blocks_fd.shape[0]
                )

    def set_crossfade(self, new_state=None):
        """
        Parameters
        ----------
        new_state : bool or None, optional
            new crossfade state if output signals applying the current filter should be cross-faded
            with the output signals of the last filter, if `None` is given this function works as a
            toggle between states

        Returns
        -------
        bool
            actually realized crossfade state
        """
        if new_state is None:
            self._is_crossfade = not self._is_crossfade
        else:
            self._is_crossfade = new_state

        # clean buffers if crossfade was turned off
        if not self._is_crossfade:
            self._last_blocks_fd.fill(0)
            self._last_filters_fd.fill(0)

        return self._is_crossfade

    def get_input_channel_count(self):
        """
        Returns
        -------
        int
            number of rendered binaural source positions
        """
        return self._sources_deg.shape[0]

    def get_output_channel_count(self):
        """
        Returns
        -------
        int
            number of processed output channels
        """
        # noinspection PyProtectedMember
        return self._filter._irs_td.shape[1]

    def _get_current_filters_fd(self):
        """
        Returns
        -------
        numpy.ndarray
            complex one-sided filter frequency spectra to be applied to the signal (based on
            current passthrough state and position) of size [number of sources; number of blocks;
            number of output channels; block length (+1 depending on even or uneven length)]
        """
        if self._is_passthrough:
            # return np.repeat(
            #     self._filter.get_dirac_blocks_fd(), self._sources_deg.shape[0], axis=1
            # )[np.newaxis, :]
            return self._filter.get_dirac_blocks_fd()[np.newaxis, :]

        azims_deg, elevs_deg = self._calculate_individual_directions()
        ## azims_deg = [self.track_azim]
        ## elevs_deg = [self.track_elev]
        # for s in range(azims_deg.shape[0]):
        #     print(
        #         f"source {s} AZIM head {self._tracker_deg[HeadTracker.DataIndex.AZIM]:>+6.1f} "
        #         f"deg, source relative {azims_deg[s]:>3.0f} deg"
        #     )
        #     print(
        #         f"source {s} ELEV head {self._tracker_deg[HeadTracker.DataIndex.ELEV]:>+6.1f} "
        #         f"deg, source relative {elevs_deg[s]:>3.0f} deg"
        #     )

        # stack for all sources
        return np.stack(
            [
                self._filter.get_filter_blocks_fd(azim_deg, elev_deg)
                for azim_deg, elev_deg in zip(azims_deg, elevs_deg)
            ]
        )
    
    def _calculate_individual_directions(self):
        """
        Returns
        -------
        (numpy.ndarray, numpy.ndarray)
            rotation azimuth angle in degrees (wrapped to be between 0 and 359) of size
            [number of sources], rotation elevation angle in degrees (wrapped to be between
            -180 and 179) of size [number of sources]
        """
        # invert tracker direction in case a BRIR (not HRIR) is rendered
        # noinspection PyProtectedMember
        tracker_dir = 1 if self._filter._is_hrir else -1

        azims_deg = (
            tracker_dir * self._tracker_deg[HeadTracker.DataIndex.AZIM]
            + self._sources_deg[:, 0]
        )
        # azimuth between 0 and 359
        azims_deg = (azims_deg + 360.0) % 360.0

        elevs_deg = (
            tracker_dir * self._tracker_deg[HeadTracker.DataIndex.ELEV]
            + self._sources_deg[:, 1]
        )
        # elevation between -180 and 179
        elevs_deg = ((elevs_deg + 180.0) % 360.0) - 180.0

        # use floats to calculate above to preserve `_sources_deg` dtype
        return azims_deg, elevs_deg

class AdjustableShConvolver(AdjustableFdConvolver):
    """
    Extension of `AdjustableFdConvolver` to allow fast convolution in spherical harmonics domain
    while adjusting orientation by a rotation matrix i.e., for binaural rendering (depending on
    the head  orientation).

    The current spherical harmonics rendering order can be adjusted i.e., lowered, during execution.

    Attributes
    ----------
    _sh_m : numpy.ndarray
        set of spherical harmonics orders of size [count according to `sh_max_order`]
    _sh_m_rev_id : list of int
        set of reversed spherical harmonics orders indices of size
        [count according to `sh_max_order`]
    _sh_cur_order : int
        current maximum spherical harmonics order being rendered
    _sh_bases_weighted : numpy.ndarray
        spherical harmonic bases weighted by grid weights of spatial sampling points of size
        [number according to `sh_max_order`; number of input channels]
    _last_sh_azim_nm : numpy.ndarray
        set of spherical harmonics azimuth weights that were applied to the signal in the last
        processing frame of size [count according to `sh_max_order`; 1; 1]
    _comp : list of str or list of Compensation.Type or str or Compensation.Type
        type of spherical harmonics compensation being applied to the filter
    _comp_arir_config : sfa.io.ArrayConfiguration
        recording / measurement microphone array configuration for spherical harmonics compensation
        being applied to the filter
    _comp_mrf_limit : int
        maximum amplification limit in dB of modal radial filter being applied to the filter
    """

    ## def __init__(self, filter_set, block_length, source_positions, azim_deg=0, elevs_deg = 0): ##shared_tracker_data):
    def __init__(self, filter_set, block_length, source_positions, shared_tracker_data):
    
        """
        Extends the function of `OverlapSaveConvolver` to initialize a binaural renderer by
        loading the provided positions of virtual sound sources.

        Parameters
        ----------
        source_positions : tuple of int or tuple of float
            rendered binaural source positions as list of tuple of azimuth (counterclockwise) and
            elevation in degrees, int or float values are possible
        shared_tracker_data : multiprocessing.Array
            shared data array from an existing tracker instance for dynamic binaural rendering, see
            `HeadTracker`

        Raises
        ------
        NotImplementedError
            in case more then one `source_positions` are given
        """
        super().__init__(
            filter_set=filter_set,
            block_length=block_length,
            source_positions=source_positions,
            shared_tracker_data=shared_tracker_data,
            ## azim_deg=azim_deg,
            ## elevs_deg=elevs_deg
        )

        if self._sources_deg.shape[0] > 1:
            raise NotImplementedError(
                "more then one virtual source position given, which is not supported yet."
            )

        self._sh_m = None
        self._sh_m_rev_id = None
        self._sh_cur_order = None
        self._sh_bases_weighted = None
        self._last_filters_fd = None
        self._last_sh_azim_nm = None
        self._comp = None
        self._comp_arir_config = None
        self._comp_mrf_limit = None

    def __copy__(self):
        # _filter = copy(self._filter)
        # _filter.load(block_length=self._block_length, is_prevent_logging=True,
        #              is_single_precision=self._filter.get_dirac_td().dtype == np.float32)
        # new = type(self)(_filter, self._block_length, self._sources_deg, self._tracker_deg)
        # new.__dict__.update(self.__dict__)
        # # this is supposed to be the filter of the pre-renderer !!!
        # new.prepare_sh_processing(_filter.get_sh_configuration(), 0)
        # return new
        raise NotImplementedError("This implementation was not tested so far.")

    def __str__(self):
        return (
            f"[{super().__str__()[1:-1]}, _sh_m=shape{self._sh_m.shape}, "
            f"_sh_m_rev_id=shape{self._sh_m_rev_id.shape}, "
            f"_sh_cur_order={self._sh_cur_order},"
            f"_sh_bases_weighted=shape{self._sh_bases_weighted.shape}]"
        )

    # noinspection PyProtectedMember
    def prepare_sh_processing(
        self, input_sh_config, mrf_limit_db, compensation_type, logger=None
    ):
        """
        Calculate components which can be prepared before spherical harmonic processing in
        real-time. This contains calculating all spherical harmonics orders, coefficients and
        base functions. Also a modal radial filter according to the provided input array
        configuration, as well as further compensation filters will be generated and applied
        preliminary.

        Parameters
        ----------
        input_sh_config : FilterSetShConfig
            combined filter configuration with all necessary information to transform an incoming
            audio block into spherical harmonics sound field coefficients in real-time
        mrf_limit_db : int
            maximum modal amplification limit in dB
        compensation_type : str or Compensation.Type
            type of spherical harmonics processing compensation technique
        logger : logging.Logger, optional
            instance to provide identical logging behaviour as the parent process
        """
        # prepare attributes, copy to ensure C-order
        self._sh_m = input_sh_config.sh_m.copy()
        self._sh_m_rev_id = sfa.sph.reverseMnIds(self._filter._sh_max_order)
        self._sh_cur_order = self._filter._sh_max_order
        self._sh_bases_weighted = input_sh_config.sh_bases_weighted.copy()
        self._last_sh_azim_nm = np.zeros(
            (self._sh_bases_weighted.shape[0], 1, 1),
            dtype=self._sh_bases_weighted.dtype,
        )

        # store SH compensation configurations, in case it should be re-applied
        self._comp = [compensation_type, Compensation.Type.MRF]
        self._comp_arir_config = input_sh_config.arir_config
        self._comp_mrf_limit = mrf_limit_db

        # apply SH compensation
        self._apply_sh_compensation(is_plot=True, logger=logger)

        # adjust buffer block sizes according to array configuration
        arir_channel_count = input_sh_config.sh_bases_weighted.shape[-1]
        self._input_block_td = np.zeros(
            (arir_channel_count, self._block_length * 2),
            dtype=self._filter.get_dirac_td().dtype,
        )

        # catch up on running debugging help function in case of `AdjustableShConvolver`
        if system_config.IS_DEBUG_MODE:
            self._debug_filter_block(input_count=arir_channel_count,is_generate_noise=True)

    # noinspection PyProtectedMember
    def update_sh_processing(self, sh_new_order, logger=None):
        """
        Update the current spherical harmonics processing order. With that, potentially used
        compensation filters will be re-calculated and re-applied.

        Parameters
        ----------
        sh_new_order : int or float or None
            desired SH processing order
        logger : logging.Logger, optional
            instance to provide identical logging behaviour as the parent process

        Returns
        -------
        int
            actually realized SH processing order
        """
        if sh_new_order is None:
            # restore max order if no value is specified
            sh_new_order = self._filter._sh_max_order
        else:
            # cast to integer
            sh_new_order = int(sh_new_order)

        if not 0 <= sh_new_order <= self._filter._sh_max_order:
            logger.error(
                f'value "{sh_new_order}" out of bounds, "set SH processing order" ignored.'
            )
            return
        if self._sh_cur_order == sh_new_order:
            return sh_new_order

        # temporarily pause execution
        event_running_state_before = system_config.IS_RUNNING.is_set()
        system_config.IS_RUNNING.clear()

        # adjust current SH order in convolver
        self._sh_cur_order = sh_new_order
        # re-apply adjusted SH compensations in convolver
        self._apply_sh_compensation(is_plot=False, logger=logger)

        # restore beforehand execution state
        if event_running_state_before:
            system_config.IS_RUNNING.set()

        return sh_new_order


    # TODO: Restore use of compensation as preimplemented
    
    # noinspection PyProtectedMember
    def _apply_sh_compensation(self, is_plot=True, logger=None):
        """
        Calculate and apply modal radial filter as well as further compensation filters. This
        function can be re-used during runtime, in case aspects of the rendering configuration
        change i.e., the current spherical harmonics rendering order.

        Parameters
        ----------
        is_plot : bool, optional
            if compensation filters should be plotted and exported
        logger : logging.Logger, optional
            instance to provide identical logging behaviour as the parent process
        """
        # reset compensation specific parameters to initial values (relevant when re-applying the
        # compensations)
        Compensation.reset_config(is_plot=is_plot)

        # (re)calculate block buffers
        self._filter.calculate_filter_blocks_nm()

        # backup raw block buffers
        irs_blocks_nm_before = self._filter._irs_blocks_nm.copy()

        # generate specified compensations based on one block length
        comp_nm = Compensation.generate_by_type(
            compensation_types=self._comp,
            filter_set=self._filter,
            arir_config=self._comp_arir_config,
            amp_limit_db=self._comp_mrf_limit,
            nfft=None,
            nfft_padded=self._input_block_td.shape[-1],
            logger=logger,
        )

        # apply compensations
        self._filter._irs_blocks_nm *= comp_nm

        # plot comparison of raw and compensated block buffers
        name = self._filter._generate_plot_name(
            block_length=self._block_length, logger=logger
        )
        tools.export_plot(
            figure=tools.plot_nm_rms(
                data_nm_fd=np.concatenate(
                    (irs_blocks_nm_before, self._filter._irs_blocks_nm), axis=0
                )
            ),
            name=f"{name}_COMP",
            logger=logger,
        )

    def get_input_channel_count(self):
        """
        Returns
        -------
        int
            number of processed input channels
        """
        return self._input_block_td.shape[-2]

    def filter_block(self, input_block_td):
        """
        Process a block of samples with the given `FilterSet`. Steps before the complex
        multiplication are provided by `_filter_block_shift_and_convert_input()`. Steps after the
        complex multiplication are provided by `_filter_block_shift_and_convert_result()`.

        In passthrough mode, the functionality of `OverlapSaveConvolver` filtering is used.

        When the current rendering order is lowered during execution, the sound field is still
        decomposed at the full maximum order. Although, only coefficients up to the specified
        current order are used to calculated the ear signals. For best efficiency also the
        decomposition would only be done at the current order, but the implementation would
        become much more complicated (sizes of all internal buffers in SH domain would change).

        Parameters
        ----------
        input_block_td : numpy.ndarray or None
            block of time domain input samples of size [number of input channels; `_block_length`]

        Returns
        -------
        numpy.ndarray
            block of filtered time domain output samples of size [number of output channels;
            `_block_length`]
        """
        if self._is_passthrough or input_block_td is None:
            return super().filter_block(input_block_td)

        # transform into frequency domain and sh-coefficients
        input_block_nm = sfa.process.spatFT_RT(
            data=self._filter_block_shift_and_convert_input(input_block_td),
            spherical_harmonic_weighted=self._sh_bases_weighted,
        )

        # # _TODO: implement block-wise processing if filter is longer
        # for filter_block_nm, block_nm in zip(
        #     self._filter.get_filter_blocks_nm(), self._blocks_nm
        # ):
        #     block_nm[0] += filter_block_nm * input_block_nm * ...

        # apply reverse index and adjust size according to filter channels
        input_block_nm = input_block_nm[self._sh_m_rev_id][:, np.newaxis, :]
        input_block_nm = np.repeat(input_block_nm, self._blocks_fd.shape[-2], axis=1)
        # apply HRIR coefficients
        input_block_nm *= self._filter.get_filter_blocks_nm()[0]

        # get head-tracker position (neglect elevation)
        azim_deg, _ = self._calculate_individual_directions()
        ## azim_deg = self.track_azim
        ## _ = self.track_elev
        sh_azim_nm = np.exp(
            self._blocks_fd.dtype.type(-1j) * self._sh_m * np.deg2rad(azim_deg)
        )
        # consider only the current rendering order here
        sh_azim_nm = sh_azim_nm[: (self._sh_cur_order + 1) ** 2, np.newaxis, np.newaxis]

        # calculation back into frequency domain into current buffer, after applying rotation
        # coefficients
        self._blocks_fd[0, 0] = np.sum(
            input_block_nm[: sh_azim_nm.shape[0]] * sh_azim_nm, axis=0
        )
        # transform back into time domain
        output_in_block_td = self._filter_block_shift_and_convert_result(
            is_last_block=False
        )

        # skip further calculations in case no crossfade in time domain should be done
        if not self._is_crossfade:
            return output_in_block_td

        # calculation back into frequency domain into last buffer, after applying rotation
        # coefficients
        self._last_blocks_fd[0, 0] = np.sum(
            input_block_nm[: self._last_sh_azim_nm.shape[0]] * self._last_sh_azim_nm,
            axis=0,
        )
        # transform back into time domain
        output_out_block_td = self._filter_block_shift_and_convert_result(
            is_last_block=True
        )

        # store last used azimuth exponents
        self._last_sh_azim_nm = sh_azim_nm  # copy should not be necessary here

        # add in time domain after applying windows
        return (output_in_block_td * self._window_in_td) + (
            output_out_block_td * self._window_out_td
        )

    def set_crossfade(self, new_state=None):
        """
        Parameters
        ----------
        new_state : bool or None, optional
            new crossfade state if output signals applying the current filter should be cross-faded
            with the output signals of the last filter, if `None` is given this function works as a
            toggle between states

        Returns
        -------
        bool
            actually realized crossfade state
        """
        try:
            super().set_crossfade(new_state)
        except AttributeError:
            pass

        # clean buffers if crossfade was turned off
        if not self._is_crossfade:
            self._last_sh_azim_nm.fill(0)

        return self._is_crossfade






class AdjustableShConvolverMeasuredEnc(AdjustableShConvolver):
    """
    Extension of `AdjustableFdConvolver` to allow fast convolution in spherical harmonics domain
    while adjusting orientation by a rotation matrix i.e., for binaural rendering (depending on
    the head  orientation).

    The current spherical harmonics rendering order can be adjusted i.e., lowered, during execution.

    Attributes
    ----------
    _sh_m : numpy.ndarray
        set of spherical harmonics orders of size [count according to `sh_max_order`]
    _sh_m_rev_id : list of int
        set of reversed spherical harmonics orders indices of size
        [count according to `sh_max_order`]
    _sh_cur_order : int
        current maximum spherical harmonics order being rendered
    _sh_bases_weighted : numpy.ndarray
        spherical harmonic bases weighted by grid weights of spatial sampling points of size
        [number according to `sh_max_order`; number of input channels]
    _last_sh_azim_nm : numpy.ndarray
        set of spherical harmonics azimuth weights that were applied to the signal in the last
        processing frame of size [count according to `sh_max_order`; 1; 1]
    _comp : list of str or list of Compensation.Type or str or Compensation.Type
        type of spherical harmonics compensation being applied to the filter
    _comp_arir_config : sfa.io.ArrayConfiguration
        recording / measurement microphone array configuration for spherical harmonics compensation
        being applied to the filter
    _comp_mrf_limit : int
        maximum amplification limit in dB of modal radial filter being applied to the filter
    """

    ## def __init__(self, filter_set, block_length, source_positions, azim_deg=0, elevs_deg = 0): ##shared_tracker_data):
    def __init__(self, filter_set, block_length, source_positions, shared_tracker_data,filter_set_encoding):
    
        """
        Extends the function of `OverlapSaveConvolver` to initialize a binaural renderer by
        loading the provided positions of virtual sound sources.

        Parameters
        ----------
        source_positions : tuple of int or tuple of float
            rendered binaural source positions as list of tuple of azimuth (counterclockwise) and
            elevation in degrees, int or float values are possible
        shared_tracker_data : multiprocessing.Array
            shared data array from an existing tracker instance for dynamic binaural rendering, see
            `HeadTracker`

        Raises
        ------
        NotImplementedError
            in case more then one `source_positions` are given
        """
        super().__init__(
            filter_set=filter_set,
            block_length=block_length,
            source_positions=source_positions,
            shared_tracker_data=shared_tracker_data,
            ## azim_deg=azim_deg,
            ## elevs_deg=elevs_deg
        )

        if self._sources_deg.shape[0] > 1:
            raise NotImplementedError(
                "more then one virtual source position given, which is not supported yet."
            )

        self._sh_m = None
        self._sh_m_rev_id = None
        self._sh_cur_order = None
        self._sh_bases_weighted = None
        self._last_filters_fd = None
        self._last_sh_azim_nm = None
        self._comp = None
        self._comp_arir_config = None
        self._comp_mrf_limit = None
        self._encoding_filters = filter_set_encoding
        self._encoding_filters.calculate_filter_blocks_fd(block_length)

    def __copy__(self):
        # _filter = copy(self._filter)
        # _filter.load(block_length=self._block_length, is_prevent_logging=True,
        #              is_single_precision=self._filter.get_dirac_td().dtype == np.float32)
        # new = type(self)(_filter, self._block_length, self._sources_deg, self._tracker_deg)
        # new.__dict__.update(self.__dict__)
        # # this is supposed to be the filter of the pre-renderer !!!
        # new.prepare_sh_processing(_filter.get_sh_configuration(), 0)
        # return new
        raise NotImplementedError("This implementation was not tested so far.")

    def __str__(self):
        return (
            f"[{super().__str__()[1:-1]}, _sh_m=shape{self._sh_m.shape}, "
            f"_sh_m_rev_id=shape{self._sh_m_rev_id.shape}, "
            f"_sh_cur_order={self._sh_cur_order},"
            f"_sh_bases_weighted=shape{self._sh_bases_weighted.shape}]"
        )

    # noinspection PyProtectedMember
    def prepare_sh_processing(
        self, input_sh_config, mrf_limit_db, compensation_type, logger=None
    ):
        """
        Calculate components which can be prepared before spherical harmonic processing in
        real-time. This contains calculating all spherical harmonics orders, coefficients and
        base functions. Also a modal radial filter according to the provided input array
        configuration, as well as further compensation filters will be generated and applied
        preliminary.

        Parameters
        ----------
        input_sh_config : FilterSetShConfig
            combined filter configuration with all necessary information to transform an incoming
            audio block into spherical harmonics sound field coefficients in real-time
        mrf_limit_db : int
            maximum modal amplification limit in dB
        compensation_type : str or Compensation.Type
            type of spherical harmonics processing compensation technique
        logger : logging.Logger, optional
            instance to provide identical logging behaviour as the parent process
        """
        
        


        # prepare attributes, copy to ensure C-order
        self._sh_m = input_sh_config.sh_m.copy()
        self._sh_m_rev_id = sfa.sph.reverseMnIds(self._filter._sh_max_order)
        self._sh_cur_order = self._filter._sh_max_order
        self._sh_bases_weighted = input_sh_config.sh_bases_weighted.copy()
        self._last_sh_azim_nm = np.zeros(
            (self._sh_bases_weighted.shape[0], 1, 1),
            dtype=self._sh_bases_weighted.dtype,
        )

        # store SH compensation configurations, in case it should be re-applied
        #self._comp = [compensation_type, Compensation.Type.MRF]
        self._comp = [compensation_type]
        self._comp_arir_config = input_sh_config.arir_config
        self._comp_mrf_limit = mrf_limit_db

        # apply SH compensation
        self._apply_sh_compensation(is_plot=True, logger=logger)

        

        #logger.info(f"sh bases weighted dimensions: {input_sh_config.sh_bases_weighted.shape}")

        # adjust buffer block sizes according to array configuration
        arir_channel_count = input_sh_config.sh_bases_weighted.shape[-1]
        self._input_block_td = np.zeros(
            (arir_channel_count, self._block_length * 2),
            dtype=self._filter.get_dirac_td().dtype,
        )

        # catch up on running debugging help function in case of `AdjustableShConvolver`
        if system_config.IS_DEBUG_MODE:
            self._debug_filter_block(input_count=arir_channel_count,is_generate_noise=True)

    # noinspection PyProtectedMember
    def update_sh_processing(self, sh_new_order, logger=None):
        """
        Update the current spherical harmonics processing order. With that, potentially used
        compensation filters will be re-calculated and re-applied.

        Parameters
        ----------
        sh_new_order : int or float or None
            desired SH processing order
        logger : logging.Logger, optional
            instance to provide identical logging behaviour as the parent process

        Returns
        -------
        int
            actually realized SH processing order
        """
        if sh_new_order is None:
            # restore max order if no value is specified
            sh_new_order = self._filter._sh_max_order
        else:
            # cast to integer
            sh_new_order = int(sh_new_order)

        if not 0 <= sh_new_order <= self._filter._sh_max_order:
            logger.error(
                f'value "{sh_new_order}" out of bounds, "set SH processing order" ignored.'
            )
            return
        if self._sh_cur_order == sh_new_order:
            return sh_new_order

        # temporarily pause execution
        event_running_state_before = system_config.IS_RUNNING.is_set()
        system_config.IS_RUNNING.clear()

        # adjust current SH order in convolver
        self._sh_cur_order = sh_new_order
        # re-apply adjusted SH compensations in convolver
        self._apply_sh_compensation(is_plot=False, logger=logger)

        # restore beforehand execution state
        if event_running_state_before:
            system_config.IS_RUNNING.set()

        return sh_new_order


    # TODO: Restore use of compensation as preimplemented
    
    # noinspection PyProtectedMember
    def _apply_sh_compensation(self, is_plot=True, logger=None):
        """
        Calculate and apply modal radial filter as well as further compensation filters. This
        function can be re-used during runtime, in case aspects of the rendering configuration
        change i.e., the current spherical harmonics rendering order.

        Parameters
        ----------
        is_plot : bool, optional
            if compensation filters should be plotted and exported
        logger : logging.Logger, optional
            instance to provide identical logging behaviour as the parent process
        """
        # reset compensation specific parameters to initial values (relevant when re-applying the
        # compensations)
        Compensation.reset_config(is_plot=is_plot)

        # (re)calculate block buffers
        self._filter.calculate_filter_blocks_nm()

        # backup raw block buffers
        irs_blocks_nm_before = self._filter._irs_blocks_nm.copy()

        # generate specified compensations based on one block length
        comp_nm = Compensation.generate_by_type(
            compensation_types=self._comp,
            filter_set=self._filter,
            arir_config=self._comp_arir_config,
            amp_limit_db=self._comp_mrf_limit,
            nfft=None,
            nfft_padded=self._input_block_td.shape[-1],
            logger=logger,
        )

        # apply compensations
        #self._filter._irs_blocks_nm *= comp_nm

        # plot comparison of raw and compensated block buffers
        name = self._filter._generate_plot_name(
            block_length=self._block_length, logger=logger
        )
        tools.export_plot(
            figure=tools.plot_nm_rms(
                data_nm_fd=np.concatenate(
                    (irs_blocks_nm_before, self._filter._irs_blocks_nm), axis=0
                )
            ),
            name=f"{name}_COMP",
            logger=logger,
        )

    def get_input_channel_count(self):
        """
        Returns
        -------
        int
            number of processed input channels
        """
        return self._input_block_td.shape[-2]

    def filter_block(self, input_block_td):
        """
        Process a block of samples with the given `FilterSet`. Steps before the complex
        multiplication are provided by `_filter_block_shift_and_convert_input()`. Steps after the
        complex multiplication are provided by `_filter_block_shift_and_convert_result()`.

        In passthrough mode, the functionality of `OverlapSaveConvolver` filtering is used.

        When the current rendering order is lowered during execution, the sound field is still
        decomposed at the full maximum order. Although, only coefficients up to the specified
        current order are used to calculated the ear signals. For best efficiency also the
        decomposition would only be done at the current order, but the implementation would
        become much more complicated (sizes of all internal buffers in SH domain would change).

        Parameters
        ----------
        input_block_td : numpy.ndarray or None
            block of time domain input samples of size [number of input channels; `_block_length`]

        Returns
        -------
        numpy.ndarray
            block of filtered time domain output samples of size [number of output channels;
            `_block_length`]
        """
        if self._is_passthrough or input_block_td is None:
            return super().filter_block(input_block_td)

        # transform into frequency domain and sh-coefficients
        
        #input_block_nm_1 = sfa.process.spatFT_RT(
        #    data=self._filter_block_shift_and_convert_input(input_block_td),
        #    spherical_harmonic_weighted=self._sh_bases_weighted,
        #)
        

        input_block_nm = self._sh_encode(data=self._filter_block_shift_and_convert_input(input_block_td))


        #logger.info(f"dim of filter encoding: {np.shape(input_block_nm)} ")
        #logger.info(f"dim of math encoding: {np.shape(input_block_nm_1)} ")
        # # _TODO: implement block-wise processing if filter is longer
        # for filter_block_nm, block_nm in zip(
        #     self._filter.get_filter_blocks_nm(), self._blocks_nm
        # ):
        #     block_nm[0] += filter_block_nm * input_block_nm * ...

        # apply reverse index and adjust size according to filter channels
        input_block_nm = input_block_nm[self._sh_m_rev_id][:, np.newaxis, :]
        
        #input_block_nm = input_block_nm[:][:, np.newaxis, :]
        
        #logger.info(f"dim of sig post new axis: {np.shape(input_block_nm)} ")
        input_block_nm = np.repeat(input_block_nm, self._blocks_fd.shape[-2], axis=1)
        #logger.info(f"dim of sig post repeat: {np.shape(input_block_nm)} ")
        #logger.info(f"blocks fd shape: {self._blocks_fd.shape[-2]} ")
        
        # for mm in range(9):
        #     if mm == 0: #or mm == 1:
        #         input_block_nm[mm,:,:] *=1
        #     elif mm == 3:
        #         input_block_nm[mm,1,:]*=-1
        #     else:
        #         input_block_nm[mm,:,:] =0

        # my_filter = self._filter.get_filter_blocks_nm()[0][self._sh_m_rev_id]
        # for mm in range(np.size(self._sh_m)):
        #     my_filter[mm] *= -1**(mm) 


        # apply HRIR coefficients
        #logger.info(f"dim of filter filter_block: {np.shape(self._filter.get_filter_blocks_nm())} ")
        #input_block_nm *= self._filter.get_filter_blocks_nm()[0]
        #input_block_nm *= my_filter
        

        for mm in range(9):
            if mm == 0 or mm==2 :
                input_block_nm[mm,:,:]*=self._filter.get_filter_blocks_nm()[0][mm,:,:]*0.5
            elif mm == 3:
                input_block_nm[mm,1,:]*=self._filter.get_filter_blocks_nm()[0][1,1,:]
                input_block_nm[mm,0,:]*=self._filter.get_filter_blocks_nm()[0][1,0,:]
            elif mm == 1:
                input_block_nm[mm,:,:] *=self._filter.get_filter_blocks_nm()[0][3,:,:]
            else:
                input_block_nm[mm,:,:] *=self._filter.get_filter_blocks_nm()[0][mm,:,:]*0

       
        # get head-tracker position (neglect elevation)
        azim_deg, _ = self._calculate_individual_directions()
        ## azim_deg = self.track_azim
        ## _ = self.track_elev
        sh_azim_nm = np.exp(
            self._blocks_fd.dtype.type(-1j) * self._sh_m * np.deg2rad(azim_deg)
        )
        #logger.info(f"sh_azim_nm: {sh_azim_nm}")
        # consider only the current rendering order here
        sh_azim_nm = sh_azim_nm[: (self._sh_cur_order + 1) ** 2, np.newaxis, np.newaxis]
        

        # calculation back into frequency domain into current buffer, after applying rotation
        # coefficients
        self._blocks_fd[0, 0] = np.sum(
            input_block_nm[: sh_azim_nm.shape[0]] * sh_azim_nm, axis=0
            #input_block_nm, axis=0
        )
        # transform back into time domain
        output_in_block_td = self._filter_block_shift_and_convert_result(
            is_last_block=False
        )

        output_in_block_td = np.real(output_in_block_td)
        # skip further calculations in case no crossfade in time domain should be done
        if not self._is_crossfade:
            return output_in_block_td

        # calculation back into frequency domain into last buffer, after applying rotation
        # coefficients
        self._last_blocks_fd[0, 0] = np.sum(
            input_block_nm[: self._last_sh_azim_nm.shape[0]] * self._last_sh_azim_nm,
            axis=0,
            #input_block_nm, axis=0
        )
        # transform back into time domain
       
        output_out_block_td = self._filter_block_shift_and_convert_result(
            is_last_block=True
        )
        output_out_block_td = np.real(output_out_block_td)
        # store last used azimuth exponents
        self._last_sh_azim_nm = sh_azim_nm  # copy should not be necessary here

        # add in time domain after applying windows
        return (output_in_block_td * self._window_in_td) + (
            output_out_block_td * self._window_out_td
        )

    def set_crossfade(self, new_state=None):
        """
        Parameters
        ----------
        new_state : bool or None, optional
            new crossfade state if output signals applying the current filter should be cross-faded
            with the output signals of the last filter, if `None` is given this function works as a
            toggle between states

        Returns
        -------
        bool
            actually realized crossfade state
        """
        try:
            super().set_crossfade(new_state)
        except AttributeError:
            pass

        # clean buffers if crossfade was turned off
        if not self._is_crossfade:
            self._last_sh_azim_nm.fill(0)

        return self._is_crossfade

    def _sh_encode(self,data):
        encoding_filter = self._encoding_filters.get_filter_blocks_fd()
        #mat_encoding_filter = np.reshape(encoding_filter,(8,8,np.shape(data)[1]))
        #logger.info(f"encoding_filter shape: {np.shape(encoding_filter)}" )
        
        #logger.info(f"encoding shape: {np.shape(encoding_filter[0,0,2+(3*8),:])}" )
        #print(data.dtype)
        res = np.zeros((9,np.shape(data)[1]),dtype=data.dtype)

        for i in range(8):
            for j in range(8):
                res_row = data[j,:] * encoding_filter[0,0,i+j*8,:] 
                # if i < 6: 
                #     writeChannel = i
                # else:
                #     writeChannel = i + 1
                # res[writeChannel,:] += res_row
                if i==0:
                    writeChannel= i
                    res[writeChannel,:] += res_row
                elif i==1:
                    writeChannel= i
                    res[writeChannel,:] += res_row
                elif i==2:
                    writeChannel= i
                    res[writeChannel,:] += res_row
                elif i==3:
                    writeChannel= i
                    res[writeChannel,:] += res_row
                elif i==4:
                    writeChannel= i
                    res[writeChannel,:] += res_row*0
                elif i==5:
                    writeChannel= i
                    res[writeChannel,:] += res_row*0
                elif i==6:
                    writeChannel= i+1
                    res[writeChannel,:] += res_row*0
                elif i==7:
                    writeChannel= i+1
                    res[writeChannel,:] += res_row*0
                
            #res[writeChannel] *= (-1)**(writeChannel +1)
            #logger.info(f"R channel abs sum: {np.sum(np.abs(res[6,:]))}")
        return res