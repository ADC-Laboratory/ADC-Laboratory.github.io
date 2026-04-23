# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is the ADC Lab website — a static HTML site for the Autonomous Decision Control Laboratory at the University of Science and Technology Beijing. The site focuses on reinforcement learning, optimal control, and adaptive dynamic programming research.

## Development

**Local Development:**
```bash
npx browser-sync start --server --files "*.html, assets/**/*.css, assets/**/*.js"
```
BrowserSync will auto-reload the browser when HTML/CSS/JS files change.

## Structure

- **Root**: Contains 5 main HTML pages (`index.html`, `people.html`, `publications.html`, `software.html`, `teaching.html`) plus `benchmark_*.html` iframe pages
- **assets/css/main.css**: Primary stylesheet (also has `fontawesome-all.min.css`)
- **assets/js/**: jQuery and utility JS files (`main.js`, `util.js`, `breakpoints.min.js`, `browser.min.js`, `jquery.min.js`, `jquery.dropotron.min.js`)
- **assets/sass/**: SCSS source files (libs/ contains mixins, functions, variables)
- **assets/webfonts/**: Font Awesome webfonts
- **images/**: Lab member photos, banners, and logos
- **benchmark_dsact.html / benchmark_run2.html**: Embedded iframe pages for software benchmarks

## Design

Template from HTML5 UP (Stellar). Uses Font Awesome icons, jQuery for mobile navigation dropdowns, and responsive breakpoints in `breakpoints.min.js`.

## Publication Updater Tool

The `tool/` directory contains a Python script to fetch publications from Google Scholar and update `publications.html` automatically.

**Setup:**
```bash
cd tool && pip install -r requirements.txt
```

**Run:**
```bash
python tool/fetch_scholar.py
```

See `tool/README.md` for full usage details. The tool caches results to avoid Google Scholar rate limits.

## Notes

- No build tools or compilation required — pure static HTML/CSS/JS
- External links: GitHub org (ADC-laboratory), arXiv papers, GOPS documentation
- Contact email: duanjl15@163.com
