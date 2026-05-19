from setuptools import setup, Extension
import numpy as np

ext = Extension(
    "src._fraud",
    sources=["src/_fraud.c"],
    include_dirs=[np.get_include()],
    extra_compile_args=["-O3", "-ffast-math"],
)

setup(
    name="fraud",
    ext_modules=[ext],
)
