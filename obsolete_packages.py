import dnf
import re
import subprocess
import sys
from collections import defaultdict


FIRST = 14
EOL = 29
RAWHIDEVER = 32

DNF_CACHEDIR = '_dnf_cache_dir'
ARCH = 'x86_64'

INTSTART = re.compile(r'^(\d+).+')

sacks = {}

# modularity problems :(
# https://bugzilla.redhat.com/show_bug.cgi?id=1636285
excludepkgs = ('fedora-release,fedora-release-cinnamon,fedora-release-cloud,'
               'fedora-release-container,fedora-release-coreos,'
               'fedora-release-iot,fedora-release-kde,'
               'fedora-release-matecompiz,fedora-release-server,'
               'fedora-release-silverblue,fedora-release-snappy,'
               'fedora-release-soas,fedora-release-workstation,'
               'fedora-release-xfce,generic-release')


def rawhide_sack():
    try:
        return sacks[None]
    except KeyError:
        pass
    base = dnf.Base()
    conf = base.conf
    conf.cachedir = DNF_CACHEDIR
    conf.substitutions['releasever'] = str(RAWHIDEVER)
    conf.substitutions['basearch'] = ARCH
    base.repos.add_new_repo('rawhide', conf,
        metalink='https://mirrors.fedoraproject.org/metalink?repo=rawhide&arch=$basearch',
        skip_if_unavailable=False,
        enabled=True,
        excludepkgs=excludepkgs)
    base.fill_sack(load_system_repo=False, load_available_repos=True)
    sacks[None] = base.sack
    return base.sack


def fedora_sack(version):
    try:
        return sacks[version]
    except KeyError:
        pass
    base = dnf.Base()
    conf = base.conf
    conf.cachedir = DNF_CACHEDIR
    conf.substitutions['releasever'] = str(version)
    conf.substitutions['basearch'] = ARCH
    base.repos.add_new_repo(f'fedora{version}', conf,
        metalink='https://mirrors.fedoraproject.org/metalink?repo=fedora-$releasever&arch=$basearch',
        skip_if_unavailable=False,
        enabled=True,
        excludepkgs=excludepkgs)
    base.repos.add_new_repo(f'updates{version}', conf,
        metalink='https://mirrors.fedoraproject.org/metalink?repo=updates-released-f$releasever&arch=$basearch',
        skip_if_unavailable=False,
        enabled=True,
        excludepkgs=excludepkgs)
    base.repos.add_new_repo(f'updates-testing{version}', conf,
        metalink='https://mirrors.fedoraproject.org/metalink?repo=updates-testing-f$releasever&arch=$basearch',
        skip_if_unavailable=False,
        enabled=True,
        excludepkgs=excludepkgs)
    base.fill_sack(load_system_repo=False, load_available_repos=True)
    sacks[version] = base.sack
    return base.sack


def repoquery(*args, **kwargs):
    version = kwargs.pop('version', None)
    if version is None:
        sack = rawhide_sack()
    else:
        sack = fedora_sack(version)
    if 'whatrequires' in kwargs:
        return sack.query().available().filter(requires=kwargs['whatrequires'])
    if 'whatobsoletes' in kwargs:
        return sack.query().filter(obsoletes=kwargs['whatobsoletes'])
    if 'requires' in kwargs:
        pkgs = sack.query().filter(name=kwargs['requires'], latest=1).run()
        return pkgs[0].requires
    if 'all' in kwargs and kwargs['all']:
        return sack.query()
    raise RuntimeError('unknown query')


def old_pkgs():
    fedoras = {}
    for version in range(FIRST, RAWHIDEVER+1):
        fedoras[version] = set()
        for dependency in ('python(abi) = 2.7',
                           'libpython2.7.so.1.0()(64bit)',
                           'libpython2.7_d.so.1.0()(64bit)'):
            pkgs = repoquery(version=version,
                             whatrequires=dependency)
            news = {f'{p.name} {p.evr}' for p in pkgs}
            if news:
                print(f'{len(news)} pkgs require {dependency} in Fedora {version}',
                      file=sys.stderr)
            fedoras[version] |= set(news)
        names = {nevr.split(' ')[0] for nevr in fedoras[version]}
        for older_version in fedoras:
            if older_version == version:
                continue
            for nevr in set(fedoras[older_version]):
                if nevr.split(' ')[0] in names:
                    fedoras[older_version].remove(nevr)
    return fedoras


class SortableEVR:
    def __init__(self, evr):
        self.evr = evr

    def __repr__(self):
        return f"evr'{self.evr}'"

    def __eq__(self, other):
        return self.evr == other.evr

    def __lt__(self, other):
        return subprocess.call(('rpmdev-vercmp', self.evr, other.evr),
                               stdout=subprocess.DEVNULL) == 12


def removed_pkgs():
    name_versions = defaultdict(set)
    fedoras = old_pkgs()
    last_fedoras = defaultdict(set)
    new = {pkg.name for pkg in repoquery(all=True)}
    for version in fedoras:
        for name_evr in set(fedoras[version]):
            name, _, evr = name_evr.partition(' ')
            if name not in new:
                name_versions[name].add(evr)
                last_fedoras[version].add(name)
    max_versions = {name: max(versions, key=SortableEVR)
                    for name, versions in name_versions.items()}
    return last_fedoras, max_versions


def drop_dist(evr):
    ev, _, release = evr.rpartition('-')
    parts = (part for part in release.split('.') if not part.startswith('fc'))
    release = '.'.join(parts)
    return f'{ev}-{release}'


def drop_0epoch(evr):
    epoch, _, vr = evr.partition(':')
    return vr if epoch == '0' else evr


def bump_release(evr):
    ev, _, release = evr.rpartition('-')
    parts = release.split('.')
    release = []
    for i, part in enumerate(parts):
        if part == '0' and i != len(parts)-1:
            release.append(part)
        else:
            try:
                release.append(str(int(part) + 1))
            except ValueError:
                if i != len(parts)-1:
                    release.append(part)
                    continue
                match = INTSTART.match(part)
                if match:
                    release.append(str(int(match.group(1)) + 1))
                else:
                    raise
            release = '.'.join(release)
            return f'{ev}-{release}'
    else:
        raise RuntimeError(f'Cannot bump {evr}')


def format_obsolete(pkg, evr):
    evr = bump_release(evr)
    return f'%obsolete {pkg} {evr}'


last_fedoras, max_versions = removed_pkgs()


for fed_version in sorted(last_fedoras):
    print(f'\n# Python 2 packages removed in Fedora {fed_version+1} but never obsoleted')
    for pkg in sorted(last_fedoras[fed_version]):
        requires = repoquery(requires=pkg, version=fed_version)
        for require in requires:
            if require not in ('', 'python(abi) = 2.7', 'libpython2.7.so.1.0()(64bit)'):
                break
        else:
            print(f'# {pkg} only requires Python 2', file=sys.stderr)
            continue
        pkg_version = drop_0epoch(drop_dist(max_versions[pkg]))
        obsoleted_previous = False
        for fedora in range(fed_version, RAWHIDEVER):
            whatobsoletes = list(repoquery(whatobsoletes=f'{pkg} = {pkg_version}', version=fedora))
            if whatobsoletes:
                if obsoleted_previous:
                    print(f'# {pkg} obsoleted in Fedora {fedora-1} and {fedora}', file=sys.stderr)
                    break
                obsoleted_previous = True
            else:
                obsoleted_previous = False
        else:
            whatobsoletes = list(repoquery(whatobsoletes=f'{pkg} = {pkg_version}'))
            if not whatobsoletes or whatobsoletes[0].name == 'fedora-obsolete-packages':
                print(format_obsolete(pkg, pkg_version))
            else:
                obs = ', '.join(p.name for p in whatobsoletes)
                print(f'# {pkg} {pkg_version} obsoleted by {obs}', file=sys.stderr)
