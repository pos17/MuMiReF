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
from mics_process.jack_ambi_enc import JackAmbisonicEncoder
import numpy as np


# TODO: HANDLING LOGGING CORRECTLY

_INITIALIZE_DELAY = 0.5
"""Delay in seconds waited after certain points of the initialization progress to get a clear
logging behaviour. """

def main_ambisonic_encoder():

    def setup_ambisonic_encoder(
        name, 
        OSC_port, 
        BLOCK_LENGTH,
        starting_input_channel,
        input_channel_count,
        starting_output_channel,
        output_channel_count,
        config_type,
        config_file,
        sh_max_order,
        sh_is_enforce_pinv
    ):
        new_ambi_enc = None
        try:
            new_ambi_enc = JackAmbisonicEncoder(
                name=name,
                OSC_port=OSC_port,
                block_length=BLOCK_LENGTH,
                file_name = config_file,
                sh_max_order=sh_max_order,
                sh_is_enforce_pinv = sh_is_enforce_pinv,
            )

           

            server_input_ports = new_ambi_enc.get_server_ports(is_audio=True,is_input=True)
            server_output_ports = new_ambi_enc.get_server_ports(is_audio=True, is_output=True)
            source_ports = []
            for i in range(input_channel_count):
                source_ports.append(server_output_ports[starting_input_channel+i])
            
            output_ports = []
            for i in range(output_channel_count):
                output_ports.append(server_input_ports[starting_output_channel+i])

            
        

            if sh_max_order is not None:
                    new_ambi_enc.load_config_file(is_single_precision=system_config.IS_SINGLE_PRECISION)

            new_ambi_enc.start(client_connect_target_ports=output_ports)
            print("output ports:")
            print(output_ports)
            ## new_jack_renderer._client_register_and_connect_outputs(target_ports=output_ports)
            
            new_ambi_enc.set_output_volume_db(0)
            new_ambi_enc.set_output_mute(False)
            #new_renderer.client_register_and_connect_inputs(source_ports=source_ports)
            
            sleep(_INITIALIZE_DELAY)
            new_ambi_enc.client_register_and_connect_inputs(source_ports=source_ports)
            print("Source ports no prerenderer:")
            print(source_ports)
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            logger.error(e)
            terminate_all(not_working_client = new_ambi_enc)
            raise InterruptedError
        return new_ambi_enc

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
            for i in range(len(jack_chains)):
                for j in range(len(jack_chains[i])):
                    try:
                        jack_chains[i][j].terminate()
                        jack_chains[i][j].join()
                    except (NameError, AttributeError):
                        pass
    
    # code to be executed inside main

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
    with open('./srcs/config_spatial_mic_ambisonic_encoder_1.yml', 'r') as file:
        mics_config = yaml.safe_load(file) 
    logger = process_logger.setup()
    #print(mics_config["microphones"][1]["name"])

    renderers_num = mics_config["clients_num"]
    BLOCK_LENGTH = mics_config["BLOCK_LENGTH"]
    sh_max_order = mics_config["SH_MAX_ORDER"]
    microphones = mics_config["microphones"]
    jack_chains = [] 

    system_config.BLOCK_LENGTH = BLOCK_LENGTH
    
    try:
        for i in range(renderers_num):
            name = microphones[i]["name"]
            OSC_port = microphones[i]["osc_port"]
            starting_input_channel = microphones[i]["starting_input_channel"]
            input_channel_count = microphones[i]["input_channel_count"]
            starting_output_channel = microphones[i]["starting_output_channel"]
            output_channel_count = microphones[i]["output_channel_count"]
            config_type = microphones[i]["arir_type"]
            config_file = microphones[i]["arir_file"]
            

            jack_chains.append([])

    
            
            ambi_enc = setup_ambisonic_encoder(
                name=name,
                OSC_port=OSC_port,
                BLOCK_LENGTH=BLOCK_LENGTH,
                starting_input_channel=starting_input_channel,
                input_channel_count=input_channel_count,
                starting_output_channel=starting_output_channel,
                output_channel_count=output_channel_count,
                config_type=config_type,
                config_file=config_file,
                sh_max_order=sh_max_order,
                sh_is_enforce_pinv=False
                          )
            jack_chains[i].append(ambi_enc)


    except InterruptedError:
        logger.error("application interrupted.")
        terminate_all()
        return logger  # terminate application

    for i in range(renderers_num):
        # set tracker reference position at application start
        ##jack_chains[i][0].set_zero_position()
        system_config.IS_RUNNING.set()

    # startup completed
    print(tools.SEPARATOR)
    logger.info(
        "use [CTRL]+[C] (once!) to interrupt execution or OSC for remote control ..."
    )

main_ambisonic_encoder()