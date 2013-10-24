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
from nova.openstack.common import log as logging
from nova import utils
from nova.openstack.common.gettextutils import _
from nova.virt.libvirt import vif
from nova.virt.libvirt.mlnx import config  as mlxconfig

LOG = logging.getLogger(__name__)
HEX_BASE = 16
VIF_TYPE_HOSTDEV = 'hostdev'


class MlxEthVIFDriver(vif.LibvirtBaseVIFDriver):
    """VIF driver for Mellanox Embedded switch Plugin"""
    def __init__(self, get_connection):
        super(MlxEthVIFDriver, self).__init__(get_connection)
        self.libvirt_gen_drv = vif.LibvirtGenericVIFDriver(get_connection)

    def get_dev_config(self, mac_address, dev):
        conf = None
        conf = mlxconfig.MlxLibvirtConfigGuestDevice()
        self._set_source_address(conf, dev)
        return conf

    def get_config(self, instance, vif, image_meta,
                   inst_type):
        vif_type = vif.get('type')
        vnic_mac = vif['address']
        device_id = instance['uuid']
        network = vif['network']
        fabric = network['meta']['physical_network']

        if vif_type:
            LOG.debug(_("vif_type=%s"), vif_type)

        try:
            if vif_type == VIF_TYPE_HOSTDEV:
                dev_name = None
                try:
                    res = utils.execute('ebrctl', 'allocate-port',
                                        vnic_mac, device_id, fabric, vif_type)
                    dev = res[0].strip()

                except exception.ProcessExecutionError:
                    LOG.exception(_("Failed while config vif"),
                                  instance=instance)
                    dev = None
            else:
                conf = self.libvirt_gen_drv.get_config(instance, vif,
                                                       image_meta, inst_type)
                return conf
        except Exception as e:
            LOG.debug("Error in get_config: %s", e)
            raise exception.NovaException(_("Processing Failure during "
                                            "vNIC allocation"))
        #Allocation Failed
        if dev is None:
            raise exception.NovaException(_("Failed to allocate "
                                            "device for vNIC"))
        conf = self.get_dev_config(vnic_mac, dev)
        return conf

    def plug(self, instance, vif):
        vif_type = vif.get('type')
        network = vif['network']
        fabric = network['meta']['physical_network']
        vnic_mac = vif['address']
        device_id = instance['uuid']
        dev_name = None

        if vif_type:
            LOG.debug(_("vif_type=%s"), vif_type)

        try:
            if vif_type == VIF_TYPE_HOSTDEV:
                dev = utils.execute('ebrctl', 'add-port', vnic_mac, device_id,
                                    fabric, vif_type, dev_name)
                if dev is None:
                    error_msg = "Cannot plug VIF with no allocated device "
                    raise exception.NovaException(_(error_msg))
            else:
                self.libvirt_gen_drv.plug(instance, vif)

        except Exception as e:
            LOG.debug(_("Error in Plug: %s"), e)
            raise exception.NovaException(_("Processing Failure "
                                            "during vNIC plug"))

    def unplug(self, instance, vif):
        vif_type = vif.get('type')
        network = vif['network']
        fabric = network['meta']['physical_network']
        vnic_mac = vif['address']

        if vif_type:
            LOG.debug(_("vif_type=%s"), vif_type)

        try:
            if vif_type == VIF_TYPE_HOSTDEV:
                utils.execute('ebrctl', 'del-port', fabric, vnic_mac)
            else:
                self.libvirt_gen_drv.unplug(instance, vif)
        except Exception, e:
            LOG.warning(_("Failed while unplugging vif %s"), e)

    def _str_to_hex(self, str_val):
        ret_val = hex(int(str_val, HEX_BASE))
        return ret_val

    def _set_source_address(self, conf, dev):
        source_address = re.split(r"\.|\:", dev)
        conf.domain, conf.bus, conf.slot, conf.function = source_address
        conf.domain = self._str_to_hex(conf.domain)
        conf.bus = self._str_to_hex(conf.bus)
        conf.slot = self._str_to_hex(conf.slot)
        conf.function = self._str_to_hex(conf.function)
