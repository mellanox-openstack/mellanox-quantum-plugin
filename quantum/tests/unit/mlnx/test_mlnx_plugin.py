# Copyright (c) 2012 OpenStack, LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from quantum.tests.unit import test_db_plugin as test_plugin


class MlnxPluginV2TestCase(test_plugin.QuantumDbPluginV2TestCase):

    _plugin_name = ('quantum.plugins.mlnx.mlnx_plugin.MellanoxEswitchPlugin')

    def setUp(self):
        super(MlnxPluginV2TestCase, self).setUp(self._plugin_name)


class TestMlnxBasicGet(test_plugin.TestBasicGet,MlnxPluginV2TestCase):
    pass


class TestMlnxV2HTTPResponse(test_plugin.TestV2HTTPResponse,MlnxPluginV2TestCase):
    pass


class TestMlnxPortsV2(test_plugin.TestPortsV2,MlnxPluginV2TestCase):
    pass


class TestMlnxNetworksV2(test_plugin.TestNetworksV2,MlnxPluginV2TestCase):
    pass
