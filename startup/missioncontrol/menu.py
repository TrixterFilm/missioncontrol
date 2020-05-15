# ######################################################################################################################
#  Copyright 2020 TRIXTER GmbH                                                                                         #
#                                                                                                                      #
#  Redistribution and use in source and binary forms, with or without modification, are permitted provided             #
#  that the following conditions are met:                                                                              #
#                                                                                                                      #
#  1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following #
#  disclaimer.                                                                                                         #
#                                                                                                                      #
#  2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the        #
#  following disclaimer in the documentation and/or other materials provided with the distribution.                    #
#                                                                                                                      #
#  3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote     #
#  products derived from this software without specific prior written permission.                                      #
#                                                                                                                      #
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,  #
#  INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE   #
#  DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,  #
#  SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS        #
#  OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF           #
#  LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY    #
#  OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.                                 #
# ######################################################################################################################

# everything that has to do something with menus, we will do it here...
import functools
import logging
import os

import Gaffer
import GafferUI
import IECore

from missioncontrol.nodes import (
    JobtronautTask,
    JobtronautProcessor,
    HierarchyTask,
    Root,
    Parallel,
    Serial
)

_LOG = logging.getLogger("trixter.gaffer.menu")


def append_compounds_to_menu(menu):
    def _load(filepath, node, menu):
        node.load(filepath)

    compounds_path = os.getenv("GAFFER_COMPOUNDS_PATH")
    if not compounds_path or not os.path.exists(compounds_path):
        _LOG.info("GAFFER_COMPOUNDS_PATH not set or the path does not exist. No compounds will be loaded.")
        return
    for compound in os.listdir(compounds_path):
        name, ext = os.path.splitext(compound)
        if ext == ".grf":
            menu_entry = "/Compounds/{}".format(name)
            filepath = os.path.join(compounds_path, compound)
            menu.append(menu_entry,
                        functools.partial(Gaffer.Reference, name),
                        postCreator=functools.partial(_load, filepath),
                        searchText=name)


def append_jobtronaut_plugins_to_menu(menu):
    from jobtronaut.author.plugins import Plugins
    tasks = Plugins().tasks
    processors = Plugins().processors

    for name in sorted(tasks):
        menu.append("/Tasks/{}".format(name),
                    functools.partial(JobtronautTask, name, name),
                    searchText=name)
    for name in sorted(processors):
        menu.append("/Processors/{}".format(name),
                    functools.partial(JobtronautProcessor, name, name),
                    searchText=name)


# ======================================================================================================================
# define the main window
application_window_menu = GafferUI.ScriptWindow.menuDefinition(application)
GafferUI.ApplicationMenu.appendDefinitions(application_window_menu, prefix="/Gaffer")
GafferUI.FileMenu.appendDefinitions(application_window_menu, prefix="/File" )
GafferUI.EditMenu.appendDefinitions(application_window_menu, prefix="/Edit" )
GafferUI.LayoutMenu.appendDefinitions(application_window_menu, name="/Layout" )

# ======================================================================================================================
# define dispatcher menus
# GafferUI.DispatcherUI.appendMenuDefinitions(application_window_menu, prefix="/Execute" )
# GafferUI.LocalDispatcherUI.appendMenuDefinitions(application_window_menu, prefix="/Execute")

# ======================================================================================================================
# define node creation menu, try to keep the alphabetical order here, because it matters!
moduleSearchPath = IECore.SearchPath(os.environ["PYTHONPATH"])
nodeMenu = GafferUI.NodeMenu.acquire(application)

nodeMenu.append("Root", Root, searchText="Root")
nodeMenu.append("HierarchyTask", HierarchyTask, searchText="HierarchyTask")
nodeMenu.append("Parallel", Parallel, searchText="Paralel")
nodeMenu.append("Serial", Serial, searchText="Serial")

nodeMenu.definition().append("/Utility/Backdrop", {"command": GafferUI.BackdropUI.nodeMenuCreateCommand})
nodeMenu.append("/Utility/Box", GafferUI.BoxUI.nodeMenuCreateCommand)
nodeMenu.append("/Utility/BoxIn", Gaffer.BoxIn)
nodeMenu.append("/Utility/BoxOut", Gaffer.BoxOut)
nodeMenu.append("/Utility/Dot", Gaffer.Dot)

nodeMenu.append("/Utility/Dot", Gaffer.Dot)
# nodeMenu.append("/FTrack/InitializeFTrackSession", nodes.InitializeFTrackSession, searchText="InitializeFTrackSession")
# append_compounds_to_menu(nodeMenu)
append_jobtronaut_plugins_to_menu(nodeMenu)

# nodeMenu.definition().append("/Utility/Backdrop", {"command": GafferUI.BackdropUI.nodeMenuCreateCommand})
# nodeMenu.append("/Utility/Reference", GafferUI.ReferenceUI.nodeMenuCreateCommand)

# ======================================================================================================================
# do whatever future forces us to do
