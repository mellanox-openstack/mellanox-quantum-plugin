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

import logging

from sqlalchemy.orm import exc

from quantum.common import exceptions as q_exc
import quantum.db.api as db
from quantum.db import models_v2
from quantum.openstack.common import cfg
from quantum.plugins.mlnx.common import config
from quantum.plugins.mlnx.db import mlnx_models_v2

LOG = logging.getLogger(__name__)

def initialize():
    db.configure_db()


def _remove_non_allocatable_vlans(session, allocations, physical_network, vlan_ids):
    if physical_network in allocations:
        for entry in allocations[physical_network]:
            try:
                # see if vlan is allocatable
                vlan_ids.remove(entry.segmentation_id) 
            except KeyError:
                # it's not allocatable, so check if its allocated
                if not entry.allocated:
                    # it's not, so remove it from table
                    LOG.debug("removing vlan %s on physical network "
                        "%s from pool" % 
                        (entry.segmentation_id, physical_network))
                    session.delete(entry)
       
        del allocations[physical_network]
   

def _add_missing_allocatable_vlans(session, physical_network, vlan_ids):
    for vlan_id in sorted(vlan_ids):
        entry = mlnx_models_v2.SegmentationIdAllocation(physical_network, vlan_id)
        session.add(entry)


def _remove_unconfigured_vlans(session, allocations):
    for entries in allocations.itervalues():
        for entry in entries:
            if not entry.allocated:
                LOG.debug("removing vlan %s on physical network %s"
                    " from pool" % 
                    (entry.segmentation_id, entry.physical_network))
                session.delete(entry)


def sync_network_states(network_vlan_ranges):
    """Synchronize network_states table with current configured VLAN ranges."""

    session = db.get_session()
    with session.begin():
        # get existing allocations for all physical networks
        allocations = dict()
        entries = (session.query(mlnx_models_v2.SegmentationIdAllocation).
                  all())
        for entry in entries:
            if entry.physical_network not in allocations:
                allocations[entry.physical_network] = set()
            allocations[entry.physical_network].add(entry)
        # process vlan ranges for each configured physical network
        for physical_network, vlan_ranges in network_vlan_ranges.iteritems():
            # determine current configured allocatable vlans for this
            # physical network
            vlan_ids = set()
            for vlan_range in vlan_ranges:
                vlan_ids |= set(xrange(vlan_range[0], vlan_range[1] + 1))
            # remove from table unallocated vlans not currently allocatable
            _remove_non_allocatable_vlans(session, allocations, 
                                          physical_network, vlan_ids)
            # add missing allocatable vlans to table
            _add_missing_allocatable_vlans(session, physical_network, vlan_ids)
        # remove from table unallocated vlans for any unconfigured physical
        # networks
        _remove_unconfigured_vlans(session, allocations)


def get_network_state(physical_network, segmentation_id):
    """Get entry of specified network"""
    session = db.get_session()
    try:
        entry = (session.query(mlnx_models_v2.SegmentationIdAllocation).
                 filter_by(physical_network=physical_network,
                           segmentation_id=segmentation_id).
                 one())
        return entry
    except exc.NoResultFound:
        return None


def reserve_network(session):
    with session.begin(subtransactions=True):
        entry = (session.query(mlnx_models_v2.SegmentationIdAllocation).
                 filter_by(allocated=False).
                 first())
        if not entry:
            raise q_exc.NoNetworkAvailable()
        LOG.debug("reserving vlan %s on physical network %s from pool" %
                  (entry.segmentation_id, entry.physical_network))
        entry.allocated = True
        return (entry.physical_network, entry.segmentation_id)


def reserve_specific_network(session, physical_network, segmentation_id):
    with session.begin(subtransactions=True):
        try:
            entry = (session.query(mlnx_models_v2.SegmentationIdAllocation).
                     filter_by(physical_network=physical_network,
                               segmentation_id=segmentation_id).
                     one())
            if entry.allocated:
                raise q_exc.VlanIdInUse(vlan_id=segmentation_id,
                                            physical_network=physical_network)
            LOG.debug("reserving specific vlan %s on physical network %s "
                      "from pool" % (segmentation_id, physical_network))
            entry.allocated = True
        except exc.NoResultFound:
            LOG.debug("reserving specific vlan %s on physical network %s "
                      "outside pool" % (segmentation_id, physical_network))
            entry = mlnx_models_v2.SegmentationIdAllocation(physical_network, segmentation_id)
            entry.allocated = True
            session.add(entry)


def release_network(session, physical_network, segmentation_id, network_vlan_ranges):
    with session.begin(subtransactions=True):
        try:
            state = (session.query(mlnx_models_v2.SegmentationIdAllocation).
                     filter_by(physical_network=physical_network,
                               segmentation_id=segmentation_id).
                     one())
            state.allocated = False
            inside = False
            for vlan_range in network_vlan_ranges.get(physical_network, []):
                if segmentation_id >= vlan_range[0] and segmentation_id <= vlan_range[1]:
                    inside = True
                    break
            if inside:
                LOG.debug("releasing vlan %s on physical network %s to pool" %
                          (segmentation_id, physical_network))
            else:
                LOG.debug("releasing vlan %s on physical network %s outside "
                          "pool" % (segmentation_id, physical_network))
                session.delete(state)
        except exc.NoResultFound:
            LOG.warning("vlan_id %s on physical network %s not found" %
                        (segmentation_id, physical_network))


def add_network_binding(session, network_id, network_type,physical_network, vlan_id):
    with session.begin(subtransactions=True):
        binding = mlnx_models_v2.NetworkBinding(network_id,network_type,
                                                     physical_network, vlan_id)
        session.add(binding)


def get_network_binding(session, network_id):
    try:
        binding = (session.query(mlnx_models_v2.NetworkBinding).
                   filter_by(network_id=network_id).
                   one())
        return binding
    except exc.NoResultFound:
        return

def add_port_profile_binding(session, port_id, vnic_type):
    with session.begin(subtransactions=True):
        binding = mlnx_models_v2.PortProfileBinding(port_id,vnic_type)
        session.add(binding)


def get_port_profile_binding(session, port_id):
    try:
        binding = (session.query(mlnx_models_v2.PortProfileBinding).
                   filter_by(port_id=port_id).
                   one())
        return binding
    except exc.NoResultFound:
        return

def get_port_from_device(device):
    """Get port from database"""
    LOG.debug("get_port_from_device() called")
    session = db.get_session()
    ports = session.query(models_v2.Port).all()
    if not ports:
        return
    for port in ports:
        if port['id'].startswith(device):
            return port
    return


def get_port_from_device_mac(device_mac):
    """Get port from database"""
    LOG.debug("get_port_from_device_mac() called")
    session = db.get_session()
    try:
        port = (session.query(models_v2.Port).
                filter_by(mac_address=device_mac).
                one())
        return port
    except exc.NoResultFound:
        return


def set_port_status(port_id, status):
    """Set the port status"""
    LOG.debug("set_port_status as %s called", status)
    session = db.get_session()
    try:
        port = session.query(models_v2.Port).filter_by(id=port_id).one()
        port['status'] = status
        session.merge(port)
        session.flush()
    except exc.NoResultFound:
        raise q_exc.PortNotFound(port_id=port_id)
