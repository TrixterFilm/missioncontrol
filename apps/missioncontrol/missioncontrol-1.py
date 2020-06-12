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

import os
import traceback
import sys

import functools

import Gaffer
import GafferDispatch
import IECore

try:
    import GafferUI
except ImportError:
    GafferUI = None


class missioncontrol(Gaffer.Application):

    description = """
    A magical place where all your task dependency dreams come true.
    """

    def __init__(self):
        super(missioncontrol, self).__init__(self.description)

        self.parameters().addParameters(
            [
                IECore.FileNameParameter(
                    name="script",
                    description="The gfr script to load",
                    defaultValue="",
                    extensions="gfr",
                    allowEmptyString=True,
                    check=IECore.FileNameParameter.CheckType.MustExist,
                ),
                IECore.BoolParameter(
                    name="fullScreen",
                    description="Opens the UI in full screen mode.",
                    defaultValue=False,
                ),
                IECore.BoolParameter(
                    name="dispatch",
                    description="Opens the UI in full screen mode.",
                    defaultValue=False,
                ),
                IECore.StringVectorParameter(
                    name="nodes",
                    description="The names of the task nodes to dispatch.",
                    defaultValue=IECore.StringVectorData([]),
                ),
                IECore.StringVectorParameter(
                    name="settings",
                    description="The values to be set on the nodes or the dispatcher. Values "
                                "should be in the format -nodeA.plugA value -nodeA.plugB value -nodeB.plugC value "
                                "-dispatcher.plugD value -LocalDispatcher.plugE value -context.entry value",
                    defaultValue=IECore.StringVectorData([]),
                    userData={
                        "parser": {
                            "acceptFlags": IECore.BoolData(True),
                        },
                    },
                ),
            ]

        )

        self.parameters().userData()["parser"] = IECore.CompoundObject(
            {
                "flagless": IECore.StringVectorData(["script"])
            }
        )

    def _run(self, args):
        if not args["dispatch"].value:
            self.__setupClipboardSync()

            GafferUI.ScriptWindow.connect(self.root())

            # Must start the event loop before adding scripts,
            # because `FileMenu.addScript()` may launch
            # interactive dialogues.
            GafferUI.EventLoop.addIdleCallback(functools.partial(self.__addScript, args))
            GafferUI.EventLoop.mainEventLoop().start()

        self.__addScript(args)

        if args["dispatch"].value:
            self.dispatcher = GafferDispatch.Dispatcher.create(GafferDispatch.Dispatcher.getDefaultDispatcherType())

            if not len(args["nodes"]):
                IECore.msg(IECore.Msg.Level.Error, "missioncontrol dispatch", "No nodes were specified.")
                return 1

            self.__applySettings(args)
            self.__dispatch(args)

    def __dispatch(self, args):
        nodes = [self.scriptNode.descendant(node) for node in args["nodes"]]

        try:
            with self.scriptNode.context():
                self.dispatcher.dispatch(nodes)
        except Exception:
            IECore.msg(
                IECore.Msg.Level.Error,
                "missioncontrol dispatch : dispatching %s" % str([node.relativeName(self.scriptNode) for node in nodes]),
                "".join(traceback.format_exception(*sys.exc_info())),
            )
            return 1

        return 0

    def __addScript(self, args):
        self.scriptNode = Gaffer.ScriptNode()
        Gaffer.NodeAlgo.applyUserDefaults(self.scriptNode)
        self.root()["scripts"].addChild(self.scriptNode)

        if args["script"].value:
            self.scriptNode["fileName"].setValue(os.path.abspath(args["script"].value))
            self.scriptNode.load()

        if not args["dispatch"] and args["fullScreen"].value:
            primaryScript = self.root()["scripts"][-1]
            primaryWindow = GafferUI.ScriptWindow.acquire(primaryScript)
            primaryWindow.setFullScreen(True)

        return False  # Remove idle callback

    def __applySettings(self, args):
        if len(args["settings"]) % 2:
            IECore.msg(IECore.Msg.Level.Error, "missioncontrol dispatch",
                       "\"settings\" parameter must have matching entry/value pairs")
            return 1

        for i in range(0, len(args["settings"]), 2):
            key = args["settings"][i].lstrip("-")
            value = args["settings"][i + 1]
            if key.startswith("dispatcher."):
                identifier = key.partition("dispatcher.")[-1]
                status = self.__setValue(identifier, value, self.dispatcher)
            else:
                status = self.__setValue(key, value, self.scriptNode)
            if status:
                return status

    @staticmethod
    def __setValue(identifier, value, parent):
        plug = parent.descendant(identifier)
        if not plug:
            IECore.msg(IECore.Msg.Level.Error, "missioncontrol dispatch",
                       "\"%s\" does not contain a plug named \"%s\"." % (parent.getName(), identifier))
            return 1
        if not plug.settable():
            IECore.msg(IECore.Msg.Level.Error, "missioncontrol dispatch", "\"%s\" cannot be set." % identifier)
            return 1

        try:
            ## \todo: this eval isn't ideal. we should have a way of parsing values
            # and setting them onto plugs.
            plug.setValue(eval(value))
        except Exception as exception:
            IECore.msg(IECore.Msg.Level.Error, "missioncontrol dispatch: setting \"%s\"" % identifier, str(exception))
            return 1

        return 0

    def __setupClipboardSync(self):
        ## This function sets up two way syncing between the clipboard held in the Gaffer::ApplicationRoot
        # and the global QtGui.QClipboard which is shared with external applications, and used by the cut and paste
        # operations in GafferUI's underlying QWidgets. This is very useful, as it allows nodes to be copied from
        # the graph and pasted into emails/chats etc, and then copied out of emails/chats and pasted into the node graph.
        #
        ## \todo I don't think this is the ideal place for this functionality. Firstly, we need it in all apps
        # rather than just the gui app. Secondly, we want a way of using the global clipboard using GafferUI
        # public functions without needing an ApplicationRoot. Thirdly, it's questionable that ApplicationRoot should
        # have a clipboard anyway - it seems like a violation of separation between the gui and non-gui libraries.
        # Perhaps we should abolish the ApplicationRoot clipboard and the ScriptNode cut/copy/paste routines, relegating
        # them all to GafferUI functionality?

        from Qt import QtWidgets

        self.__clipboardContentsChangedConnection = self.root().clipboardContentsChangedSignal().connect(
            Gaffer.WeakMethod(self.__clipboardContentsChanged))
        QtWidgets.QApplication.clipboard().dataChanged.connect(Gaffer.WeakMethod(self.__qtClipboardContentsChanged))
        self.__ignoreQtClipboardContentsChanged = False
        self.__qtClipboardContentsChanged()  # Trigger initial sync

    def __clipboardContentsChanged(self, applicationRoot):
        assert (applicationRoot.isSame(self.root()))

        data = applicationRoot.getClipboardContents()

        from Qt import QtWidgets
        clipboard = QtWidgets.QApplication.clipboard()
        try:
            self.__ignoreQtClipboardContentsChanged = True  # avoid triggering an unecessary copy back in __qtClipboardContentsChanged
            clipboard.setText(str(data))
        finally:
            self.__ignoreQtClipboardContentsChanged = False

    def __qtClipboardContentsChanged(self):
        import GafferUI
        if self.__ignoreQtClipboardContentsChanged:
            return

        from Qt import QtWidgets

        text = QtWidgets.QApplication.clipboard().text().encode("utf-8")
        if text:
            with Gaffer.BlockedConnection(self.__clipboardContentsChangedConnection):
                self.root().setClipboardContents(IECore.StringData(text))


IECore.registerRunTimeTyped(missioncontrol)
