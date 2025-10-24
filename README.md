# YouTube Scout

## Overview

This repository contains a Python-based desktop application that allows you to search and analyze YouTube videos, playlists, and channels through the YouTube Data API v3. It provides a clean graphical interface built with Tkinter, supporting filters for views, duration, and publication dates — along with thumbnail previews, sortable columns, CSV export, and keyboard shortcuts.

## Features

- Search YouTube for videos, playlists, and channels
- Filter results by minimum view count, duration, and publish date range
- Sort results instantly by any column (views, likes, date, etc.)
- View thumbnails and metadata in a built-in preview panel
- Export search results to CSV for offline analysis
- Open or copy video URLs directly from the app
- Keyboard shortcuts for quick navigation and actions
- Optional thumbnail display using Pillow

## Planned Features



## Requirements

- Python 3.10 or higher
- YouTube Data API v3 key
- Required packages listed in `requirements.txt`

## Installation

1. Clone or download the repository.

2. Ensure that Python 3.10+ is installed on your system. You can download it from the [official Python website](https://www.python.org/downloads/).

3. Install the required dependencies:

```
pip install -r requirements.txt
```

## Usage

Run the application directly from the command line. Once launched, enter a search query such as “guitar pedal review” or “python tutorial.”

Choose which result types to include — videos, playlists, or channels — and apply filters such as minimum views, duration, and publish date range.

Click Search to retrieve and display results. Select a result to preview its details and thumbnail.

Use Export CSV to save your results locally.

Double-click or right-click and choose Open in browser to view the video directly on YouTube.

## Contributing

Contributions to this repository are welcome! If you’d like to suggest improvements, optimize API usage, or expand analytics features, feel free to create a pull request or open an issue.

## License

This project is licensed under the [GNU General Public License](https://www.gnu.org/licenses/gpl-3.0.en.html).
