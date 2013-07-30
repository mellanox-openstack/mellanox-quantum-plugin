import re
import StringIO
from quantum.agent.linux import dhcp
from quantum.agent.linux import utils
from quantum.openstack.common import log as logging

LOG = logging.getLogger(__name__)


class MlnxDnsmasq(dhcp.Dnsmasq):
    def _output_hosts_file(self):
        """Writes a dnsmasq compatible hosts file."""
        LOG.debug(_("Mlnx Hosts files!!!!"))
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
