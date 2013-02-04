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
import glob
import libvirt
from lxml import etree
from nova.openstack.common import log as logging
from utils.pci_utils import pciUtils
from db import device_db

LOG = logging.getLogger('mlnx_daemon')

PCI_PATH = "/sys/bus/pci/devices/"

class ResourceManager:    
    def __init__(self):
        self.pci_utils = pciUtils()
        self.device_db = device_db.DeviceDB()
        
    def scan_attached_devices(self):
        devices = {'direct':[]}   
        conn = self.libvirtconn = libvirt.open('qemu:///system')
        domains = conn.listDomainsID()
        for domid in domains:
            domain = conn.lookupByID(domid)
            raw_xml = domain.XMLDesc(0)
            tree = etree.XML(raw_xml)
            interfaces = tree.xpath("devices/interface")

            for interface in interfaces:
                mac = interface.find('mac').get('address')
                dev = interface.find('source').get('dev')
                fabric = self.get_fabric_for_dev(dev)
                if fabric:
                    devices['direct'].append((dev,mac,fabric))
                else:
                    LOG.debug("No Fabric defined for device %s",dev)
        return devices 
    
    def _get_pf_details(self,pf):
        hca_port = self.pci_utils.get_eth_port(pf)
        pci_id  = self.pci_utils.get_pf_pci(pf)
        return (pci_id,hca_port)
    
    def get_fabric_pf(self,fabric):
        return self.device_db.get_pf(fabric)

    def discover_devices(self,pci_id,hca_port): 
        eths = list()
        vfs = list()    
        vfs_paths = glob.glob(PCI_PATH + pci_id + ".[!0]*")   
        for vf_path in vfs_paths:
            path = vf_path+'/net'
            if os.path.isdir(path):
                eth_dirs = os.listdir(path)
                for eth in eth_dirs:
                    port_path = "/".join([path,eth,"dev_id"])
                    fd = open(port_path)
                    dev_id = int(fd.read(),0)

                    if int(dev_id) == int(hca_port)-1:
                        eths.append(eth)
            else:
                vf = vf_path.split('/')[-1]
                vfs.append(vf) 
        return (eths,vfs)
              
    def add_fabric(self, fabric, pf):
        pci_id,hca_port = self._get_pf_details(pf)
        self.device_db.add_fabric(fabric,pf,pci_id,hca_port)
        eths,vfs = self.discover_devices(pci_id,hca_port)
        self.device_db.set_fabric_devices(fabric,eths,vfs)
        
    def get_free_eths(self, fabric):
        return self.device_db.get_free_eths(fabric)
    
    def get_free_vfs(self,fabric):
        return self.device_db.get_free_vfs(fabric)
    
    def get_free_devices(self,fabric):
        return self.device_db.get_free_devices(fabric)

    def allocate_device(self, fabric, dev_type, dev=None):
        is_device = True if dev_type == 'direct' else False
        try:
            dev = self.device_db.allocate_device(fabric,is_device,dev)        
            return dev
        except Exception:
            return None

    def deallocate_device(self, fabric,dev_type,dev):
        is_device = True if dev_type == 'direct' else False
        try:
            dev = self.device_db.deallocate_device(fabric,is_device,dev)        
            return dev
        except Exception:
            return None
     
    def get_fabric_for_dev(self, dev):
        return self.device_db.get_dev_fabric(dev)
