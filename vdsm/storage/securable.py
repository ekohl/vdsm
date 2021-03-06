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

from threading import Event
from functools import wraps

OVERRIDE_ARG = "__securityOverride"
SECURE_FIELD = "__secured__"

class SecureError(RuntimeError): pass

class Securable(type):
    def __new__(mcs, name, bases, fdict):

        def _isSafe(self):
            return self._safety.isSet()

        def _setSafe(self):
            self._safety.set()

        def _setUnsafe(self):
            self._safety.clear()

        for fun, val in fdict.iteritems():
            if not callable(val):
                continue

            if hasattr(val, SECURE_FIELD) and (not getattr(val, SECURE_FIELD)):
                continue

            if fun.startswith("__"):
                #Wrapping builtins might cause weird results
                continue

            fdict[fun] = secured(val)

        fdict['__securable__'] = True
        fdict['_safety'] = Event()
        fdict['_isSafe'] = _isSafe
        fdict['_setSafe'] = _setSafe
        fdict['_setUnsafe'] = _setUnsafe
        return type.__new__(mcs, name, bases, fdict)

def unsecured(f):
    setattr(f, SECURE_FIELD, False)
    return f

def secured(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not hasattr(args[0], "__securable__"):
            raise RuntimeError("Secured object is not a securable")

        override = kwargs.get(OVERRIDE_ARG, False)
        try:
            del kwargs[OVERRIDE_ARG]
        except KeyError:
            pass

        if not (args[0]._isSafe() or override):
            raise SecureError()

        return f(*args, **kwargs)

    return wrapper
