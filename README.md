MELLANOX  OPENSTACK QUANTUM PLUGIN Rev 1.0
====================================================


#Contents:
===============================================================================
1. Overview
    1. Mellanox Quantum Plugin
    2. Mellanox nova VIF Driver
    3. Prerequisite
2. Code Structure
3. Mellanox Quantum Plugin Installation
4. Mellanox Quantum Plugin Configuration
   1. Quantum Configuration
   2. Nova Configuration (compute node(s))
5. Additional Information

	   
# Overview
===============================================================================
## Mellanox Quantum Plugin
-------------------------------------------------------------------------------
Openstack Mellanox Quantum plugin supports Mellanox embedded switch 
functionality as part of the VPI (Ethernet/InfiniBand) HCA.
Mellanox Quantum Plugin allows hardware vNICs (based on SR-IOV Virtual 
Functions) per each Virtual Machine vNIC to have its unique 
connectivity, security, and QoS attributes. 
Hardware vNICs can be mapped to the guest VMs through para-virtualization 
(using a Tap device), or directly as a Virtual PCI device to the guest, 
allowing higher performance and advanced features such as RDMA.

Hardware based switching, provides better performance, functionality, 
and security/isolation for virtual cloud environments.
Future versions of the plug-in will include OpenFlow API to control and 
monitor the embedded switch and vNICs functionality 

This plugin is implemented according to Plugin-Agent pattern.


		          +-----------------+                       +--------------+
                  | Controller node |                       | Compute node |
        +-----------------------------------+     +-----------------------------------+
        |  +-----------+      +----------+  |     |  +----------+       +----------+  |
        |  |           |      |          |  |     |  |          |  zmq  |          |  |
        |  | Openstack | v2.0 | Mellanox |  | RPC |  | Mellanox |REQ/REP| Mellanox |  |
        |  | Quantum   +------+ Quantum  +-----------+ Quantum  +-------+ Embedded |  |
        |  |           |      | Plugin   |  |     |  | Agent    |       | Switch   |  |
        |  |           |      |          |  |     |  |          |       | (NIC)    |  |
        |  +-----------+      +----------+  |     |  +----------+       +----------+  |
        +-----------------------------------+     +-----------------------------------+
			 
* Openstack Mellanox Quantum Plugin implements the Quantum v2.0 API.
* Mellanox Quantum Plugin processes the Quantum API calls and manages 
    network segmentation ID allocation. 
* The plugin uses Databsase to store configuration and allocation mapping.
* The plugin maintains compatibility to Linux Bridge Plugin support DHCP 
    and L3 Agents by running L2 Linux Bridge Agent on Network Node.
* Mellanox Openstack Quantum Agent (L2 Agent) should run on each compute node. 
* Agent should apply VIF connectivity based on mapping between a VIF (VM vNIC) 
    and Embedded Switch port.

## Mellanox nova VIF Driver
-------------------------------------------------------------------------------
Mellanox Nova VIF driver should be used when running Mellanox Quantum Plugin. 
VIF driver supports VIF plugging by binding vNIC (Para-virtualized or SR-IOV 
with optional RDMA guest access) to the Embedded Switch port.

## Prerequisite
-------------------------------------------------------------------------------
The following are the Mellanox Quantum Plugin prerequisites:

1. Compute nodes should be equiped with Mellanox ConnectX®-2/ConnectX®-3 
    Network Adapter. 
2. OFED 2.0 installed.
3. eswitchd controller utility - An add-on user space software that manages 
    HCA embedded switch via user space utilities should be installed


# Code Structure
===============================================================================
Mellanox Quantum Plugin and supporting nova VIF driver are located at
http://github.com/mellanox-openstack/mellanox-quantum-plugin

##### Quantum Plugin package structure:
 
    quantum/etc/quantum/plugins/mlnx -plugin configuration
    mlnx_conf.ini - sample plugin configuration
    
    quantum/quantum/plugins/mlnx -  plugin code   
    /agent - Agent code
    /common - common  code   
    /db - plugin persistency model and wrapping methods
    mlnx_plugin.py - Mellanox Openstack Plugin
    rpc_callbacks.py - RPC handler for received messages
    agent_notify_api.py - Agent RPC notify methods

Mellanox Quantum Plugin should be located under /quantum/quantum/plugins/ 

##### Nova VIF Driver package structure is:
    nova/nova/mlnx - nova vif driver code

Mellanox nova VIF driver  should be located under /nova/virt/libvirt/ 

# Mellanox Quantum Plugin Installation
===============================================================================
For detailed installation guide please refer to 
http://github.com/mellanox-openstack/mellanox-quantum-plugin/install_guide


# Mellanox Quantum Plugin Configuration
===============================================================================
## Quantum Configuration
-------------------------------------------------------------------------------
1. Make the Mellanox plugin the current quantum plugin by 
   edit quantum.conf and change the core_plugin

    core_plugin = quantum.plugins.mlnx.mlnx_plugin.MellanoxEswitchPlugin

2. Database configuration
   MySQL should be installed on the central server. 
   A database named quantum should be created

3. Plugin configuration
   Edit the configuration file: etc/quantum/plugins/mlnx/mlnx_conf.ini

##### On central server node

    [DATABASE]
    sql_connection - must match the mysql configuration

    [VLANS]
    tenant_network_type - must be set on of supported tenant network types
   
    network_vlan_ranges - must be configured to specify the names of the physical networks
                         managed by the mellanox plugin, along with the ranges of VLAN IDs
                         available on each physical network for allocation to virtual networks. 
				
##### On compute node(s))

    [AGENT]
    polling_interval - interfval to poll for existing vNICs
    rpc  - must be set to True

    [ESWITCH]
    physical_interface_mapping -  the network_interface_mappings maps each physical network name
                                 to the physical interface (on top of Mellanox Adapter) connecting 
								 the node to that physical network. 
							  
For Plugin consfiguration file example, please refer to 

http://github.com/mellanox-openstack/mellanox-quantum-plugin/quantum/etc/quantum/plugins/mlnx/mlnx_conf.ini

## Nova Configuration (compute node(s)) 
------------------------------------
Edit the nova.conf file 

##### Configure the vif driver, and libvirt/vif type

    compute_driver=nova.virt.libvirt.driver.LibvirtDriver
    connection_type=libvirt
    libvirt_vif_driver=nova.virt.libvirt.mlnx.vif.MlxEthVIFDriver

##### Configure vnic_type ('direct' or 'hostdev')

    vnic_type= direct 

##### Define Embedded Switch managed physical network (currently  single fabric on node)

    fabric=default - specifies physical network for vNICs

##### Enable DHCP server to allow VMs to acquire IPs

    quantum_use_dhcp=true


# Additional Information
===============================================================================
For more details, please refer your question to openstack@mellanox.com
