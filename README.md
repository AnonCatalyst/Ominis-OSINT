># Ominis OSINT Toolkit 🌐🕵️‍♂️©

**Information Obtained**
    Discover online mentions of a query or username.
    Identify potential social profiles and forums.
    Enhance web searches with SerpApi for more accurate results.


-- **NOTE:** `Hellow World 🌍 👋 - an update for Ominis-Osint is currently being worked on so expect faulty runs with thee script until official release! 😉`


## Compatibility and Future Releases

📱 **Mobile Compatibility:** Please note that Ominis OSINT Toolkit is primarily designed for use on PC platforms and may not work on mobile environments such as Termux. However, a mobile release is being considered for future development to extend the toolkit's accessibility to mobile users. Stay tuned for updates!

**Contributing**
Contributions are welcome! Fork the repository, make changes, and submit a pull request.

> **License**
This project is licensed under the MIT License - see the LICENSE file for details.

🚀 Happy OSINTing! 🕵️‍♂️

<img src="src/img/screenshot.png" alt="Ominis Osint Project - screenshot" width="550" height="430"/>

Ominis OSINT Tool is a powerful open-source tool designed for OSINT (Open-Source Intelligence) investigations. It combines three scripts to perform web searches, username searches, and gather information using the SerpApi service.

## Features

🚀 Enhanced User Interface

Enjoy a redesigned interface for a seamless experience, suitable for both novice and experienced users.
🔎 Expanded Digital Reconnaissance

Conduct thorough investigations with advanced tools to gather and analyze publicly available information from diverse online sources.
💡 Threading Optimization

Experience faster execution times with optimized threading, improving efficiency and reducing waiting periods during username searches.
🔍 Advanced SerpApi Integration

Utilize the power of SerpApi for lightning-fast and accurate web searches, enhancing speed and reliability while maintaining anonymity.
📊 Detailed Results

Gain comprehensive insights from search results, including detailed information extracted from various sources such as social profiles, mentions, and potential forum links.

Upon running the script, you will be prompted to enter a search query. After entering the query, the tool will scrape Google search results for relevant information, including titles, URLs, and social media profiles. The results will be displayed in the terminal, providing insights into web mentions and associated social profiles.
⚙️ Proxy Validation

The tool validates proxies for secure and efficient web requests, ensuring anonymity and privacy during the search process. This feature enhances the reliability of the search results by utilizing a pool of validated proxies, mitigating the risk of IP blocking and ensuring seamless execution of the search queries.
🕵️‍♂️ Human-like Behavior Mimicking

To mimic human-like behavior and avoid detection by anti-bot mechanisms, the tool randomizes user agents for each request. This helps in making the requests appear more natural and reduces the likelihood of being flagged as automated activity.
🛡️ Randomized Proxy Agents

In addition to proxy validation, the tool utilizes randomized proxy agents for each request, further enhancing user anonymity. By rotating through a pool of proxies, the tool reduces the chances of being tracked or identified by websites, thus safeguarding user privacy throughout the reconnaissance process.

These measures collectively contribute to ensuring user anonymity and privacy, providing a secure environment for conducting digital reconnaissance activities.

- **Username Search:**
  - Searches a list of URLs for a specific username.
  - Utilizes threading for parallel execution.
  - Provides detailed results with URL and HTTP status code.

- **SerpApi Integration:**
  - Utilizes SerpApi for enhanced web searches.
  - Retrieves Google search results programmatically.
  - Option to use SerpApi with your API key (optional).

### Digital Reconnaissance
Positioned as a robust solution for digital reconnaissance, Ominis OSINT Tools excels in gathering and analyzing publicly available information from online sources. The toolkit empowers users with the capability to navigate and extract valuable insights from the vast landscape of digital data.

### Targeted and Actionable Results
Ominis OSINT Tools is dedicated to delivering results that are not only targeted but also actionable. The emphasis is on providing users with information that is relevant to their investigations and capable of guiding informed decision-making.

![Watch the video](src/img/video.gif)

## Key Features
- **User-Friendly Interface:** Meticulously designed for ease of use, ensuring a smooth experience for both novice and experienced users.
- **Digital Reconnaissance Excellence:** Leverage the toolkit's strength in digital reconnaissance to uncover valuable insights.

- **Results:**
   - Results are displayed in the terminal with detailed information.
   - Social profiles, mentions, and potential forum links are extracted.

## Configuration

- Web search uses Google by default.
- Configure the list of URLs in `src/urls.txt` for username searches.

## Installation
   ```
   git clone https://github.com/AnonCatalyst/Ominis-Osint
   pip install -r requirements.txt
   ```
>>## Usage

1. Navigate to the script's directory:
   - `cd Ominis-OSINT`
3. Run the desired script:
   - `python3 Ominis.py`

## SerpApi Integration (Optional)

- To use SerpApi for web searches, obtain an API key from the [SerpApi Dashboard](https://serpapi.com/dashboard).
- Save the API key in `src/api_key.json` file.
