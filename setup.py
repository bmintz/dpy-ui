from setuptools import setup

def _read(file):
    with open(file) as f:
        return f.read()

readme = _read('README.md')
# get version without importing the package
exec(compile(_read('discord/ext/ui/version.py'), 'discord/ext/ui/version.py', 'exec'))

setup(
    name='discord.py-ui',
    author='Ikusaba-san',
    url='https://github.com/Ikusaba-san/discord.py-ui',
    version=__version__,
    packages=['discord.ext.ui'],
    license='MIT',
    description='User interaction utilities for discord.py.',
    long_description=readme,
    include_package_data=True,
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Topic :: Internet',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Utilities',
    ]
)