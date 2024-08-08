from setuptools import setup, find_packages

setup(
    name='Ominis-OSINT',
    version='4.7',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    python_requires='>=3.9',
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
        'anyio>=4.4.0',  # not directly required, pinned by Snyk to avoid a vulnerability
        'zipp>=3.19.1',  # not directly required, pinned by Snyk to avoid a vulnerability
    ],
    entry_points={
        'console_scripts': [
            'ominis=ominis:main',
        ],
    },
    include_package_data=True,
    description='Discover online mentions of a query or username. Identify potential social profiles and forums.',
    long_description="""
    🌐 Premier Digital Reconnaissance Solution
    
    Ominis OSINT Secure Web-Hunter stands as a premier solution for digital reconnaissance, offering unparalleled capabilities in gathering, analyzing, and interpreting publicly available information sourced from diverse online platforms. With its comprehensive suite of features, Ominis equips users to navigate through the expansive digital landscape with precision and efficiency, enabling the extraction of valuable insights from a myriad of sources.
    
    🔍 Comprehensive Data Gathering
    
    From scouring social media platforms and forums to parsing through web pages and search engine results, Ominis OSINT leaves no stone unturned in the quest for relevant data. Its robust functionality encompasses advanced techniques for data collection, including scraping proxies, asynchronous HTTP requests, and intelligent pattern matching. This ensures that users can access a wealth of information while adhering to the highest standards of data integrity and security.
    
    📊 Sophisticated Analysis Capabilities
    
    Moreover, Ominis OSINT goes beyond mere data retrieval, providing sophisticated analysis tools to uncover hidden connections, identify emerging trends, and discern actionable intelligence from vast troves of digital content. Whether it's investigating potential threats, conducting due diligence, or gathering competitive intelligence, Ominis empowers users with the insights they need to make informed decisions and stay ahead in an increasingly complex digital landscape.
    
    🛠️ Cutting-edge Technology
    
    In essence, Ominis OSINT redefines digital reconnaissance, offering a comprehensive solution that combines cutting-edge technology with intuitive functionality. By harnessing the power of publicly available data, Ominis enables users to unlock new opportunities, mitigate risks, and navigate the digital realm with confidence and precision.
    """,
    long_description_content_type='text/markdown',
    author='AnonCatalyst',
    author_email='hard2find.co.01@gmail.com',
    url='https://github.com/AnonCatalyst/Ominis-OSINT',
    license='MIT',
)
