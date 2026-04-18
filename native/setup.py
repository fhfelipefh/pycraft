from setuptools import Extension, setup

import pybind11


ext_modules = [
    Extension(
        name="_voxel_native",
        sources=["voxel_native.cpp"],
        include_dirs=[pybind11.get_include()],
        language="c++",
        extra_compile_args=["-O3", "-std=c++17"],
    )
]


setup(
    name="pycraft-voxel-native",
    version="0.1.0",
    description="Native acceleration helpers for PyCraft",
    ext_modules=ext_modules,
)
