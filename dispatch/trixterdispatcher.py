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

import re
import os
import sys
import textwrap

try:
    import autopep8
except ImportError:
    autopep8 = None

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


class Lambda(object):
    def __init__(self, code):
        self._code = code

    def __repr__(self):
        return self._code


class TaskTemplate(object):
    def __init__(self, name):
        self.name = name
        self.title = ""
        self.description = ""
        self.argument_defaults = {}
        self.argument_processors = []
        self.required_tasks = []
        self.elements_id = ""
        self.per_element = False

    def __repr__(self):
        code = "class {}(Task):".format(self.name)
        code += "\n    title = '''{}'''".format(self.title)
        code += "\n    description = '''{}'''".format(self.description) if self.description else ""
        code += "\n    elements_id = '{}'".format(self.elements_id) if self.elements_id else ""
        code += "\n    argument_defaults = {}".format(self.argument_defaults) if self.argument_defaults else ""
        code += "\n    argument_processors = {}".format(self.argument_processors) if self.argument_processors else ""
        code += "\n    flags = Task.Flags.PER_ELEMENT" if self.per_element else ""
        code += "\n    required_tasks = {}".format(self.required_tasks)

        return code


class ProcessorDefinitionTemplate(object):
    def __init__(self, name):
        self.name = name
        self.scope = []
        self.parameters = {}

    def __repr__(self):
        code = "ProcessorDefinition("
        code += "name='{}'".format(self.name)
        code += ",scope={}".format(self.scope) if self.scope else ""
        code += ",parameters={}".format(self.parameters) if self.parameters else ""
        code += ")"

        return code


class JobtronautDispatcher(GafferDispatch.Dispatcher):
    """ Helper class to work around the limitation that we can't instantiate
    Gaffer.GafferDispatch.Dispatcher._TaskBatch directly. We have to utilize
    a proper Dipatcher for this purpose.
    """
    def __init__(self, name="Jobtronaut"):
        super(JobtronautDispatcher, self).__init__(name)
        self.scriptnode = Gaffer.ScriptNode("ScriptNode")
        self.graphgadget = None

        # Set and hide existing plugs
        self.getChild("jobsDirectory").setValue("/tmp/gafferdispatch")
        Gaffer.Metadata.registerPlugValue(self.__class__, "framesMode", "plugValueWidget:type", "")
        Gaffer.Metadata.registerPlugValue(self.__class__, "ignoreScriptLoadErrors", "plugValueWidget:type", "")
        Gaffer.Metadata.registerPlugValue(self.__class__, "environmentCommand", "plugValueWidget:type", "")
        Gaffer.Metadata.registerPlugValue(self.__class__, "jobName", "plugValueWidget:type", "")
        Gaffer.Metadata.registerPlugValue(self.__class__, "jobsDirectory", "plugValueWidget:type", "")

        # Add custom plugs to the Dispatcher UI
        taskfile_location_plug = Gaffer.StringPlug("taskfile", Gaffer.Plug.Direction.In)
        taskfile_location_plug.setValue("/tmp/temptasks.py")
        Gaffer.Metadata.registerPlugValue(taskfile_location_plug, "nodule:type", "")
        Gaffer.Metadata.registerPlugValue(taskfile_location_plug, "plugValueWidget:type", "GafferUI.FileSystemPathPlugValueWidget")
        Gaffer.Metadata.registerPlugValue(taskfile_location_plug, "path:leaf", False)
        self.addChild(taskfile_location_plug)

    @staticmethod
    def _get_named_values(parent, plug_name, ignore_if_default=False):
        mapped = {}
        for plug in parent.getChild(plug_name).values():
            if plug.getChild("enabled"):
                value = plug.getChild("value").getValue()
                if isinstance(value, (
                IECore.IntVectorData, IECore.StringVectorData, IECore.FloatVectorData, IECore.BoolVectorData)):
                    value = list(value)
                elif isinstance(value, basestring):
                    if re.match(r"^\s*lambda\s+.*", value):
                        value = Lambda(value)
                    else:
                        try:
                            value = eval(value)
                        except SyntaxError:
                            pass

                if ignore_if_default:
                    if not plug.getChild("value").isSetToDefault():
                        mapped[plug.getChild("name").getValue()] = value
                else:
                    mapped[plug.getChild("name").getValue()] = value

        return mapped

    def dispatch(self, nodes):
        submitting_node = nodes[0]
        scriptnode = submitting_node.scriptNode()

        # todo: figure out how to get the filename/scriptnode in the __init__ call
        # filename = os.path.splitext(os.path.basename(scriptnode.getChild("fileName").getValue()))[0]
        # self.getChild("taskfile").setValue("/tmp/jobtronaut_plugins/{}.py".format(filename))

        all_hierarchy_nodes = JobtronautDispatcher.get_hierarchy_nodes(submitting_node, scriptnode)

        code = "from jobtronaut.author import (Task, ProcessorDefinition)"

        for hierarchy_node in all_hierarchy_nodes:
            template = TaskTemplate(hierarchy_node.getName())
            template.required_tasks = JobtronautDispatcher.get_required_tasks(hierarchy_node, scriptnode)

            for processor_node in JobtronautDispatcher.get_processors(hierarchy_node):
                processor = ProcessorDefinitionTemplate(processor_node.getChild("type").getValue())
                processor.scope = list(processor_node.getChild("scope").getValue())

                processor.parameters = self._get_named_values(processor_node, "parameters", ignore_if_default=True)

                template.argument_processors.append(processor)

            argument_defaults = self._get_named_values(hierarchy_node, "argument_defaults")

            template.argument_defaults = argument_defaults
            template.title = hierarchy_node.getChild("title").getValue()
            template.description = hierarchy_node.getChild("description").getValue()
            template.elements_id = hierarchy_node.getChild("elements_id").getValue()
            template.per_element = hierarchy_node.getChild("per_element").getValue()

            code += "\n\n\n{}".format(template)

        code = textwrap.dedent(code)

        if autopep8:
            code = autopep8.fix_code(code, options={
                "aggressive": True,
                "experimental": True,
                "hang_closing": False,
                "max_line_length": 80
            })

        filepath = self.getChild("taskfile").getValue()
        with open(filepath, "w+") as fp:
            fp.write(code)

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
                processors.insert(0, current_node)
                current_plug = current_node.getChild("in").getInput()
        return processors


    @staticmethod
    def get_required_tasks(startnode, scriptnode):
        graphgadget = GafferUI.GraphGadget(scriptnode)
        assert graphgadget, "We need a proper graphgadget."

        def _reduce_hierarchy_levels(nodes):
            """ Reduces unnecessary hierarchy levels for those cases that there's
            only a single entry in a Tuple or List. In these cases the nesting
            does not add any useful information and can be ignored.
            """
            if isinstance(nodes, List):
                while len(nodes) == 1:
                    nodes = nodes[0]

            elif isinstance(nodes, Tuple):
                while (len(nodes)) == 1:
                    nodes = nodes[0]
                if not isinstance(nodes, Tuple):
                    nodes = Tuple(nodes)

            return nodes

        def _get_nodes(current):
            required_tasks = List([])
            downstream_nodes = tuple([g.node() for g in graphgadget.connectedNodeGadgets(
                current,
                Gaffer.Plug.Direction.Out,
                1
            )])

            # Sorting by the x position is the expected behaviour for serial execution.
            # We assume that the x ordering of downstream nodes is the determining
            # factor for execution order.
            downstream_nodes = sorted(downstream_nodes, key=lambda node: graphgadget.getNodePosition(node).x)

            for node in downstream_nodes:
                if isinstance(node, Gaffer.Dot):
                    required_tasks.append(_reduce_hierarchy_levels(_get_nodes(node)))
                elif isinstance(node, Serial):
                    required_tasks.append(_reduce_hierarchy_levels(Tuple(_get_nodes(node))))
                elif isinstance(node, Parallel):
                    required_tasks.append(_reduce_hierarchy_levels(List(_get_nodes(node))))
                elif isinstance(node, (HierarchyTask, JobtronautTask)):
                    required_tasks.append(node.getName())

            return _reduce_hierarchy_levels(required_tasks)

        required_tasks = _get_nodes(startnode)

        # Make sure that we don't end up with a single required task without any wrapping List or Tuple
        return required_tasks if isinstance(required_tasks, (List, Tuple)) else [required_tasks]



    @staticmethod
    def initialize(parent_plug):
        pass


