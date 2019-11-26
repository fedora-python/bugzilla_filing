import subprocess
import sys
import time
from collections import defaultdict


RAWHIDEVER = 32


def repoquery(*args, **kwargs):
    cmd = ['repoquery']
    version = kwargs.pop('version', None)
    if version is None:
        cmd.append('--repo=rawhide')
    else:
        cmd.extend(['--repo=fedora', '--repo=updates',
                    '--repo=updates-testing', f'--releasever={version}'])
    if args:
        cmd.extend(args)
    for option, value in kwargs.items():
        cmd.append(f'--{option}')
        if value is not True:
            cmd.append(value)
    while True:
        try:
            proc = subprocess.run(cmd,
                                  text=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL,
                                  check=True)
        except subprocess.CalledProcessError:
            print('! repoquery failed, retrying in 5 seconds', file=sys.stderr)
            time.sleep(5)
        else:
            return proc.stdout.splitlines()


def old_pkgs():
    fedoras = {}
    # Fedora 14 was the first with Python 2.7
    for version in range(14, RAWHIDEVER+1):
        fedoras[version] = set()
        for dependency in ('python(abi) = 2.7',
                           'libpython2.7.so.1.0()(64bit)',
                           'libpython2.7_d.so.1.0()(64bit)'):
            news = repoquery(version=version,
                             whatrequires=dependency,
                             qf='%{NAME} %{EPOCH}:%{VERSION}-%{RELEASE}')
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
    new = set(repoquery(all=True, qf='%{NAME}'))
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
    for part in parts:
        if part == '0':
            release.append(part)
        else:
            release.append(str(int(part) + 1))
            release = '.'.join(release)
            return f'{ev}-{release}'
    else:
        raise RuntimeError(f'Cannot bump {evr}')


def format_obsolete(pkg, evr):
    evr = bump_release(evr)
    return f'%obsolete {pkg} {evr}'


last_fedoras, max_versions = removed_pkgs()


last_known = 'qtiplot'
#  last_known = None


for fed_version in sorted(last_fedoras):
    print(f'# Python 2 packages removed in Fedora {fed_version+1} but never obsoleted')
    for pkg in sorted(last_fedoras[fed_version]):
        if last_known:
            if last_known == pkg:
                last_known = None
            continue
        print(pkg, file=sys.stderr, end='')
        requires = repoquery(requires=pkg, version=fed_version)
        for require in requires:
            if require not in ('', 'python(abi) = 2.7', 'libpython2.7.so.1.0()(64bit)'):
                break
        else:
            print(f'\r# {pkg} only requires Python 2', file=sys.stderr)
            continue
        pkg_version = drop_0epoch(drop_dist(max_versions[pkg]))
        obsoleted_previous = False
        for fedora in range(fed_version, RAWHIDEVER):
            print('.', file=sys.stderr, end='')
            whatobsoletes = repoquery(whatobsoletes=f'{pkg} = {pkg_version}', qf='%{NAME}', version=fedora)
            if whatobsoletes:
                if obsoleted_previous:
                    print(f'\r# {pkg} obsoleted in Fedora {fedora-1} and {fedora}', file=sys.stderr)
                    break
                obsoleted_previous = True
            else:
                obsoleted_previous = False
        else:
            whatobsoletes = repoquery(whatobsoletes=f'{pkg} = {pkg_version}', qf='%{NAME}')
            if not whatobsoletes or whatobsoletes == ['fedora-obsolete-packages']:
                print('\r', file=sys.stderr, end='')
                print(format_obsolete(pkg, pkg_version))
            else:
                obs = ', '.join(whatobsoletes)
                print(f'\r# {pkg} {pkg_version} obsoleted by {obs}', file=sys.stderr)
