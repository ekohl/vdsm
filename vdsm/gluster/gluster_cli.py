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

import re

import supervdsm as svdsm
import gluster_utils as gutils
import gluster_exception as ge

_GLUSTER_CMD = ["--mode=script"]
_GLUSTER_VOL_CMD = _GLUSTER_CMD + ["volume"]
_GLUSTER_PEER_CMD = _GLUSTER_CMD + ["peer"]

def _execGluster(cmd):
    return svdsm.getProxy().execGluster(cmd)


def _parseVolumeInfo(out):
    if not out[0].strip():
        out = out[1:]
    if out[-1].strip():
        out += [""]

    volumeInfoDict = {}
    volumeInfo = {}
    volumeName = None
    brickList = []
    volumeOptions = {}
    for line in out:
        line = line.strip()
        if line.upper() == "NO VOLUMES PRESENT":
            continue
        if not line:
            if volumeName and volumeInfo:
                volumeInfo["bricks"] = brickList
                volumeInfo["options"] = volumeOptions
                volumeInfoDict[volumeName] = volumeInfo
                volumeInfo = {}
                volumeName = None
                brickList = []
                volumeOptions = {}
            continue

        tokens = line.split(":", 1)
        if tokens[0].strip().upper() == "BRICKS":
            continue
        elif tokens[0].strip().upper() == "OPTIONS RECONFIGURED":
            continue
        elif tokens[0].strip().upper() == "VOLUME NAME":
            volumeName = tokens[1].strip()
            volumeInfo["volumeName"] = volumeName
        elif tokens[0].strip().upper() == "VOLUME ID":
            volumeInfo["uuid"] = tokens[1].strip().upper()
        elif tokens[0].strip().upper() == "TYPE":
            volumeInfo["volumeType"] = tokens[1].strip().upper()
        elif tokens[0].strip().upper() == "STATUS":
            volumeInfo["volumeStatus"] = tokens[1].strip().upper()
        elif tokens[0].strip().upper() == "TRANSPORT-TYPE":
            volumeInfo["transportType"] = tokens[1].strip().upper().split(',')
        elif tokens[0].strip().upper().startswith("BRICK"):
            brickList.append(tokens[1].strip())
        elif tokens[0].strip().upper() == "NUMBER OF BRICKS":
            volumeInfo["brickCount"] = tokens[1].strip()
        else:
            volumeOptions[tokens[0].strip()] = tokens[1].strip()

    regex = re.compile('(\d+) x (\d+) = (\d+)')
    for volumeName, volumeInfo in volumeInfoDict.iteritems():
        if volumeInfo["volumeType"] == "REPLICATE":
            volumeInfo["replicaCount"] = volumeInfo["brickCount"]
        elif volumeInfo["volumeType"] == "STRIPE":
            volumeInfo["stripeCount"] = volumeInfo["brickCount"]
        elif volumeInfo["volumeType"] == "DISTRIBUTED-REPLICATE":
            m = regex.match(volumeInfo["brickCount"])
            if m:
                volumeInfo["replicaCount"] = m.groups()[1]
            else:
                volumeInfo["replicaCount"] = ""

        elif volumeInfo["volumeType"] == "DISTRIBUTED-STRIPE":
            m = regex.match(volumeInfo["brickCount"])
            if m:
                volumeInfo["stripeCount"] = m.groups()[1]
            else:
                volumeInfo["stripeCount"] = ""
    return volumeInfoDict


def volumeInfo():
    """
    Returns:
        {VOLUMENAME: {'brickCount': BRICKCOUNT,
                      'bricks': [BRICK1, BRICK2, ...],
                      'options': {ATTRIBUTE: VALUE, ...},
                      'transportType': [ETHERNET,INFINIBAND, ...],
                      'uuid': UUID,
                      'volumeName': NAME,
                      'volumeStatus': STATUS,
                      'volumeType': TYPE}, ...}
    """
    rc, out, err = _execGluster(_GLUSTER_VOL_CMD + ["info"])
    if rc:
        raise ge.GlusterVolumesListFailedException(rc, out, err)
    else:
        return _parseVolumeInfo(out)


def volumeCreate(volumeName, brickList, replicaCount=0, stripeCount=0,
                 transport=''):
    command = _GLUSTER_VOL_CMD + ["create", volumeName]
    if stripeCount:
        command += ["stripe", "%s" % stripeCount]
    if replicaCount:
        command += ["replica", "%s" % replicaCount]
    if transport:
        command += ["transport", transport]
    command += brickList

    rc, out, err = _execGluster(command)
    if rc:
        raise ge.GlusterVolumeCreateFailedException(rc, out, err)
    else:
        return True


def volumeStart(volumeName, force=False):
    if force:
        rc, out, err = _execGluster(_GLUSTER_VOL_CMD + ["start", volumeName,
                                                        "force"])
    else:
        rc, out, err = _execGluster(_GLUSTER_VOL_CMD + ["start", volumeName])
    if rc:
        raise ge.GlusterVolumeStartFailedException(rc, out, err)
    else:
        return True


def volumeStop(volumeName, force=False):
    if force:
        rc, out, err = _execGluster(_GLUSTER_VOL_CMD + ["stop", volumeName,
                                                        "force"])
    else:
        rc, out, err = _execGluster(_GLUSTER_VOL_CMD + ["stop", volumeName])
    if rc:
        raise ge.GlusterVolumeStopFailedException(rc, out, err)
    else:
        return True


def volumeDelete(volumeName):
    rc, out, err = _execGluster(_GLUSTER_VOL_CMD + ["delete", volumeName])
    if rc:
        raise ge.GlusterVolumeDeleteFailedException(rc, out, err)
    else:
        return True


def volumeSet(volumeName, key, value):
    rc, out, err = _execGluster(_GLUSTER_VOL_CMD + ["set", volumeName,
                                                    key, value])
    if rc:
        raise ge.GlusterVolumeSetFailedException(rc, out, err)
    else:
        return True


def volumeAddBrick(volumeName, brickList,
                   replicaCount=0, stripeCount=0):
    command = _GLUSTER_VOL_CMD + ["add-brick", volumeName]
    if stripeCount:
        command += ["stripe", "%s" % stripeCount]
    if replicaCount:
        command += ["replica", "%s" % replicaCount]
    command += brickList

    rc, out, err = _execGluster(command)
    if rc:
        raise ge.GlusterVolumeBrickAddFailedException(rc, out, err)
    else:
        return True


def volumeRebalanceStart(volumeName, rebalanceType="", force=False):
    command = _GLUSTER_VOL_CMD + ["rebalance", volumeName]
    if rebalanceType:
        command += [rebalanceType]
    command += ["start"]
    if force:
        command += ["force"]
    rc, out, err = _execGluster(command)
    if rc:
        raise ge.GlusterVolumeRebalanceStartFailedException(rc, out, err)
    else:
        return True


def volumeRebalanceStop(volumeName, force=False):
    if force:
        rc, out, err = _execGluster(_GLUSTER_VOL_CMD + ["rebalance", volumeName,
                                                        "stop", "force"])
    else:
        rc, out, err = _execGluster(_GLUSTER_VOL_CMD
                                    + ["rebalance", volumeName, "stop"])
    if rc:
        raise ge.GlusterVolumeRebalanceStopFailedException(rc, out, err)
    else:
        return True


def volumeRebalanceStatus(volumeName):
    rc, out, err = _execGluster(_GLUSTER_VOL_CMD + ["rebalance", volumeName,
                                                    "status"])
    if rc:
        raise ge.GlusterVolumeRebalanceStatusFailedException(rc, out, err)
    if 'in progress' in out[0]:
        return 'RUNNING', "\n".join(out)
    elif 'complete' in out[0]:
        return 'COMPLETED', "\n".join(out)
    else:
        return 'UNKNOWN', "\n".join(out)


def volumeReplaceBrickStart(volumeName, existingBrick, newBrick):
    rc, out, err = _execGluster(_GLUSTER_VOL_CMD + ["replace-brick",
                                                    volumeName, existingBrick,
                                                    newBrick, "start"])
    if rc:
        raise ge.GlusterVolumeReplaceBrickStartFailedException(rc, out, err)
    else:
        return True


def volumeReplaceBrickAbort(volumeName, existingBrick, newBrick):
    rc, out, err = _execGluster(_GLUSTER_VOL_CMD + ["replace-brick",
                                                    volumeName, existingBrick,
                                                    newBrick, "abort"])
    if rc:
        raise ge.GlusterVolumeReplaceBrickAbortFailedException(rc, out, err)
    else:
        return True


def volumeReplaceBrickPause(volumeName, existingBrick, newBrick):
    rc, out, err = _execGluster(_GLUSTER_VOL_CMD + ["replace-brick",
                                                    volumeName, existingBrick,
                                                    newBrick, "pause"])
    if rc:
        raise ge.GlusterVolumeReplaceBrickPauseFailedException(rc, out, err)
    else:
        return True


def volumeReplaceBrickStatus(volumeName, existingBrick, newBrick):
    rc, out, err = _execGluster(_GLUSTER_VOL_CMD + ["replace-brick",
                                                    volumeName, existingBrick,
                                                    newBrick, "status"])
    if rc:
        raise ge.GlusterVolumeReplaceBrickStatusFailedException(rc, out,
                                                                err)
    message = "\n".join(out)
    if 'PAUSED' in out[0].strip().upper():
        return 'PAUSED', message
    elif out[0].strip().upper().endswith('MIGRATION COMPLETE'):
        return 'COMPLETED', message
    elif out[0].strip().upper().startswith('NUMBER OF FILES MIGRATED'):
        return 'RUNNING', message
    elif out[0].strip().upper().endswith("UNKNOWN"):
        return 'UNKNOWN', message
    else:
        return 'NA', message


def volumeReplaceBrickCommit(volumeName, existingBrick, newBrick,
                             force=False):
    if force:
        rc, out, err = _execGluster(_GLUSTER_VOL_CMD
                                    + ["replace-brick",
                                       volumeName, existingBrick,
                                       newBrick, "commit", "force"])
    else:
        rc, out, err = _execGluster(_GLUSTER_VOL_CMD
                                    + ["replace-brick",
                                       volumeName, existingBrick,
                                       newBrick, "commit"])
    if rc:
        raise ge.GlusterVolumeReplaceBrickCommitFailedException(rc, out,
                                                                err)
    else:
        return True


def volumeRemoveBrickStart(volumeName, brickList, replicaCount=0):
    command = _GLUSTER_VOL_CMD + ["remove-brick", volumeName]
    if replicaCount:
        command += ["replica", "%s" % replicaCount]
    command += brickList + ["start"]

    rc, out, err = _execGluster(command)
    if rc:
        raise ge.GlusterVolumeRemoveBrickStartFailedException(rc, out, err)
    else:
        return True


def volumeRemoveBrickPause(volumeName, brickList, replicaCount=0):
    command = _GLUSTER_VOL_CMD + ["remove-brick", volumeName]
    if replicaCount:
        command += ["replica", "%s" % replicaCount]
    command += brickList + ["pause"]
    rc, out, err = _execGluster(command)

    if rc:
        raise ge.GlusterVolumeRemoveBrickPauseFailedException(rc, out, err)
    else:
        return True


def volumeRemoveBrickAbort(volumeName, brickList, replicaCount=0):
    command = _GLUSTER_VOL_CMD + ["remove-brick", volumeName]
    if replicaCount:
        command += ["replica", "%s" % replicaCount]
    command += brickList + ["abort"]
    rc, out, err = _execGluster(command)

    if rc:
        raise ge.GlusterVolumeRemoveBrickAbortFailedException(rc, out, err)
    else:
        return True


def volumeRemoveBrickStatus(volumeName, brickList, replicaCount=0):
    command = _GLUSTER_VOL_CMD + ["remove-brick", volumeName]
    if replicaCount:
        command += ["replica", "%s" % replicaCount]
    command += brickList + ["status"]
    rc, out, err = _execGluster(command)

    if rc:
        raise ge.GlusterVolumeRemoveBrickStatusFailedException(rc, out, err)
    else:
        return "\n".join(out)


def volumeRemoveBrickCommit(volumeName, brickList, replicaCount=0):
    command = _GLUSTER_VOL_CMD + ["remove-brick", volumeName]
    if replicaCount:
        command += ["replica", "%s" % replicaCount]
    command += brickList + ["commit"]
    rc, out, err = _execGluster(command)

    if rc:
        raise ge.GlusterVolumeRemoveBrickCommitFailedException(rc, out, err)
    else:
        return True


def volumeRemoveBrickForce(volumeName, brickList, replicaCount=0):
    command = _GLUSTER_VOL_CMD + ["remove-brick", volumeName]
    if replicaCount:
        command += ["replica", "%s" % replicaCount]
    command += brickList + ["force"]
    rc, out, err = _execGluster(command)

    if rc:
        raise ge.GlusterVolumeRemoveBrickCommitFailedException(rc, out, err)
    else:
        return True


def peerProbe(hostName):
    rc, out, err = _execGluster(_GLUSTER_PEER_CMD + ["probe", hostName])
    if rc:
        raise ge.GlusterHostAddFailedException(rc, out, err)
    else:
        return True


def peerDetach(hostName):
    rc, out, err = _execGluster(_GLUSTER_PEER_CMD + ["detach", hostName])
    if rc:
        raise ge.GlusterHostRemoveFailedException(rc, out, err)
    else:
        return True


def _parsePeerStatus(out):
    hostInfoDict = {}
    hostName = gutils.getGlusterHostname()
    hostInfo = {"hostName" : hostName, "uuid" : gutils.getGlusterUuid()}
    for line in out:
        line = line.strip()
        if line.upper() == "NO PEERS PRESENT":
            break
        if not line:
            if hostName and hostInfo:
                hostInfoDict[hostName] = hostInfo
                hostInfo = {}
                hostName = None
        tokens = line.split(":", 1)
        if tokens[0].strip().upper() == "HOSTNAME":
            hostName = tokens[1].strip()
            hostInfo["hostName"] = hostName
        elif tokens[0].strip().upper() == "UUID":
            hostInfo["uuid"] = tokens[1].strip().upper()
    if hostName and hostInfo:
        hostInfoDict[hostName] = hostInfo
    return hostInfoDict


def peerStatus():
    """
    Returns:
        {HOSTNAME : {'uuid': UUID, 'hostName': HOSTNAME}, ...}
    """
    rc, out, err = _execGluster(_GLUSTER_PEER_CMD + ["status"])
    if rc:
        raise ge.GlusterHostListFailedException(rc, out, err)
    else:
        return _parsePeerStatus(out)
