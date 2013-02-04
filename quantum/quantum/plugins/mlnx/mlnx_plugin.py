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

import sys

from quantum.api.v2 import attributes
from quantum.common import exceptions as q_exc
from quantum.common import topics
from quantum.db import db_base_plugin_v2
from quantum.db import l3_db
from quantum.extensions import providernet as provider
from quantum.openstack.common import context
from quantum.openstack.common import cfg
from quantum.openstack.common import rpc
from quantum.openstack.common import log as logging
from quantum.plugins.mlnx.common import constants
from quantum.plugins.mlnx.db import mlnx_db_v2 as db
from quantum.plugins.mlnx import rpc_callbacks
from quantum.plugins.mlnx import agent_notify_api
from quantum import policy


LOG = logging.getLogger(__name__)

class MellanoxEswitchPlugin(db_base_plugin_v2.QuantumDbPluginV2,
                          l3_db.L3_NAT_db_mixin):
    """
    @note: Realization of Quantum API on top of Mellanox
           NIC embedded switch technology.
           Current plugin provides embedded NIC Switch connectivity.
           Code is based on the Linux Bridge plugin content to 
           support consistency with L3 & DHCP Agents.    
    """
    
    # This attribute specifies whether the plugin supports or not
    # bulk operations. Name mangling is used in order to ensure it
    # is qualified by class
    __native_bulk_support = True

    supported_extension_aliases = ["provider", "router"]

    def __init__(self):
        """
        @note: Start Mellanox Quantum Plugin.       
        """
        db.initialize()
        self._parse_network_vlan_ranges()
        db.sync_network_states(self.network_vlan_ranges)
        self._set_tenant_network_type()
        self.agent_rpc = cfg.CONF.AGENT.rpc
        self._setup_rpc()
        LOG.debug("Mellanox Embedded Switch Plugin initialisation complete")
     
    def _setup_rpc(self):
        # RPC support
        self.topic = topics.PLUGIN
        self.rpc_context = context.RequestContext('quantum', 'quantum',
                                                  is_admin=False)
        self.conn = rpc.create_connection(new=True)
        self.notifier = agent_notify_api.AgentNotifierApi(topics.AGENT)       
        self.callbacks = rpc_callbacks.MlnxRpcCallbacks(self.rpc_context)
        self.dispatcher = self.callbacks.create_rpc_dispatcher()
        self.conn.create_consumer(self.topic, self.dispatcher,
                                  fanout=False)
        # Consume from all consumers in a thread
        self.conn.consume_in_thread()
        
    def _parse_network_vlan_ranges(self):
        self.network_vlan_ranges = {}
        for entry in cfg.CONF.VLANS.network_vlan_ranges:
            if ':' in entry:
                try:
                    physical_network, vlan_min, vlan_max = entry.split(':')
                    self._add_network_vlan_range(physical_network,
                                                 int(vlan_min),
                                                 int(vlan_max))
                except ValueError as ex:
                    LOG.error("Invalid network VLAN range: \'%s\' - %s" %
                              (entry, ex))
                    sys.exit(1)
            else:
                self._add_network(entry)
        LOG.debug("network VLAN ranges: %s" % self.network_vlan_ranges)
        
    def _add_network_vlan_range(self, physical_network, vlan_min, vlan_max):
        self._add_network(physical_network)
        self.network_vlan_ranges[physical_network].append((vlan_min, vlan_max))

    def _add_network(self, physical_network):
        if physical_network not in self.network_vlan_ranges:
            self.network_vlan_ranges[physical_network] = []
    
    def _check_provider_view_auth(self, context, network):
        return policy.check(context,
                            "extension:provider_network:view",
                            network)

    def _enforce_provider_set_auth(self, context, network):
        return policy.enforce(context,
                              "extension:provider_network:set",
                              network)

    def _extend_network_dict_provider(self, context, network):
        if self._check_provider_view_auth(context, network):
            binding = db.get_network_binding(context.session, network['id'])
            network[provider.NETWORK_TYPE] = binding.network_type
            if binding.network_type == constants.TYPE_FLAT:
                network[provider.PHYSICAL_NETWORK] = binding.physical_network
                network[provider.SEGMENTATION_ID] = None
            elif binding.network_type == constants.TYPE_LOCAL:
                network[provider.PHYSICAL_NETWORK] = None
                network[provider.SEGMENTATION_ID] = None
            else:
                network[provider.PHYSICAL_NETWORK] = binding.physical_network
                network[provider.SEGMENTATION_ID] = binding.segmentation_id
                        
    def _set_tenant_network_type(self):  
        self.tenant_network_type = cfg.CONF.VLANS.tenant_network_type
        if self.tenant_network_type not in [constants.TYPE_VLAN, 
                                            constants.TYPE_IB,
                                            constants.TYPE_LOCAL,
                                            constants.TYPE_NONE]:
            LOG.error(_("Invalid tenant_network_type: %s. "
                        "Service terminated!"),
                      self.tenant_network_type)
            sys.exit(1)  
     
    def _process_provider_create(self, context, attrs):
        network_type = attrs.get(provider.NETWORK_TYPE)
        physical_network = attrs.get(provider.PHYSICAL_NETWORK)
        segmentation_id = attrs.get(provider.SEGMENTATION_ID)

        network_type_set = attributes.is_attr_set(network_type)
        physical_network_set = attributes.is_attr_set(physical_network)
        segmentation_id_set = attributes.is_attr_set(segmentation_id)
        
        if not (network_type_set or physical_network_set or
                segmentation_id_set):
            return (None, None, None)
        
        # Authorize before exposing plugin details to client
        self._enforce_provider_set_auth(context, attrs)

        if not network_type_set:
            msg = _("provider:network_type required")
            raise q_exc.InvalidInput(error_message=msg)
        elif network_type == constants.TYPE_FLAT:
            if segmentation_id_set:
                msg = _("provider:segmentation_id specified for flat network")
                raise q_exc.InvalidInput(error_message=msg)
            else:
                segmentation_id = constants.FLAT_VLAN_ID
     
        elif network_type in [constants.TYPE_VLAN, constants.TYPE_IB]:
            if not segmentation_id_set:
                msg = _("provider:segmentation_id required")
                raise q_exc.InvalidInput(error_message=msg)
            if segmentation_id < 1 or segmentation_id > 4094:
                msg = _("provider:segmentation_id out of range "
                        "(1 through 4094)")
                raise q_exc.InvalidInput(error_message=msg)
            
        elif network_type == constants.TYPE_LOCAL:
            if physical_network_set:
                msg = _("provider:physical_network specified for local "
                        "network")
                raise q_exc.InvalidInput(error_message=msg)
            else:
                physical_network = None
            if segmentation_id_set:
                msg = _("provider:segmentation_id specified for local "
                        "network")
                raise q_exc.InvalidInput(error_message=msg)
            else:
                segmentation_id = constants.LOCAL_VLAN_ID 
        else:
            msg = _("provider:network_type %s not supported" % network_type)
            raise q_exc.InvalidInput(error_message=msg)
                   
        if network_type in [constants.TYPE_VLAN, constants.TYPE_IB, constants.TYPE_FLAT]:
            if physical_network_set:
                if physical_network not in self.network_vlan_ranges:
                    msg = _("unknown provider:physical_network %s" %
                            physical_network)
                    raise q_exc.InvalidInput(error_message=msg)
            elif 'default' in self.network_vlan_ranges:
                physical_network = 'default'
            else:
                msg = _("provider:physical_network required")
                raise q_exc.InvalidInput(error_message=msg)        
        return (network_type, physical_network, segmentation_id)

    def _check_provider_update(self, context, attrs):
        network_type = attrs.get(provider.NETWORK_TYPE)
        physical_network = attrs.get(provider.PHYSICAL_NETWORK)
        segmentation_id = attrs.get(provider.SEGMENTATION_ID)

        network_type_set = attributes.is_attr_set(network_type)
        physical_network_set = attributes.is_attr_set(physical_network)
        segmentation_id_set = attributes.is_attr_set(segmentation_id)

        if not (network_type_set or physical_network_set or
                segmentation_id_set):
            return

        # Authorize before exposing plugin details to client
        self._enforce_provider_set_auth(context, attrs)

        msg = _("plugin does not support updating provider attributes")
        raise q_exc.InvalidInput(error_message=msg)

    def create_network(self, context, network):              
        session = context.session
        with session.begin(subtransactions=True):
            (network_type, physical_network,vlan_id) = self._process_provider_create(context, network['network'])       
            if not network_type:
                # tenant network
                network_type = self.tenant_network_type
                if network_type == constants.TYPE_NONE:
                    raise q_exc.TenantNetworksDisabled()
                elif network_type in [constants.TYPE_VLAN,constants.TYPE_IB]:
                    physical_network, vlan_id = db.reserve_network(session)
                else:  # TYPE_LOCAL
                    vlan_id = constants.LOCAL_VLAN_ID
            else:
                # provider network
                if network_type in [constants.TYPE_VLAN, constants.TYPE_IB,constants.TYPE_FLAT]:
                    db.reserve_specific_network(session, 
                                                physical_network,
                                                vlan_id)
            net = super(MellanoxEswitchPlugin, self).create_network(context,
                                                                  network)
            db.add_network_binding(session, net['id'],
                                   network_type,
                                   physical_network, 
                                   vlan_id)
            
            self._process_l3_create(context, network['network'], net['id'])
            self._extend_network_dict_provider(context, net)
            self._extend_network_dict_l3(context, net)
            # note - exception will rollback entire transaction
            LOG.debug(_("Created network: %s"), net['id'])
            return net    
         
    def update_network(self, context, net_id, network):
        self._check_provider_update(context, network['network'])

        session = context.session
        with session.begin(subtransactions=True):
            net = super(MellanoxEswitchPlugin, self).update_network(context, net_id,
                                                                  network)
            self._process_l3_update(context, network['network'], net_id)
            self._extend_network_dict_provider(context, net)
            self._extend_network_dict_l3(context, net)
        return net

    def delete_network(self, context, net_id):
        LOG.debug(_("delete network"))
        session = context.session
        with session.begin(subtransactions=True):
            binding = db.get_network_binding(session, net_id)
            result = super(MellanoxEswitchPlugin, self).delete_network(context,net_id)
            if binding.segmentation_id != constants.LOCAL_VLAN_ID:
                db.release_network(session, binding.physical_network,
                                   binding.segmentation_id, self.network_vlan_ranges)
            # the network_binding record is deleted via cascade from
            # the network record, so explicit removal is not necessary
        if self.agent_rpc:
            self.notifier.network_delete(self.rpc_context, net_id)

    def get_network(self, context, net_id, fields=None):
        net = super(MellanoxEswitchPlugin, self).get_network(context, net_id, None)
        self._extend_network_dict_provider(context, net)
        self._extend_network_dict_l3(context, net)
        return self._fields(net, fields)

    def get_networks(self, context, filters=None, fields=None):
        nets = super(MellanoxEswitchPlugin, self).get_networks(context, filters,
                                                             None)
        for net in nets:
            self._extend_network_dict_provider(context, net)
            self._extend_network_dict_l3(context, net)

        # TODO(rkukura): Filter on extended provider attributes.
        nets = self._filter_nets_l3(context, nets, filters)
        return [self._fields(net, fields) for net in nets]
    
    def update_port(self, context, port_id, port):
        if self.agent_rpc:
            original_port = super(MellanoxEswitchPlugin, self).get_port(context,
                                                                      port_id)
        port = super(MellanoxEswitchPlugin, self).update_port(context, port_id, port)
        if self.agent_rpc:
            if original_port['admin_state_up'] != port['admin_state_up']:
                binding = db.get_network_binding(context.session,
                                                 port['network_id'])
                self.notifier.port_update(self.rpc_context, port,
                                          binding.physical_network,
                                          binding.network_type,
                                          binding.segmentation_id)
        return port
        
    def delete_port(self, context, id, l3_port_check=True):

        # if needed, check to see if this is a port owned by
        # and l3-router.  If so, we should prevent deletion.
        if l3_port_check:
            self.prevent_l3_port_deletion(context, id)
        self.disassociate_floatingips(context, id)
        return super(MellanoxEswitchPlugin, self).delete_port(context, id)
