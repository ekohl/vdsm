# Copyright 2008 Red Hat, Inc. and/or its affiliates.
#
# Licensed to you under the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.  See the files README and
# LICENSE_GPL_v2 which accompany this distribution.
#

EXTRA_DIST = \
	before_vm_start.py

install-data-local:
	$(MKDIR_P) $(DESTDIR)$(vdsmhooksdir)/before_vm_start
	$(INSTALL_SCRIPT) $(srcdir)/before_vm_start.py \
		$(DESTDIR)$(vdsmhooksdir)/before_vm_start/50_smartcard

uninstall-local:
	$(RM) $(DESTDIR)$(vdsmhooksdir)/before_vm_start/50_smartcard
