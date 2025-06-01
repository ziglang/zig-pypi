Zig PyPI distribution
=====================

[Zig][] is a general-purpose programming language and toolchain for maintaining robust, optimal, and reusable software. The [ziglang][pypi] Python package redistributes the Zig toolchain so that it can be used as a dependency of Python projects.

[zig]: https://ziglang.org/
[pypi]: https://pypi.org/project/ziglang/

Rationale
---------

Although Zig is useful in itself, the Zig toolchain includes a drop-in C and C++ compiler, [`zig cc`][zigcc], based on [clang][]. Unlike clang itself, `zig cc` is standalone: it does not require additional development files to be installed to target any of the platforms it supports. Through `zig cc`, Python code that generates C or C++ code can build it without any external dependencies.

[clang]: https://clang.llvm.org/
[zigcc]: https://andrewkelley.me/post/zig-cc-powerful-drop-in-replacement-gcc-clang.html

Usage
-----
To install and run the Zig toolchain from the command line, use:

```shell
pip install ziglang
python -m ziglang
```

To run the Zig toolchain from a Python program, use `sys.executable` to locate the Python binary to invoke. For example:

```python
import sys, subprocess

subprocess.call([sys.executable, "-m", "ziglang"])
```

Binary wrapper
--------------

The [ziglang][pypi] Python package installs a binary wrapper for the Zig compiler under the name `python-zig`; the name is different to avoid conflicts with any system-wide or user-wide `zig` binaries that may be already installed.


Using with `uv`
---------------

The Zig compiler distributed in this Python package can be launched by [uv](https://docs.astral.sh/uv) without installation:

```shell
uvx --from ziglang python-zig
License
-------

The [Zig license](https://github.com/ziglang/zig#license).
