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

import os
from nova.openstack.common import log as logging

LOG = logging.getLogger('mlnx_daemon')

class pciUtils:
    pci_path =      "/sys/bus/pci/devices/"
    VF_PF_NETDEV =  "/sys/bus/pci/devices/VF/physfn/net"
    ETH_PF_NETDEV = "/sys/class/net/DEV/device/physfn/net"
    ETH_VF =        "/sys/class/net/ETH/device"
    ETH_PORT =      "/sys/class/net/ETH/dev_id"
    
    def __init__(self):
        pass
       
    def get_eth_vf(self, dev):
        """
        @param dev: Ethetnet device
        @return: VF of Ethernet device
        """
        vf_path = pciUtils.ETH_VF.replace("ETH", dev)
        try:
            device = os.readlink(vf_path)
            vf = device.split('/')[3]
            return vf
        except:
            return None 
    
    def get_pf_pci(self, pf):
        vf = self.get_eth_vf(pf)
        if vf:
            return vf[:-2]
        else:
            return None
        
    def get_vf_index(self, dev, dev_type):
        """
        @param dev: Ethernet device or VF
        @param dev_type: 'direct' or 'hostdev'        
        @return: VF index 
        """
        if dev_type == 'direct':
            dev = self.get_eth_vf(dev)
            dev_type = 'hostdev'
        if dev_type == 'hostdev':
            try:
                l = dev.split('.')
                if len(l) == 2:
                    return l[1]
                else:
                    return None
            except:
                return None
        else:
            return None
        
    def get_eth_port(self, dev):
        port_path = pciUtils.ETH_PORT.replace("ETH", dev)
        try:
            with open(port_path) as f:
                dev_id = int(f.read(),0)
                return dev_id+1
        except IOError:
            return
            
