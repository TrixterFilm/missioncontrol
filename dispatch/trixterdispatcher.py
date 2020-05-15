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

import sys

import IECore

import Gaffer
import GafferUI
import GafferDispatch

from missioncontrol.nodes import (
    Root,
    Serial,
    Parallel,
    HierarchyTask,
    JobtronautProcessor,
    JobtronautTask
)

class TaskTemplate(object):
    def __init__(self, name):
        self.name = name
        self.argument_processors = []
        self.required_tasks = []

    def __repr__(self):
        code = \
            """
            from jobtronaut.author import Task
            
            class {name}(Task):
                title = {name}
                argument_processors = {processors}
                required_tasks = {tasks}
            """.format(
                name=self.name,
                processors=self.argument_processors,
                tasks=self.required_tasks
            )
        return code

class JobtronautDispatcher(GafferDispatch.Dispatcher):
    """ Helper class to work around the limitation that we can't instantiate
    Gaffer.GafferDispatch.Dispatcher._TaskBatch directly. We have to utilize
    a proper Dipatcher for this purpose.
    """
    def __init__(self, name="Jobtronaut"):
        super(JobtronautDispatcher, self).__init__(name)
        self.scriptnode = None
        self.graphgadget = None

    def dispatch(self, nodes):
        submitting_node = nodes[0]
        scriptnode = submitting_node.scriptNode()

        all_hierarchy_nodes = JobtronautDispatcher.get_hierarchy_nodes(submitting_node, scriptnode)

        for hierarchy_node in all_hierarchy_nodes:
            template = TaskTemplate(hierarchy_node.getName())
            template.required_tasks = JobtronautDispatcher.get_required_tasks(hierarchy_node, scriptnode)
            template.argument_processors = JobtronautDispatcher.get_processors(hierarchy_node)
            print(template)

    @staticmethod
    def get_hierarchy_nodes(startnode, scriptnode, type_filter=HierarchyTask):
        connected = Gaffer.StandardSet()
        graphgadget = GafferUI.GraphGadget(scriptnode)
        if graphgadget is not None:
            connected.add([g.node() for g in graphgadget.connectedNodeGadgets(
                startnode,
                Gaffer.Plug.Direction.Out,
                sys.maxint
            ) if isinstance(g.node(), type_filter)])

        if isinstance(startnode, type_filter):
            connected.add(startnode)
        return connected

    @staticmethod
    def get_processors(startnode):
        processors = []
        current_plug = startnode.getChild("processor").getInput()

        while current_plug:
            current_node = current_plug.node()
            if isinstance(current_node, Gaffer.Dot):
                current_plug = current_node.getChild("in").getInput()
            elif isinstance(current_node, JobtronautProcessor):
                processors.insert(0, current_node.getName())
                current_plug = current_node.getChild("in").getInput()
        return processors

    @staticmethod
    def get_required_tasks(startnode, scriptnode):
        graphgadget = GafferUI.GraphGadget(scriptnode)
        assert graphgadget, "We need a proper graphgadget."

        class Tuple(tuple):
            def __init__(self, iterable):
                if len(iterable) == 1:
                    super(Tuple, self).__init__(iterable[0])
                else:
                    super(Tuple, self).__init__(iterable)

        class List(list):
            def __init__(self, iterable):
                if len(iterable) == 1:
                    super(List, self).__init__(iterable[0])
                else:
                    super(List, self).__init__(iterable)

        def _get_nodes(current):
            required_tasks = []
            downstream_nodes = tuple([g.node() for g in graphgadget.connectedNodeGadgets(
                current,
                Gaffer.Plug.Direction.Out,
                1
            )])

            for node in downstream_nodes:
                if isinstance(node, Gaffer.Dot):
                    required_tasks.append(_get_nodes(node))
                elif isinstance(node, Serial):
                    required_tasks.append(Tuple(_get_nodes(node)))
                elif isinstance(node, (Parallel)):
                    required_tasks.append(List(_get_nodes(node)))
                elif isinstance(node, (HierarchyTask, JobtronautTask)):
                    required_tasks.append(node.getName())

                # while len(required_tasks) == 1 and isinstance(required_tasks[0], (List, tuple)):
                #         required_tasks = required_tasks[0]

            return required_tasks

        required_tasks = _get_nodes(startnode)
        return required_tasks


    @staticmethod
    def generate_code(hierarchynode, stuff):
        pass

    @staticmethod
    def initialize(*args, **kwargs):
        print(args, kwargs)


GafferDispatch.Dispatcher.deregisterDispatcher("Tractor")
GafferDispatch.Dispatcher.deregisterDispatcher("Local")

IECore.registerRunTimeTyped(JobtronautDispatcher, typeName="trixterdispatcher::JobtronautDispatcher")
GafferDispatch.Dispatcher.registerDispatcher("JobtronautDispatcher", JobtronautDispatcher, JobtronautDispatcher.initialize)

Gaffer.Metadata.registerPlugValue(JobtronautDispatcher, "framesMode", "plugValueWidget:type", "")
Gaffer.Metadata.registerPlugValue(JobtronautDispatcher, "ignoreScriptLoadErrors", "plugValueWidget:type", "")
Gaffer.Metadata.registerPlugValue(JobtronautDispatcher, "environmentCommand", "plugValueWidget:type", "")
