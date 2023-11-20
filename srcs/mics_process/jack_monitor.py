from .jack_client import JackClient

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
        self.set_output_mute(True)
        # set attributes
        self._is_passthrough = True
        self._input_count = 0
        self._binaural_feeds = []
        self._listened_bin_input = None

    
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

        self._client_register_inputs(len(source_ports))
        self._logger.info(
                f"new list of inputs connected to monitoring"
            )
        if is_connect:
            # connect source to input ports
            for src, dst in zip(source_ports, self._client.inports):
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
