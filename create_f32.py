#!/usr/bin/env python3
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.

# create.py: Create a new bug report

import bugzilla
import os

maxbugz = float(os.getenv('MAXBUGZ', 'inf'))

# public test instance of bugzilla.redhat.com.
#
# Don't worry, changing things here is fine, and won't send any email to
# users or anything. It's what partner-bugzilla.redhat.com is for!
URL = "bugzilla.redhat.com"
TRACKER = [1625773, 1698500, 1708725]
CC = [
    "mhroncok@redhat.com",
    "pviktori@redhat.com",
    "cstratak@redhat.com",
    "ngompa13@gmail.com",
    "i.gnatenko.brain@gmail.com",
    "zbyszek@in.waw.pl",
]
bzapi = bugzilla.Bugzilla(URL)
if not bzapi.logged_in:
    print("This example requires cached login credentials for %s" % URL)
    bzapi.interactive_login()

TO_RETIRE = [
    "pyifp",
    "pypoppler",
    "pyside-tools",
    "python-arc",
    "python-backports",
    "python-enum34",
    "python-gtkextra",
    "python-socksipychain",
    "python-subprocess32",
    "python-volatility",
]

TO_DROP = {
    "PyQt4": ["PyQt4", "PyQt4-devel", "PyQt4-webkit"],
    "PyYAML": ["python2-pyyaml"],
    "audit": ["python2-audit"],
    "ioprocess": ["python2-ioprocess"],
    "python-PyPDF2": ["python2-PyPDF2"],
    "python-atomicwrites": ["python2-atomicwrites"],
    "python-augeas": ["python2-augeas"],
    "python-distutils-extra": ["python2-distutils-extra"],
    "python-dpkt": ["python2-dpkt"],
    "python-empy": ["python2-empy"],
    "python-funcsigs": ["python2-funcsigs"],
    "python-gstreamer1": ["python2-gstreamer1"],
    "python-idna": ["python2-idna"],
    "python-inotify": ["python2-inotify", "python2-inotify-examples"],
    "python-mock": ["python2-mock"],
    "python-musicbrainzngs": ["python2-musicbrainzngs"],
    "python-mutagen": ["python2-mutagen"],
    "python-pathlib2": ["python2-pathlib2"],
    "python-py": ["python2-py"],
    "python-pyside": ["python-pyside-devel", "python2-pyside"],
    "python-pysocks": ["python2-pysocks"],
    "python-scandir": ["python2-scandir"],
    "python-zmq": ["python2-zmq", "python2-zmq-tests"],
    "qpid-proton": ["python2-qpid-proton"],
    "shiboken": ["shiboken", "shiboken-python2-devel", "shiboken-python2-libs"],
}

# Get a list of components for which the bugs already exists
tracking_bug = bzapi.getbug(TRACKER[0])
existing_bugz = bzapi.getbugs(tracking_bug.depends_on,
                              include_fields=["component"])
existing_bugz_components = [b.component for b in existing_bugz]

TEMPLATE_RETIRE = """In line with the Retire Python 2 Fedora change [0], all (sub)packages of {pkg} were marked for removal.

There was no FESCo exception for this package.

Please retire your package in Rawhide (Fedora 32).

Please don't remove packages from Fedora 31/30/29, removing packages from a released Fedora branch is forbidden and out of scope of this request.

If there is no objection in a week, we will retire the package for you.

We hope this doesn't come to you as a surprise. If you want to know our motivation for this, please read the change document [0].

[0] https://fedoraproject.org/wiki/Changes/RetirePython2"""

TEMPLATE_DROP = """In line with the Retire Python 2 Fedora change [0], the following (sub)packages of {pkg} were marked for removal:

{subpkgs}

Please remove them from your package in Rawhide (Fedora 32).

Please don't remove packages from Fedora 31/30/29, removing packages from a released Fedora branch is forbidden and out of scope of this request.

If there is no objection in a week, we will remove the package(s) as soon as we get to it. This change might not match your packaging style, so we'd prefer if you did the change. If you need more time, please let us know here.

If you do the change yourself, it would help us a lot by reducing the amount of packages we need to mass change.

We hope this doesn't come to you as a surprise. If you want to know our motivation for this, please read the change document [0].

[0] https://fedoraproject.org/wiki/Changes/RetirePython2"""


def format_list(pkgs):
    return "\n".join(f" * {pkg}" for pkg in pkgs)


# Similar to build_query, build_createbug is a helper function that handles
# some bugzilla version incompatibility issues. All it does is return a
# properly formatted dict(), and provide friendly parameter names.
# The argument names map to those accepted by XMLRPC Bug.create:
# https://bugzilla.readthedocs.io/en/latest/api/core/v1/bug.html#create-bug
#
# The arguments specified here are mandatory, but there are many other
# optional ones like op_sys, platform, etc. See the docs

components = [*TO_DROP] + TO_RETIRE
bugz_created = 0

for component in components:
    if component in existing_bugz_components:
        continue

    if bugz_created >= maxbugz:
        break

    if component in TO_RETIRE:
        summary = f"Retire {component} in Fedora 32+"
        description = TEMPLATE_RETIRE.format(pkg=component)
    else:
        subpackages = TO_DROP[component]
        subpackages.sort()
        if len(subpackages) > 4:
            sum_list = ', '.join(subpackages[:4]) + '...'
        else:
            sum_list = ', '.join(subpackages)
        summary = f"{component}: Remove (sub)packages from Fedora 32+: {sum_list}"
        description = TEMPLATE_DROP.format(pkg=component,
                                           subpkgs=format_list(subpackages))

    createinfo = bzapi.build_createbug(
        product="Fedora",
        version="rawhide",
        component=component,
        cc=CC,
        blocks=TRACKER,
        summary=summary,
        description=description)

    newbug = bzapi.createbug(createinfo)
    print(f"{component} {newbug.weburl}")

    bugz_created += 1
