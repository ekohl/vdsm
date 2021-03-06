#
# Copyright 2010-2011 Red Hat, Inc.
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


"""
Generic LVM interface wrapper

Incapsulates the actual LVM mechanics.
"""
import errno

import os
import pwd
import grp
import logging
from collections import namedtuple
import pprint as pp
import threading
from itertools import chain
from subprocess import list2cmdline

from vdsm import constants
import misc
import multipath
import storage_exception as se
from vdsm.config import config
import devicemapper

log = logging.getLogger("Storage.LVM")

LVM_DEFAULT_TTL = 100

PV_FIELDS = "uuid,name,size,vg_name,vg_uuid,pe_start,pe_count,pe_alloc_count,mda_count,dev_size"
VG_FIELDS = "uuid,name,attr,size,free,extent_size,extent_count,free_count,tags,vg_mda_size,vg_mda_free"
LV_FIELDS = "uuid,name,vg_name,attr,size,seg_start_pe,devices,tags"

VG_ATTR_BITS = ("permission", "resizeable", "exported",
                  "partial", "allocation", "clustered")
LV_ATTR_BITS = ("voltype, permission, allocations, fixedminor, state, devopen")

PV = namedtuple("PV", PV_FIELDS + ",guid")
VG = namedtuple("VG", VG_FIELDS + ",writeable,partial")
LV = namedtuple("LV", LV_FIELDS + ",writeable,opened,active")
Stub = namedtuple("Stub", "name, stale")

class Unreadable(Stub):
    __slots__ = ()
    def __getattr__(self, attrName):
        log.warning("%s can't be reloaded, please check your storage connections.", self.name)
        raise AttributeError("Failed reload: %s" % self.name)

#VG states
VG_OK = "OK"
VG_PARTIAL = "PARTIAL"
VG_UNKNOWN = "UNKNOWN"

SEPARATOR = "|"
LVM_NOBACKUP = ("--autobackup", "n")
LVM_FLAGS = ("--noheadings", "--units", "b", "--nosuffix", "--separator", SEPARATOR)

PV_PREFIX = "/dev/mapper"

#operations lock
LVM_OP_INVALIDATE = "lvm invalidate operation"
LVM_OP_RELOAD = "lvm reload operation"

PVS_CMD = ("pvs",) + LVM_FLAGS + ("-o", PV_FIELDS)
VGS_CMD = ("vgs",) + LVM_FLAGS + ("-o", VG_FIELDS)
LVS_CMD = ("lvs",) + LVM_FLAGS + ("-o", LV_FIELDS)

# FIXME we must use different METADATA_USER ownership for qemu-unreadable metadata
# volumes
USER_GROUP = constants.DISKIMAGE_USER + ":" + constants.DISKIMAGE_GROUP

LVMCONF_TEMPLATE = """
devices {
preferred_names = ["^/dev/mapper/"]
ignore_suspended_devices=1
write_cache_state=0
disable_after_error_count=3
%s
}

global {
 locking_type=1
 prioritise_write_locks=1
 wait_for_locks=1
}

backup {
 retain_min = 50
 retain_days = 0
}
"""

VAR_RUN_VDSM = constants.P_VDSM_RUN
VDSM_LVM_SYSTEM_DIR = os.path.join(VAR_RUN_VDSM, "lvm")
VDSM_LVM_CONF = os.path.join(VDSM_LVM_SYSTEM_DIR, "lvm.conf")

USER_DEV_LIST = filter(None, config.get("irs", "lvm_dev_whitelist").split(","))

def _buildFilter(devList):
    devList = list(devList)
    devList.sort()
    filt = '|'.join(dev.strip() for dev in devList if dev.strip())
    if len(filt) > 0:
        filt = '"a%' + filt + '%", '

    filt = 'filter = [ ' + filt + '"r%.*%" ]'
    return filt

def _buildConfig(devList):
    flt = _buildFilter(chain(devList, USER_DEV_LIST))
    conf = LVMCONF_TEMPLATE % flt
    return conf.replace("\n", " ")

def _updateLvmConf(conf):
    # Make a convenience copy for the debugging purposes
    try:
        if not os.path.isdir(VDSM_LVM_SYSTEM_DIR):
            os.mkdir(VDSM_LVM_SYSTEM_DIR)

        with open(VDSM_LVM_CONF, "w") as lvmconf:
            lvmconf.write(conf)

    except IOError, e:
        # We are not interested in exceptions here, note it and
        log.warning("Cannot create %s file %s", VDSM_LVM_CONF, str(e))

def _setupLVMEnv():
    lvmenvfname = os.path.join(VAR_RUN_VDSM, "lvm.env")
    with file(lvmenvfname, "w") as lvmenv:
        lvmenv.write("export LVM_SYSTEM_DIR=%s\n" % VDSM_LVM_SYSTEM_DIR)

def _setupLVM():
    try:
        _setupLVMEnv()
    except IOError, e:
        log.warning("Cannot create env file %s", e)

#
# Make sure that "args" is suitable for consumption in interfaces
# that expect an iterabale argument. The string is treated a single
# argument an converted into list, containing that string.
# Strings have not __iter__ attribute.
#
def _normalizeargs(args = None):
    if args is None:
        args = []
    elif not hasattr(args, "__iter__"):
        args = [args]

    return args

def _tags2Tuple(sTags):
    """
    Tags comma separated string as a list.

    Return an empty tuple for sTags == ""
    """
    return tuple(sTags.split(",")) if sTags else tuple()

def _attr2NamedTuple(sAttr, attrMask, label):
    """
    Converts a attr string into a named tuple.

    Fields are named as in attrMask.
    """
    Attrs = namedtuple(label, attrMask)
    values = tuple(sAttr) # tuple("wz--n-") = ('w', 'z', '-', '-', 'n', '-')
    attrs = Attrs(*values)
    return attrs


def makePV(*args):
    guid = os.path.basename(args[1])
    args += (guid,)
    return PV(*args)


def makeVG(*args):
    args = list(args)
    #Convert tag string into tuple.
    tags = _tags2Tuple(args[VG._fields.index("tags")])
    args[VG._fields.index("tags")] = tags
    #Convert attr string into named tuple fields.
    attrs = _attr2NamedTuple(args[VG._fields.index("attr")], VG_ATTR_BITS, "VG_ATTR")
    args[VG._fields.index("attr")] = attrs
    #Add properties. Should be ordered as VG_PROPERTIES.
    args.append(attrs.permission == "w") #Writable
    args.append(VG_OK if attrs.partial == "-" else VG_PARTIAL) #Partial
    return VG(*args)


def makeLV(*args):
    args = list(args)
    #Convert tag string into tuple.
    tags = _tags2Tuple(args[LV._fields.index("tags")])
    args[LV._fields.index("tags")] = tags
    #Convert attr string into named tuple fields.
    attrs = _attr2NamedTuple(args[LV._fields.index("attr")], LV_ATTR_BITS, "LV_ATTR")
    args[LV._fields.index("attr")] = attrs
    #Add properties. Should be ordered as VG_PROPERTIES.
    args.append(attrs.permission == "w") #writable
    args.append(attrs.devopen == "o")    #opened
    args.append(attrs.state == "a")      #active
    return LV(*args)


class LVMCache(object):
    """
    Keep all the LVM information.
    """

    def _getCachedExtraCfg(self):
        if not self._filterStale:
            return self._extraCfg

        with self._filterLock:
            if not self._filterStale:
                return self._extraCfg

            self._extraCfg = _buildConfig(multipath.getMPDevNamesIter())
            _updateLvmConf(self._extraCfg)
            self._filterStale = False

            return self._extraCfg

    def _addExtraCfg(self, cmd, devList=None):
        newcmd = [constants.EXT_LVM, cmd[0]]
        if devList is not None:
            devList = list(set(devList))
            devList.sort()
            conf = _buildConfig(devList)
        else:
            conf = self._getCachedExtraCfg()

        newcmd += ["--config", conf]

        if len(cmd) > 1:
            newcmd += cmd[1:]

        return newcmd

    def invalidateFilter(self):
        self._filterStale = True

    def invalidateCache(self):
        self.invalidateFilter()
        self.flush()

    def __init__(self):
        self._filterStale = True
        self._extraCfg = None
        _setupLVM()
        self._filterLock = threading.Lock()
        self._oplock = misc.OperationMutex()
        self._stalepv = True
        self._stalevg = True
        self._stalelv = True
        self._pvs = {}
        self._vgs = {}
        self._lvs = {}

    def cmd(self, cmd):
        finalCmd = self._addExtraCfg(cmd)
        rc, out, err = misc.execCmd(finalCmd, sudo=True)
        if rc != 0:
            #Filter might be stale
            self.invalidateFilter()
            newCmd = self._addExtraCfg(cmd)
            # Before blindly trying again make sure
            # that the commands are not identical, because
            # the devlist is sorted there is no fear
            # of two identical filters looking differently
            if newCmd != finalCmd:
                return misc.execCmd(newCmd, sudo=True)

        return rc, out, err


    def __str__(self):
        return ("PVS:\n%s\n\nVGS:\n%s\n\nLVS:\n%s" %
            (pp.pformat(self._pvs),
            pp.pformat(self._vgs),
            pp.pformat(self._lvs)))


    def bootstrap(self):
        self._reloadpvs()
        self._reloadvgs()
        self._reloadAllLvs()


    def _reloadpvs(self, pvName=None):
        cmd = list(PVS_CMD)
        pvNames = _normalizeargs(pvName)
        cmd.extend(pvNames)
        with self._oplock.acquireContext(LVM_OP_RELOAD):
            rc, out, err = self.cmd(cmd)
            if rc != 0:
                log.warning("lvm pvs failed: %s %s %s", str(rc), str(out), str(err))
                pvNames = pvNames if pvNames else self._pvs.keys()
                for p in pvNames:
                    if isinstance(self._pvs.get(p), Stub):
                        self._pvs[p] = Unreadable(self._pvs[p].name, True)
                return dict(self._pvs)

            updatedPVs = {}
            for line in out:
                fields = [field.strip() for field in line.split(SEPARATOR)]
                pv = makePV(*fields)
                self._pvs[pv.name] = pv
                updatedPVs[pv.name] = pv
            # If we updated all the PVs drop stale flag
            if not pvName:
                self._stalepv = False
                #Remove stalePVs
                stalePVs = [staleName for staleName in self._pvs.keys() if staleName not in updatedPVs.iterkeys()]
                for staleName in stalePVs:
                    log.warning("Removing stale PV: %s", staleName)
                    self._pvs.pop((staleName), None)

        return updatedPVs


    def _reloadvgs(self, vgName=None):
        cmd = list(VGS_CMD)
        vgNames = _normalizeargs(vgName)
        cmd.extend(vgNames)

        with self._oplock.acquireContext(LVM_OP_RELOAD):
            rc, out, err = self.cmd(cmd)

            if rc != 0:
                log.warning("lvm vgs failed: %s %s %s", str(rc), str(out), str(err))
                vgNames = vgNames if vgNames else self._vgs.keys()
                for v in vgNames:
                    if isinstance(self._vgs.get(v), Stub):
                        self._vgs[v] = Unreadable(self._vgs[v].name, True)

            if not len(out):
                return dict(self._vgs)

            updatedVGs = {}
            for line in out:
                fields = [field.strip() for field in line.split(SEPARATOR)]
                vg = makeVG(*fields)
                self._vgs[vg.name] = vg
                updatedVGs[vg.name] = vg
            # If we updated all the VGs drop stale flag
            if not vgName:
                self._stalevg = False
                #Remove stale VGs
                staleVGs = [staleName for staleName in self._vgs.keys() if staleName not in updatedVGs.iterkeys()]
                for staleName in staleVGs:
                    removeVgMapping(staleName)
                    log.warning("Removing stale VG: %s", staleName)
                    self._vgs.pop((staleName), None)

        return updatedVGs



    def _reloadlvs(self, vgName, lvNames=None):
        lvNames = _normalizeargs(lvNames)
        cmd = list(LVS_CMD)
        if lvNames:
            cmd.extend(["%s/%s" % (vgName, lvName) for lvName in lvNames])
        else:
            cmd.append(vgName)

        with self._oplock.acquireContext(LVM_OP_RELOAD):
            rc, out, err = self.cmd(cmd)

            if rc != 0:
                log.warning("lvm lvs failed: %s %s %s", str(rc), str(out), str(err))
                lvNames = lvNames if lvNames else self._lvs.keys()
                for l in lvNames:
                    if isinstance(self._lvs.get(l), Stub):
                        self._lvs[l] = Unreadable(self._lvs[l].name, True)
                return dict(self._lvs)

            updatedLVs = {}
            for line in out:
                fields = [field.strip() for field in line.split(SEPARATOR)]
                lv = makeLV(*fields)
                # For LV we are only interested in its first extent
                if lv.seg_start_pe == "0":
                    self._lvs[(lv.vg_name, lv.name)] = lv
                    updatedLVs[(lv.vg_name, lv.name)] = lv

            # Determine if there are stale LVs
            if lvNames:
                staleLVs = (lvName for lvName in lvNames if (vgName, lvName) not in updatedLVs.iterkeys())
            else:
                #All the LVs in the VG
                staleLVs = (lvName for v, lvName in self._lvs.keys() if (v == vgName) and ((vgName, lvName) not in updatedLVs.iterkeys()))

            for lvName in staleLVs:
                log.warning("Removing stale lv: %s/%s", vgName, lvName)
                self._lvs.pop((vgName, lvName), None)

        return updatedLVs



    def _reloadAllLvs(self):
        """
        Used only during bootstrap.
        """
        cmd = list(LVS_CMD)
        rc, out, err = self.cmd(cmd)
        if rc == 0:
            updatedLVs = set()
            for line in out:
                fields = [field.strip() for field in line.split(SEPARATOR)]
                lv = makeLV(*fields)
                # For LV we are only interested in its first extent
                if lv.seg_start_pe == "0":
                    self._lvs[(lv.vg_name, lv.name)] = lv
                    updatedLVs.add((lv.vg_name, lv.name))

            #Remove stales
            for vgName, lvName in self._lvs.keys():
                if (vgName, lvName) not in updatedLVs:
                    self._lvs.pop((vgName, lvName), None)
                    log.error("Removing stale lv: %s/%s", vgName, lvName)
            self._stalelv = False
        return dict(self._lvs)


    def _invalidatepvs(self, pvNames):
        with self._oplock.acquireContext(LVM_OP_INVALIDATE):
            pvNames = _normalizeargs(pvNames)
            for pvName in pvNames:
                self._pvs[pvName] = Stub(pvName, True)

    def _invalidateAllPvs(self):
        with self._oplock.acquireContext(LVM_OP_INVALIDATE):
            self._stalepv = True
            self._pvs.clear()


    def _invalidatevgs(self, vgNames):
        vgNames = _normalizeargs(vgNames)
        with self._oplock.acquireContext(LVM_OP_INVALIDATE):
            for vgName in vgNames:
                self._vgs[vgName] = Stub(vgName, True)

    def _invalidateAllVgs(self):
        with self._oplock.acquireContext(LVM_OP_INVALIDATE):
            self._stalevg = True
            self._vgs.clear()


    def _invalidatelvs(self, vgName, lvNames=None):
        with self._oplock.acquireContext(LVM_OP_INVALIDATE):
            lvNames = _normalizeargs(lvNames)
            # Invalidate LVs in a specific VG
            if lvNames:
                # Invalidate a specific LVs
                for lvName in lvNames:
                    self._lvs[(vgName, lvName)] = Stub(lvName, True)
            else:
                # Invalidate all the LVs in a given VG
                for lv in self._lvs.values():
                    if not isinstance(lv, Stub):
                        if lv.vg_name == vgName:
                            self._lvs[(vgName, lv.name)] = Stub(lv.name, True)

    def _invalidateAllLvs(self):
        with self._oplock.acquireContext(LVM_OP_INVALIDATE):
            self._stalelv = True
            self._lvs.clear()


    def flush(self):
        self._invalidateAllPvs()
        self._invalidateAllVgs()
        self._invalidateAllLvs()


    def getPv(self, pvName):
        # Get specific PV
        pv = self._pvs.get(pvName)
        if not pv or isinstance(pv, Stub):
            pvs = self._reloadpvs(pvName)
            pv = pvs.get(pvName)
        return pv

    def getAllPvs(self):
        # Get everything we have
        if self._stalepv:
            pvs = self._reloadpvs()
        else:
            pvs = dict(self._pvs)
            stalepvs = [pv.name for pv in pvs.itervalues() if isinstance(pv, Stub)]
            if stalepvs:
                reloaded = self._reloadpvs(stalepvs)
                pvs.update(reloaded)
        return pvs.values()


    def getVg(self, vgName):
        # Get specific VG
        vg = self._vgs.get(vgName)
        if not vg or isinstance(vg, Stub):
            vgs = self._reloadvgs(vgName)
            vg = vgs.get(vgName)
        return vg

    def getVgs(self, vgNames):
        """Reloads all the VGs of the set.

        Can block for suspended devices.
        Fills the cache but not uses it.
        Only returns found VGs.
        """
        return [vg for vgName, vg in self._reloadvgs(vgNames).iteritems() if vgName in vgNames]


    def getAllVgs(self):
        # Get everything we have
        if self._stalevg:
            vgs = self._reloadvgs()
        else:
            vgs = dict(self._vgs)
            stalevgs = [vg.name for vg in vgs.itervalues() if isinstance(vg, Stub)]
            if stalevgs:
                reloaded = self._reloadvgs(stalevgs)
                vgs.update(reloaded)
        return vgs.values()


    def getLv(self, vgName, lvName=None):
        # Checking self._stalelv here is suboptimal, because unnecessary reloads
        # are done.

        # Return vgName/lvName info
        # If both 'vgName' and 'lvName' are None then return everything
        # If only 'lvName' is None then return all the LVs in the given VG
        # If only 'vgName' is None it is weird, so return nothing
        # (we can consider returning all the LVs with a given name)
        if lvName:
            # vgName, lvName
            lv = self._lvs.get((vgName, lvName))
            if not lv or isinstance(lv, Stub):
                # while we here reload all the LVs in the VG
                lvs = self._reloadlvs(vgName)
                lv = lvs.get((vgName, lvName))
                if not lv:
                    log.warning("lv: %s not found in lvs vg: %s response", lvName, vgName)
            res = lv
        else:
            # vgName, None
            # If there any stale LVs reload the whole VG, since it would
            # cost us around same efforts anyhow and these stale LVs can
            # be in the vg.
            # Will be better when the pvs dict will be part of the vg.
            #Fix me: should not be more stubs
            if self._stalelv  or any(isinstance(lv, Stub) for lv in self._lvs.values()):
                lvs = self._reloadlvs(vgName)
            else:
                lvs = dict(self._lvs)
            #lvs = self._reloadlvs()
            lvs = [lv for lv in lvs.values() if not isinstance(lv, Stub) and (lv.vg_name == vgName)]
            res = lvs
        return res

    def getAllLvs(self):
        # None, None
        if self._stalelv or any(isinstance(lv, Stub) for lv in self._lvs.values()):
            lvs = self._reloadAllLvs()
        else:
            lvs = dict(self._lvs)
        return lvs.values()


_lvminfo = LVMCache()

def invalidateCache():
    _lvminfo.invalidateCache()

def _vgmknodes(vg):
    cmd = ["vgmknodes", vg]
    rc, out, err = _lvminfo.cmd(cmd)
    if rc != 0:
        raise se.VolumeGroupActionError("vgmknodes %s failed" % (vg))

def _fqpvname(pv):
    if pv and not pv.startswith(PV_PREFIX):
        pv = os.path.join(PV_PREFIX, pv)
    return pv

def _initpvs(devices, metadataSize):
    devices = _normalizeargs(devices)
    # Size for pvcreate should be with units k|m|g
    metadatasize = str(metadataSize) + 'm'
    cmd = ["pvcreate", "--metadatasize", metadatasize, "--metadatacopies", "2",
           "--metadataignore", "y"]
    cmd.extend(devices)

    #pvcreate on a dev that is already a PV but not in a VG returns rc = 0.
    #The device is created with the new parameters.
    rc, out, err = _lvminfo.cmd(cmd)
    if rc != 0:
        # This could have failed because a VG was removed on another host.
        #Let us check with lvm
        found, notFound = getVGsOfReachablePVs(devices)
        #If returned not found devices or any device is in a VG
        if notFound or any(found.itervalues()):
            raise se.PhysDevInitializationError("found: %s notFound: %s" %
                                                (found, notFound))
        #All devices are free and reachable, calling the ghostbusters!
        for device in devices:
            try:
                devicemapper.removeMappingsHoldingDevice(os.path.basename(device))
            except OSError, e:
                if e.errno == errno.ENODEV:
                    raise se.PhysDevInitializationError("%s: %s" % (device, str(e)))
                else:
                    raise
        #Retry pvcreate
        rc, out, err = _lvminfo.cmd(cmd)
        if rc != 0:
            raise se.PhysDevInitializationError(device)

    _lvminfo._invalidatepvs(devices)

def getLvDmName(vgName, lvName):
    return "%s-%s" % (vgName.replace("-", "--"), lvName)

def getVGsOfReachablePVs(pvNames):
    """
    Return a (found, notFound) tuple.
    found: {pvName: vgName} of reachable PVs.
    notFound: (PvName, ...) for unreachable PVs.
    """
    pvNames = _normalizeargs(pvNames)
    cmd = ["pvs", "-o", "vg_name,pv_name", "--noheading"]
    cmd.extend(pvNames)
    rc, out, err = _lvminfo.cmd(cmd)
    found = {} #{pvName, vgName}
    for line in out:
        try:
            #Safe: volume group name containg spaces is invalid
            vgName, pvName = line.strip().split()
        except ValueError:
            pvName = line.strip()
            found[pvName] = None #Free PV
        else:
            found[pvName] = vgName
    notFound = tuple(pvName for pvName in pvNames if pvName not in found.iterkeys())

    return found, notFound

def removeVgMapping(vgName):
    """
    Removes the mapping of the specified volume group.
    Utilizes the fact that the mapping created by the LVM looks like that
    e45c12b0--f520--498a--82bb--c6cb294b990f-master
    i.e vg name concatenated with volume name (dash is escaped with dash)
    """
    mappingPrefix = getLvDmName(vgName, "")
    mappings = devicemapper.getAllMappedDevices()

    for mapping in mappings:
        if not mapping.startswith(mappingPrefix):
            continue
        try:
            devicemapper.removeMapping(mapping)
        except Exception:
            pass

#Activation of the whole vg is assumed to be used nowhere.
#This is a separate function just in case.
def _setVgAvailability(vgs, available):
    vgs = _normalizeargs(vgs)
    cmd = ["vgchange", "--available", available] + vgs
    rc, out, err = _lvminfo.cmd(cmd)
    for vg in vgs:
        _lvminfo._invalidatelvs(vg)
    if rc != 0:
        #During deactivation, in vg.py (sic):
        # we ignore error here becuase we don't care about this vg anymore
        if available == "n":
            log.info("deactivate vg %s failed: rc %s - %s %s (ignored)" % (vgs, rc, out, err))
        else:
            raise se.VolumeGroupActionError("vgchange on vg(s) %s failed. %d %s %s" % (vgs, rc, out, err))

def changelv(vg, lvs, attrName, attrValue):
    # Note:
    # You may activate an activated LV without error
    # but lvchange returns an error (RC=5) when activating rw if already rw
    lvs = _normalizeargs(lvs)
    # If it fails or not we (may be) change the lv,
    # so we invalidate cache to reload these volumes on first occasion
    lvnames = tuple("%s/%s" % (vg, lv) for lv in lvs)
    cmd = ("lvchange",) + LVM_NOBACKUP + (attrName, attrValue) + lvnames
    rc, out, err = _lvminfo.cmd(cmd)
    _lvminfo._invalidatelvs(vg, lvs)
    if rc != 0  and len(out) < 1:
        raise se.StorageException("%d %s %s\n%s/%s" % (rc, out, err, vg, lvs))


def _setLVAvailability(vg, lvs, available):
    try:
        changelv(vg, lvs, "--available", available)
    except se.StorageException, e:
        error = {"y":se.CannotActivateLogicalVolumes, "n":se.CannotDeactivateLogicalVolume}.get(available, se.VolumeGroupActionError)
        raise error(str(e))

#
# Public Object Accessors
#

def getPV(pv):
    return _lvminfo.getPv(_fqpvname(pv))

def getAllPVs():
    return _lvminfo.getAllPvs()


def getVG(vgName):
    vg = _lvminfo.getVg(vgName)   #returns single VG namedtuple
    if not vg:
        raise se.VolumeGroupDoesNotExist(vgName)
    else:
        return vg

def getVGs(vgNames):
    return _lvminfo.getVgs(vgNames) #returns list

def getAllVGs():
    return _lvminfo.getAllVgs() #returns list

# TODO: lvm VG UUID should not be exposed.
# Remove this function when hsm.public_createVG is removed.
def getVGbyUUID(vgUUID):
    # cycle through all the VGs until the one with the given UUID found
    for vg in getAllVGs():
        try:
            if vg.uuid == vgUUID:
                return vg
        except AttributeError, e:
            # An unreloadable VG found but may be we are not looking for it.
            log.debug("%s" % e.message, exc_info=True)
            continue
    # If not cry loudly
    raise se.VolumeGroupDoesNotExist("vg_uuid: %s" % vgUUID)


def getLV(vgName, lvName=None):
    lv = _lvminfo.getLv(vgName, lvName)
    #getLV() should not return None
    if not lv:
        raise se.LogicalVolumeDoesNotExistError("%s/%s" % (vgName, lvName))
    else:
        return lv


#
# Public Volume Group interface
#

def createVG(vgName, devices, initialTag, metadataSize, extentsize="128m"):
    pvs = [_fqpvname(pdev) for pdev in _normalizeargs(devices)]
    _checkpvsblksize(pvs)

    # Remove this check when we'll support different block sizes.
    bs = _getpvblksize(pvs[0])
    if bs not in constants.SUPPORTED_BLOCKSIZE:
       raise se.DeviceBlockSizeError(bs)

    _initpvs(pvs, metadataSize)
    #Activate the 1st PV metadata areas
    cmd = ["pvchange", "--metadataignore", "n"]
    cmd.append(pvs[0])
    rc, out, err = _lvminfo.cmd(cmd)
    if rc != 0:
        raise se.PhysDevInitializationError(pvs[0])

    options = ["--physicalextentsize", extentsize]
    if initialTag:
        options.extend(("--addtag", initialTag))
    cmd = ["vgcreate"] + options + [vgName] + pvs
    rc, out, err = _lvminfo.cmd(cmd)
    if rc == 0:
        _lvminfo._invalidatepvs(pvs)
        _lvminfo._invalidatevgs(vgName)
        log.debug("Cache after createvg %s", _lvminfo._vgs)
    else:
        raise se.VolumeGroupCreateError(vgName, pvs)


def removeVG(vgName):
    # Get the list of potentially affected PVs
    pvs = [pv.name for pv in _lvminfo.getAllPvs() if pv.vg_name == vgName]
    # Remove the vg from the cache
    _lvminfo._vgs.pop(vgName, None)
    # and now destroy it
    cmd = ["vgremove", "-f", vgName]
    rc, out, err = _lvminfo.cmd(cmd)
    # PVS needs to be reloaded anyhow: if vg is removed they are staled,
    # if vg remove failed, something must be wrong with devices and we want
    # cache updated as well
    _lvminfo._invalidatepvs(pvs)
    # If vgremove failed reintroduce the VG into the cache
    if rc != 0:
        _lvminfo._invalidatevgs(vgName)
        raise se.VolumeGroupRemoveError("VG %s remove failed." % vgName)

def removeVGbyUUID(vgUUID):
    vg = getVGbyUUID(vgUUID)
    if vg:
        removeVG(vg.name)


def renameVG(oldvg, newvg):
    pvs = [pv.name for pv in _lvminfo.getAllPvs() if pv.vg_name == oldvg]
    cmd = ["vgrename"] + [oldvg, newvg]
    rc, out, err = _lvminfo.cmd(cmd)
    # Renaming VG will affect our PV database as well,
    # since we keep the VG name of each PV
    _lvminfo._invalidatepvs(pvs)
    if rc == 0:
        _lvminfo._vgs.pop(oldvg, None)
        _lvminfo._reloadvgs(newvg)
    else:
        _lvminfo._invalidatevgs(oldvg)
        raise se.VolumeGroupRenameError()


def extendVG(vgName, devices):
    pvs = [_fqpvname(pdev) for pdev in _normalizeargs(devices)]
    _checkpvsblksize(pvs, getVGBlockSizes(vgName))
    vg = _lvminfo.getVg(vgName)
    #Format extension PVs as all the other already in the VG
    _initpvs(pvs, int(vg.vg_mda_size) / 2 ** 20)

    cmd = ["vgextend", vgName] + pvs
    rc, out, err = _lvminfo.cmd(cmd)
    if rc == 0:
        _lvminfo._invalidatepvs(pvs)
        _lvminfo._invalidatevgs(vgName)
        log.debug("Cache after extending vg %s", _lvminfo._vgs)
    else:
        raise se.VolumeGroupExtendError(vgName, pvs)


def chkVG(vgName):
    cmd = ["vgck", vgName]
    rc, out, err = _lvminfo.cmd(cmd)
    if rc != 0:
        _lvminfo._invalidatevgs(vgName)
        _lvminfo._invalidatelvs(vgName)
        raise se.StorageDomainAccessError("%s: %s" % (vgName, err))
    return True

def deactivateVG(vgName):
    getVG(vgName) #Check existence
    _setVgAvailability(vgName, available="n")


def invalidateVG(vgName):
    _lvminfo._invalidatevgs(vgName)
    _lvminfo._invalidatelvs(vgName)

def _getpvblksize(pv):
    dev = devicemapper.getDmId(os.path.basename(pv))
    return multipath.getDeviceBlockSizes(dev)

def _checkpvsblksize(pvs, vgBlkSize=None):
    for pv in pvs:
        pvBlkSize = _getpvblksize(pv)

        if pvBlkSize not in constants.SUPPORTED_BLOCKSIZE:
            raise se.DeviceBlockSizeError(pvBlkSize)

        if vgBlkSize is None:
            vgBlkSize = pvBlkSize

        if pvBlkSize != vgBlkSize:
            raise se.VolumeGroupBlockSizeError(vgBlkSize, pvBlkSize)

def checkVGBlockSizes(vgUUID, vgBlkSize=None):
    pvs = listPVNames(vgUUID)
    if not pvs:
        raise se.VolumeGroupDoesNotExist("vg_uuid: %s" % vgUUID)
    _checkpvsblksize(pvs, vgBlkSize)

def getVGBlockSizes(vgUUID):
    pvs = listPVNames(vgUUID)
    if not pvs:
        raise se.VolumeGroupDoesNotExist("vg_uuid: %s" % vgUUID)
    # Returning the block size of the first pv is correct since we don't allow
    # devices with different block size to be on the same VG.
    return _getpvblksize(pvs[0])

#
# Public Logical volume interface
#

def createLV(vgName, lvName, size, activate=True, contiguous=False, initialTag=None):
    """
    Size units: MB (1024 ** 2 = 2 ** 20)B.
    """
    #WARNING! From man vgs:
    #All sizes are output in these units: (h)uman-readable,  (b)ytes,  (s)ectors,  (k)ilobytes,
    #(m)egabytes,  (g)igabytes, (t)erabytes, (p)etabytes, (e)xabytes.
    #Capitalise to use multiples of 1000 (S.I.) instead of 1024.

    cont = {True:"y", False:"n"}[contiguous]
    cmd = ["lvcreate"]
    cmd.extend(LVM_NOBACKUP)
    cmd.extend(("--contiguous", cont, "--size", "%sm" % size))
    if initialTag is not None:
        cmd.extend(("--addtag", initialTag))
    cmd.extend(("--name", lvName, vgName))
    rc, out, err = _lvminfo.cmd(cmd)

    if rc == 0:
        _lvminfo._invalidatevgs(vgName)
        _lvminfo._invalidatelvs(vgName, lvName)
    else:
        raise se.CannotCreateLogicalVolume(vgName, lvName)

    # TBD: Need to explore the option of running lvcreate w/o devmapper
    # so that if activation is not needed it would be skipped in the
    # first place
    if activate:
        lv_path = lvPath(vgName, lvName)
        st = os.stat(lv_path)
        uName = pwd.getpwuid(st.st_uid).pw_name
        gName = grp.getgrgid(st.st_gid).gr_name
        if ":".join((uName, gName)) != USER_GROUP:
            cmd = [constants.EXT_CHOWN, USER_GROUP, lv_path]
            if misc.execCmd(cmd, sudo=True)[0] != 0:
                log.warning("Could not change ownership of one or more volumes in vg (%s) - %s", vgName, lvName)
    else:
        _setLVAvailability(vgName, lvName, "n")


def removeLVs(vgName, lvNames):
    lvNames = _normalizeargs(lvNames)
    #Assert that the LVs are inactive before remove.
    for lvName in lvNames:
        if _isLVActive(vgName, lvName):
            #Fix me
            #Should not remove active LVs
            #raise se.CannotRemoveLogicalVolume(vgName, lvName)
            log.warning("Removing active volume %s/%s" % (vgName, lvName))

    #LV exists or not in cache, attempting to remove it.
    #Removing Stubs also. Active Stubs should raise.
    # Destroy LV
    #Fix me:removes active LVs too. "-f" should be removed.
    cmd = ["lvremove", "-f"]
    cmd.extend(LVM_NOBACKUP)
    for lvName in lvNames:
        cmd.append("%s/%s" % (vgName, lvName))
    rc, out, err = _lvminfo.cmd(cmd)
    if rc == 0:
        for lvName in lvNames:
            # Remove the LV from the cache
            _lvminfo._lvs.pop((vgName, lvName), None)
            # If lvremove succeeded it affected VG as well
            _lvminfo._invalidatevgs(vgName)
    else:
        # Otherwise LV info needs to be refreshed
        _lvminfo._invalidatelvs(vgName, lvName)
        raise se.CannotRemoveLogicalVolume(vgName, str(lvNames))


def extendLV(vgName, lvName, size):
    """
    Size units: MB (1024 ** 2 = 2 ** 20)B.
    """
    #WARNING! From man vgs:
    #All sizes are output in these units: (h)uman-readable,  (b)ytes,  (s)ectors,  (k)ilobytes,
    #(m)egabytes,  (g)igabytes, (t)erabytes, (p)etabytes, (e)xabytes.
    #Capitalise to use multiples of 1000 (S.I.) instead of 1024.
    cmd = ("lvextend",) + LVM_NOBACKUP
    cmd += ("--size", "%sm" % (size,), "%s/%s" % (vgName, lvName))
    rc, out, err = _lvminfo.cmd(cmd)
    if rc == 0:
        _lvminfo._invalidatevgs(vgName)
        _lvminfo._invalidatelvs(vgName, lvName)

    elif rc == 3:
        #In LVM we trust. Hope that 3 is only for this.
        log.debug("New size (in extents) matches existing size (in extents).")
    elif rc != 0:
        #get the free extents size
        #YaRC
        vg = getVG(vgName)
        free_size = int(vg.extent_size) * int(vg.free_count) #in B
        if free_size < int(size) * constants.MEGAB:
            raise se.VolumeGroupSizeError("%s/%s %d > %d (MiB)" % (vgName, lvName, int(size), free_size / constants.MEGAB))

        raise se.LogicalVolumeExtendError(vgName, lvName,"%sM" % (size,))


def activateLVs(vgName, lvNames):
    lvNames = _normalizeargs(lvNames)
    toActivate = [lvName for lvName in lvNames if not _isLVActive(vgName, lvName)]
    if toActivate:
        _setLVAvailability(vgName, toActivate, "y")


def deactivateLVs(vgName, lvNames):
    lvNames = _normalizeargs(lvNames)
    toDeactivate = [lvName for lvName in lvNames if _isLVActive(vgName, lvName)]
    if toDeactivate:
        _setLVAvailability(vgName, toDeactivate, "n")


def renameLV(vg, oldlv, newlv):
    cmd = ("lvrename",) + LVM_NOBACKUP + (vg, oldlv, newlv)
    rc, out, err = _lvminfo.cmd(cmd)
    if rc != 0:
        raise se.LogicalVolumeRenameError("%s %s %s" % (vg, oldlv, newlv))

    _lvminfo._lvs.pop((vg, oldlv), None)
    _lvminfo._reloadlvs(vg, newlv)


def refreshLV(vgName, lvName):
    #If  the  logical  volume  is active, reload its metadata.
    cmd = ['lvchange', '--refresh', "%s/%s" % (vgName, lvName)]
    rc, out, err = _lvminfo.cmd(cmd)
    _lvminfo._invalidatelvs(vgName, lvName)
    if rc != 0:
        raise se.LogicalVolumeRefreshError("%s failed" % list2cmdline(cmd))


#Fix me: Function name should mention LV or unify with VG version.
#may be for all the LVs in the whole VG?
def addtag(vg, lv, tag):
    lvname = "%s/%s" % (vg, lv)
    cmd = ("lvchange",) + LVM_NOBACKUP + ("--addtag", tag) + (lvname,)
    rc, out, err = _lvminfo.cmd(cmd)
    _lvminfo._invalidatelvs(vg, lv)
    if rc != 0:
        #Fix me: should be se.ChangeLogicalVolumeError but this not exists.
        raise se.MissingTagOnLogicalVolume("%s/%s" % (vg, lv), tag)

def changeLVTags(vg, lv, delTags=[], addTags=[]):
    lvname = '%s/%s' % (vg, lv)
    delTags = set(delTags)
    addTags = set(addTags)
    if delTags.intersection(addTags):
        raise se.LogicalVolumeReplaceTagError("Cannot add and delete the same tag lv: `%s` tags: `%s`" % (lvname,
                ", ".join(delTags.intersection(addTags))))

    cmd = ['lvchange']
    cmd.extend(LVM_NOBACKUP)

    for tag in delTags:
        cmd.extend(("--deltag", tag))

    for tag in addTags:
        cmd.extend(('--addtag', tag))

    cmd.append(lvname)

    rc, out, err = _lvminfo.cmd(cmd)
    _lvminfo._invalidatelvs(vg, lv)
    if rc != 0:
        raise se.LogicalVolumeReplaceTagError('lv: `%s` add: `%s` del: `%s` (%s)' % (lvname,
            ", ".join(addTags), ", ".join(delTags), err[-1]))


def addLVTags(vg, lv, addTags):
    changeLVTags(vg, lv, addTags=addTags)


#
# Helper functions
#
def lvPath(vgName, lvName):
    return os.path.join("/dev", vgName, lvName)


def _isLVActive(vgName, lvName):
    """Active volumes have a mp link.

    This function should not be used out of this module.
    """
    return os.path.exists(lvPath(vgName, lvName))


def changeVGTags(vgName, delTags=[], addTags=[]):
    delTags = set(delTags)
    addTags = set(addTags)
    if delTags.intersection(addTags):
        raise se.VolumeGroupReplaceTagError("Cannot add and delete the same tag vg: `%s` tags: `%s`", vgName,
                ", ".join(delTags.intersection(addTags)))

    cmd = ["vgchange"]

    for tag in delTags:
        cmd.extend(("--deltag", tag))
    for tag in addTags:
        cmd.extend(("--addtag", tag))

    cmd.append(vgName)
    rc, out, err = _lvminfo.cmd(cmd)
    _lvminfo._invalidatevgs(vgName)
    if rc != 0:
        raise se.VolumeGroupReplaceTagError("vg:%s del:%s add:%s (%s)" % (vgName, ", ".join(delTags), ", ".join(addTags), err[-1]))


def addVGTag(vgName, tag):
    _lvminfo._invalidatevgs(vgName)
    cmd = ["vgchange", "--addtag", tag, vgName]
    rc, out, err = _lvminfo.cmd(cmd)
    if rc != 0:
        raise se.VolumeGroupAddTagError("Failed adding tag %s to VG %s." % (tag, vgName))

def remVGTag(vgName, tag):
    _lvminfo._invalidatevgs(vgName)
    cmd = ["vgchange", "--deltag", tag, vgName]
    rc, out, err = _lvminfo.cmd(cmd)
    if rc != 0:
        raise se.VolumeGroupRemoveTagError(vgName)


def replaceVGTag(vg, oldTag, newTag):
    changeVGTags(vg, [oldTag], [newTag])


def addVGTags(vgName, tags):
    changeVGTags(vgName, addTags=tags)


def remVGTags(vgName, tags):
    changeVGTags(vgName, delTags=tags)


def getFirstExt(vg, lv):
    return getLV(vg, lv).devices.strip(" )").split("(")

def listPVNames(vgName):
    pvs = getAllPVs()
    return [pv.name for pv in pvs if pv.vg_name == vgName]


def setrwLV(vg, lv, rw=True):
    permission = {False:'r', True:'rw'}[rw]
    try:
        changelv(vg, lv, "--permission", permission)
    except se.StorageException:
        l = getLV(vg, lv)
        if l.writeable == rw:
            # Ignore the error since lv is now rw, hoping that the error was
            # because lv was already rw, see BZ#654691. We may hide here another
            # lvchange error.
            return

        raise se.CannotSetRWLogicalVolume(vg, lv, permission)


def lvsByTag(vgName, tag):
    return [lv for lv in getLV(vgName) if tag in lv.tags]


#Fix me: unify with addTag
def replaceLVTag(vg, lv, deltag, addtag):
    """
    Removes and add tags atomically.
    """
    lvname = "%s/%s" % (vg, lv)
    cmd = ("lvchange",) + LVM_NOBACKUP + ("--deltag", deltag) + ("--addtag", addtag) + (lvname,)
    rc, out, err = _lvminfo.cmd(cmd)
    _lvminfo._invalidatelvs(vg, lv)
    if rc != 0:
        raise se.LogicalVolumeReplaceTagError("%s/%s" % (vg, lv), "%s,%s" % (deltag, addtag))
