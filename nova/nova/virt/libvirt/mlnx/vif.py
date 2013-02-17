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

import re
from nova import exception
from nova import flags
from nova.openstack.common import cfg
from nova.openstack.common import log as logging
from nova.virt import vif
from nova.virt.libvirt.mlnx import conn_utils 
from nova.virt.libvirt.mlnx import config  as mlxconfig

mlnx_vif_opts = [
    cfg.StrOpt('vnic_type',
        default='direct',
        help="vNIC type: direct or hostdev"),
    cfg.StrOpt('fabric',
                default='default',
                help='Physical Network Name'),
]

FLAGS = flags.FLAGS
FLAGS.register_opts(mlnx_vif_opts)

LOG = logging.getLogger(__name__)
HEX_BASE = 16

class MlxEthVIFDriver(vif.VIFDriver):
    """VIF driver for Mellanox Embedded switch Plugin"""
    def __init__(self):
        self.conn_util = conn_utils.ConnUtil()
        self.vnic_type = FLAGS.vnic_type
        self.fabric = FLAGS.fabric

    def get_config(self, mac_address, dev):
        conf = None
        if self.vnic_type == 'direct':
            conf = mlxconfig.MlxLibvirtConfigGuestInterface()
            conf.source_dev = dev
            conf.mac_addr = mac_address
        elif self.vnic_type == 'hostdev':
            conf = mlxconfig.MlxLibvirtConfigGuestDevice()
            self._set_source_address(conf , dev)
        else:
            LOG.warning(_("Unknown vnic type %s"),self.vnic_type)
        return conf

    def plug(self, instance, vif):
        network, mapping = vif
        vnic_mac = mapping['mac']
        device_id = instance['uuid']
        try:
            dev = self.conn_util.allocate_nic(vnic_mac, device_id, self.fabric, self.vnic_type)
        except Exception:
            raise exception.VirtualInterfaceCreateException()
        #Allocation Failed
        if dev is None:
            raise exception.VirtualInterfaceCreateException()
        conf = self.get_config(vnic_mac, dev)
        return conf

    def unplug(self, instance, vif):
        network, mapping = vif
        vnic_mac = mapping['mac']
        try:
            dev = self.conn_util.deallocate_nic(vnic_mac, self.fabric)
        except Exception,e:
            LOG.warning(_("Failed while unplugging vif %s"), e)
                       
    def _str_to_hex(self,str_val):
        ret_val = hex(int(str_val,HEX_BASE))
        return ret_val
    
    def _set_source_address(self, conf , dev):
        source_address = re.split(r"\.|\:", dev)
        conf.domain, conf.bus , conf.slot, conf.function = source_address
        conf.domain = self._str_to_hex(conf.domain)
        conf.bus = self._str_to_hex(conf.bus)
        conf.slot = self._str_to_hex(conf.slot)
        conf.function = self._str_to_hex(conf.function)
            

