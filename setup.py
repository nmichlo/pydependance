import setuptools

# ========================================================================= #
# HELPER                                                                    #
# ========================================================================= #


with open("README.md", "r", encoding="utf-8") as file:
    long_description = file.read()

with open("requirements.txt", "r") as f:
    install_requires = (req[0] for req in map(lambda x: x.split("#"), f.readlines()))
    install_requires = [req for req in map(str.strip, install_requires) if req]


# ========================================================================= #
# SETUP                                                                     #
# ========================================================================= #


setuptools.setup(
    name="pydependance",
    author="Nathan Juraj Michlo",
    author_email="NathanJMichlo@gmail.com",
    version="0.1.0",
    python_requires=">=3.10",
    packages=setuptools.find_packages(),
    install_requires=install_requires,
    url="https://github.com/nmichlo/pydependance",
    description="Python local package dependency discovery and resolution",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.10",
    ],
)


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
