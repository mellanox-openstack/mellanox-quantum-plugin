# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2013 Mellanox Technologies, Ltd
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

"""
    Configuration for Guest Interfaces and Devices to support direct and hostdev vNICs on top
    of Mellanox HCA embedded Switch.
"""
from lxml import etree
from nova.openstack.common import log as logging
from nova.virt.libvirt import config

LOG = logging.getLogger(__name__)

class MlxLibvirtConfigGuestDevice(config.LibvirtConfigGuestDevice):
    """
    @note: Overrides LibvirtConfigGuestDevice to support hosdev PCI device when using
           SR-IOV Virtual Function assignment.
    """
    def __init__(self, **kwargs):
        super(MlxLibvirtConfigGuestDevice, self).__init__(**kwargs)
        self.domain   = None
        self.bus      = None
        self.slot     = None
        self.function = None

    def format_dom(self):
        dev = etree.Element("hostdev", mode="subsystem", type="pci" )
        address = etree.Element("address", 
                                domain=self.domain,
                                bus=self.bus,
                                slot=self.slot,
                                function=self.function)

        source = etree.Element("source")
        source.append(address)
        dev.append(source)
        return dev

class MlxLibvirtConfigGuestInterface(config.LibvirtConfigGuestDevice):
    """
    @note: Overrides LibvirtConfigGuestInterface to support pass-through mode when using
           SR-IOV Para-Virtualization
    """
    def __init__(self, **kwargs):
        super(MlxLibvirtConfigGuestInterface, self).__init__(root_name="interface",**kwargs)
        self.mac_addr = None
        self.source_dev = None

    def format_dom(self):
        dev = super(MlxLibvirtConfigGuestInterface, self).format_dom()
        dev.set("type","direct")
        dev.append(etree.Element("mac", address=self.mac_addr))
        dev.append(etree.Element("model", type='virtio'))
        dev.append(etree.Element("source", dev=self.source_dev, mode='passthrough'))
        return dev



