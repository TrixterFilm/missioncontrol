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

import imp
import os

import Gaffer
import IECore

# get the actual gui class we want to derive from (and patch)
app = imp.load_source(
    "apps",
    os.path.abspath(os.path.join(os.path.dirname(Gaffer.__file__), "..", "..", "apps", "gui", "gui-1.py"))
)


# patch the init to perform calls of base classes
def __init__(self, description):
    super(GUIPatch, self).__init__(description)

    self.parameters().addParameters(
        [
            IECore.StringVectorParameter(
                name="scripts",
                description="A list of scripts to edit.",
                defaultValue=IECore.StringVectorData(),
            ),
            IECore.BoolParameter(
                name="fullScreen",
                description="Opens the UI in full screen mode.",
                defaultValue=False,
            ),
        ]
    )

    self.parameters().userData()["parser"] = IECore.CompoundObject(
        {
            "flagless": IECore.StringVectorData(["scripts"])
        }
    )

    #self.__setupClipboardSync()
    GUIPatch._gui__setupClipboardSync(self)


GUIPatch = type("GUIPatch", app.gui.__bases__, dict(app.gui.__dict__))
GUIPatch.__init__ = __init__


class missioncontrol(GUIPatch):

    description = """
    A magical place where all your task dependency dreams come true.
    """
    def __init__(self):
        super(missioncontrol, self).__init__(self.description)

        # more stuff to come (eventually ;) )...

IECore.registerRunTimeTyped(missioncontrol)
