from . import mp_context, tools


# ################# #
#  ! DO NOT EDIT !  #
# ################# #



IS_RUNNING = mp_context.Event()
"""If the application is running and rendering audio at the moment. This needs to be set after
all rendering clients have started up. This can also be used to globally interrupt rendering and
output of all clients. """
