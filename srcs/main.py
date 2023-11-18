from hashlib import new
from http import client
import sys
import yaml
import os
import mics_process.jack_client
from mics_process.jack_client import JackClient
from mics_process import process_logger
from mics_process import system_config
from time import sleep

# TODO: HANDLING LOGGING CORRECTLY

_INITIALIZE_DELAY = 0.5
"""Delay in seconds waited after certain points of the initialization progress to get a clear
logging behaviour. """

def main():

    # simple starting function for jack client implementation 
    def setup_jack_client(name, OSC_port, BLOCK_LENGTH,starting_input_channel,input_channel_count,starting_output_port,output_channel_count):
       
        new_jack_client = JackClient(name,OSC_port=OSC_port,block_length=BLOCK_LENGTH)

        server_input_ports = new_jack_client.get_server_ports(is_audio=True,is_input=True)
        server_output_ports = new_jack_client.get_server_ports(is_audio=True, is_output=True)
        source_ports = []
        for i in range(input_channel_count):
            source_ports.append(server_output_ports[starting_input_channel+i])
        
        output_ports = []
        for i in range(output_channel_count):
            output_ports.append(server_input_ports[starting_output_channel+i])

        new_jack_client.start()
        new_jack_client._client_register_and_connect_outputs(target_ports=output_ports)
        new_jack_client.set_output_volume_db(0)
        new_jack_client.set_output_mute(False)
        new_jack_client.client_register_and_connect_inputs(source_ports=source_ports)
        
        sleep(_INITIALIZE_DELAY)
        try:
            pass
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            logger.error(e)
            terminate_all_simple_clients(not_working_client = new_jack_client)
            raise InterruptedError
        return new_jack_client

    def terminate_all_simple_clients(not_working_client=None):
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
                not_working_client.terminate()
                not_working_client.join()
            except (NameError, AttributeError):
                pass
            for i in range(len(jack_clients)):
                try:
                    jack_clients[i].terminate()
                    jack_clients[i].join()
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
    with open('./srcs/config.yml', 'r') as file:
        mics_config = yaml.safe_load(file) 
    logger = process_logger.setup()
    #print(mics_config["microphones"][1]["name"])

    clients_num = mics_config["clients_num"]
    BLOCK_LENGTH = mics_config["BLOCK_LENGTH"]
    microphones = mics_config["microphones"]
    jack_clients = []
    for i in range(clients_num):
        name = microphones[i]["name"]
        OSC_port = microphones[i]["osc_port"]
        starting_input_channel = microphones[i]["starting_input_channel"]
        input_channel_count = microphones[i]["input_channel_count"]
        starting_output_channel = microphones[i]["starting_output_channel"]
        output_channel_count = microphones[i]["output_channel_count"]
        jack_clients.append(setup_jack_client(name,OSC_port,BLOCK_LENGTH,starting_input_channel,input_channel_count,starting_output_channel,output_channel_count))
        
    system_config.IS_RUNNING.set()


        
main()