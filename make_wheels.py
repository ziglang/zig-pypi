import argparse
import hashlib
import io
import json
import os
import tarfile
import urllib.request
from email.message import EmailMessage
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from wheel.wheelfile import WheelFile

ZIG_VERSION_INFO_URL = 'https://ziglang.org/download/index.json'
ZIG_PYTHON_PLATFORMS = {
    'x86_64-windows': 'win_amd64',
    'x86_64-macos':   'macosx_10_9_x86_64',
    'aarch64-macos':  'macosx_11_0_arm64',
    'i386-linux':     'manylinux_2_12_i686.manylinux2010_i686.musllinux_1_1_i686',
    'x86_64-linux':   'manylinux_2_12_x86_64.manylinux2010_x86_64.musllinux_1_1_x86_64',
    'aarch64-linux':  'manylinux_2_17_aarch64.manylinux2014_aarch64.musllinux_1_1_aarch64',
    # no longer present?
    # 'armv7a-linux':   'manylinux_2_17_armv7l.manylinux2014_armv7l.musllinux_1_1_armv7l',
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


def iter_archive_contents(archive):
    magic = archive[:4]
    if magic[:4] == b"\xfd7zX":
        with tarfile.open(mode="r|xz", fileobj=io.BytesIO(archive)) as tar:
            for entry in tar:
                if entry.isreg():
                    yield entry.name, entry.mode | (1 << 15), tar.extractfile(entry).read()
    elif magic[:4] == b"PK\x03\x04":
        with ZipFile(io.BytesIO(archive)) as zip_file:
            for entry in zip_file.infolist():
                yield entry.filename, entry.external_attr >> 16, zip_file.read(entry)
    else:
        raise RuntimeError("Unsupported archive format")

def write_ziglang_wheel(out_dir, *, version, zig_version, platform, archive):
    contents = {}

    contents['ziglang/__main__.py'] = b'''\
import sys

from . import main

if __name__ == "__main__":
    sys.exit(main())
'''

    for entry_name, entry_mode, entry_data in iter_archive_contents(archive):
        entry_name = '/'.join(entry_name.split('/')[1:])
        if not entry_name:
            continue

        zip_info = ZipInfo(f'ziglang/{entry_name}')
        zip_info.external_attr = (entry_mode & 0xFFFF) << 16
        contents[zip_info] = entry_data

        if entry_name.startswith('zig'):
            contents['ziglang/__init__.py'] = f'''\
import os
import subprocess
import sys

__version__ = "{version}"
__zig_version__ = "{zig_version}"
__zig_local_path__ = "{entry_name}"
__zig_path__ = os.path.join(os.path.dirname(__file__), __zig_local_path__)

__all__ = ["zig"]


def zig(*args, **kwargs):
    return subprocess.call([__zig_path__, *args], **kwargs)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    return zig(*argv)
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


def fetch_and_write_ziglang_wheels(outdir='dist/', zig_version='master', python_version_suffix='', platforms=tuple()):
    if not platforms:
        platforms = list(ZIG_PYTHON_PLATFORMS)
    zig_versions_info = fetch_zig_version_info()

    try:
        zig_version_info = zig_versions_info[zig_version]
    except KeyError:
        print(f"Invalid version, valid values: {list(zig_versions_info.keys())}")
        raise

    effective_zig_version = zig_version_info.get('version', zig_version)

    for zig_platform in platforms:
        python_platform = ZIG_PYTHON_PLATFORMS[zig_platform]
        zig_download = zig_version_info[zig_platform]
        zig_url = zig_download['tarball']
        expected_hash = zig_download['shasum']
        with urllib.request.urlopen(zig_url) as request:
            zig_archive = request.read()
            zig_archive_hash = hashlib.sha256(zig_archive).hexdigest()
            if zig_archive_hash != expected_hash:
                print(zig_download, "SHA256 hash mismatch!")
                raise AssertionError

            print(f'{zig_archive_hash} {zig_url}')

        wheel_path = write_ziglang_wheel(outdir,
            version=effective_zig_version.replace('-', '.') + python_version_suffix,
            zig_version=effective_zig_version,
            platform=python_platform,
            archive=zig_archive)
        with open(wheel_path, 'rb') as wheel:
            print(f'  {hashlib.sha256(wheel.read()).hexdigest()} {wheel_path}')

def get_argparser():
    parser = argparse.ArgumentParser(prog=__file__, description="Repackage official Zig downloads as Python wheels")
    parser.add_argument("--version", default="0.10.1")
    parser.add_argument("--suffix", default=".post2")
    parser.add_argument("--outdir", default="dist/")
    parser.add_argument("--platform", action="append", choices=list(ZIG_PYTHON_PLATFORMS.keys()), default=[])
    return parser

def main():
    args = get_argparser().parse_args()
    fetch_and_write_ziglang_wheels(zig_version=args.version, python_version_suffix=args.suffix, platforms=args.platform)

if __name__ == '__main__':
    main()
