from setuptools import setup, find_packages

setup(
    name="oranjenmr",
    version="0.1.0",
    description="NMR Preprocessing Widgets for Orange3 — binning, normalization, "
                "baseline correction, filtering, region exclusion, and alignment",
    packages=find_packages(),
    include_package_data=True,
    author="Philipp Weller",
    author_email="philipp.weller@googlemail.com",
    install_requires=[
        "Orange3>=3.40.0",
        "numpy>=1.22",
        "scipy>=1.9",
    ],
    extras_require={"full": ["orangecontrib.spectroscopy>=0.6"]},
    entry_points={
        "orange.widgets": (
            "NMR Preprocessing = oranjenmr.widgets",
        ),
    },
    package_data={
        "oranjenmr": ["widgets/icons/*.svg"],
    },
    project_urls={
        "Source": "https://github.com/philippweller/WellerLab/tree/main/orange-nmr-addon",
        "Bug Tracker": "https://github.com/philippweller/WellerLab/issues",
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Chemistry :: NMR",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
    ],
    keywords="nmr, preprocessing, chemometrics, orange3, widget",
    python_requires=">=3.9",
)