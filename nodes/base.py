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

import ast
import imath
import inspect
import logging
import sys

from collections import namedtuple
import contextlib
from uuid import uuid4

import Gaffer
import GafferDispatch
import IECore

from jobtronaut.constants import LOGGING_NAMESPACE
from jobtronaut.author.plugins import Plugins

TASKS_PLUGS_TO_HIDE = [
    "preTasks",
    "postTasks",
    "task"
]

LOG_MESSAGE_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)s: node: {node}: line: %(lineno)s %(message)s"
LOG_TIME_FORMAT = "%H:%M:%S"

_TASK_COLOR = imath.Color3f(0.75, 0.24, 0.18)
_PROCESSOR_COLOR = imath.Color3f(0.18, 0.4, 0.6)
_HIERARCHY_TASK_COLOR = imath.Color3f(0.2, 0.2, 0.2)
_TASK_IN_OUT_COLOR = imath.Color3f(0.65, 0.14, 0.08)
_PROCESSOR_IN_OUT_COLOR = imath.Color3f(0.08, 0.3, 0.5)
_ARGUMENTS_COLOR = imath.Color3f(0.48, 0.35, 0.5)
_ARGUMENTS_CONNECTION_COLOR = imath.Color3f(0.5, 0.5, 0.5)

Expansion = namedtuple("Expansion", ["root", "arguments"])

@contextlib.contextmanager
def temporary_attribute_value(obj, attr, new_value):
    """ Temporarily set an attribute on an object for the duration of the context manager

    Args:
        obj (instance):
        attr (): name of the attribute to override
        new_value (): override value

    Returns:

    """
    replaced = False
    old_value = None
    if hasattr(obj, attr):
        try:
            if attr in obj.__dict__:
                replaced = True
        except AttributeError:
            if attr in obj.__slots__:
                replaced = True
        if replaced:
            old_value = getattr(obj, attr)
    setattr(obj, attr, new_value)
    yield replaced, old_value
    if not replaced:
        delattr(obj, attr)
    else:
        setattr(obj, attr, old_value)


def get_expand_task_names(cls):
    class NodeVisitor(ast.NodeVisitor):
        def __init__(self, *args, **kwargs):
            super(NodeVisitor, self).__init__(*args, **kwargs)
            self.expansions = []

        def visit_Call(self, tree_node):
            if hasattr(tree_node.func, "attr"):
                if tree_node.func.attr == "__EXPAND__":
                    self.expansions.append(
                        Expansion(
                            tree_node.args[0].s,
                            [key.s for key in tree_node.args[1].keys]
                        )
                    )

    tree = ast.parse(inspect.getsource(cls))
    visitor = NodeVisitor()
    visitor.visit(tree)
    return visitor.expansions


class PluginSerialiser(Gaffer.NodeSerialiser):

    def moduleDependencies(self, node, serialisation):
        return {"missioncontrol.nodes.base as nodebase"} | Gaffer.NodeSerialiser.moduleDependencies(self, node, serialisation)

    def constructor(self, node, serialisation):
        return "nodebase.{}(\"{}\", \"{}\")".format(
            node.__class__.__name__, node.getName(), node.getChild("type").getValue()
        )


class ArgumentsPlug(Gaffer.Plug):
    def __init__( self, name="ArgumentsPlug", direction=Gaffer.Plug.Direction.In, flags = Gaffer.Plug.Flags.Default ) :
        Gaffer.Plug.__init__(self, name, direction, flags)
        self.inputHasBeenSet = False

    def acceptsInput(self, plug):
        if not Gaffer.Plug.acceptsInput(self, plug):
            return False

        return isinstance(plug, (ArgumentsPlug, type(None)))

    def setInput(self, plug):
        Gaffer.Plug.setInput(self, plug)
        self.inputHasBeenSet = True

    def acceptsParent(self, potentialParent):
        if not Gaffer.Plug.acceptsParent(self, potentialParent):
            return False

        if isinstance(potentialParent, Gaffer.ValuePlug):
            return False

        return True

    def createCounterpart(self, name, direction):
        return ArgumentsPlug(name, direction, self.getFlags())


class ProcessorPlug(Gaffer.Plug):
    def __init__( self, name="ProcessorPlug", direction=Gaffer.Plug.Direction.In, flags = Gaffer.Plug.Flags.Default ) :
        Gaffer.Plug.__init__(self, name, direction, flags)
        self.inputHasBeenSet = False

    def acceptsInput(self, plug):
        if not Gaffer.Plug.acceptsInput(self, plug):
            return False

        return isinstance(plug, (ProcessorPlug, type(None)))

    def setInput(self, plug):
        Gaffer.Plug.setInput(self, plug)
        self.inputHasBeenSet = True

    def acceptsParent(self, potentialParent):
        if not Gaffer.Plug.acceptsParent(self, potentialParent):
            return False

        if isinstance(potentialParent, Gaffer.ValuePlug):
            return False

        return True

    def createCounterpart(self, name, direction):
        return ProcessorPlug(name, direction, self.getFlags())

IECore.registerRunTimeTyped(ArgumentsPlug)
IECore.registerRunTimeTyped(ProcessorPlug)


# todo: consider injecting a global base class to all node base types, so we don't need to have those mixins
class GafferNodeBaseMixin(object):
    def _setup_logger(self):
        # generate an unique logger per node per instance
        if not hasattr(self, "log"):
            self.log = logging.getLogger("{0}.gaffer.nodes.{1}".format(LOGGING_NAMESPACE, str(uuid4())))

        if not hasattr(self, "_log_handler"):
            self._log_handler = logging.StreamHandler(stream=sys.stdout)
            self.log.addHandler(self._log_handler)

        # always let the formatter include the current node name, so we can
        # easily identify our message emitter
        self._log_handler.setFormatter(
            logging.Formatter(
                LOG_MESSAGE_FORMAT.format(node=self.fullName()),
                LOG_TIME_FORMAT
            )
        )

    def _setup_signals(self):
        # handle auto connection to preTasks plugs
        self.__plugInputChangedConnection = self.plugInputChangedSignal().connect(
            Gaffer.WeakMethod(self._on_plug_input_changed)
        )
        # handle logger setup
        self.__nameChangedConnections = self.nameChangedSignal().connect(
            Gaffer.WeakMethod(self._on_name_changed)
        )

    def _on_name_changed(self, node):
        self._setup_logger()

    def _on_plug_input_changed(self, plug):
        pass


class GafferTaskNodeBase(Gaffer.TaskNode, GafferNodeBaseMixin):
    def __init__(self, name="BaseTask", hide_plugs=TASKS_PLUGS_TO_HIDE):
        super(GafferTaskNodeBase, self).__init__(name)
        self._setup_logger()
        self._setup_signals()
        self.ignore_changed_inputs_signal = False

        for name in hide_plugs:
            Gaffer.Metadata.registerPlugValue(self.getChild(name), "nodule:type", "")

    def _add_to_input_nodes(self, input_nodes, plug):
        if plug.getInput() not in (self, None):
            if isinstance(plug.source().node(), (GafferTaskNodeBase, Gaffer.Dot, Gaffer.Box)):
                _input = plug.source()
                if _input:
                    input_nodes.add(_input.node())

    def _get_unique_value_inputs(self):
        input_nodes = set()
        for plug in self.values():
            if plug.direction() == Gaffer.Plug.Direction.In:
                if plug.typeName() == "Gaffer::ArrayPlug":
                    for childplug in plug.values():
                        self._add_to_input_nodes(input_nodes, childplug)
                else:
                    self._add_to_input_nodes(input_nodes, plug)
        return input_nodes

    def _disconnect_all_tasks(self):
        for task in self.getChild("preTasks").values():
            task.setInput(None)

    def _connect_task(self, node):
        _task_plug = node.getChild("task")
        if _task_plug:
            self.getChild("preTasks")[-1].setInput(node.getChild("task"))

    #### slots ####

    def _on_plug_input_changed(self, plug):

        # ignore event handling for taskplugs
        if plug.typeName() == "GafferDispatch::TaskNode::TaskPlug":
            return

        if self.ignore_changed_inputs_signal:
            return

        with temporary_attribute_value(self, "ignore_changed_inputs_signal", True):
            self._disconnect_all_tasks()

            for node in self._get_unique_value_inputs():
                self._connect_task(node)

        return


class GafferDependencyNodeBase(Gaffer.DependencyNode, GafferNodeBaseMixin):
    def __init__(self, name="BaseTask"):
        super(GafferDependencyNodeBase, self).__init__(name)
        self._setup_logger()
        self._setup_signals()

        type_plug = Gaffer.StringPlug("type", Gaffer.Plug.Direction.In)
        type_plug.setValue(name)
        Gaffer.MetadataAlgo.setReadOnly(type_plug, True)
        Gaffer.Metadata.registerPlugValue(type_plug, "nodule:type", "")
        self.addChild(type_plug)

    def _on_plug_input_changed(self, plug):
        if isinstance(plug, ArgumentsPlug) and plug.getInput():
            name = plug.getInput().getName()
            self.setName(name)
            self.getChild("type").setValue(name)
        return


class JobtronautPluginBase(GafferTaskNodeBase):

    def add_code_nodules(self, plugin):
        code_plug = Gaffer.StringPlug("source", defaultValue=inspect.getsource(plugin))
        Gaffer.Metadata.registerPlugValue(code_plug, "nodule:type", "")
        Gaffer.Metadata.registerValue(
            code_plug, "layout:section", "Code"
        )
        Gaffer.Metadata.registerValue(
            code_plug,
            "plugValueWidget:type", "GafferUI.MultiLineStringPlugValueWidget"
        )
        Gaffer.Metadata.registerValue(
            code_plug,
            "multiLineStringPlugValueWidget:role", "code"
        )
        Gaffer.Metadata.registerValue(
            code_plug,
            "layout:section:Settings.Code:summary",
            "Information about the source code of this plugin."
        )
        Gaffer.MetadataAlgo.setReadOnly(code_plug, True)
        self.addChild(code_plug)

        module_plug = Gaffer.StringPlug("module", defaultValue=Plugins().get_module_path(self.type_plug.getValue()))
        Gaffer.Metadata.registerValue(
            module_plug, "layout:section", "Code"
        )
        Gaffer.MetadataAlgo.setReadOnly(module_plug, True)
        self.addChild(module_plug)


class JobtronautTask(JobtronautPluginBase):
    def __init__(self, name, task_name):
        super(JobtronautTask, self).__init__(name)

        Gaffer.Metadata.registerValue(self.__class__, "nodeGadget:color", _TASK_COLOR)

        in_plug = GafferDispatch.TaskNode.TaskPlug("in", Gaffer.Plug.Direction.In)
        Gaffer.Metadata.registerPlugValue(in_plug, "nodule:type", "GafferUI::StandardNodule")
        Gaffer.Metadata.registerPlugValue(in_plug, "nodule:color", _TASK_IN_OUT_COLOR)
        Gaffer.Metadata.registerPlugValue(in_plug, "noduleLayout:section", "top")
        Gaffer.Metadata.registerPlugValue(in_plug, "plugValueWidget:type", "")
        self.addChild(in_plug)

        self.type_plug = self.getChild("type")
        if not self.type_plug:
            self.type_plug = Gaffer.StringPlug("type", Gaffer.Plug.Direction.In)
            self.addChild(self.type_plug)

        self.type_plug.setValue(task_name)
        Gaffer.MetadataAlgo.setReadOnly(self.type_plug, True)
        Gaffer.Metadata.registerPlugValue(self.type_plug, "nodule:type", "")

        plugin = Plugins().task(task_name)

        Gaffer.Metadata.registerValue(self, "description", plugin.description)

        expansions = get_expand_task_names(plugin)
        for expansion in expansions:
            expand_plug = GafferDispatch.TaskNode.TaskPlug(expansion.root, Gaffer.Plug.Direction.Out)
            Gaffer.Metadata.registerPlugValue(expand_plug, "nodule:type", "GafferUI::StandardNodule")
            Gaffer.Metadata.registerPlugValue(expand_plug, "nodule:color", _TASK_IN_OUT_COLOR)
            Gaffer.Metadata.registerPlugValue(expand_plug, "noduleLayout:section", "right")
            Gaffer.Metadata.registerPlugValue(expand_plug, "plugValueWidget:type", "")
            self.addChild(expand_plug)

            for argument in expansion.arguments:
                arguments_plug = ArgumentsPlug(argument, Gaffer.Plug.Direction.Out)
                Gaffer.Metadata.registerPlugValue(arguments_plug, "nodule:type", "GafferUI::StandardNodule")
                Gaffer.Metadata.registerPlugValue(arguments_plug, "nodule:color", _ARGUMENTS_COLOR)
                Gaffer.Metadata.registerPlugValue(arguments_plug, "noduleLayout:section", "right")
                Gaffer.Metadata.registerPlugValue(arguments_plug, "plugValueWidget:type", "")
                Gaffer.Metadata.registerPlugValue(arguments_plug, "connectionGadget:color", _ARGUMENTS_CONNECTION_COLOR)
                self.addChild(arguments_plug)

        self.add_code_nodules(plugin)


class JobtronautProcessor(JobtronautPluginBase):
    def __init__(self, name, processor_name):
        super(JobtronautProcessor, self).__init__(name)

        Gaffer.Metadata.registerValue(self.__class__, "nodeGadget:color", _PROCESSOR_COLOR)
        Gaffer.Metadata.registerValue(self.__class__, "icon", "processor.png")

        scope_name_plug = Gaffer.StringVectorDataPlug(
            "scope", Gaffer.Plug.Direction.In, defaultValue=IECore.StringVectorData()
        )
        Gaffer.Metadata.registerPlugValue(scope_name_plug, "nodule:type", "")
        self.addChild(scope_name_plug)

        self.type_plug = self.getChild("type")
        if not self.type_plug:
            self.type_plug = Gaffer.StringPlug("type", Gaffer.Plug.Direction.In)
            self.addChild(self.type_plug)

        self.type_plug.setValue(processor_name)
        Gaffer.MetadataAlgo.setReadOnly(self.type_plug, True)
        Gaffer.Metadata.registerPlugValue(self.type_plug, "nodule:type", "")

        in_plug = ProcessorPlug("in", Gaffer.Plug.Direction.In)
        Gaffer.Metadata.registerPlugValue(in_plug, "nodule:type", "GafferUI::StandardNodule")
        Gaffer.Metadata.registerPlugValue(in_plug, "nodule:color", _PROCESSOR_IN_OUT_COLOR)
        Gaffer.Metadata.registerPlugValue(in_plug, "noduleLayout:section", "top")
        Gaffer.Metadata.registerPlugValue(in_plug, "plugValueWidget:type", "")
        self.addChild(in_plug)

        out_plug = ProcessorPlug("out", Gaffer.Plug.Direction.Out)
        Gaffer.Metadata.registerPlugValue(out_plug, "nodule:type", "GafferUI::StandardNodule")
        Gaffer.Metadata.registerPlugValue(out_plug, "nodule:color", _PROCESSOR_IN_OUT_COLOR)
        Gaffer.Metadata.registerPlugValue(out_plug, "noduleLayout:section", "bottom")
        Gaffer.Metadata.registerPlugValue(out_plug, "plugValueWidget:type", "")
        self.addChild(out_plug)

        plugin = Plugins().processor(processor_name)

        Gaffer.Metadata.registerValue(
            self["scope"],
            "layout:section:Settings.Scope:summary",
            "The scopes the processed values will be applied to."
        )
        Gaffer.Metadata.registerValue(
            self["scope"], "layout:section", "Settings.Scope"
        )

        parameters_plug = Gaffer.CompoundDataPlug("parameters", Gaffer.Plug.Direction.In)

        Gaffer.Metadata.registerPlugValue(parameters_plug, "nodule:type", "")
        Gaffer.Metadata.registerValue(
            parameters_plug, "layout:section", "Settings.Parameters"
        )
        Gaffer.Metadata.registerValue(
            parameters_plug,
            "layout:section:Settings.Parameters:summary",
            "The parameters this processor is supposed to work with."
        )
        for parameter_name, parameter_value in plugin.parameters.items():
            if isinstance(parameter_value, basestring):
                plug = Gaffer.NameValuePlug(
                    parameter_name, IECore.StringData(parameter_value), True, name=parameter_name
                )
            elif isinstance(parameter_value, float):
                plug = Gaffer.NameValuePlug(
                    parameter_name, IECore.FloatData(parameter_value), True, name=parameter_name
                )
            elif isinstance(parameter_value, bool):
                plug = Gaffer.NameValuePlug(
                    parameter_name, IECore.BoolData(parameter_value), True, name=parameter_name
                )
            elif isinstance(parameter_value, int):
                plug = Gaffer.NameValuePlug(
                    parameter_name, IECore.IntData(parameter_value), True, name=parameter_name
                )
            elif isinstance(parameter_value, list):
                if parameter_value and all([isinstance(_, basestring) for _ in parameter_value]):
                    plug = Gaffer.NameValuePlug(
                        parameter_name,
                        IECore.StringVectorData(parameter_value),
                        True,
                        name=parameter_name
                    )
                elif parameter_value and all([isinstance(_, bool) for _ in parameter_value]):
                    plug = Gaffer.NameValuePlug(
                        parameter_name,
                        IECore.BoolVectorData(parameter_value),
                        True,
                        name=parameter_name
                    )
                elif parameter_value and all([isinstance(_, int) for _ in parameter_value]):
                    plug = Gaffer.NameValuePlug(
                        parameter_name,
                        IECore.IntVectorData(parameter_value),
                        True,
                        name=parameter_name
                    )
                elif parameter_value and all([isinstance(_, float) for _ in parameter_value]):
                    plug = Gaffer.NameValuePlug(
                        parameter_name,
                        IECore.FloatVectorData(parameter_value),
                        True,
                        name=parameter_name
                    )
            else:
                plug = Gaffer.NameValuePlug(
                    parameter_name, IECore.StringData(str(parameter_value)), True, name=parameter_name
                )

            parameters_plug.addChild(plug)

        self.addChild(parameters_plug)
        self.add_code_nodules(plugin)

        Gaffer.Metadata.registerValue(self, "description", plugin.description)


class HierarchyTask(GafferDependencyNodeBase):
    def __init__(self, name="HierarchyTask"):
        super(HierarchyTask, self).__init__(name)

        Gaffer.Metadata.registerValue(self.__class__, "nodeGadget:color", _HIERARCHY_TASK_COLOR)
        Gaffer.Metadata.registerValue(self.__class__, "icon", "hierarchy.png")

        title_plug = Gaffer.StringPlug("title", Gaffer.Plug.Direction.In, defaultValue="No title set.")
        Gaffer.Metadata.registerPlugValue(title_plug, "nodule:type", "")
        self.addChild(title_plug)

        description_plug = Gaffer.StringPlug("description", Gaffer.Plug.Direction.In, defaultValue="No description")
        Gaffer.Metadata.registerPlugValue(description_plug, "plugValueWidget:type", "GafferUI.MultiLineStringPlugValueWidget")
        Gaffer.Metadata.registerPlugValue(description_plug, "multiLineStringPlugValueWidget:continuousUpdate", True)
        Gaffer.Metadata.registerPlugValue(description_plug, "nodule:type", "")
        self.addChild(description_plug)

        argument_defaults_plug = Gaffer.CompoundDataPlug("argument_defaults", Gaffer.Plug.Direction.In)

        Gaffer.Metadata.registerPlugValue(argument_defaults_plug, "nodule:type", "")
        Gaffer.Metadata.registerValue(
            argument_defaults_plug, "layout:section", "Settings.Argument_Defaults"
        )
        Gaffer.Metadata.registerValue(
            argument_defaults_plug,
            "layout:section:Settings.ArgumentDefaults:summary",
            "The default values for arguments the task requires."
        )
        self.addChild(argument_defaults_plug)

        elements_id_plug = Gaffer.StringPlug("elements_id", Gaffer.Plug.Direction.In, defaultValue="")
        Gaffer.Metadata.registerPlugValue(elements_id_plug, "nodule:type", "")
        self.addChild(elements_id_plug)

        per_element_plug = Gaffer.BoolPlug("per_element", Gaffer.Plug.Direction.In, defaultValue=False)
        Gaffer.Metadata.registerPlugValue(per_element_plug, "nodule:type", "")
        self.addChild(per_element_plug)

        in_plug = GafferDispatch.TaskNode.TaskPlug("in", Gaffer.Plug.Direction.In)
        Gaffer.Metadata.registerPlugValue(in_plug, "nodule:type", "GafferUI::StandardNodule")
        Gaffer.Metadata.registerPlugValue(in_plug, "nodule:color", _TASK_IN_OUT_COLOR)
        Gaffer.Metadata.registerPlugValue(in_plug, "noduleLayout:section", "top")
        Gaffer.Metadata.registerPlugValue(in_plug, "plugValueWidget:type", "")
        self.addChild(in_plug)

        out_plug = GafferDispatch.TaskNode.TaskPlug("out", Gaffer.Plug.Direction.Out)
        Gaffer.Metadata.registerPlugValue(out_plug, "nodule:type", "GafferUI::StandardNodule")
        Gaffer.Metadata.registerPlugValue(out_plug, "nodule:color", _TASK_IN_OUT_COLOR )
        Gaffer.Metadata.registerPlugValue(out_plug, "noduleLayout:section", "bottom")
        Gaffer.Metadata.registerPlugValue(out_plug, "plugValueWidget:type", "")
        self.addChild(out_plug)
        
        processor_plug = ProcessorPlug("processor", Gaffer.Plug.Direction.In)
        Gaffer.Metadata.registerPlugValue(processor_plug, "nodule:type", "GafferUI::StandardNodule")
        Gaffer.Metadata.registerPlugValue(processor_plug, "nodule:color", _PROCESSOR_IN_OUT_COLOR)
        Gaffer.Metadata.registerPlugValue(processor_plug, "noduleLayout:section", "right")
        Gaffer.Metadata.registerPlugValue(processor_plug, "plugValueWidget:type", "")
        self.addChild(processor_plug)
        

class Root(GafferTaskNodeBase):
    def __init__(self, name="Root"):
        super(Root, self).__init__(name)

        Gaffer.Metadata.registerValue(self.__class__, "nodeGadget:color", _ARGUMENTS_COLOR)

        in_plug = GafferDispatch.TaskNode.TaskPlug("in", Gaffer.Plug.Direction.In)
        Gaffer.Metadata.registerPlugValue(in_plug, "nodule:type", "GafferUI::StandardNodule")
        Gaffer.Metadata.registerPlugValue(in_plug, "nodule:color", _TASK_IN_OUT_COLOR )
        Gaffer.Metadata.registerPlugValue(in_plug, "noduleLayout:section", "top")
        Gaffer.Metadata.registerPlugValue(in_plug, "plugValueWidget:type", "")
        self.addChild(in_plug)
        
        out_plug = GafferDispatch.TaskNode.TaskPlug("out", Gaffer.Plug.Direction.Out)
        Gaffer.Metadata.registerPlugValue(out_plug, "nodule:type", "GafferUI::StandardNodule")
        Gaffer.Metadata.registerPlugValue(out_plug, "nodule:color", _TASK_IN_OUT_COLOR )
        Gaffer.Metadata.registerPlugValue(out_plug, "noduleLayout:section", "bottom")
        Gaffer.Metadata.registerPlugValue(out_plug, "plugValueWidget:type", "")
        self.addChild(out_plug)

        arguments_plug = ArgumentsPlug("arguments_in", Gaffer.Plug.Direction.In)
        Gaffer.Metadata.registerPlugValue(arguments_plug, "nodule:type", "GafferUI::StandardNodule")
        Gaffer.Metadata.registerPlugValue(arguments_plug, "nodule:color", _ARGUMENTS_COLOR)
        Gaffer.Metadata.registerPlugValue(arguments_plug, "noduleLayout:section", "left")
        Gaffer.Metadata.registerPlugValue(arguments_plug, "plugValueWidget:type", "")
        Gaffer.Metadata.registerPlugValue(arguments_plug, "connectionGadget:color", _ARGUMENTS_CONNECTION_COLOR)
        self.addChild(arguments_plug)

    def _on_plug_input_changed(self, plug):
        if isinstance(plug, ArgumentsPlug) and plug.getInput():
            name = plug.getInput().getName()
            self.setName(name)
            self.getChild("type").setValue(name)
        return


class Parallel(GafferDependencyNodeBase):
    def __init__(self, name="Parallel"):
        super(Parallel, self).__init__(name)

        Gaffer.Metadata.registerValue(self.__class__, "icon", "parallel.png")

        in_plug = GafferDispatch.TaskNode.TaskPlug("in", Gaffer.Plug.Direction.In)
        Gaffer.Metadata.registerPlugValue(in_plug, "nodule:type", "GafferUI::StandardNodule")
        Gaffer.Metadata.registerPlugValue(in_plug, "nodule:color", _TASK_IN_OUT_COLOR)
        Gaffer.Metadata.registerPlugValue(in_plug, "noduleLayout:section", "top")
        Gaffer.Metadata.registerPlugValue(in_plug, "plugValueWidget:type", "")
        self.addChild(in_plug)

        out_plug = GafferDispatch.TaskNode.TaskPlug("out", Gaffer.Plug.Direction.Out)
        Gaffer.Metadata.registerPlugValue(out_plug, "nodule:type", "GafferUI::StandardNodule")
        Gaffer.Metadata.registerPlugValue(out_plug, "nodule:color", _TASK_IN_OUT_COLOR)
        Gaffer.Metadata.registerPlugValue(out_plug, "noduleLayout:section", "bottom")
        Gaffer.Metadata.registerPlugValue(out_plug, "plugValueWidget:type", "")
        self.addChild(out_plug)


class Serial(GafferDependencyNodeBase):
    def __init__(self, name="Serial"):
        super(Serial, self).__init__(name)

        Gaffer.Metadata.registerValue(self.__class__, "icon", "serial.png")

        in_plug = GafferDispatch.TaskNode.TaskPlug("in", Gaffer.Plug.Direction.In)
        Gaffer.Metadata.registerPlugValue(in_plug, "nodule:type", "GafferUI::StandardNodule")
        Gaffer.Metadata.registerPlugValue(in_plug, "nodule:color", _TASK_IN_OUT_COLOR)
        Gaffer.Metadata.registerPlugValue(in_plug, "noduleLayout:section", "top")
        Gaffer.Metadata.registerPlugValue(in_plug, "plugValueWidget:type", "")
        self.addChild(in_plug)

        out_plug = GafferDispatch.TaskNode.TaskPlug("out", Gaffer.Plug.Direction.Out)
        Gaffer.Metadata.registerPlugValue(out_plug, "nodule:type", "GafferUI::StandardNodule")
        Gaffer.Metadata.registerPlugValue(out_plug, "nodule:color", _TASK_IN_OUT_COLOR)
        Gaffer.Metadata.registerPlugValue(out_plug, "noduleLayout:section", "bottom")
        Gaffer.Metadata.registerPlugValue(out_plug, "plugValueWidget:type", "")
        self.addChild(out_plug)
