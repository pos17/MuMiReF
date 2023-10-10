import multiprocessing
import sys
import signal
import os
import threading
import numpy as np
import yaml
import mic_client

# TODO: HANDLING LOGGING CORRECTLY


num_of_clients = 5
clients= []
if __name__ == "__main__":
    try:
        mp_context = multiprocessing.get_context("fork")
    except AttributeError:
        mp_context = multiprocessing


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
        prime_service = yaml.safe_load(file)
    argv = iter(sys.argv)
    # By default, use script name without extension as client name:
    
    
    defaultclientname = os.path.splitext(os.path.basename(next(argv)))[0]
    
    for i in range(num_of_clients):
        defaultclientnameSpec = defaultclientname + i
        clientname = next(argv, defaultclientname)
        servername = next(argv, None)
        clients.append()
        
        if clients[i].status.server_started:
            print('JACK server started')
        if clients[i].status.name_not_unique:
            print('unique name {0!r} assigned'.format(clients[i].name))

    event = threading.Event()
