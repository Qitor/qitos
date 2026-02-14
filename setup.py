"""QitOS Framework v3.1 Setup Configuration"""

from setuptools import setup, find_packages
import os
import re

# Read version from __init__.py
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'qitos', '__init__.py'), encoding='utf-8') as f:
    init_content = f.read()
    version_match = re.search(r'^__version__ = [\'"]([^\'"]*)[\'"]', init_content, re.M)
    if version_match:
        __version__ = version_match.group(1)
    else:
        __version__ = "3.1.0-alpha"

# Read long description from README
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='qitos',
    version=__version__,
    description='QitOS Framework v3.1 - A state-driven Agent framework for developer happiness',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='QitOS Team',
    author_email='team@qitos.dev',
    url='https://github.com/qitos/framework',
    license='MIT',
    
    # Package structure
    packages=find_packages(exclude=['tests*', 'examples*']),
    package_dir={
        'qitos': 'qitos',
        'qitos.core': 'qitos/core',
        'qitos.engine': 'qitos/engine',
        'qitos.cli': 'qitos/cli',
        'qitos.utils': 'qitos/utils',
    },
    
    # Entry points for CLI
    entry_points={
        'console_scripts': [
            'qitos=qitos.cli.main:main',
        ],
    },
    
    # Python version requirement
    python_requires='>=3.8',
    
    # Classifiers
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
        'Topic :: Software Development :: Libraries :: Python Frameworks',
    ],
    
    # Keywords
    keywords=[
        'agent', 'ai', 'llm', 'openai', 'anthropic', 
        'framework', 'state-driven', 'developer-tools'
    ],
    
    # Install_requires (minimal - core has no dependencies)
    install_requires=[],
    
    # Optional dependencies
    extras_require={
        'dev': [
            'pytest>=7.0.0',
            'pytest-cov>=4.0.0',
            'black>=23.0.0',
            'flake8>=6.0.0',
            'mypy>=1.0.0',
        ],
        'openai': ['openai>=1.0.0'],
        'anthropic': ['anthropic>=0.3.0'],
        'cli': ['rich>=13.0.0'],
        'all': [
            'openai>=1.0.0',
            'anthropic>=0.3.0',
            'pyyaml>=6.0',
            'rich>=13.0.0',
        ],
    },
    
    # Include package data
    include_package_data=True,
    
    # ZIP-safe
    zip_safe=False,
)
