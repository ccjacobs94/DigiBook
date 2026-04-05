# Features Track Record

> **CODE NORM:** Any agent or contributor adding a new feature to this project MUST add the feature and a description of what it is to this file. This ensures that everyone can see and understand what the code can currently do.

## Existing Features

- **Name a new audiobook:** Ability to provide a name for a new audiobook being digitized.
- **Interactively rip one disk at a time:** Process of copying audio data from individual audiobook CDs to the disk.
- **Automatically merge ripped disks into a single MP3 file:** Combines the ripped audio from multiple disks into one cohesive MP3 file for easy listening.
- **View your local library of processed audiobooks:** Interface to browse the collection of audiobooks that have been digitized and merged.
- **Enhanced Metadata Selection via Open Library:** When adding a book or editing metadata, users can search Open Library in real-time by title. A list of matching results is displayed, allowing the user to select the exact edition they own. This automatically populates accurate metadata (Title, Author, Year, Cover Art, ISBN, and Description), which is embedded into the final MP3 files using mutagen. Users can still manually override these fields.
- **Sort by Metadata:** Users can now sort their local library of processed audiobooks by metadata (Date Added, Title, Author, Year) in ascending or descending order. This helps navigate larger libraries more easily.
- **In-Browser Playback:** Users can now click on a book cover in their library to listen to the audiobook directly in the browser via an HTML5 audio player. The playback position is automatically saved and restored using local storage.
- **One-Click "Auto-Digitize" Mode:** A hands-free automation mode that automatically detects a newly inserted CD, rips it, ejects the tray, and prompts for the next disk with an audio cue, minimizing manual interaction during the conversion process.
- **Enhanced Audiobook Player Controls & Persistence:** In-browser audio player now features variable playback speeds, a sleep timer, and visual bookmarks. The library dashboard visually tracks playback progress and allows one-click resumption of listening directly to the saved position.
- **Automatic Variable Bitrate (VBR) Duration Correction:** Implements a second ffmpeg pass (`-write_xing 1`) when merging audiobook disks to generate an accurate Xing/Info VBR header. This resolves incorrect duration calculations in media players without requiring full audio transcoding, ensuring users can accurately seek through long audiobooks.
- **Specialized Audiobook Encoding & Automated Chapter Detection:** Users can choose to export audiobooks as specialized `.m4b` files or standard `.mp3` files. The system automatically detects original disk tracks and creates embedded chapter markers for easy navigation. The web player UI extracts these chapters and displays them for one-click skipping between sections.
- **Mobile-First Responsive UI & PWA:** Transforms the desktop interface into a touch-friendly Progressive Web App installable on mobile devices, with dynamic layout adjustments for screens down to 360px.
- **Cross-Device Sync:** Syncs playback progress via a backend SQLite database (`metadata.db`) so users can seamlessly resume listening across multiple devices without losing their place.
