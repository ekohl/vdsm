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

from vdsm.define import doneCode
import gluster_utils as gutils
import gluster_cli as gcli
import gluster_exception as ge


SUCCESS = {'status': doneCode}

class GlusterApi(object):
    """
    The gluster interface of vdsm.

    """

    def __init__ (self, cif, log):
        self.cif = cif
        self.log = log


    def volumesList(self, options=None):
        """
        Returns:
            {'status' : {'code': CODE, 'message': MESSAGE},
             'volumes': {VOLUMENAME: {'brickCount': BRICKCOUNT,
                                      'bricks': [BRICK1, BRICK2, ...],
                                      'options': {ATTRIBUTE: VALUE, ...},
                                      'transportType': [ETHERNET,
                                                        INFINIBAND, ...],
                                      'uuid': UUID,
                                      'volumeName': NAME,
                                      'volumeStatus': STATUS,
                                      'volumeType': TYPE}, ...}}
        """
        transportMap = {'TCP': 'ETHERNET',
                        'RDMA': 'INFINIBAND'}

        volumeInfoDict = gcli.volumeInfo()
        for name, info in volumeInfoDict.iteritems():
            info["volumeType"] = info["volumeType"].replace("-", "_")
            if info["volumeStatus"] == "STARTED":
                info["volumeStatus"] = "ONLINE"
            else:
                info["volumeStatus"] = "OFFLINE"
            info["transportType"] = map(lambda x:
                                            transportMap.get(x.upper(), ''),
                                        info["transportType"])
        return {'status': doneCode, 'volumes' : volumeInfoDict}


    def volumeCreate(self, volumeName, brickList, replicaCount=0, stripeCount=0,
                     transportList=[], options=None):
        transportMap = {'ETHERNET': 'tcp',
                        'INFINIBAND': 'rdma'}
        transport = reduce(lambda x, y: (x + ',' + y) if (x and y) \
                               else x if x else y,
                           map(lambda x: transportMap.get(x.upper(), ''),
                               transportList))
        if gcli.volumeCreate(volumeName, brickList, replicaCount, stripeCount,
                             transport):
            return SUCCESS


    def volumeStart(self, volumeName, force=False, options=None):
        if gcli.volumeStart(volumeName, force):
            return SUCCESS


    def volumeStop(self, volumeName, force=False, options=None):
        if gcli.volumeStop(volumeName, force):
            return SUCCESS


    def volumeDelete(self, volumeName, options=None):
        if gcli.volumeDelete(volumeName):
            return SUCCESS


    def volumeSet(self, volumeName, key, value, options=None):
        if gcli.volumeSet(volumeName, key, value):
            return SUCCESS


    def volumeBrickAdd(self, volumeName, brickList,
                       replicaCount=0, stripeCount=0, options=None):
        if gcli.volumeAddBrick(volumeName, brickList, replicaCount,
                               stripeCount):
            return SUCCESS


    def volumeRebalanceStart(self, volumeName, rebalanceType="",
                             force=False, options=None):
        if gcli.volumeRebalanceStart(volumeName, rebalanceType, force):
            return SUCCESS


    def volumeRebalanceStop(self, volumeName, force=False, options=None):
        if gcli.volumeRebalanceStop(volumeName, force):
            return SUCCESS


    def volumeRebalanceStatus(self, volumeName, options=None):
        status, message = gcli.volumeRebalanceStatus(volumeName)
        return {'status': doneCode, 'rebalance': status, 'message': message}


    def volumeReplaceBrickStart(self, volumeName, existingBrick, newBrick,
                                options=None):
        if gcli.volumeReplaceBrickStart(volumeName, existingBrick, newBrick):
            return SUCCESS


    def volumeReplaceBrickAbort(self, volumeName, existingBrick, newBrick,
                                options=None):
        if gcli.volumeReplaceBrickAbort(volumeName, existingBrick, newBrick):
            return SUCCESS


    def volumeReplaceBrickPause(self, volumeName, existingBrick, newBrick,
                                options=None):
        if gcli.volumeReplaceBrickPause(volumeName, existingBrick, newBrick):
            return SUCCESS


    def volumeReplaceBrickStatus(self, volumeName, existingBrick, newBrick,
                                 options=None):
        status, message = gcli.volumeReplaceBrickStatus(volumeName,
                                                        existingBrick, newBrick)
        return {'status': doneCode, 'replaceBrick': status, 'message': message}


    def volumeReplaceBrickCommit(self, volumeName, existingBrick, newBrick,
                                 force=False, options=None):
        if gcli.volumeReplaceBrickCommit(volumeName, existingBrick, newBrick,
                                         force):
            return SUCCESS


    def volumeRemoveBrickStart(self, volumeName, brickList,
                               replicaCount=0, options=None):
        if gcli.volumeRemoveBrickStart(volumeName, brickList, replicaCount):
            return SUCCESS


    def volumeRemoveBrickPause(self, volumeName, brickList,
                               replicaCount=0, options=None):
        if gcli.volumeRemoveBrickPause(volumeName, brickList, replicaCount):
            return SUCCESS


    def volumeRemoveBrickAbort(self, volumeName, brickList,
                               replicaCount=0, options=None):
        if gcli.volumeRemoveBrickAbort(volumeName, brickList, replicaCount):
            return SUCCESS


    def volumeRemoveBrickStatus(self, volumeName, brickList,
                                replicaCount=0, options=None):
        message = gcli.volumeRemoveBrickStatus(volumeName,
                                               brickList, replicaCount)
        return {'status': doneCode, 'message' : message}


    def volumeRemoveBrickCommit(self, volumeName, brickList,
                                replicaCount=0, options=None):
        if gcli.volumeRemoveBrickCommit(volumeName, brickList, replicaCount):
            return SUCCESS


    def volumeRemoveBrickForce(self, volumeName, brickList,
                               replicaCount=0, options=None):
        if gcli.volumeRemoveBrickForce(volumeName, brickList, replicaCount):
            return SUCCESS


    def hostAdd(self, hostName, options=None):
        if gcli.peerProbe(hostName):
            return SUCCESS


    def hostRemove(self, hostName, options=None):
        if gcli.peerDetach(hostName):
            return SUCCESS


    def hostsList(self, options=None):
        """
        Returns:
            {'status': {'code': CODE, 'message': MESSAGE},
             'hosts' : {HOSTNAME: {'uuid': UUID, 'hostName': HOSTNAME}, ...}}
        """
        return {'status': doneCode, 'hosts' : gcli.peerStatus()}


    def disksList(options=None):
        """
        Returns:
            {'status': {'code': CODE, 'message': MESSAGE},
             'disks' : {DEVICENAME: {'fsType': FSTYPE,
                                     'major': MAJOR,
                                     'minor': MINOR,
                                     'model': MODEL,
                                     'vendor': VENDOR,
                                     'mountPoint': MOUNTPOINT,
                                     'partitions': [PART1, PART2, ...],
          (optional, partition only) 'parent': DEVICE,
  (optional, if part of lvm/md only) 'container': DEVICE,
             (optional, lvm/md only) 'members': [DEVICE1, DEVICE2, ...],
                                     'size': SIZE,
                                     'spaceInUse': SIZE,
                                     'status': STATUS,
                                     'name': DEVICENAME,
                                     'type': TYPE,
                                     'uuid': UUID}, ...}}
        """
        try:
            return {'status': doneCode,
                    'disks': gutils.getDisksList(gutils.getCdromDevices())}
        except:
            raise ge.GlusterDisksListFailedException()
