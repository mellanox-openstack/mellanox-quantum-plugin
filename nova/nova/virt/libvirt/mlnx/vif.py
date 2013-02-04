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

from nova import exception
from nova import flags
from nova.openstack.common import cfg
from nova.openstack.common import log as logging
from nova.virt import vif
from nova.virt.libvirt.mlnx import conn_utils 
from nova.virt.libvirt.mlnx import config  as mlxconfig

mlnx_vif_opts = [
    cfg.StrOpt('vnic_type',
        default='eth',
        help="vNIC type: direct or hostdev"),
    cfg.StrOpt('fabric',
                default='default',
                help='Physical Network Name'),
]

FLAGS = flags.FLAGS
FLAGS.register_opts(mlnx_vif_opts)

LOG = logging.getLogger(__name__)

class MlxEthVIFDriver(vif.VIFDriver):
    """VIF driver for Mellanox Embedded switch Plugin"""
    def __init__(self):
        self.conn_util = conn_utils.ConnUtil()
        self.vnic_type = FLAGS.vnic_type
        self.fabric = FLAGS.fabric

    def get_config(self, mac_address, dev):
        conf = mlxconfig.MlxLibvirtConfigGuestInterface()
        conf.model = 'virtio'
        conf.net_type = "direct"
        conf.source_dev = dev
        conf.script = ""
        conf.mac_addr = mac_address
        conf.mode = "passthrough"
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
            

