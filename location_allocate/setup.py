import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'location_allocate'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/schemas/legacy',
         ['../schemas/legacy/lfs_schema_v1.json']),
        ('share/' + package_name + '/schemas',
         ['../schemas/paper_candidate_schema_v2.json']),
        ('share/' + package_name + '/config', ['config/lfs_policy.template.yaml']),
        ('share/' + package_name + '/prompts', glob('prompts/*')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=[
        'setuptools',
        'jsonschema',
        'openai',
        'httpx',
        'numpy',
        'scipy',
    ],
    zip_safe=True,
    maintainer='chen',
    maintainer_email='chen@todo.todo',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'location_allocate = location_allocate.location_allocate:main'
        ],
    },
)
