import os
import hashlib
import urllib.request
import tarfile
import gzip
from email.message import EmailMessage
from wheel.wheelfile import WheelFile, get_zipinfo_datetime
from zipfile import ZipInfo, ZIP_DEFLATED
import libarchive # from libarchive-c
import packaging.tags


zig_version = '0.8.0'
release_table = {
    'windows-i386':   'win32',
    'windows-x86_64': 'win_amd64',
    'macos-x86_64':   'macosx_10_9_x86_64',
    'macos-aarch64':  'macosx_11_0_arm64',
    'linux-i386':     'manylinux_2_12_i686.manylinux2010_i686',
    'linux-x86_64':   'manylinux_2_12_x86_64.manylinux2010_x86_64',
    'linux-aarch64':  'manylinux_2_17_aarch64.manylinux2014_aarch64',
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


def fetch_zig_archive(platform):
    url = f'https://ziglang.org/download/{zig_version}/zig-{platform}-{zig_version}.' + \
            ('zip' if platform.startswith('windows-') else 'tar.xz')
    with urllib.request.urlopen(url) as request:
        return request.read()


def build_sdist(sdist_directory, config_settings=None):
    source_date_epoch = os.environ.get('SOURCE_DATE_EPOCH')
    mtime = int(source_date_epoch) if source_date_epoch else None

    file = gzip.GzipFile(
        os.path.join(sdist_directory, f'ziglang-{zig_version}.tar.gz'),
        mode='wb',
        mtime=mtime)
    tar = tarfile.TarFile(
        mode='w',
        fileobj=file,
        format=tarfile.PAX_FORMAT)

    for file in (
        'pyproject.toml',
        'make_wheels.py',
        'LICENSE.txt',
        'README.md',
        'README.pypi.md',
    ):
        tar.add(file, f'ziglang-{zig_version}/{file}')

    return f'ziglang-{zig_version}.tar.gz'


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    for python_tag in packaging.tags._platform_tags():
        for zig_platform, python_platform in release_table.items():
            if python_tag in python_platform.split('.'):
                zig_archive = fetch_zig_archive(zig_platform)
                return write_ziglang_wheel(wheel_directory,
                    version=zig_version,
                    platform=python_platform,
                    archive=zig_archive)


if __name__ == '__main__':
    for zig_platform, python_platform in release_table.items():
        zig_archive = fetch_zig_archive(zig_platform)
        print(f'{hashlib.sha256(zig_archive).hexdigest()} {zig_url}')

        wheel_path = write_ziglang_wheel('dist/',
            version=zig_version,
            platform=python_platform,
            archive=zig_archive)
        with open(wheel_path, 'rb') as wheel:
            print(f'  {hashlib.sha256(wheel.read()).hexdigest()} {wheel_path}')
