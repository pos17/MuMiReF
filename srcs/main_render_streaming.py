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
from mics_process._remote import OscRemote
from time import sleep
from mics_process.tracker import HeadTracker
import numpy as np

from mics_process.jack_monitor import JackMonitor

# TODO: HANDLING LOGGING CORRECTLY

_INITIALIZE_DELAY = 0.5
"""Delay in seconds waited after certain points of the initialization progress to get a clear
logging behaviour. """

def main_renderer():

    def setup_tracker(
        name,
        TRACKER_TYPE,
        TRACKER_PORT
        ):
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
            tracker_type=TRACKER_TYPE,
            tracker_port=TRACKER_PORT,
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
                OSC_port=OSC_port,
                block_length=BLOCK_LENGTH,
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
        starting_input_channel,
        input_channel_count,
        starting_output_channel,
        output_channel_count,
        hrir_type,
        hrir_file,
        hrir_delay,
        hrir_level,
        arir_type,
        arir_file,
        arir_delay,
        arir_level,
        arir_mute,
        sh_max_order,
        ir_truncation_level,
        existing_tracker,
        existing_pre_renderer,
        azim_deg,
        compensation_setting,
        is_measured_encoding,
        encoding_filter_name,
        encoding_filter_type
    ):
        new_renderer = None
        try:
            new_renderer = JackRenderer(
                f"{name}-Renderer",
                OSC_port=OSC_port,
                block_length=BLOCK_LENGTH,
                filter_name=hrir_file,
                filter_type=hrir_type,
                input_delay_ms=hrir_delay,
                source_positions=[(azim_deg,0)],
                ##source_positions=None,
                ##source_positions=[(np.pi,3/2*np.pi)],
                shared_tracker_data=existing_tracker.get_shared_position(),
                sh_max_order= sh_max_order,
                sh_is_enforce_pinv=False,
                ir_trunc_db=ir_truncation_level,
                is_main_client=True,
                is_measure_levels=True,
                is_single_precision=system_config.IS_SINGLE_PRECISION,
                is_measured_encoding = is_measured_encoding,
                encoding_filter_name = encoding_filter_name,
                encoding_filter_type = encoding_filter_type,
                # azim_deg=azim_deg,
                # elevs_deg=0
            )

            server_input_ports = new_renderer.get_server_ports(is_audio=True,is_input=True)
            server_output_ports = new_renderer.get_server_ports(is_audio=True, is_output=True)
            source_ports = []
            for i in range(input_channel_count):
                source_ports.append(server_output_ports[starting_input_channel+i])
            
            output_ports = []
            for i in range(output_channel_count):
                output_ports.append(server_input_ports[starting_output_channel+i])
        

            if sh_max_order is not None and existing_pre_renderer:
                    prerenderer_sh_config = existing_pre_renderer.get_pre_renderer_sh_config()
                    if(sh_max_order == 2):
                        prerenderer_sh_config.sh_bases_weighted[-3,:] = 0
                    new_renderer.prepare_renderer_sh_processing(
                        input_sh_config= prerenderer_sh_config, ## existing_pre_renderer.get_pre_renderer_sh_config(),
                        mrf_limit_db=system_config.ARIR_RADIAL_AMP,
                        compensation_type= compensation_setting ##system_config.SH_COMPENSATION_TYPE,
                    )

            new_renderer.start(client_connect_target_ports=output_ports)
            print("output ports:")
            print(output_ports)
            ## new_jack_renderer._client_register_and_connect_outputs(target_ports=output_ports)
            
            new_renderer.set_output_volume_db(hrir_level)
            new_renderer.set_output_mute(False)
            #new_renderer.client_register_and_connect_inputs(source_ports=source_ports)
            
            sleep(_INITIALIZE_DELAY)
            if existing_pre_renderer and existing_pre_renderer.is_alive():
                if (
                    tools.transform_into_type(arir_type, FilterSet.Type)
                    is FilterSet.Type.AS_MIRO
                ):
                    # connect to system recording ports in case audio stream should be rendered
                    ## if config.SOURCE_FILE:
                        # recorded audio stream (generated `JackPlayer` has to connect to input
                        # ports later)
                    ##    new_renderer.client_register_and_connect_inputs(
                    ##        source_ports=False
                    ##    )
                    ## else:
                        # real-time captured audio stream (connect to system recording ports)
                    new_renderer.client_register_and_connect_inputs(
                        source_ports= source_ports
                       
                    )
                    print("Source ports:")
                    print(source_ports)
                else:
                    new_renderer.client_register_and_connect_inputs(
                        existing_pre_renderer.get_client_outputs()
                    )
            ## if existing_generator:
            ##    new_renderer.client_register_and_connect_inputs(
            ##        existing_generator.get_client_outputs()
            ##    )
            else:
                new_renderer.client_register_and_connect_inputs(source_ports=source_ports)
                print("Source ports no prerenderer:")
                print(source_ports)
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            logger.error(e)
            terminate_all(not_working_client = new_renderer)
            raise InterruptedError
        return new_renderer

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
    
    def setup_monitor(
            name,
            OSC_port,
            block_length,
            jack_chains,
            starting_output_channel,
            output_channel_count
        ):
        new_monitor = JackMonitor(
            name = name,
            OSC_port = OSC_port,
            block_length = block_length,
            is_measure_levels=True,
        )

        server_input_ports = new_monitor.get_server_ports(is_audio=True,is_input=True)
        
        output_ports = []
        for i in range(output_channel_count):
            output_ports.append(server_input_ports[starting_output_channel+i])
        
        new_monitor.start(client_connect_target_ports=output_ports)

        for i in range(len(jack_chains)):
            source_ports = jack_chains[i]["renderer"].get_client_outputs()
            source_name = jack_chains[i]["name"]
            new_monitor.client_register_and_connect_new_bin_input(input_src_name=source_name,source_ports=source_ports)
        return new_monitor
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
    with open('./srcs/config_spatial_mic_renderer_4_test_perc.yml', 'r') as file:
        mics_config = yaml.safe_load(file) 
    logger = process_logger.setup()
    #print(mics_config["microphones"][1]["name"])

    renderers_num = mics_config["clients_num"]
    BLOCK_LENGTH = mics_config["BLOCK_LENGTH"]
    sh_max_order = mics_config["SH_MAX_ORDER"]
    ir_truncation_level = mics_config["IR_TRUNCATION_LEVEL"]
    microphones = mics_config["microphones"]
    monitoring_setup = mics_config["monitoring"]
    REMOTE_OSC_PORT = mics_config["REMOTE_OSC_PORT"]
    jack_system = {}
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
            azim_deg= microphones[i]["azim_deg"]
            hrir_type = microphones[i]["hrir_type"]
            hrir_file = microphones[i]["hrir_file"]
            hrir_delay = microphones[i]["hrir_delay"]
            hrir_level = microphones[i]["hrir_level"]
            arir_type = microphones[i]["arir_type"]
            arir_file = microphones[i]["arir_file"]
            arir_delay = microphones[i]["arir_delay"]
            arir_level = microphones[i]["arir_level"]
            compensation_setting = microphones[i]["compensation"]
            is_measured_encoding = microphones[i]["is_measured_encoding"]
            encoding_filter_name = microphones[i]["encoding_filter_name"]
            encoding_filter_type = microphones[i]["encoding_filter_type"]
            jack_chains.append({})
            

            tracker = setup_tracker(name,None,OSC_port)
            pre_renderer = setup_pre_renderer(
                name=name,OSC_port=OSC_port,
                BLOCK_LENGTH=BLOCK_LENGTH,
                starting_input_channel=starting_input_channel,
                input_channel_count=input_channel_count,
                starting_output_channel=starting_output_channel,
                output_channel_count=output_channel_count,
                hrir_file=hrir_file,
                hrir_type=hrir_type,
                arir_file=arir_file,
                arir_type=arir_type,
                arir_delay=arir_delay,
                arir_level=arir_level,
                arir_mute=False,
                sh_max_order=sh_max_order,
                ir_truncation_level=ir_truncation_level,
                existing_tracker=tracker
                )

            
            jack_chains[i]["tracker"] = tracker
            jack_chains[i]["pre_renderer"]=pre_renderer
            jack_chains[i]["name"] = name
            
            renderer = setup_renderer(
                name=name,
                OSC_port=OSC_port,
                BLOCK_LENGTH=BLOCK_LENGTH,
                starting_input_channel=starting_input_channel,
                input_channel_count=input_channel_count,
                starting_output_channel=starting_output_channel,
                output_channel_count=output_channel_count,
                hrir_file=hrir_file,
                hrir_type=hrir_type,
                hrir_delay=hrir_delay,
                hrir_level=hrir_level,
                arir_file=arir_file,
                arir_type=arir_type,
                arir_delay=arir_delay,
                arir_level=arir_level,
                arir_mute=False,
                sh_max_order=sh_max_order,
                ir_truncation_level=ir_truncation_level,
                existing_tracker=tracker,
                existing_pre_renderer=pre_renderer,
                azim_deg = azim_deg,
                compensation_setting = compensation_setting,
                is_measured_encoding = is_measured_encoding,
                encoding_filter_name=encoding_filter_name,
                encoding_filter_type=encoding_filter_type
                )
            jack_chains[i]["renderer"] = renderer


    except InterruptedError:
        logger.error("application interrupted.")
        terminate_all()
        return logger  # terminate application

    for i in range(renderers_num):
        # set tracker reference position at application start
        jack_chains[i]["tracker"].set_zero_position()
       
    
    monitor_name = monitoring_setup["name"]
    monitor_OSC_port = monitoring_setup["osc_port"]
    monitor_starting_output_channel = monitoring_setup["starting_output_channel"]
    monitor_channel_count = monitoring_setup["output_channel_count"]

    monitor = setup_monitor(name=monitor_name,block_length = BLOCK_LENGTH, OSC_port=monitor_OSC_port,jack_chains=jack_chains,starting_output_channel=monitor_starting_output_channel,output_channel_count=monitor_channel_count)
    
    
    ## monitor.choose_bin_input_to_listen(0)
    system_config.IS_RUNNING.set()
    # startup completed
    print(tools.SEPARATOR)
    logger.info(
        "use [CTRL]+[C] (once!) to interrupt execution or OSC for remote control ..."
    )
    remote = OscRemote(REMOTE_OSC_PORT, logger=logger)
    sleep(_INITIALIZE_DELAY)

    clients = [monitor]
    for i in range(len(jack_chains)):
        clients.append(jack_chains[i]["tracker"])
        clients.append(jack_chains[i]["pre_renderer"])
        clients.append(jack_chains[i]["renderer"])
    # run remote interface until application is interrupted
    try:
        remote.start(clients=clients)
    except KeyboardInterrupt:
        logger.error("interrupted by user.")

    monitor.set_output_mute(False)
main_renderer()