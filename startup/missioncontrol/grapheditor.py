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

# everything that defines the graph editor behaviour
import functools
import logging
import os

import Gaffer
import GafferUI
import GafferDispatchUI

from jobtronaut.constants import LOGGING_NAMESPACE

_LOG = logging.getLogger("{}.gaffer.grapheditor".format(LOGGING_NAMESPACE))

# Slots ================================================================================================================

# opens NodeEditor
def _node_double_clicked(graphEditor, node):
    GafferUI.NodeEditor.acquire(node, floating=True)


def _node_context_menu_request(graph_editor, node, menu_definition):

    # lets us open the NodeEditor widget
    menu_definition.append("/Edit", {"command": functools.partial(GafferUI.NodeEditor.acquire, node, floating=True)})

    # lets us add an option to toggle enabled state of given node
    GafferUI.GraphEditor.appendEnabledPlugMenuDefinitions(graph_editor, node, menu_definition)

    # lets us add an option to toggle input/output connection visibility states of given node
    GafferUI.GraphEditor.appendConnectionVisibilityMenuDefinitions(graph_editor, node, menu_definition)

    # lets us open another GraphEditor to edit the node's subgraph, something that a `Box` node provides for example
    GafferUI.GraphEditor.appendContentsMenuDefinitions(graph_editor, node, menu_definition)

    # lets us add an option to open the dispatcher window
    GafferDispatchUI.DispatcherUI.appendNodeContextMenuDefinitions(graph_editor, node, menu_definition)

    # todo: figure out what this is for
    # GafferUI.UIEditor.appendNodeContextMenuDefinitions(graph_editor, node, menu_definition)

    # lets us add an option to set a node bookmarked, which can be pretty handy
    # check http://www.gafferhq.org/news/tip-bookmarks/
    GafferUI.GraphBookmarksUI.appendNodeContextMenuDefinitions(graph_editor, node, menu_definition)

    # append the menu entry specifically for the Box Node
    if node.typeName() == "Gaffer::Box":
        menu_definition.append("/ContentsDivider", {"divider": True})
        menu_definition.append("/Export Compound...", {"command": functools.partial(
                _export_compound, node=node)})


def _export_compound(menu=None, node=None):
    def _load(filepath, node, menu):
        node.load(filepath)

    # TODO: adjust the bookmarks to point to the compounds path
    bookmarks = GafferUI.Bookmarks.acquire(node, category="reference")

    compounds_path = os.getenv("GAFFER_COMPOUNDS_PATH")
    name = node.getName()

    path = Gaffer.FileSystemPath(os.path.join(compounds_path, "{}.grf".format(name)))
    path.setFilter(Gaffer.FileSystemPath.createStandardFilter(["grf"]))

    dialogue = GafferUI.PathChooserDialogue(path, title="Export Compound", confirmLabel="Export", leaf=True,
                                            bookmarks=bookmarks)
    path = dialogue.waitForPath(parentWindow=menu.ancestor(GafferUI.Window))

    if not path:
        return

    path = str(path)
    if not path.endswith(".grf"):
        path += ".grf"

    name = os.path.basename(os.path.splitext(path)[0])
    node.exportForReference(path)

    tabmenu = GafferUI.NodeMenu.acquire(application)
    menu_entry = "/Compounds/{}".format(name)
    tabmenu.append(menu_entry,
                functools.partial(Gaffer.Reference, name),
                postCreator=functools.partial(_load, path),
                searchText=name)

# Signal Connections ===================================================================================================

# I think we have to decide, do we want to edit on node doubled clicked or on context menu -> "Edit"??
# For now don't add the NodeEditor on double click, it can be annoying
# GafferUI.GraphEditor.nodeDoubleClickSignal().connect(_node_double_clicked, scoped=False)
GafferUI.GraphEditor.nodeContextMenuSignal().connect(_node_context_menu_request, scoped=False)
