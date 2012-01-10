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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#
# Refer to the README and COPYING files for full details of the license
#

import os
import glob
import rpm

from vdsm import utils
from vdsm import constants
from storage import mount
import supervdsm as svdsm

MIN_USABLE_SIZE = 1

def _normDevPath(name):
    dev = os.path.normpath('/dev/' + name)
    if os.path.exists(dev):
        return dev
    else:
        return os.path.normpath(name)

def _normDevName(dev):
    dev = os.path.normpath(dev)
    return dev.replace('/dev/', '', 1) if dev.startswith('/dev/') else dev

def getProcPartitions():
    procPartitionsDict = {}
    with open("/proc/partitions") as f:
        f.next() # skip 1st line
        f.next() # skip 2nd line
        for line in f:
            major, minor, blocks, name = line.strip().split()[:4]
            procPartitionsDict[name] = {"size" : '%.3f' % (float(blocks) /
                                                           1024.0),
                                        'major': major,
                                        'minor': minor}
    return procPartitionsDict

def getProcMdStat():
    raidArrayDict = {}
    with open("/proc/mdstat") as f:
        f.next() # skip 1st line
        for line in f:
            tokens = line.strip().split()
            if not tokens:
                continue
            if tokens[0].startswith("md"):
                raidArrayDict[tokens[0]] = {"status" : tokens[2],
                                            "type" : tokens[3],
                                            "members" : map(lambda x:
                                                                x.split('[')[0],
                                                            tokens[4:])}
    return raidArrayDict

def _reduceToDict(reducer, out):
    return reduce(reducer,
                  map(dict, map(lambda x: map(lambda y: y.split('='),
                                              x.strip().split(':')),
                                out)),
                  {})

def getLvs():
    rc, out, err = utils.execCmd([constants.EXT_LVM] +
                                 ("lvs --unquoted --noheading " +
                                  "--nameprefixes --separator : " +
                                  "--nosuffix --units m -o " +
                                  "lv_all,vg_name").split(),
                                 sudo=True)
    if rc:
        # TODO: add logging
        return {}
    def _makeLvDict(x, y):
        x[y['LVM2_LV_PATH']] = y
        return x
    return _reduceToDict(_makeLvDict, out)

def getVgs():
    rc, out, err = utils.execCmd([constants.EXT_LVM] +
                                 ("vgs --unquoted --noheading " +
                                  "--nameprefixes --separator : " +
                                  "--nosuffix --units m -o " +
                                  "vg_all,lv_path").split(),
                                 sudo=True)
    if rc:
        # TODO: add logging
        return {}
    def _makeVgDict(x, y):
        y['LVM2_LV_PATH'] = [y['LVM2_LV_PATH']] if y['LVM2_LV_PATH'] else []
        if x.has_key(y['LVM2_VG_NAME']):
            x[y['LVM2_VG_NAME']]['LVM2_LV_PATH'] += y['LVM2_LV_PATH']
        else:
            x[y['LVM2_VG_NAME']] = y
        return x
    return _reduceToDict(_makeVgDict, out)

def getPvs():
    rc, out, err = utils.execCmd([constants.EXT_LVM] +
                                 ("pvs --unquoted --noheading " +
                                  "--nameprefixes --separator : " +
                                  "--nosuffix --units m -o " +
                                  "pv_all,vg_name").split(),
                                 sudo=True)
    if rc:
        # TODO: add logging
        return {}
    def _makePvDict(x, y):
        x[y['LVM2_PV_NAME']] = y
        return x
    return _reduceToDict(_makePvDict, out)

def _getDeviceModel(name):
    model = ''
    try:
        with open("/sys/block/%s/device/model" % name) as f:
            model = f.read().strip()
    except IOError:
        pass
    return model

def _getDeviceVendor(name):
    vendor = ''
    try:
        with open("/sys/block/%s/device/vendor" % name) as f:
            vendor = f.read().strip()
    except IOError:
        pass
    return vendor

def _getDeviceMountPoint(name):
    try:
        return mount.getMountFromDevice(_normDevPath(name)).getFsFile()
    except OSError:
        return ''

def _getSpaceInUse(mountPoint):
    if not mountPoint:
        return ''
    try:
        s = os.statvfs(mountPoint)
        return '%.3f' % (((s.f_blocks - s.f_bavail) * s.f_bsize) /
                         (1024.0 * 1024.0))
    except OSError:
        return ''

def _updateMdDevices(diskDict):
    for name, info in getProcMdStat().iteritems():
        try:
            diskDict[name]['vendor'] = 'Software Raid Array'
            diskDict[name]['model'] = info["type"]
            # TODO: add info["status"]
            diskDict[name]["members"] = info["members"]
            for m in info["members"]:
                diskDict[m]["container"] = name
        except KeyError:
            pass

def _getPartNames(name, nameList):
    s1 = set(nameList)
    s2 = set([name])
    for d in (s1 - s2):
        if os.path.isdir("/sys/block/%s/%s" % (name, d)):
            yield d

def _updatePvsInfo(diskDict):
    for name, info in getPvs().iteritems():
        diskDict[_normDevName(name)]["container"] = info["LVM2_VG_NAME"]

def _getDevUuidMap():
    return dict(map(lambda x: (_normDevName(os.path.realpath(x)),
                               os.path.basename(x)),
                    glob.glob("/dev/disk/by-uuid/*")))

def _addVgsInfo(diskDict):
    vgDict = getVgs()
    for name, info in vgDict.iteritems():
        diskDict[name] = {'name': name,
                          'size': info["LVM2_VG_SIZE"],
                          'vendor': info["LVM2_VG_FMT"].upper(),
                          'model': 'Volume Group',
                          'uuid': info["LVM2_VG_UUID"],
                          'fsType': '',
                          'mountPoint': '',
                          'spaceInUse': "%.3f" % \
                              (float(info["LVM2_VG_SIZE"]) -
                               float(info["LVM2_VG_FREE"])),
                          'status': 'INITIALIZED',
                          'type': 'UNKNOWN',
                          'partitions': map(_normDevName, info['LVM2_LV_PATH']),
                          'members': [],
                          }

    # update VG with its PVs
    for name, info in diskDict.iteritems():
        cname = info.get('container')
        if cname in vgDict.keys():
            diskDict[cname]['members'] += [name]

    return diskDict

def getDisksList(exceptList=[], full=False):
    def _updateStatus(disk):
        disk['status'] = 'INITIALIZED' if disk["fsType"] else 'UNUSABLE' \
            if float(disk['size']) <= MIN_USABLE_SIZE else 'UNINITIALIZED'

    def _updateType(disk):
        if disk["mountPoint"] in ["/", "/boot", "/usr", "/var"]:
            disk["type"] = 'OS'
        elif disk["mountPoint"]:
            disk["type"] = 'DATA'
        elif disk["fsType"].upper() == 'SWAP':
            disk["type"] = 'SWAP'
        else:
            disk["type"] = 'UNKNOWN'

    devUuidMap = _getDevUuidMap()
    blkIdDict = svdsm.getProxy().getLsBlk()
    procPartitionsDict = getProcPartitions()

    for key in procPartitionsDict.keys():
        if key in exceptList:
            del procPartitionsDict[key]

    diskDict = procPartitionsDict
    for name, info in diskDict.iteritems():
        info['name'] = name
        info['model'] = _getDeviceModel(name)
        info['vendor'] = _getDeviceVendor(name)
        info["uuid"] = blkIdDict.get(name, {}).get('UUID',
                                                   devUuidMap.get(name, ''))
        info["fsType"] = blkIdDict.get(name, {}).get('FSTYPE', '')
        info["mountPoint"] = _getDeviceMountPoint(name)
        info["spaceInUse"] = _getSpaceInUse(info['mountPoint'])
        _updateStatus(info)
        _updateType(info)
        #info["partitions"] = {} # engine expects atleast empty value
        #info["members"] = [] # engine expects atleast empty value

    for name,info in diskDict.iteritems():
        partList = list(_getPartNames(name, diskDict.keys()))
        if partList:
            info["partitions"] = partList
            info["status"] = "PARTED"
            for partName in partList:
                diskDict[partName]['parent'] = name

    _updateMdDevices(diskDict)
    _updatePvsInfo(diskDict)
    _addVgsInfo(diskDict)

    # add LVM LVs as disk
    lvsDict = getLvs()
    lvDmMap = dict(map(lambda x: (x, os.path.realpath(x)), lvsDict.keys()))
    dmMap = dict(map(lambda x: (os.path.realpath(x), x),
                     glob.glob('/dev/mapper/*')))
    for dev, info in lvsDict.iteritems():
        name = _normDevName(dev)
        dmDevice = dmMap[lvDmMap[dev]]
        diskDict[name] = {'name': name,
                          'size': info["LVM2_LV_SIZE"],
                          'vendor': '',
                          'model': 'Logical Volume',
                          'uuid': info["LVM2_LV_UUID"],
                          'fsType': blkIdDict.get(dmDevice, {}).get('FSTYPE',
                                                                    ''),
                          'mountPoint': _getDeviceMountPoint(name),
                          'spaceInUse': '',
                          'status': '',
                          'type': 'UNKNOWN',
                          'parent': info['LVM2_VG_NAME'],
                          }
        diskDict[name]['spaceInUse'] = \
            _getSpaceInUse(diskDict[name]['mountPoint'])
        _updateStatus(diskDict[name])
        _updateType(diskDict[name])

    # remove dm devices
    for name in diskDict.keys():
        if os.path.isdir('/sys/block/%s/dm' % name):
            del diskDict[name]

    return diskDict


def getVolumeUuid(volumeName):
    try:
        return dict(map(lambda x: x.strip().split('=', 1),
                        open('/var/lib/glusterd/vols/%s/info' % \
                                 volumeName))).get('volume-id', '')
    except IOError:
        return ''


def getGlusterUuid():
    try:
        return dict(map(lambda x: x.strip().split('=', 1),
                        open('/var/lib/glusterd/glusterd.info'))).get('UUID',
                                                                      '')
    except IOError:
        return ''


def getGlusterHostname():
    try:
        return dict(map(lambda x: x.strip().split('=', 1),
                        open('/etc/sysconfig/network'))).get('HOSTNAME', '')
    except IOError:
        return ''


def getGlusterRpmPkgs():
    return ['glusterfs', 'glusterfs-server', 'glusterfs-fuse', 'glusterfs-rdma',
            'glusterfs-geo-replication']


def getGlusterDebPkgs():
    return {'glusterfs': 'glusterfs',
            'glusterfs-server': 'glusterfs-server',
            'glusterfs-fuse': 'glusterfs-fuse',
            'glusterfs-rdma': 'glusterfs-rdma',
            'glusterfs-geo-replication': 'glusterfs-geo-replication'}


def glusterRpmInfo():
    def _rpmSearch(name):
        rpmInfo = {}
        ts = rpm.TransactionSet()
        mi = ts.dbMatch()
        mi.pattern(rpm.RPMTAG_NAME, rpm.RPMMIRE_GLOB, name)
        for hdr in mi:
            rpmInfo[hdr[rpm.RPMTAG_NAME]] = \
                {'release': hdr[rpm.RPMTAG_RELEASE],
                 'buildtime': hdr[rpm.RPMTAG_BUILDTIME],
                 'version': hdr[rpm.RPMTAG_VERSION]}
        return rpmInfo

    return _rpmSearch('gluster*')


def getCdromDevices():
    with open("/proc/sys/dev/cdrom/info") as f:
        for line in f:
            if line.startswith("drive name:"):
                return line.strip().split()[2:]
