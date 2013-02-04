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
Configuration for Guest Interfaces to support direct and hostdev vNICs on top
of Mellanox HCAs.
"""
from lxml import etree
from nova.openstack.common import log as logging
from nova.virt.libvirt import config

LOG = logging.getLogger(__name__)

class MlxLibvirtConfigGuestInterface(config.LibvirtConfigGuestDevice):
    """
    Overrides LibvirtConfigGuestDevice to support pass-through mode when using
    SR-IOV Paravirtualization.
    """
    def __init__(self, **kwargs):
        super(MlxLibvirtConfigGuestInterface, self).__init__(
            root_name="interface",
            **kwargs)

        self.net_type = None
        self.target_dev = None
        self.model = None
        self.mac_addr = None
        self.script = None
        self.source_dev = None
        self.vporttype = None
        self.vportparams = []
        self.filtername = None
        self.filterparams = []

    def format_dom(self):
        dev = super(MlxLibvirtConfigGuestInterface, self).format_dom()

        dev.set("type", self.net_type)
        dev.append(etree.Element("mac", address=self.mac_addr))
        if self.model:
            dev.append(etree.Element("model", type=self.model))
        if self.net_type == "ethernet":
            if self.script is not None:
                dev.append(etree.Element("script", path=self.script))
            dev.append(etree.Element("target", dev=self.target_dev))
        elif self.net_type == "direct":
            if self.mode:
                dev.append(etree.Element("source", dev=self.source_dev,
                                         mode=self.mode))
            else:
                dev.append(etree.Element("source", dev=self.source_dev,
                                         mode="private"))
        else:
            dev.append(etree.Element("source", bridge=self.source_dev))

        if self.vporttype is not None:
            vport = etree.Element("virtualport", type=self.vporttype)
            for p in self.vportparams:
                param = etree.Element("parameters")
                param.set(p['key'], p['value'])
                vport.append(param)
            dev.append(vport)

        if self.filtername is not None:
            filter = etree.Element("filterref", filter=self.filtername)
            for p in self.filterparams:
                filter.append(etree.Element("parameter",
                                            name=p['key'],
                                            value=p['value']))
            dev.append(filter)
        return dev

    def add_filter_param(self, key, value):
        self.filterparams.append({'key': key, 'value': value})

    def add_vport_param(self, key, value):
        self.vportparams.append({'key': key, 'value': value})

