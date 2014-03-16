import netaddr
import re
import StringIO
from oslo.config import cfg
from neutron.agent.linux import dhcp
from neutron.agent.linux import utils
from neutron.openstack.common import log as logging

LOG = logging.getLogger(__name__)


class MlnxDnsmasq(dhcp.Dnsmasq):
    def spawn_process(self):
        """Spawns a Dnsmasq process for the network."""
        env = {
            self.NEUTRON_NETWORK_ID_KEY: self.network.id,
        }

        cmd = [
            'dnsmasq',
            '--no-hosts',
            '--no-resolv',
            '--strict-order',
            '--bind-interfaces',
            '--interface=%s' % self.interface_name,
            '--except-interface=lo',
            '--pid-file=%s' % self.get_conf_file_name(
                'pid', ensure_conf_dir=True),
            '--dhcp-hostsfile=%s' % self._output_hosts_file(),
            '--dhcp-optsfile=%s' % self._output_opts_file(),
            '--leasefile-ro',
        ]

        possible_leases = 0
        for i, subnet in enumerate(self.network.subnets):
            # if a subnet is specified to have dhcp disabled
            if not subnet.enable_dhcp:
                continue
            if subnet.ip_version == 4:
                mode = 'static'
            else:
                # TODO(mark): how do we indicate other options
                # ra-only, slaac, ra-nameservers, and ra-stateless.
                mode = 'static'
            if self.version >= self.MINIMUM_VERSION:
                set_tag = 'set:'
            else:
                set_tag = ''

            cidr = netaddr.IPNetwork(subnet.cidr)

            cmd.append('--dhcp-range=%s%s,%s,%s,%ss' %
                       (set_tag, self._TAG_PREFIX % i,
                        cidr.network,
                        mode,
                        self.conf.dhcp_lease_duration))
            possible_leases += cidr.size

        # Cap the limit because creating lots of subnets can inflate
        # this possible lease cap.
        cmd.append('--dhcp-lease-max=%d' %
                   min(possible_leases, self.conf.dnsmasq_lease_max))

        cmd.append('--conf-file=%s' % self.conf.dnsmasq_config_file)
        if self.conf.dnsmasq_dns_server:
            cmd.append('--server=%s' % self.conf.dnsmasq_dns_server)

        if self.conf.dhcp_domain:
            cmd.append('--domain=%s' % self.conf.dhcp_domain)

        cmd.append('--dhcp-broadcast')

        if self.network.namespace:
            ip_wrapper = ip_lib.IPWrapper(self.root_helper,
                                          self.network.namespace)
            ip_wrapper.netns.execute(cmd, addl_env=env)
        else:
            # For normal sudo prepend the env vars before command
            cmd = ['%s=%s' % pair for pair in env.items()] + cmd
            utils.execute(cmd, self.root_helper)

    def _output_hosts_file(self):
        """Writes a dnsmasq compatible hosts file."""
        r = re.compile('[:.]')
        buf = StringIO.StringIO()

        prefix = 'ff:00:00:00:00:00:02:00:00:02:c9:00:'
        for port in self.network.ports:
            for alloc in port.fixed_ips:
                name = '%s.%s' % (r.sub('-', alloc.ip_address),
                                  self.conf.dhcp_domain)

                mac_first = port.mac_address[:8]
                middle = ':00:00:'
                mac_last = port.mac_address[9:]
                client_id = ''.join([prefix, mac_first, middle, mac_last])

                buf.write('%s,id:%s,%s,%s\n' %
                          (port.mac_address, client_id,
                           name, alloc.ip_address))

        name = self.get_conf_file_name('host')
        utils.replace_file(name, buf.getvalue())
        return name
