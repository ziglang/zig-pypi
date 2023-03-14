import argparse
import os
import json
import hashlib
import urllib.request
from pathlib import Path
from email.message import EmailMessage
from wheel.wheelfile import WheelFile, get_zipinfo_datetime
from zipfile import ZipInfo, ZIP_DEFLATED
import libarchive # from libarchive-c

ZIG_VERSION_INFO_URL = 'https://ziglang.org/download/index.json'
ZIG_PYTHON_PLATFORMS = {
    'x86_64-windows': 'win_amd64',
    'x86_64-macos':   'macosx_10_9_x86_64',
    'aarch64-macos':  'macosx_11_0_arm64',
    'i386-linux':     'manylinux_2_12_i686.manylinux2010_i686.musllinux_1_1_i686',
    # renamed i386 to x86
    'x86-linux':      'manylinux_2_12_i686.manylinux2010_i686.musllinux_1_1_i686',
    'x86_64-linux':   'manylinux_2_12_x86_64.manylinux2010_x86_64.musllinux_1_1_x86_64',
    'aarch64-linux':
        'manylinux_2_17_aarch64.manylinux2014_aarch64.musllinux_1_1_aarch64',
    # no longer present?
    'armv7a-linux':   'manylinux_2_17_armv7l.manylinux2014_armv7l.musllinux_1_1_armv7l',
}

class ReproducibleWheelFile(WheelFile):
    def writestr(self, zinfo, *args, **kwargs):
        if not isinstance(zinfo, ZipInfo):
            raise ValueError("ZipInfo required")
        zinfo.date_time = (1980,1,1,0,0,0)
        zinfo.create_system = 3
        super().writestr(zinfo, *args, **kwargs)


def make_message(headers, payload=None):
    msg = EmailMessage()
    for name, value in headers.items():
        if isinstance(value, list):
            for value_part in value:
                msg[name] = value_part
        else:
            msg[name] = value
    if payload:
        msg.set_payload(payload)
    return msg


def write_wheel_file(filename, contents):
    with ReproducibleWheelFile(filename, 'w') as wheel:
        for member_info, member_source in contents.items():
            if not isinstance(member_info, ZipInfo):
                member_info = ZipInfo(member_info)
                member_info.external_attr = 0o644 << 16
            member_info.file_size = len(member_source)
            member_info.compress_type = ZIP_DEFLATED
            wheel.writestr(member_info, bytes(member_source))
    return filename


def write_wheel(out_dir, *, name, version, tag, metadata, description, contents):
    wheel_name = f'{name}-{version}-{tag}.whl'
    dist_info  = f'{name}-{version}.dist-info'
    return write_wheel_file(os.path.join(out_dir, wheel_name), {
        **contents,
        f'{dist_info}/METADATA': make_message({
            'Metadata-Version': '2.1',
            'Name': name,
            'Version': version,
            **metadata,
        }, description),
        f'{dist_info}/WHEEL': make_message({
            'Wheel-Version': '1.0',
            'Generator': 'ziglang make_wheels.py',
            'Root-Is-Purelib': 'false',
            'Tag': tag,
        }),
    })


def write_ziglang_wheel(out_dir, *, version, platform, archive):
    contents = {}
    contents['ziglang/__init__.py'] = b''

    with libarchive.memory_reader(archive) as archive:
        for entry in archive:
            entry_name = '/'.join(entry.name.split('/')[1:])
            if entry.isdir or not entry_name:
                continue

            zip_info = ZipInfo(f'ziglang/{entry_name}')
            zip_info.external_attr = (entry.mode & 0xFFFF) << 16
            contents[zip_info] = b''.join(entry.get_blocks())

            if entry_name.startswith('zig'):
                contents['ziglang/__main__.py'] = f'''\
import os, sys, subprocess
sys.exit(subprocess.call([
    os.path.join(os.path.dirname(__file__), "{entry_name}"),
    *sys.argv[1:]
]))
'''.encode('ascii')

    with open('README.pypi.md') as f:
        description = f.read()

    return write_wheel(out_dir,
        name='ziglang',
        version=version,
        tag=f'py3-none-{platform}',
        metadata={
            'Summary': 'Zig is a general-purpose programming language and toolchain for maintaining robust, optimal, and reusable software.',
            'Description-Content-Type': 'text/markdown',
            'License': 'MIT',
            'Classifier': [
                'License :: OSI Approved :: MIT License',
            ],
            'Project-URL': [
                'Homepage, https://ziglang.org',
                'Source Code, https://github.com/ziglang/zig-pypi',
                'Bug Tracker, https://github.com/ziglang/zig-pypi/issues',
            ],
            'Requires-Python': '~=3.5',
        },
        description=description,
        contents=contents,
    )


def fetch_zig_version_info():
    with urllib.request.urlopen(ZIG_VERSION_INFO_URL) as request:
        return json.loads(request.read())


def fetch_and_write_ziglang_wheels(
    outdir='dist/', zig_version='master', python_version_suffix='', platforms=tuple()
):
    Path(outdir).mkdir(exist_ok=True)
    if not platforms:
        platforms = list(ZIG_PYTHON_PLATFORMS)
    zig_versions_info = fetch_zig_version_info()

    if zig_version == 'latest':
        zig_version = [version for version in zig_versions_info if version != 'master'][0]

    try:
        zig_version_info = zig_versions_info[zig_version]
    except KeyError:
        print(f"Invalid version, valid values: {list(zig_versions_info)}")
        raise

    effective_zig_version = zig_version_info.get('version', zig_version)

    for zig_platform in platforms:
        python_platform = ZIG_PYTHON_PLATFORMS[zig_platform]
        if zig_platform not in zig_version_info:
            print(f"{zig_platform} not present for "
                  f"version {zig_version} / {effective_zig_version}")
            continue
        zig_download = zig_version_info[zig_platform]
        zig_url = zig_download['tarball']
        expected_hash = zig_download['shasum']

        with urllib.request.urlopen(zig_url) as request:
            zig_archive = request.read()
            zig_archive_hash = hashlib.sha256(zig_archive).hexdigest()
            if zig_archive_hash != expected_hash:
                print(zig_download, "SHA256 hash mismatch!")
                raise AssertionError
            print(f'{hashlib.sha256(zig_archive).hexdigest()} {zig_url}')

        wheel_path = write_ziglang_wheel(outdir,
            version=effective_zig_version.replace('-', '.') + python_version_suffix,
            platform=python_platform,
            archive=zig_archive)
        with open(wheel_path, 'rb') as wheel:
            print(f'  {hashlib.sha256(wheel.read()).hexdigest()} {wheel_path}')

def get_argparser():
    parser = argparse.ArgumentParser(prog=__file__, description="Repackage official Zig downloads as Python wheels")
    parser.add_argument('--version', default='latest',
                        help="version to package, use `latest` for latest release, `master` for nightly build")
    parser.add_argument('--suffix', default='', help="wheel version suffix")
    parser.add_argument('--outdir', default='dist/', help="target directory")
    parser.add_argument('--platform', action='append', choices=list(ZIG_PYTHON_PLATFORMS.keys()), default=[],
                        help="platform to build for, can be repeated")
    return parser

def main():
    args = get_argparser().parse_args()
    fetch_and_write_ziglang_wheels(outdir=args.outdir, zig_version=args.version,
                                   python_version_suffix=args.suffix, platforms=args.platform)

if __name__ == '__main__':
    main()
