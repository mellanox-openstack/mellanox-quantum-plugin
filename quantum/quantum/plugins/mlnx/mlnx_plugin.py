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

from oslo.config import cfg
from quantum.api.v2 import attributes
from quantum.common import exceptions as q_exc
from quantum.common import topics
from quantum.db import db_base_plugin_v2
from quantum.db import l3_db
from quantum.db import agents_db
# NOTE: quota_db cannot be removed, it is for db model
from quantum.db import quota_db
from quantum.extensions import providernet as provider
from quantum.extensions import portbindings
from quantum.openstack.common import rpc
from quantum.openstack.common import log as logging
from quantum.plugins.mlnx.common import constants
from quantum.plugins.mlnx.db import mlnx_db_v2 as db
from quantum.plugins.mlnx import rpc_callbacks
from quantum.plugins.mlnx import agent_notify_api
from quantum import policy


LOG = logging.getLogger(__name__)

class MellanoxEswitchPlugin(db_base_plugin_v2.QuantumDbPluginV2,
                          l3_db.L3_NAT_db_mixin, 
                          agents_db.AgentDbMixin):
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
    #  __native_pagination_support = True
    #  __native_sorting_support = True

    supported_extension_aliases = ["provider", "router", "binding", "agent", "quotas"]
    
    network_view = "extension:provider_network:view"
    network_set = "extension:provider_network:set"
    binding_view = "extension:port_binding:view"
    binding_set = "extension:port_binding:set"

    def __init__(self):
        """
        @note: Start Mellanox Quantum Plugin.       
        """
        db.initialize()
        self._parse_network_vlan_ranges()
        db.sync_network_states(self.network_vlan_ranges)
        self._set_tenant_network_type()
        self.agent_rpc = cfg.CONF.AGENT.rpc
        self.vnic_type = cfg.CONF.ESWITCH.vnic_type
        self._setup_rpc()
        LOG.debug("Mellanox Embedded Switch Plugin initialisation complete")
     
    def _setup_rpc(self):
        # RPC support
        self.topic = topics.PLUGIN
        self.conn = rpc.create_connection(new=True)
        self.notifier = agent_notify_api.AgentNotifierApi(topics.AGENT)  
        self.callbacks = rpc_callbacks.MlnxRpcCallbacks() 
       
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
                    LOG.error(_("Invalid network VLAN range: "
                                "'%(entry)s' - %(ex)s. "
                                "Service terminated!"),
                              locals())
                    sys.exit(1)
            else:
                self._add_network(entry)
        LOG.debug("network VLAN ranges: %s" % self.network_vlan_ranges)
     
    def _check_view_auth(self, context, resource, action):
        return policy.check(context, action, resource)

    def _enforce_set_auth(self, context, resource, action):
        policy.enforce(context, action, resource)

    def _add_network_vlan_range(self, physical_network, vlan_min, vlan_max):
        self._add_network(physical_network)
        self.network_vlan_ranges[physical_network].append((vlan_min, vlan_max))

    def _add_network(self, physical_network):
        if physical_network not in self.network_vlan_ranges:
            self.network_vlan_ranges[physical_network] = []
 
    def _extend_network_dict_provider(self, context, network):
        if self._check_view_auth(context, network, self.network_view):
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
        self._enforce_set_auth(context, attrs, self.network_set)
        
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
        self._enforce_set_auth(context, attrs, self.network_set)

        msg = _("Plugin does not support updating provider attributes")
        raise q_exc.InvalidInput(error_message=msg)

    def _process_port_binding_create(self,context,attrs):
        binding_profile = attrs.get(portbindings.PROFILE)
        binding_profile_set = attributes.is_attr_set(binding_profile)
        if not binding_profile_set:
            return self.vnic_type
        msg = str()
        if constants.VNIC_TYPE in binding_profile:
            if binding_profile[constants.VNIC_TYPE] in (constants.VIF_TYPE_DIRECT, constants.VIF_TYPE_HOSTDEV):
                return binding_profile[constants.VNIC_TYPE]
            else:
                msg = "invalid vnic_type on port_create"
        else:   
            msg = "vnic_type is not defined in port profile"
        raise q_exc.InvalidInput(error_message=msg)
    
    def create_network(self, context, network):     
        (network_type, physical_network,
           vlan_id) = self._process_provider_create(context, network['network'])   
                 
        session = context.session
        with session.begin(subtransactions=True):
                   
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
            self.notifier.network_delete(context, net_id)

    def get_network(self, context, net_id, fields=None):
        session = context.session
        with session.begin(subtransactions=True):
            net = super(MellanoxEswitchPlugin, self).get_network(context, net_id, None)
            self._extend_network_dict_provider(context, net)
            self._extend_network_dict_l3(context, net)
        return self._fields(net, fields)

    def get_networks(self, context, filters=None, fields=None):
        session = context.session
        with session.begin(subtransactions=True):
            nets = super(MellanoxEswitchPlugin, self).get_networks(context,
                                                                 filters,
                                                                 None)
            for net in nets:
                self._extend_network_dict_provider(context, net)
                self._extend_network_dict_l3(context, net)
            # TODO(rkukura): Filter on extended provider attributes.
            nets = self._filter_nets_l3(context, nets, filters)
        return [self._fields(net, fields) for net in nets]
    
    
    def _extend_port_dict_binding(self, context, port):
        if self._check_view_auth(context, port, self.binding_view):
            port_binding = db.get_port_profile_binding(context.session, port['id'])
            if port_binding:
                port[portbindings.VIF_TYPE] = port_binding.vnic_type
            port[portbindings.CAPABILITIES] = {
                portbindings.CAP_PORT_FILTER:
                'security-group' in self.supported_extension_aliases}
            binding = db.get_network_binding(context.session,
                                                port['network_id'])
            port[portbindings.PROFILE] = {'physical_network': binding.physical_network}
        return port
    
    def create_port(self, context, port):
        LOG.debug(_("create_port with %s"),port)
        vnic_type = self._process_port_binding_create(context,port['port'])
        port = super(MellanoxEswitchPlugin, self).create_port(context, port)
        db.add_port_profile_binding(context.session, port['id'], vnic_type)
        return self._extend_port_dict_binding(context, port)
    
    def get_port(self, context, id, fields=None):
        port = super(MellanoxEswitchPlugin, self).get_port(context, id, fields)
        return self._fields(self._extend_port_dict_binding(context, port),
                            fields)

    def get_ports(self, context, filters=None, fields=None):
        ports = super(MellanoxEswitchPlugin, self).get_ports(
            context, filters, fields)
        return [self._fields(self._extend_port_dict_binding(context, port),
                             fields) for port in ports]

    def update_port(self, context, port_id, port):
        original_port = super(MellanoxEswitchPlugin, self).get_port(context, port_id)
        session = context.session
        with session.begin(subtransactions=True):
            port = super(MellanoxEswitchPlugin, self).update_port(context, port_id, port)

        if  self.agent_rpc:
            if original_port['admin_state_up'] != port['admin_state_up']:
                binding = db.get_network_binding(context.session,
                                                 port['network_id'])
                self.notifier.port_update(context, port,
                                          binding.physical_network,
                                          binding.network_type,
                                          binding.segmentation_id)
                
        return self._extend_port_dict_binding(context, port)
        
    def delete_port(self, context, port_id, l3_port_check=True):
        # if needed, check to see if this is a port owned by
        # and l3-router.  If so, we should prevent deletion.
        if l3_port_check:
            self.prevent_l3_port_deletion(context, port_id)
        
        session = context.session
        with session.begin(subtransactions=True):
            self.disassociate_floatingips(context, port_id)
            
            return super(MellanoxEswitchPlugin, self).delete_port(context, port_id)
