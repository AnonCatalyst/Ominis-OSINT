from setuptools import setup, find_packages

setup(
    name='Ominis-OSINT',
    version='4.7',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    install_requires=[
        'beautifulsoup4',
        'colorama',
        'fake_useragent',
        'requests',
        'serpapi',
        'google-search-results',
        'httpx',
        'tenacity',
        'requests_html',
        'aiohttp',
        'urllib3',
        'asyncio',
        'lxml_html_clean',
        'html_clean',
        'tqdm',
        'anyio>=4.4.0',
        'zipp>=3.19.1',
    ],
    entry_points={
        'console_scripts': [
            'omnis=omnis:main',  # Assuming `omnis.py` has a `main` function
        ],
    },
    include_package_data=True,
    description='Discover online mentions of a query or username. Identify potential social profiles and forums.',
    author='AnonCatalyst',
    author_email='hard2ind.co.01@gmail.com',
    url='https://github.com/AnonCatalyst/omnis-osint',  # Update with your actual GitHub URL
    license='MIT',  # Choose a license that fits your project
)
