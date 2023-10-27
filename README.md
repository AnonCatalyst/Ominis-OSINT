># Ominis OSINT Toolkit 🌐🕵️‍♂️

**Information Obtained**
    Discover online mentions of a query or username.
    Identify potential social profiles and forums.
    Enhance web searches with SerpApi for more accurate results.

**Why Ominis?**
    Ominis offers a unified solution for multiple OSINT tasks.
    Threading improves efficiency for username searches.
    SerpApi integration enhances web search capabilities.

**Contributing**
Contributions are welcome! Fork the repository, make changes, and submit a pull request.
License

This project is licensed under the MIT License - see the LICENSE file for details.

🚀 Happy OSINTing! 🕵️‍♂️

<img src="src/img/screenshot.png" alt="Ominis Osint Project - screenshot" width="550" height="430"/>

Ominis OSINT Tool is a powerful open-source tool designed for OSINT (Open-Source Intelligence) investigations. It combines three scripts to perform web searches, username searches, and gather information using the SerpApi service.

## Features

- **Web Search (Google):**
  - Search the web for a given query.
  - Extracts information from search results.
  - Detects mentions in titles and URLs.

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
