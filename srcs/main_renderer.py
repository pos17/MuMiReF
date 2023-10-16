from hashlib import new
from http import client
from operator import is_
import sys
import yaml
import os
from mics_process.jack_renderer import JackRenderer
from mics_process import process_logger
from mics_process import system_config
from time import sleep

# TODO: HANDLING LOGGING CORRECTLY

_INITIALIZE_DELAY = 0.5
"""Delay in seconds waited after certain points of the initialization progress to get a clear
logging behaviour. """

def main_renderer():

    # simple starting function for jack client implementation 
    def setup_jack_renderer(name, 
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
        ir_truncation_level
    ):

        new_jack_renderer = JackRenderer(
            name,
            OSC_port=OSC_port,
            block_length=BLOCK_LENGTH,
            filter_name=hrir_file,
            filter_type=hrir_type,
            input_delay_ms=hrir_delay,
            source_positions=[(0,0)],
            shared_tracker_data=None,
            sh_max_order= sh_max_order,
            sh_is_enforce_pinv=False,
            ir_trunc_db=ir_truncation_level,
            is_main_client=True,
            is_measure_levels=True,
            is_single_precision=system_config.IS_SINGLE_PRECISION,
        )

        server_input_ports = new_jack_renderer.get_server_ports(is_audio=True,is_input=True)
        server_output_ports = new_jack_renderer.get_server_ports(is_audio=True, is_output=True)
        source_ports = []
        for i in range(input_channel_count):
            source_ports.append(server_output_ports[starting_input_channel+i])
        
        output_ports = []
        for i in range(output_channel_count):
            output_ports.append(server_input_ports[starting_output_channel+i])

        new_jack_renderer.start()
        new_jack_renderer._client_register_and_connect_outputs(target_ports=output_ports)
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

    def terminate_all_simple_clients(not_working_renderer=None):
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
    with open('./srcs/config_renderer.yml', 'r') as file:
        mics_config = yaml.safe_load(file) 
    logger = process_logger.setup()
    #print(mics_config["microphones"][1]["name"])

    renderers_num = mics_config["clients_num"]
    BLOCK_LENGTH = mics_config["BLOCK_LENGTH"]
    sh_max_order = mics_config["SH_MAX_ORDER"]
    ir_truncation_level = mics_config["IR_TRUNCATION_LEVEL"]
    microphones = mics_config["microphones"]
    jack_renderers = []
    for i in range(renderers_num):
        name = microphones[i]["name"]
        OSC_port = microphones[i]["osc_port"]
        starting_input_channel = microphones[i]["starting_input_channel"]
        input_channel_count = microphones[i]["input_channel_count"]
        starting_output_channel = microphones[i]["starting_output_channel"]
        output_channel_count = microphones[i]["output_channel_count"]
        hrir_type = microphones[i]["hrir_type"]
        hrir_file = microphones[i]["hrir_file"]
        hrir_delay = microphones[i]["hrir_delay"]
       
        jack_renderers.append(
            setup_jack_renderer(
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
                ir_truncation_level
            )                             
        )
        
    system_config.IS_RUNNING.set()


        
main_renderer()