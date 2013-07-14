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
from nova.openstack.common import log as logging
from nova.virt.libvirt.mlnx import exceptions

MLX_DAEMON = "tcp://127.0.0.1:5001"
REQUEST_TIMEOUT = 4000
LOG = logging.getLogger(__name__)

class ConnUtil(object):
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

    def send_msg(self,msg):
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
            raise exceptions.MlxException("eSwitchD: Timeout processing  request")

    def parse_response_msg(self, recv_msg):
        msg = json.loads(recv_msg)
        error_msg = " "
        if msg['status'] == 'OK':
            if 'response' in msg:
                return msg['response']
            return
        elif msg['status'] == 'FAIL':
            error_msg = "Action  %s failed: %s" %(msg['action'], msg['reason'])
        else:
            error_msg = "Unknown operation status %s" % msg['status']
        LOG.error(_(error_msg))
        raise exceptions.MlxException(error_msg)

    def allocate_nic(self, vnic_mac, device_id, fabric, vnic_type, dev_name):
        msg = json.dumps({'action':'create_port',
                          'vnic_mac':vnic_mac,
                          'device_id':device_id, 
                          'fabric':fabric, 
                          'vnic_type':vnic_type,
                          'dev_name':dev_name})
        recv_msg = self.send_msg(msg)
        dev = recv_msg['dev']
        return dev
    
    def plug_nic(self, vnic_mac, device_id, fabric, vif_type, dev_name):
        msg = json.dumps({'action':'plug_nic', 
                          'vnic_mac':vnic_mac,
                          'device_id':device_id, 
                          'fabric':fabric, 
                          'vnic_type':vif_type,
                          'dev_name':dev_name})
        
        recv_msg = self.send_msg(msg)
        dev = recv_msg['dev']
        return dev

       
    def deallocate_nic(self, vnic_mac, fabric):
        msg = json.dumps({'action':'delete_port', 
                          'fabric':fabric, 
                          'vnic_mac':vnic_mac})
        recv_msg = self.send_msg(msg)
        dev = recv_msg['dev']
        return dev
