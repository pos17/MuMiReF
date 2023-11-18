from hashlib import new
from http import client
from operator import is_
import sys
import yaml
import os
from mics_process import tools
from mics_process.filter_set import FilterSet
from mics_process.jack_renderer import JackRenderer
from mics_process import process_logger
from mics_process import system_config
from time import sleep
from mics_process.tracker import HeadTracker

# TODO: HANDLING LOGGING CORRECTLY

_INITIALIZE_DELAY = 0.5
"""Delay in seconds waited after certain points of the initialization progress to get a clear
logging behaviour. """

def main_renderer():

    # simple starting function for jack client implementation 

    def setup_tracker():
        """
        Create and start a new `HeadTracker` instance, providing head tracking data to a suitable
        `JackRenderer` process.

        Returns
        -------
        HeadTracker
            freshly created instance
        """
        new_tracker = HeadTracker.create_instance_by_type(
            name=f"{name}-Tracker",
            tracker_type=system_config.TRACKER_TYPE,
            tracker_port=system_config.TRACKER_PORT,
        )
        new_tracker.start()
        sleep(_INITIALIZE_DELAY)

        return new_tracker

    def setup_pre_renderer(
        name, 
        OSC_port, 
        BLOCK_LENGTH,
        starting_input_channel,
        input_channel_count,
        starting_output_channel,
        output_channel_count,
        hrir_type,
        hrir_file,
        arir_type,
        arir_file,
        arir_level,
        arir_mute,
        arir_delay,
        sh_max_order,
        ir_truncation_level,
        existing_tracker

    ):
        """
        Create and start a new `JackRenderer` instance, providing a pre-rendering of Array Room
        Impulse Responses by applying a streamed audio signal to it. If applicable, also a matching
        `JackGenerator` instance will be created and started.

        Returns
        -------
        JackRenderer
            freshly created instance
        JackGenerator
            freshly created instance
        """
        new_renderer = None
        # new_generator = None
        try:
            # If this line fails with `jack.Status 0x21` then the current JACK environment is
            # problematic. Therefore, try again after restarting your system.
            new_renderer = JackRenderer(
                name=f"{name}-PreRenderer",
                block_length=system_config.BLOCK_LENGTH,
                filter_name=arir_file,
                filter_type=arir_type,
                sh_max_order=sh_max_order,
                sh_is_enforce_pinv=False,
                ir_trunc_db=ir_truncation_level,
                is_main_client=False,
                is_single_precision=system_config.IS_SINGLE_PRECISION,
            )
            #checking input and output ports assigned
            server_input_ports = new_renderer.get_server_ports(is_audio=True,is_input=True)
            server_output_ports = new_renderer.get_server_ports(is_audio=True, is_output=True)
            source_ports = []
            for i in range(input_channel_count):
                source_ports.append(server_output_ports[starting_input_channel+i])
            
            output_ports = []
            for i in range(output_channel_count):
                output_ports.append(server_input_ports[starting_output_channel+i])
            # check `_counter_dropout` if file was loaded, see `JackRenderer._init_convolver()`
            if new_renderer.get_dropout_counter() is None or tools.transform_into_type(
                hrir_type, FilterSet.Type
            ) not in [FilterSet.Type.HRIR_MIRO, FilterSet.Type.HRIR_SOFA]:
                logger.warning("skipping microphone array pre-rendering.")
                return None #, new_generator

            # in case of microphone array audio stream (real-time capture or recorded)
            elif (
                tools.transform_into_type(arir_type, FilterSet.Type)
                is FilterSet.Type.AS_MIRO
            ):
                logger.warning(
                    "skipping microphone array pre-rendering (file still loaded to gather "
                    "configuration). "
                )

            # in case microphone array IR set should be rendered
            else:
                new_renderer.start(client_connect_target_ports=output_ports)
                new_renderer.set_output_volume_db(arir_level)
                new_renderer.set_output_mute(arir_mute)
                sleep(_INITIALIZE_DELAY)
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            logger.error(e)
            terminate_all(additional_renderer=new_renderer)
            raise InterruptedError
        return new_renderer

    def setup_renderer(
        name, 
        OSC_port, 
        BLOCK_LENGTH,
        hrir_type,
        hrir_file,
        hrir_delay,
        sh_max_order,
        ir_truncation_level,
        existing_tracker,
        existing_pre_renderer
        # azim_deg
    ):

        new_renderer = JackRenderer(
            name,
            OSC_port=OSC_port,
            block_length=BLOCK_LENGTH,
            filter_name=hrir_file,
            filter_type=hrir_type,
            input_delay_ms=hrir_delay,
            source_positions=[(0,0)],
            shared_tracker_data=existing_tracker.get_shared_position(),
            sh_max_order= sh_max_order,
            sh_is_enforce_pinv=False,
            ir_trunc_db=ir_truncation_level,
            is_main_client=True,
            is_measure_levels=True,
            is_single_precision=system_config.IS_SINGLE_PRECISION,
            # azim_deg=azim_deg,
            # elevs_deg=0
        )

        ## server_input_ports = new_jack_renderer.get_server_ports(is_audio=True,is_input=True)
        ## server_output_ports = new_jack_renderer.get_server_ports(is_audio=True, is_output=True)
        ## source_ports = []
        ## for i in range(input_channel_count):
        ##     source_ports.append(server_output_ports[starting_input_channel+i])
        ## 
        ## output_ports = []
        ## for i in range(output_channel_count):
        ##     output_ports.append(server_input_ports[starting_output_channel+i])

        if sh_max_order is not None and existing_pre_renderer:
                new_renderer.prepare_renderer_sh_processing(
                    input_sh_config=existing_pre_renderer.get_pre_renderer_sh_config(),
                    mrf_limit_db=config.ARIR_RADIAL_AMP,
                    compensation_type=config.SH_COMPENSATION_TYPE,
                )

        new_renderer.start(client_connect_target_ports=output_ports)
        ## new_jack_renderer._client_register_and_connect_outputs(target_ports=output_ports)
        
        new_jack_renderer.set_output_volume_db(0)
        new_jack_renderer.set_output_mute(False)
        new_jack_renderer.client_register_and_connect_inputs(source_ports=source_ports)
        
        sleep(_INITIALIZE_DELAY)
        try:
            pass
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            logger.error(e)
            terminate_all_simple_clients(not_working_client = new_jack_renderer)
            raise InterruptedError
        return new_jack_renderer

    def terminate_all(not_working_renderer=None):
            """
            Terminate all (potentially) spawned child processes after muting the last client in the
            rendering chain (headphone compensation or binaural renderer).

            Parameters
            ----------
            not_working_client : JackClient, optional
                client that should be terminated, which was not (yet) returned to the main run
                function and is part of the usually implemented list of clients (see below)
            """
            system_config.IS_RUNNING.clear()
            try:
                not_working_renderer.terminate()
                not_working_renderer.join()
            except (NameError, AttributeError):
                pass
            for i in range(len(jack_renderers)):
                try:
                    jack_renderers[i].terminate()
                    jack_renderers[i].join()
                except (NameError, AttributeError):
                    pass


    print("starting system")
    if sys.version_info < (3, 0):
        # In Python 2.x, event.wait() cannot be interrupted with Ctrl+C.
        # Therefore, we disable the whole KeyboardInterrupt mechanism.
        # This will not close the JACK client properly, but at least we can
        # use Ctrl+C.
        print("python version < 3.0")
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        
    else:
        # If you use Python 3.x, everything is fine.
        print("python version > 3.0")

    # opening config file
    with open('./srcs/config_renderer_1.yml', 'r') as file:
        mics_config = yaml.safe_load(file) 
    logger = process_logger.setup()
    #print(mics_config["microphones"][1]["name"])

    renderers_num = mics_config["clients_num"]
    BLOCK_LENGTH = mics_config["BLOCK_LENGTH"]
    sh_max_order = mics_config["SH_MAX_ORDER"]
    ir_truncation_level = mics_config["IR_TRUNCATION_LEVEL"]
    microphones = mics_config["microphones"]
    jack_chains = []

    system_config.BLOCK_LENGTH = BLOCK_LENGTH
    try:
        name = "test"
        tracker = setup_tracker()
        for i in range(renderers_num):
            
            jack_chains.append([])

            name = microphones[i]["name"]
            OSC_port = microphones[i]["osc_port"]
            starting_input_channel = microphones[i]["starting_input_channel"]
            input_channel_count = microphones[i]["input_channel_count"]
            starting_output_channel = microphones[i]["starting_output_channel"]
            output_channel_count = microphones[i]["output_channel_count"]
            angle= microphones[i]["angle"]
            hrir_type = microphones[i]["hrir_type"]
            hrir_file = microphones[i]["hrir_file"]
            hrir_delay = microphones[i]["hrir_delay"]



            jack_chains[i].append(
                setup_pre_renderer(
                    name,
                    OSC_port,
                    BLOCK_LENGTH,
                    starting_input_channel,
                    input_channel_count,
                    starting_output_channel,
                    output_channel_count,
                    hrir_type,
                    hrir_file,
                    hrir_delay,
                    sh_max_order,
                    ir_truncation_level,
                    existing_tracker=tracker
                    # azim_deg=angle
                )                             
            )
    except InterruptedError:
        logger.error("application interrupted.")
        terminate_all()
        return logger  # terminate application

    # set tracker reference position at application start
    tracker.set_zero_position()
    system_config.IS_RUNNING.set()


        
main_renderer()