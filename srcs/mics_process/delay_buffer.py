import numpy as np
class DelayBuffer(object):
    """
    Basic class to provide a delay line of time domain signals with a ringbuffer. The realized
    delay will always be integer multiples of the system audio block size. There is a system wide
    configurable maximum delay time.

    Attributes
    ----------
    _buffer : numpy.ndarray
        time domain block buffer of size [number of maximum delay blocks; number of input channels;
        `_block_length`]
    _buffer_ptr : int
        index of current block in the buffer being filled with new input, where the index of the
        current block in the buffer being delivered as output is relative to this
    _sample_rate : int
        system specific sampling frequency
    _block_length : int
        system specific size of every audio block
    _delay_blocks : int
        current delay in blocks, being integer multiples of the block length
    """

    def __init__(self, sample_rate, block_length, delay_ms=0.0):
        """
        Parameters
        ----------
        sample_rate : int
            system specific sampling frequency
        block_length : int
            system specific size of every audio block
        delay_ms : float, optional
            starting delay in delay in milliseconds
        """
        self._buffer = None
        self._buffer_ptr = 0
        self._sample_rate = sample_rate
        self._block_length = block_length
        self._delay_blocks = self._calculate_delay_blocks(delay_ms)

    def init(self, max_length_sec, channel_count):
        """
        Parameters
        ----------
        max_length_sec : int
            maximum possible delay to buffer in seconds, determining the size of the buffer
        channel_count : int
            number of channels to buffer
        """
        # +1 for being able to realize the maximum delay without wrapping around to the current
        # block
        block_count = self._calculate_delay_blocks(delay_ms=max_length_sec * 1000) + 1
        self._buffer = np.zeros(
            shape=(block_count, channel_count, self._block_length), dtype=np.float32
        )
        self._reset()

    def _calculate_delay_blocks(self, delay_ms):
        """
        Parameters
        ----------
        delay_ms : float
            delay in milliseconds

        Returns
        -------
        int
            required number of whole processing blocks to realize desired delay
        """
        return int(np.ceil((delay_ms / 1000) * self._sample_rate / self._block_length))

    def _reset(self):
        """Reset the buffer by filling it with zeros."""
        if self._buffer is not None:
            self._buffer.fill(0)
        self._buffer_ptr = 0

    def set_delay(self, new_delay_ms=0.0):
        """
        Parameters
        ----------
        new_delay_ms : float, optional
            new delay in milliseconds, if no value is given the delay is set to 0

        Returns
        -------
        float
            actually realized delay in milliseconds
        """
        if self._buffer is None:
            return self._delay_blocks

        # round to full block length
        self._delay_blocks = self._calculate_delay_blocks(new_delay_ms)

        # limit to maximum number of blocks
        if self._delay_blocks > self._buffer.shape[0]:
            self._delay_blocks = self._buffer.shape[0]

        if self._delay_blocks == 0:
            self._reset()

        # return delay in ms
        return (self._delay_blocks * self._block_length / self._sample_rate) * 1000

    def process_block(self, input_td):
        """
        Parameters
        ----------
        input_td : numpy.ndarray or None
            current time domain input block of size [number of input channels; `_block_length`]

        Returns
        -------
        numpy.ndarray
            delayed time domain output block of size [number of output channels; `_block_length`]
        """
        if self._buffer is None or not self._delay_blocks or input_td is None:
            return input_td

        # write current block into buffer
        self._buffer[self._buffer_ptr] = input_td

        # read delayed block from buffer
        output_td = self._buffer[self._buffer_ptr - self._delay_blocks]

        # advance block pointer
        self._buffer_ptr += 1
        if self._buffer_ptr >= self._buffer.shape[0]:
            self._buffer_ptr = self._buffer_ptr % self._buffer.shape[0]

        return output_td
