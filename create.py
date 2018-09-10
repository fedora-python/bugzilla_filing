#!/usr/bin/env python3
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.

# create.py: Create a new bug report

import bugzilla
import json

# public test instance of bugzilla.redhat.com.
#
# Don't worry, changing things here is fine, and won't send any email to
# users or anything. It's what partner-bugzilla.redhat.com is for!
URL = "bugzilla.redhat.com"
TRACKER = "1625773"
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

with open('../portingdb/_check_drops/results-retire_now-srpms.json', 'r') as f:
    results = json.load(f)

with open('./bugz.json', 'r') as f:
    bugz = json.load(f)


TEMPLATE = """In line with the Mass Python 2 Package Removal [0], all (sub)packages of {pkg} were marked for removal:

{subpkgs}

According to our query, those packages only provide a Python 2 importable module. If this is not true, please tell us why, so we can fix our query.

Please retire your package in Rawhide (Fedora 30).

If there is no objection in a week, we will retire the package for you.

We hope this doesn't come to you as a surprise. If you want to know our motivation for this, please read the change document [0].

[0] https://fedoraproject.org/wiki/Changes/Mass_Python_2_Package_Removal"""

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

components = {results[r]["source"] for r in results}

for component in components:
    if component in bugz:
        continue

    subpackages = [r for r in results if results[r]["source"] == component]
    description = TEMPLATE.format(pkg=component,
                                  subpkgs=format_list(subpackages))

    createinfo = bzapi.build_createbug(
        product="Fedora",
        version="rawhide",
        component=component,
        cc=CC,
        blocks=TRACKER,
        summary=f"Retire {component} in Fedora 30+",
        description=description)

    newbug = bzapi.createbug(createinfo)
    bugz[component] = newbug.weburl
    print(f"{component} {newbug.weburl}")

with open('./bugz.json', 'w') as f:
    json.dump(bugz, f, indent=2)
