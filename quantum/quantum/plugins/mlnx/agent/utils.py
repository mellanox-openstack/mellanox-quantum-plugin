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

import json
import zmq

from oslo.config import cfg
from quantum.openstack.common import log as logging
from quantum.plugins.mlnx.common import exceptions

MLX_DAEMON = "tcp://127.0.0.1:5001"
REQUEST_TIMEOUT = 1000

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class  eSwitchUtils(object):
    def __init__(self):
        self.__conn = None

    @property
    def _conn(self):
        if self.__conn is None:
            context = zmq.Context()
            socket = context.socket(zmq.REQ)
            socket.setsockopt(zmq.LINGER, 0)
            socket.connect(MLX_DAEMON)
            self.__conn = socket
            self.poller = zmq.Poller()
            self.poller.register(self._conn, zmq.POLLIN)
        return self.__conn

    def send_msg(self, msg):
        self._conn.send(msg)

        socks = dict(self.poller.poll(REQUEST_TIMEOUT))
        if socks.get(self._conn) == zmq.POLLIN:
            recv_msg = self._conn.recv()
            response = self.parse_response_msg(recv_msg)
            return response
        else:
            self._conn.setsockopt(zmq.LINGER, 0)
            self._conn.close()
            self.poller.unregister(self._conn)
            self.__conn = None
            raise exceptions.MlxException("eSwitchD: Request timeout")

    def parse_response_msg(self, recv_msg):
        msg = json.loads(recv_msg)
        error_msg = " "
        if msg['status'] == 'OK':
            if 'response' in msg:
                return msg['response']
            return
        elif msg['status'] == 'FAIL':
            LOG.error(_("Action %s failed: %s"), msg['action'], msg['reason'])
            error_msg = "Action %s failed: %s" % (msg['action'], msg['reason'])
        else:
            LOG.error(_("Unknown operation status %s"), msg['status'])
            error_msg = "Unknown operation status %s" % msg['status']
        raise exceptions.MlxException(error_msg)

    def get_attached_vnics(self):
        LOG.debug(_("get_attached_vnics"))
        msg = json.dumps({'action': 'get_vnics', 'fabric': '*'})
        vnics = self.send_msg(msg)
        return vnics

    def set_port_vlan_id(self, physical_network,
                        segmentation_id, port_mac):
        LOG.debug(_("Set Vlan  %s on Port %s on Fabric %s"),
                    segmentation_id, port_mac, physical_network)
        msg = json.dumps({'action': 'set_vlan',
                          'fabric': physical_network,
                          'port_mac': port_mac,
                          'vlan': segmentation_id})
        recv_msg = self.send_msg(msg)
        return True

    def define_fabric_mappings(self, interface_mapping):
        for fabric, phy_interface in interface_mapping.iteritems():
            LOG.debug(_("Define Fabric %s on interface %s"),
                       fabric, phy_interface)
            msg = json.dumps({'action': 'define_fabric_mapping',
                              'fabric': fabric,
                              'interface': phy_interface})
            self.send_msg(msg)
        return True

    def port_up(self, fabric, port_mac):
        LOG.debug(_("Port Up for %s on fabric %s"), port_mac, fabric)
        msg = json.dumps({'action': 'port_up',
                          'fabric': fabric,
                          'ref_by': 'mac_address',
                          'mac': 'port_mac'})
        self.send_msg(msg)
        return True

    def port_down(self, fabric, port_mac):
        LOG.debug(_("Port Down for %s on fabric %s"), port_mac, fabric)
        msg = json.dumps({'action': 'port_down',
                          'fabric': fabric,
                          'ref_by': 'mac_address',
                          'mac': port_mac})
        self.send_msg(msg)
        return True

    def port_release(self, fabric, port_mac):
        LOG.debug(_("release port %s on fabric %s"), port_mac, fabric)
        msg = json.dumps({'action': 'port_release',
                          'fabric': fabric,
                          'ref_by': 'mac_address',
                          'mac': port_mac})
        self.send_msg(msg)
        return True

    def get_eswitch_ports(self, fabric):
        """
        @todo - to implement for next phase
        """
        ports = dict()
        return ports

    def get_eswitch_id(self, fabric):
        """
        @todo: to implement for next phase
        """
        eswitch_id = str()
        return eswitch_id
