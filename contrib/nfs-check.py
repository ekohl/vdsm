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

import os
import sys
import subprocess
import tempfile
import pwd
import grp
import signal
import socket

# Constants
TIMEOUT_NFS = 10 # seconds

EXPORTS     = "/etc/exports"
MOUNT       = "/bin/mount"
UMOUNT      = "/bin/umount"
SU          = "/bin/su"

UID         = 36
GUID        = 36

USER        = "vdsm"
GROUP       = "kvm"

TESTFILE    = "vdsmTest"

def usage():
    print "Usage: " +  sys.argv[0] + " server:/target"
    print "nfs-check is a python script to validate nfs targets to use" \
            " with oVirt project."
    print "Some operations includes: mount the nfs target," \
            " create a file as %s:%s and remove it." % (USER, GROUP)
    sys.exit(0)

class Alarm(Exception):
    pass

class Nfs(object):
    def handler(self, signum, frame):
        raise Alarm()

    def mount(self, server, target, pathName):
        cmd = "%s:%s" % (server, target)
        process = subprocess.Popen([MOUNT, "-t", "nfs", cmd, pathName],
                shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        signal.signal(signal.SIGALRM, self.handler)
        signal.alarm(TIMEOUT_NFS)

        print "Current hostname: %s - IP addr %s" % (self.getHostName(), self.getLocalIP())
        print "Trying to %s -t nfs %s..." % (MOUNT, cmd)

        try:
            errorMsg  = process.communicate()[1].strip()
            signal.alarm(0)
        except Alarm:
            print "Timeout, cannot mount the nfs! Please check the status " \
                    "of NFS service or/and the Firewall settings!"
            self.exitCode(-1)

        # get return from mount cmd
        ret = process.poll()

        # Let`s check if the NFS Server is local machine
        localIP      = self.getLocalIP()
        serverIP     = self.getIP(server)
        localMachine = False

        # check if server (argument) IP address is the same for
        # hostname IP address
        for ip in serverIP:
            if localIP == ip:
                localMachine = True

        if ret != 0 and localMachine == True:
            ret = self.checkLocalServer(ret, errorMsg, target)
        elif ret != 0:
            print "return = %s error %s" % (ret, errorMsg)

        return ret

    def checkLocalServer(self, ret, errorMsg, target):
        print "NFS Server is local machine, looking local configurations.."
        if "access denied" in errorMsg:
            print "return = %s error msg = %s" % (ret, errorMsg)
            print "Access Denied: Cannot mount nfs!"
            if not os.path.isfile(EXPORTS):
                print EXPORTS + " doesn`t exist, please create one" \
                        " and start nfs server!"
            else:
                targetFound = False
                with open(EXPORTS, 'r') as f:
                    for line in f.readlines():
                        if target in line.split(" ")[0]:
                            targetFound = True
                    if targetFound == False:
                        print "Please include %s into %s and restart" \
                                " nfs server!" % (target, EXPORTS)

        elif "does not exist" in errorMsg:
            if not os.path.isdir(pathName):
                print "return = %s error msg = %s" % (ret, errorMsg)
        else:
            print "NFS server down?"
            print "return = %s error msg = %s" % (ret, errorMsg)

        return ret

    def getIP(self, Server):
        ip = []

        try:
            addrList = socket.getaddrinfo(Server, None)
        except:
            print "Cannot get address from %s" % Server
            self.exitCode(-1)

        for item in addrList:
            ip.append(item[4][0])

        return ip

    def getHostName(self):
        return socket.gethostname()

    def getLocalIP(self):
        return socket.gethostbyname(socket.gethostname())

    def exitCode(self, ret):
        sys.exit(ret)

    def tests(self, pathName):
        ret = 0

        try:
            if pwd.getpwnam(USER).pw_uid != UID:
                print "WARNING: %s user has UID [%s] which is different from " \
                   "the required [%s]" % (USER, pwd.getpwnam(USER).pw_uid, UID)
        except:
            print "Cannot find %s user! You must have %s user created!" % \
                        (USER, USER)
            ret = -1

        try:
            if grp.getgrnam(GROUP).gr_gid != GUID:
                print "WARNING: %s group has GUID [%s] which is different from " \
                   "the required [%s]" % (GROUP, grp.getgrnam(GROUP).gr_gid, GUID)
        except:
            print "Cannot find %s group! The system must have %s group" % \
                           (GROUP, GROUP)
            ret = -1

        if ret != -1:
            fileTest = pathName + "/" + TESTFILE
            cmdTouch = "/bin/touch " + fileTest
            process = subprocess.Popen([SU, USER, "-c", cmdTouch, "-s", "/bin/bash"],
                    shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            signal.signal(signal.SIGALRM, self.handler)
            signal.alarm(TIMEOUT_NFS)

            try:
                errorMsg  = process.communicate()[1].strip()
                signal.alarm(0)
            except Alarm:
                print "Timeout, cannot execute: %s" % cmdTouch
                ret = -1

            if ret != -1:
                # get the return from the command
                ret = process.poll()
                if ret != 0:
                    if "Permission denied" in errorMsg:
                        print "Permission denied: %s user as %s cannot " \
                                "create a file into %s" % (USER, GROUP, pathName)
                        print "Suggestions: please verify the permissions of " \
                                "target (chmod or/and selinux booleans)"
                        print "return = %s error msg = %s" % (ret, errorMsg)
                        ret = -1
                    elif "Read-only file system" in errorMsg:
                        print "Please make sure the target NFS contain the read " \
                                "and WRITE access"
                        print "return = %s error msg = %s" % (ret, errorMsg)
                        ret = -1
                    else:
                        print "return = %s error msg = %s" % (ret, errorMsg)
                        ret = -1

                # remove the file
                if ret != -1:
                    print "Removing %s file.." % TESTFILE
                    os.remove(fileTest)
        return ret

    def umount(self, pathName):
        process = subprocess.Popen([UMOUNT, pathName],
                shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        signal.signal(signal.SIGALRM, self.handler)
        signal.alarm(TIMEOUT_NFS)

        try:
            errorMsg = process.communicate()[1].strip()
            signal.alarm(0)
        except Alarm:
            print "Timeout, cannot %s the nfs!" % UMOUNT
            self.exitCode(-1)

        # get the return from the command
        ret = process.poll()

        if ret != 0:
            print "cannot execute %s!" % UMOUNT
            print "return = %s error msg = %s" % (ret, errorMsg)

        return ret

if __name__ == "__main__":
    if os.geteuid() != 0:
        print "You must be root to run this script."
        sys.exit(-1)

    if len(sys.argv) <> 2 or ":" not in sys.argv[1]:
        usage()

    nfsData = sys.argv[1].split(":")

    NFS_SERVER = nfsData[0]
    NFS_TARGET = nfsData[1]

    nfs = Nfs()

    LOCALPATH = tempfile.mkdtemp()

    try:
        ret = nfs.mount(NFS_SERVER, NFS_TARGET, LOCALPATH)
        if ret != 0:
            nfs.exitCode(ret)

        print "Executing NFS tests.."
        ret = nfs.tests(LOCALPATH)
        if ret != 0:
            print "Status of tests [Failed]"
        else:
            print "Status of tests [OK]"

        print "Disconnecting from NFS Server.."
        ret = nfs.umount(LOCALPATH)
        if ret != 0:
            print "Umount [Failed]\n"
            nfs.exitCode(ret)
    finally:
        os.removedirs(LOCALPATH)

    print "Done!"
