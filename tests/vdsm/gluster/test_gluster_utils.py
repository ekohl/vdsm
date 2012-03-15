#
# Copyright 2012 Red Hat, Inc.
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#

import unittest

from vdsm.gluster import gluster_utils as gu


PROC_MDSTAT = """\
Personalities : [raid6] [raid5] [raid4]
md0 : active raid5 sdc1[3] sdd1[4] sda1[1] sdb1[2]
      2930280960 blocks super 1.2 level 5, 512k chunk, algorithm 2 [4/4] [UUUU]

unused devices: <none>
"""

EXPECTED_MDSTAT = {'md0':
        {
            'status': 'active',
            'type': 'raid5',
            'members': ['sdc1', 'sdd1', 'sda1', 'sdb1'],
        }
}

LVS = """\
  LVM2_LV_UUID=mk9VFc-DxFy-MVKc-cvgJ-jT5w-T3d6-HQ4k0M:LVM2_LV_NAME=c6:LVM2_LV_PATH=/dev/vg/c6:LVM2_LV_ATTR=-wi-ao:LVM2_LV_MAJOR=-1:LVM2_LV_MINOR=-1:LVM2_LV_READ_AHEAD=auto:LVM2_LV_KERNEL_MAJOR=254:LVM2_LV_KERNEL_MINOR=15:LVM2_LV_KERNEL_READ_AHEAD=0,12:LVM2_LV_SIZE=10240,00:LVM2_SEG_COUNT=1:LVM2_ORIGIN=:LVM2_ORIGIN_SIZE=0:LVM2_SNAP_PERCENT=:LVM2_COPY_PERCENT=:LVM2_MOVE_PV=:LVM2_CONVERT_LV=:LVM2_LV_TAGS=:LVM2_MIRROR_LOG=:LVM2_MODULES=:LVM2_VG_NAME=vg
  LVM2_LV_UUID=Hx3suS-Pvvx-ITL3-WWlx-EGaz-paMK-DB6cMP:LVM2_LV_NAME=distfiles:LVM2_LV_PATH=/dev/vg/distfiles:LVM2_LV_ATTR=-wi-ao:LVM2_LV_MAJOR=-1:LVM2_LV_MINOR=-1:LVM2_LV_READ_AHEAD=auto:LVM2_LV_KERNEL_MAJOR=254:LVM2_LV_KERNEL_MINOR=11:LVM2_LV_KERNEL_READ_AHEAD=0,12:LVM2_LV_SIZE=20480,00:LVM2_SEG_COUNT=1:LVM2_ORIGIN=:LVM2_ORIGIN_SIZE=0:LVM2_SNAP_PERCENT=:LVM2_COPY_PERCENT=:LVM2_MOVE_PV=:LVM2_CONVERT_LV=:LVM2_LV_TAGS=:LVM2_MIRROR_LOG=:LVM2_MODULES=:LVM2_VG_NAME=vg
"""

EXPECTED_LVS = {
        '/dev/vg/c6': {'LVM2_LV_ATTR': '-wi-ao', 'LVM2_MIRROR_LOG': '',
            'LVM2_LV_KERNEL_MINOR': '15', 'LVM2_LV_SIZE': '10240,00',
            'LVM2_LV_MAJOR': '-1', 'LVM2_ORIGIN_SIZE': '0',
            'LVM2_COPY_PERCENT': '', 'LVM2_CONVERT_LV': '',
            'LVM2_LV_KERNEL_READ_AHEAD': '0,12', 'LVM2_LV_NAME': 'c6',
            'LVM2_LV_UUID': 'mk9VFc-DxFy-MVKc-cvgJ-jT5w-T3d6-HQ4k0M',
            'LVM2_LV_MINOR': '-1', 'LVM2_LV_KERNEL_MAJOR': '254',
            'LVM2_LV_TAGS': '', 'LVM2_MODULES': '', 'LVM2_VG_NAME': 'vg',
            'LVM2_LV_PATH': '/dev/vg/c6', 'LVM2_LV_READ_AHEAD': 'auto',
            'LVM2_SNAP_PERCENT': '', 'LVM2_MOVE_PV': '', 'LVM2_ORIGIN': '',
            'LVM2_SEG_COUNT': '1'},
        '/dev/vg/distfiles': {'LVM2_LV_ATTR': '-wi-ao', 'LVM2_MIRROR_LOG': '',
            'LVM2_LV_KERNEL_MINOR': '11', 'LVM2_LV_SIZE': '20480,00',
            'LVM2_LV_MAJOR': '-1', 'LVM2_ORIGIN_SIZE': '0',
            'LVM2_COPY_PERCENT': '', 'LVM2_CONVERT_LV': '',
            'LVM2_LV_KERNEL_READ_AHEAD': '0,12', 'LVM2_LV_NAME': 'distfiles',
            'LVM2_LV_UUID': 'Hx3suS-Pvvx-ITL3-WWlx-EGaz-paMK-DB6cMP',
            'LVM2_LV_MINOR': '-1', 'LVM2_LV_KERNEL_MAJOR': '254',
            'LVM2_LV_TAGS': '', 'LVM2_MODULES': '', 'LVM2_VG_NAME': 'vg',
            'LVM2_LV_PATH': '/dev/vg/distfiles', 'LVM2_LV_READ_AHEAD': 'auto',
            'LVM2_SNAP_PERCENT': '', 'LVM2_MOVE_PV': '', 'LVM2_ORIGIN': '',
            'LVM2_SEG_COUNT': '1'},
}

VGS = """\
  LVM2_LV_UUID=EwTukL-LCH2-1gGt-Rfi0-Sb2r-kpBh-8eGmUr:LVM2_LV_NAME=home:LVM2_LV_PATH=/dev/vg/home:LVM2_LV_ATTR=-wi-ao:LVM2_LV_MAJOR=-1:LVM2_LV_MINOR=-1:LVM2_LV_READ_AHEAD=auto:LVM2_LV_KERNEL_MAJOR=254:LVM2_LV_KERNEL_MINOR=0:LVM2_LV_KERNEL_READ_AHEAD=0,12:LVM2_LV_SIZE=51200,00:LVM2_SEG_COUNT=2:LVM2_ORIGIN=:LVM2_ORIGIN_SIZE=0:LVM2_SNAP_PERCENT=:LVM2_COPY_PERCENT=:LVM2_MOVE_PV=:LVM2_CONVERT_LV=:LVM2_LV_TAGS=:LVM2_MIRROR_LOG=:LVM2_MODULES=:LVM2_VG_NAME=vg
  LVM2_LV_UUID=s2rWFF-6YLy-WOyG-hfGF-ifTI-eZPZ-ecsGD3:LVM2_LV_NAME=puppet:LVM2_LV_PATH=/dev/vg/puppet:LVM2_LV_ATTR=-wi-a-:LVM2_LV_MAJOR=-1:LVM2_LV_MINOR=-1:LVM2_LV_READ_AHEAD=auto:LVM2_LV_KERNEL_MAJOR=254:LVM2_LV_KERNEL_MINOR=1:LVM2_LV_KERNEL_READ_AHEAD=0,12:LVM2_LV_SIZE=10240,00:LVM2_SEG_COUNT=1:LVM2_ORIGIN=:LVM2_ORIGIN_SIZE=0:LVM2_SNAP_PERCENT=:LVM2_COPY_PERCENT=:LVM2_MOVE_PV=:LVM2_CONVERT_LV=:LVM2_LV_TAGS=:LVM2_MIRROR_LOG=:LVM2_MODULES=:LVM2_VG_NAME=vg
"""

EXPECTED_VGS = {'vg': {'LVM2_CONVERT_LV': '',
    'LVM2_COPY_PERCENT': '',
    'LVM2_LV_ATTR': '-wi-ao',
    'LVM2_LV_KERNEL_MAJOR': '254',
    'LVM2_LV_KERNEL_MINOR': '0',
    'LVM2_LV_KERNEL_READ_AHEAD': '0,12',
    'LVM2_LV_MAJOR': '-1',
    'LVM2_LV_MINOR': '-1',
    'LVM2_LV_NAME': 'home',
    'LVM2_LV_PATH': ['/dev/vg/home', '/dev/vg/puppet'],
    'LVM2_LV_READ_AHEAD': 'auto',
    'LVM2_LV_SIZE': '51200,00',
    'LVM2_LV_TAGS': '',
    'LVM2_LV_UUID': 'EwTukL-LCH2-1gGt-Rfi0-Sb2r-kpBh-8eGmUr',
    'LVM2_MIRROR_LOG': '',
    'LVM2_MODULES': '',
    'LVM2_MOVE_PV': '',
    'LVM2_ORIGIN': '',
    'LVM2_ORIGIN_SIZE': '0',
    'LVM2_SEG_COUNT': '2',
    'LVM2_SNAP_PERCENT': '',
    'LVM2_VG_NAME': 'vg'}}


class TestGlusterUtils(unittest.TestCase):
    def test__parseProcMdStat(self):
        parsed = gu._parseProcMdStat(PROC_MDSTAT.splitlines())
        self.assertDictEqual(EXPECTED_MDSTAT, parsed)

    def test__parseLvs(self):
        parsed = gu._parseLvs(LVS.splitlines())
        self.assertDictEqual(EXPECTED_LVS, parsed)

    def test__parseVgs(self):
        self.maxDiff = None
        parsed = gu._parseVgs(VGS.splitlines())
        self.assertDictEqual(EXPECTED_VGS, parsed)

if __name__ == '__main__':
    unittest.main()
