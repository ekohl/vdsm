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

########################################################
##
##  Set of user defined gluster exceptions.
##
########################################################

########################################################
##
## IMPORTANT NOTE: USE CODES BETWEEN 4100 AND 4800
##
########################################################

class GlusterException(Exception):
    code = 4100
    message = "Gluster Exception"
    rc = 0
    out = []
    err = []
    def __init__(self, rc, out, err):
        self.rc = rc if rc else 0
        self.out = out if out else []
        self.err = err if err else []
    def __str__(self):
        return "%s\n---\nError:\n%s\n---\n%s\n---\nReturn Code:\n%s" % \
            (self.message, "\n".join(self.out), "\n".join(self.err), self.rc)
    def response(self):
        return { 'status': {'code': self.code, 'message': str(self),
                            'rc': self.rc, 'out': self.out, 'err': self.err} }

# General
class GlusterGeneralException(GlusterException):
    code = 4101
    message = "Gluster General Exception"

class GlusterPermissionDeniedException(GlusterGeneralException):
    code = 4102
    message = "Permission denied"

class GlusterSyntaxErrorException(GlusterGeneralException):
    code = 4103
    message = "Syntax error"

class GlusterMissingArgumentException(GlusterGeneralException):
    code = 4104
    message = "Missing argument"
    def __init__(self, *args):
        GlusterGeneralException.__init__(self, 0, [], [])
        self.message = 'Missing argument: %s' % args

class GlusterDisksListFailedException(GlusterGeneralException):
    code = 4105
    message = "disks list failed"
    def __init__(self):
        GlusterGeneralException.__init__(self, 0, [], [])

# Volume
class GlusterVolumeException(GlusterException):
    code = 4111
    message = "Gluster Volume Exception"

class GlusterVolumeNameErrorException(GlusterVolumeException):
    code = 4112
    message = "Volume name error"

class GlusterBrickNameErrorException(GlusterVolumeException):
    code = 4113
    message = "Brick name error"

class GlusterVolumeAlreadyExistException(GlusterVolumeException):
    code = 4114
    message = "Volume already exist"

class GlusterBrickCreationFailedException(GlusterVolumeException):
    code = 4115
    message = "Brick creation failed"

class GlusterInvalidTransportException(GlusterVolumeException):
    code = 4116
    message = "Invalid transport"

class GlusterPeerNotFriendException(GlusterVolumeException):
    code = 4117
    message = "Peer not found"

class GlusterInvalidStripeCountException(GlusterVolumeException):
    code = 4118
    message = "Invalid stripe count"

class GlusterInvalidReplicaCountException(GlusterVolumeException):
    code = 4119
    message = "Invalid replica count"

class GlusterInsufficientBrickException(GlusterVolumeException):
    code = 4120
    message = "Insufficient brick"

class GlusterBrickInUseException(GlusterVolumeException):
    code = 4121
    message = "Brick already in use"

class GlusterVolumeCreateFailedException(GlusterVolumeException):
    code = 4122
    message = "Volume create failed"

## TODO: when server down, what is the error for volume creation with it

class GlusterVolumeNotFoundException(GlusterVolumeException):
    code = 4123
    message = "Volume not found"

class GlusterVolumeAlreadyStartedException(GlusterVolumeException):
    code = 4124
    message = "Volume already started"

class GlusterVolumeStartFailedException(GlusterVolumeException):
    code = 4125
    message = "Volume start failed"

class GlusterVolumeAlreadyStoppedException(GlusterVolumeException):
    code = 4126
    message = "Volume already stopped"

class GlusterVolumeStopFailedException(GlusterVolumeException):
    code = 4127
    message = "Volume stop failed"

class GlusterVolumeBrickAddFailedException(GlusterVolumeException):
    code = 4128
    message = "Volume add brick failed"

class GlusterVolumeInvalidOptionException(GlusterVolumeException):
    code = 4129
    message = "invalid volume option"

class GlusterVolumeInvalidOptionValueException(GlusterVolumeException):
    code = 4130
    message = "invalid value of volume option"

class GlusterVolumeSetFailedException(GlusterVolumeException):
    code = 4131
    message = "Volume set failed"

class GlusterBrickNotFoundException(GlusterVolumeException):
    code = 4132
    message = "brick not found"

class GlusterVolumeRebalanceUnknownTypeException(GlusterVolumeException):
    code = 4133
    message = "Unknown rebalance type"

class GlusterVolumeRebalanceAlreadyStartedException(GlusterVolumeException):
    code = 4134
    message = "Volume rebalance already started"

class GlusterVolumeRebalanceStartFailedException(GlusterVolumeException):
    code = 4135
    message = "Volume rebalance start failed"

class GlusterVolumeRebalanceAlreadyStoppedException(GlusterVolumeException):
    code = 4136
    message = "Volume rebalance already stopped"

class GlusterVolumeRebalanceStopFailedException(GlusterVolumeException):
    code = 4137
    message = "Volume rebalance stop failed"

class GlusterVolumeRebalanceStatusFailedException(GlusterVolumeException):
    code = 4138
    message = "Volume rebalance status failed"

class GlusterVolumeDeleteFailedException(GlusterVolumeException):
    code = 4139
    message = "Volume delete failed"

class GlusterVolumeBrickReplaceAlreadyStartedException(GlusterVolumeException):
    code = 4141
    message = "Volume replace brick failed"

class GlusterVolumeBrickReplaceStartFailedException(GlusterVolumeException):
    code = 4142
    message = "Volume replace brick start failed"

class GlusterVolumeBrickReplaceNotStartedException(GlusterVolumeException):
    code = 4143
    message = "Volume replace brick not started"

class GlusterVolumeBrickReplaceAbortFailedException(GlusterVolumeException):
    code = 4144
    message = "Volume replace brick abort failed"

class GlusterVolumeBrickReplacePauseFailedException(GlusterVolumeException):
    code = 4145
    message = "Volume replace brick pause failed"

class GlusterVolumeBrickReplaceStatusFailedException(GlusterVolumeException):
    code = 4146
    message = "Volume replace brick status failed"

class GlusterVolumeBrickReplaceInProgressException(GlusterVolumeException):
    code = 4147
    message = "Volume replace brick in progress"

class GlusterVolumeBrickReplaceCommitFailedException(GlusterVolumeException):
    code = 4148
    message = "Volume replace brick commit failed"

class GlusterVolumesListFailedException(GlusterVolumeException):
    code = 4149
    message = "failed to get gluster volume list"

class GlusterVolumeRemoveBrickStartFailedException(GlusterVolumeException):
    code = 4140
    message = "Volume remove brick start failed"

class GlusterVolumeRemoveBrickPauseFailedException(GlusterVolumeException):
    code = 4150
    message = "Volume remove brick pause failed"

class GlusterVolumeRemoveBrickAbortFailedException(GlusterVolumeException):
    code = 4151
    message = "Volume remove brick abort failed"

class GlusterVolumeRemoveBrickStatusFailedException(GlusterVolumeException):
    code = 4152
    message = "Volume remove brick status failed"

class GlusterVolumeRemoveBrickCommitFailedException(GlusterVolumeException):
    code = 4153
    message = "Volume remove brick commit failed"

# Host
class GlusterHostException(GlusterException):
    code = 4400
    message = "Gluster host exception"

class GlusterHostInvalidNameException(GlusterHostException):
    code = 4401
    message = "Invalid host name"

class GlusterHostAlreadyAddedException(GlusterHostException):
    code = 4402
    message = "Host already added"

class GlusterHostNotFoundException(GlusterHostException):
    code = 4403
    message = "Host not found"

class GlusterHostAddFailedException(GlusterHostException):
    code = 4404
    message = "Add host failed"

class GlusterHostInUseException(GlusterHostException):
    code = 4405
    message = "Host in use"

class GlusterHostRemoveFailedException(GlusterHostException):
    code = 4406
    message = "Remove host failed"

class GlusterHostListFailedException(GlusterHostException):
    code = 4407
    message = "get gluster host list failed"


if __name__ == "__main__":
    import types
    codes = {}
    for name, obj in globals().items():
        if not isinstance(obj, types.TypeType):
            continue

        if not issubclass(obj, GlusterException):
            continue

        if obj.code in codes:
            raise NameError, "Collision found: code %s is used by %s and %s" \
                             % (obj.code, name, codes[obj.code])
        if obj.code >= 5000:
            raise NameError, "Collision with RHEVM found: %s code %s: " \
                             "between 5000 and 6000" % (name, obj.code)

        codes[obj.code] = name
