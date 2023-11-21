from .jack_client import JackClient
from . import system_config
import jack

class JackMonitor(JackClient):
    """
    Extension of `JackClient` to provide monitoring functionalities during live rendering.
    The system accepts multiple stereo inputs and provides one stereo output

    Attributes
    ----------
    _is_passthrough : bool
        if JACK client should passthrough signals without any processing
    """


    def __init__(
        self,
        name,
        OSC_port,
        block_length,
        *args,
        **kwargs,
    ):
    
        super().__init__(name=name,OSC_port=OSC_port, block_length=block_length, *args, **kwargs)
        # set attributes
        self._is_passthrough = True
        self._input_count = 0
        self._binaural_feeds = []
        self._listened_bin_input = None

    # noinspection DuplicatedCode
    def _client_register_inputs_in_addition(self, input_count):
        """
        Parameters
        ----------
        input_count : int
            number of input ports to be registered to the current client

        Raises
        ------
        RuntimeError
            re-raise of jack.JackError
        """
        ##if input_count <= len(self._client.inports):
        ##    return

        # cleanup existing input ports
        ##self._client.inports.clear()

        try:
            # create input ports according to source channel number (index starting from 1)
            last_port = len(self._client.inports)
            for number in range(1, input_count + 1):
                self._client.inports.register(f"input_{last_port+number}")
        except jack.JackError as e:
            raise RuntimeError(f"[JackError]  {e}")

        # recreate input buffer
        self._input_buffer.init(
            max_length_sec=system_config.CLIENT_MAX_DELAY_SEC,
            channel_count=len(self._client.inports),
        )
    
    def client_register_and_connect_inputs(self, source_ports=True):
        """
        Register an identical number of input ports according to the provided source ports to the
        current client. Afterwards connect the given ports to the newly created target ports in a
        1:1 relation.

        Parameters
        ----------
        source_ports : jack.Ports or bool or None, optional
            source ports for connecting the created input ports to. If None is given, a port number
            according to the system recording ports is registered. If True is given, ports will
            be registered and also connected to the system recording ports. If False is given,
            no ports will be registered or connected.

        Raises
        ------
        ValueError
            in case no source ports are provided and also no physical recording ports are found
        """
        if source_ports is False:
            return

        is_connect = source_ports is not None

        # temporarily pause execution
        event_ready_state_before = self._event_ready.is_set()
        self._event_ready.clear()

        

        # if type(source_ports) is not jack.Ports:
        #    # get physical recording ports in case no ports were given
        #    source_ports = self._client.get_ports(is_physical=True, is_output=True)
        #    if not source_ports:
        #        raise ValueError(
        #            "no source ports given and no physical recording ports detected."
        #        )
        
        self._client_register_inputs_in_addition(len(source_ports))
        self._logger.info(
                f"new list of inputs connected to monitoring"
            )
        if is_connect:
            # connect source to input ports
            for src, dst in zip(source_ports, self._client.inports[-len(source_ports):]):
                self._logger.info(
                    f"src port: {src}, dst port: {dst}"
                )
                self._client.connect(src, dst)

        # restore beforehand execution state
        if event_ready_state_before:
            self._event_ready.set()

    def client_register_and_connect_new_bin_input(self, input_src_name, source_ports=True, ):

        self.client_register_and_connect_inputs(source_ports=source_ports)
        _new_binaural_feed = {
            "name": input_src_name,
            "source_ports": source_ports
        }
        self._binaural_feeds.append(_new_binaural_feed)

    def choose_bin_input_to_listen(self, bin_input_index):

        self._listened_bin_input = bin_input_index
        self.set_output_mute(False)

    def _process(self, input_td):
        if self._listened_bin_input == None: 
           return

        to_return = input_td[2*self._listened_bin_input:2*self._listened_bin_input+1,:]
        return to_return

    def start(self,client_connect_target_ports):
        super().start()
        self._logger.debug("activating JACK client ...")
        self._client.activate()
        self._client_register_and_connect_outputs(client_connect_target_ports)
        self._event_ready.set()
        self.set_output_mute(True)