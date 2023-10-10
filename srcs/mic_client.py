from os import system
import jack
import numpy as np
import tools
import system_config


class mic_client: 
    def __init__(self, client_name, servername):
         
        self.client = jack.Client(client_name, servername=servername)

        @self.client.set_process_callback
        def process(frames):
            """
            Process signals block wise. It should not be necessary to override this function by
            deriving classes. Rather modify the individual implementations in
            `_process_receive()`, `_process()` and `_process_deliver()`.

            Parameters
            ----------
            frames : int
                number of samples in the current block
            """
            #if self._event_terminate.is_set() or not self._client.outports:
            #    return

            # this should not be necessary here, but prevents errors when restarting `JackPlayer`
            
            #self._event_ready.wait()

            # receive, process and deliver audio blocks
            
            self._process_deliver(self._process(self._process_receive()))

            # measure and log / provide individual client and overall system load
            
            #self._report_load()

    def _process_receive(self):
        """
        Gather input audio blocks from JACK. Optionally the memory structure of the data will be
        checked here.

        Returns
        -------
        numpy.ndarray
            block of audio data that was received from JACK

        Notes
        -----
        When receiving the input arrays from JACK it is necessary to store copies when data needs
        to persist longer then this processing frame. This applies here, since at least one block
        is buffered and shifted internally even for un-partitioned convolution. In the current
        implementation `np.vstack()` creates a copy of the data.
        """
        if not self._client.inports or not system_config.IS_RUNNING.is_set():
            return None

        # receive input from JACK, `np.vstack()` creates a copy
        input_td = np.vstack([port.get_array() for port in self._client.inports])

        # buffer and delay input
        input_td = self._input_buffer.process_block(input_td)

        # TODO: prevent all dynamic variable allocations
        # self._logger.info(id(input_td))

        # # check array structure
        # if not input_td.flags["C_CONTIGUOUS"]:
        #     self._logger.warning('input array not "C_CONTIGUOUS".')

        return input_td
    
    def _process(self, input_td):
        """
        Process block of audio data. This implementation provides a straight passthrough
        behaviour. If actual signal processing should happen, a deriving class needs to override
        this function.

        Parameters
        ----------
        input_td : numpy.ndarray
            block of audio data that was received from JACK

        Returns
        -------
        numpy.ndarray
            processed block of audio data that will be delivered to JACK
        """
        # straight passthrough
        return input_td
        # TODO: skip processing in case output is muted or volume is 0?

    def _process_deliver(self, output_td):
        """
        Apply output volume to output audio blocks and deliver them to JACK. Optionally the
        memory structure and sample clipping of the data will be checked here.

        Output data channels greater then available output ports are neglected. Output ports
        greater then available output data are filled with zeros.

        Parameters
        ----------
        output_td : numpy.ndarray or None
            processed block of audio data that will be delivered to JACK
        """
        if self._event_terminate.is_set():
            return

        if self._output_mute or output_td is None:
            # output zeros
            for port in self._client.outports:
                port.get_array().fill(0)

        else:
            # apply output volume (scaling for all channels) as well as relative differences (
            # between channels)
            output_td *= self._output_volume * self._output_volume_relative

            if self._is_measure_levels:
                # calculate RMS level
                rms = tools.calculate_rms(output_td, is_level=True)
                if self._osc_client:
                    # OSC only works with float64, see
                    # https://github.com/attwad/python-osc/issues/102
                    self._osc_client.send_message(
                        f"{self._osc_name}/rms", np.round(rms, 1).astype(np.float64)
                    )
                else:
                    log_str = np.array2string(
                        rms, separator=",", precision=1, floatmode="fixed", sign="+"
                    )
                    self._logger.info(f"output RMS level [{log_str}]")

                # calculate PEAK level
                peak = tools.calculate_peak(output_td, is_level=True)
                if self._osc_client:
                    # OSC only works with float64, see
                    # https://github.com/attwad/python-osc/issues/102
                    self._osc_client.send_message(
                        f"{self._osc_name}/peak", np.round(peak, 2).astype(np.float64)
                    )
                else:
                    log_str = np.array2string(
                        peak, separator=",", precision=2, floatmode="fixed", sign="+"
                    )
                    self._logger.debug(f"output PEAK level [{log_str}]")

            # check array structure and dtype (first processing frame only)
            if self._is_first_frame:
                self._is_first_frame = False
                if output_td[0].flags["C_CONTIGUOUS"]:
                    self._logger.debug(f'output array layout is "C_CONTIGUOUS".')
                else:
                    self._logger.warning(f'output array layout is not "C_CONTIGUOUS".')
                if (self._is_single_precision and output_td.dtype == np.float32) or (
                    not self._is_single_precision and output_td.dtype == np.float64
                ):
                    self._logger.debug(
                        f'output array dtype is "{output_td.dtype}" as requested.'
                    )
                elif self._is_single_precision and output_td.dtype != np.float32:
                    self._logger.warning(
                        f'output array dtype is "{output_td.dtype}" instead of {np.float32}.'
                    )
                elif not self._is_single_precision and output_td.dtype != np.float64:
                    self._logger.warning(
                        f'output array dtype is "{output_td.dtype}" instead of {np.float64}.'
                    )
                else:
                    self._logger.warning(
                        f'output array dtype is unexpected: "{output_td.dtype}".'
                    )

            # regarding maximum number of ports or result channels
            for data, port in zip(output_td, self._client.outports):
                # check for clipping
                peak = np.abs(data).max()
                if self._is_detect_clipping and peak > 1:
                    self._logger.warning(
                        f"output clipping detected ({port.shortname} @ {peak:.2f})."
                    )

                # deliver output to JACK
                port.get_array()[:] = data  # assigning to a slice creates a copy

            # regarding ports greater then result channels
            for port in self._client.outports[output_td.shape[0] :]:
                # output zeros
                port.get_array().fill(0)