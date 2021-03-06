#
# Copyright 2011 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#
# Refer to the README and COPYING files for full details of the license
#

# for a "singleton" config object
import ConfigParser

config = ConfigParser.ConfigParser()
config.add_section('vars')
config.set('vars', 'reg_req_interval', '5')
config.set('vars', 'vdsm_conf_file', '/etc/vdsm/vdsm.conf')
config.set('vars', 'logger_conf', '/etc/vdsm-reg/logger.conf')
config.set('vars', 'pidfile', '/var/run/vdsm-reg.pid')
config.set('vars', 'test_socket_timeout', '10')
config.set('vars', 'vdc_host_name', 'None')
config.set('vars', 'vdc_host_ip', 'None')
config.set('vars', 'vdc_host_port', '80')
config.set('vars', 'vdc_reg_uri', '/SolidICE/VdsAutoRegistration.aspx')
config.set('vars', 'vdc_reg_port', '54321')
config.set('vars', 'upgrade_iso_file', '/data/updates/ovirt-node-image.iso')
config.set('vars', 'vdsm_dir', '/usr/share/vdsm')
config.set('vars', 'ticket', '')
