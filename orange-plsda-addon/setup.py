from setuptools import setup, find_packages

setup(
    name="orangeplsda",
    version="0.1.0",
    description="PLS-DA & OPLS-DA with S-Plot — classification, "
                "biomarker discovery, and orthogonal signal correction "
                "for Orange3",
    packages=find_packages(),
    include_package_data=True,
    author="Philipp Weller",
    author_email="philipp.weller@googlemail.com",
    install_requires=[
        "Orange3>=3.40.0",
        "numpy",
        "scikit-learn",
    ],
    entry_points={
        "orange.widgets": (
            "PLS-DA = orangeplsda.widgets",
        ),
    },
    package_data={
        "orangeplsda": ["widgets/icons/*.svg"],
    },
    project_urls={
        "Source": "https://github.com/philippweller/WellerLab/tree/main/orange-plsda-addon",
        "Bug Tracker": "https://github.com/philippweller/WellerLab/issues",
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)