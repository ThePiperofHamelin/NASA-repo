# NASA SPHEREx WebViewer

An interactive celestial deep-sky explorer and visualization engine built for NASA's **SPHEREx** (Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer) mission data.

The application pairs a high-performance **Python/Flask** backend for astronomical data access, WCS reprojection, and multi-band composite rendering with a responsive **Next.js/React** frontend powered by **Aladin Lite**.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [SPHEREx Detectors & Bandpasses](#spherex-detectors--bandpasses)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Option A: Docker Compose (Recommended)](#option-a-docker-compose-recommended)
  - [Option B: Local Development](#option-b-local-development)
    - [1. Backend Setup](#1-backend-setup)
    - [2. Frontend Setup](#2-frontend-setup)
- [CLI Utilities](#cli-utilities)
  - [Tile Prewarming](#tile-prewarming)
  - [Mosaic Stitching](#mosaic-stitching)
- [API Reference](#api-reference)
  - [Grid & Cells](#1-get-apicells)
  - [Cell Exposures](#2-get-apicellscell_idexposures)
  - [Tile Rendering](#3-get-apicellscell_idtilesexposure_idpng)
  - [Direct Cutout Retrieval](#4-get-apigetpic)
- [Configuration & Environment Variables](#configuration--environment-variables)
- [Prototypes](#prototypes)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## Overview

NASA's **SPHEREx** mission surveys the entire sky across 102 near-infrared spectral bands. Handling and visualizing this volume of spectral imagery presents unique challenges: FITS data files are large, observations must be reprojected onto celestial coordinates, and zodiacal light backgrounds must be removed before combining multiple detectors into meaningful colour images.

**NASA SPHEREx WebViewer** solves these problems with an end-to-end processing and visualization pipeline:

1. **Partitioned Sky Grid:** Divides the celestial sphere into a uniform ~1° × 1° coordinate grid to request, cache, and serve imagery in bite-sized chunks.
2. **On-the-Fly SIA2 Search:** Directly queries the IPAC Infrared Science Archive (IRSA) Simple Image Access v2 (SIA2) service for observations in `spherex_dr1` and `spherex_qr3`.
3. **Scientific Processing Pipeline:** Performs zodiacal light subtraction (`IMAGE` − `ZODI`), cold-pixel suppression (MAD filter), and hole filling on each FITS cutout.
4. **Lupton Asinh RGB Composites:** Dynamically pairs short- and long-wavelength detectors (e.g., D1+D4, D2+D5, D3+D6) to generate false-colour RGBA tiles with Lupton asinh stretch.
5. **Interactive Aladin Lite Viewer:** Delivers seamless pan and zoom across the sky with coordinate navigation, live metadata tracking, and visual analysis tools.

---

## Key Features

### Frontend (Next.js & Aladin Lite)
- **Deep-Sky Canvas:** Integrates **Aladin Lite v3** for smooth, hardware-accelerated pan and zoom with field-of-view (FoV) clamping between 0.05° and 2.0°.
- **Coordinate Navigator (Go To Box):** Quick-jump HUD allowing direct entry of Right Ascension ($0^\circ \le \text{RA} < 360^\circ$) and Declination ($-90^\circ \le \text{Dec} \le +90^\circ$).
- **Observation Metadata Panel:** Real-time HUD displaying the current celestial position (RA/Dec), active viewer status, and the exact UTC observation timestamp computed from Modified Julian Date (MJD).
- **Guided Discovery Tour:** A built-in 4-step interactive walkthrough explaining SPHEREx imagery, coordinate systems, contrast inspection, and multi-epoch temporal variation analysis.
- **Image Inversion Filter:** Instant contrast inversion toggle for inspecting faint structures and high-contrast features without modifying raw data.
- **Dynamic Tile Queue & Footprints:** Displays dashed bounding footprints over loading cells and prioritizes downloading tiles closest to the center of view.
- **Theme Support:** Dark and light mode switching via `next-themes`.

### Backend (Flask & Astropy)
- **Fast Bilinear Reprojection:** Custom bilinear interpolation engine (`reproject_interp`) that resamples FITS cutouts onto standard tangential (TAN) WCS projections matching SPHEREx's native 6.15″/pixel resolution.
- **Zodiacal Light Subtraction:** Isolates celestial sources by automatically subtracting the zodiacal light model (`ZODI`) extension from the observed `IMAGE` extension.
- **Lupton RGB Stretch:** Produces balanced, physically motivated false-colour composites using `astropy.visualization.make_lupton_rgb` ($Q = 8.0, \text{stretch} = 1.5$).
- **Multi-Image Mosaic Stitcher:** Command-line tool to co-add and stitch multiple FITS images into a single cohesive PNG mosaic with automated WCS framing and dynamic range clipping.
- **Multi-Tier File Cache:** Transparently caches SIA2 search results (JSON), raw cutouts (FITS), and fully rendered colour tiles (PNG) to prevent redundant remote requests.
- **Fine-Grained Concurrency:** Reentrant key-level lock pool (`KeyedLock`) and bounded semaphores to protect concurrent tile generation and avoid hammering upstream IRSA endpoints.
- **Tile Prewarming Utility:** Background job to fetch and render tiles ahead of time for targeted coordinates and fields of view.

---

## System Architecture

```
                      +---------------------------------------+
                      |       Client Browser (Next.js)        |
                      |   Aladin Lite v3 + React HUD UI       |
                      +-------------------+-------------------+
                                          |
                                          | Rewrites /api/*
                                          v
                      +---------------------------------------+
                      |         Flask API (Port 8000)         |
                      |   - /api/cells                        |
                      |   - /api/cells/<cell>/exposures       |
                      |   - /api/cells/<cell>/tiles/<exp>.png |
                      |   - /api/getPic                       |
                      +---------+-------------------+---------+
                                |                   |
             Local Disk Cache   |                   | SIA2 Query &
             (JSON, FITS, PNG)  |                   | Cutout Stream
                                v                   v
                      +-------------------+   +-----------------------+
                      |  .cache / Volume  |   |   NASA / IPAC IRSA    |
                      |  - tiles/         |   |   SPHEREx Archive     |
                      |  - cutouts/       |   |   (DR1 & QR3 SIA2)    |
                      |  - search/        |   +-----------------------+
                      +-------------------+
```

---

## SPHEREx Detectors & Bandpasses

SPHEREx carries six detectors arranged in pairs. Each pair covers complementary short- and long-wavelength infrared regimes:

| Detector | Type | Wavelength Range | Paired Detector | RGB Channel Role |
| :--- | :--- | :--- | :--- | :--- |
| **SPHEREx-D1** | Short Wavelength | $0.75\ \mu\text{m} - 1.09\ \mu\text{m}$ | SPHEREx-D4 | **Blue** (Short) |
| **SPHEREx-D2** | Short Wavelength | $1.10\ \mu\text{m} - 1.62\ \mu\text{m}$ | SPHEREx-D5 | **Blue** (Short) |
| **SPHEREx-D3** | Short Wavelength | $1.63\ \mu\text{m} - 2.41\ \mu\text{m}$ | SPHEREx-D6 | **Blue** (Short) |
| **SPHEREx-D4** | Long Wavelength | $2.42\ \mu\text{m} - 3.82\ \mu\text{m}$ | SPHEREx-D1 | **Red** (Long) |
| **SPHEREx-D5** | Long Wavelength | $3.83\ \mu\text{m} - 4.41\ \mu\text{m}$ | SPHEREx-D2 | **Red** (Long) |
| **SPHEREx-D6** | Long Wavelength | $4.42\ \mu\text{m} - 5.00\ \mu\text{m}$ | SPHEREx-D3 | **Red** (Long) |

### RGB Channel Synthesis
In the tile renderer:
- **Blue Channel:** Short-wavelength detector (D1, D2, or D3)
- **Red Channel:** Paired long-wavelength detector (D4, D5, or D6)
- **Green Channel:** Synthesized synthetic midpoint: $\text{Green} = \frac{\text{Blue} + \text{Red}}{2}$
- **Stretch:** Lupton asinh color scaling mapping the dynamic range without saturating star cores.

---

## Getting Started

### Prerequisites

- **Docker & Docker Compose** (for containerized deployment), **OR**
- **Python 3.12+** and **Bun** (or Node.js 20+) for local development.

---

### Option A: Docker Compose (Recommended)

The repository includes a multi-container Docker configuration with health checks, persistent caching, and Dokploy support:

```bash
# Clone the repository
git clone https://github.com/ThePiperofHamelin/NASA-repo.git
cd NASA-repo

# Build and start services in the background
docker compose up -d --build
```

- **Frontend:** Accessible at [http://localhost:3000](http://localhost:3000)
- **Backend API:** Internal on port 8000 (proxied through the frontend at `/api/*`)
- **Persistent Cache Volume:** Named volume `tile-cache` preserves pre-rendered tiles and cutouts across restarts.

To view logs:
```bash
docker compose logs -f
```

To shut down:
```bash
docker compose down
```

---

### Option B: Local Development

#### 1. Backend Setup

```bash
cd backend

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start Flask development server on port 8000
python main.py
```

The backend server will run on `http://localhost:8000`.

#### 2. Frontend Setup

In a separate terminal window:

```bash
cd frontend

# Install dependencies using Bun (recommended) or npm
bun install

# Start Next.js development server
bun run dev
```

Open [http://localhost:3000](http://localhost:3000) in your web browser. Next.js will automatically proxy all `/api/*` requests to `http://localhost:8000`.

---

## CLI Utilities

The backend `main.py` script doubles as a versatile CLI tool for offline maintenance and image processing.

### Tile Prewarming

Because downloading remote FITS cutouts from IRSA and generating Lupton RGB composites can take several seconds on initial access, you can prewarm specific regions:

```bash
cd backend

# Prewarm the default target field (Cyg X / standard field)
python main.py prewarm --ra 304.69 --dec 42.44 --fov 2.0

# Prewarm with time filter (Modified Julian Date) and specific detector band
python main.py prewarm --ra 304.69 --dec 42.44 --start 60790 --end 60800 --band SPHEREx-D1
```

**Options:**
- `--ra <degrees>`: Center Right Ascension (default: `304.6935`)
- `--dec <degrees>`: Center Declination (default: `42.4437`)
- `--fov <degrees>`: Field of view diameter (default: `2.0`, max `2.0`)
- `--start <mjd>`: Filter by earliest observation MJD
- `--end <mjd>`: Filter by latest observation MJD
- `--band <name>`: Filter by bandpass name (can be repeated)

### Mosaic Stitching

The backend provides a standalone image stitcher to combine arbitrary FITS files into a unified PNG mosaic using WCS reprojection and co-addition:

```bash
cd backend
python main.py stitch /path/to/image1.fits /path/to/image2.fits -o mosaic.png --hdu-index 1
```

**Options:**
- `stitch <fits...>`: One or more input FITS files.
- `-o, --output <path>`: Required output PNG file destination.
- `--hdu-index <int>`: Index of the image HDU to read (default: `1`).

---

## API Reference

All backend endpoints are available under the `/api/` prefix.

### 1. `GET /api/cells`
Returns all $\sim 1^\circ$ sky grid cells within the specified field of view.

**Parameters:**
| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `ra` | `float` | Yes | Center Right Ascension in degrees ($0$ to $360$). |
| `dec` | `float` | Yes | Center Declination in degrees ($-90$ to $+90$). |
| `fov` | `float` | No | Field of view in degrees (default: `2.0`, capped at `2.0`). |

**Example Request:**
```bash
curl "http://localhost:8000/api/cells?ra=304.69&dec=42.44&fov=1.5"
```

**Example Response:**
```json
{
  "cells": [
    {
      "id": "226_131",
      "wcs": {
        "NAXIS": 2,
        "NAXIS1": 816,
        "NAXIS2": 816,
        "CTYPE1": "RA---TAN",
        "CTYPE2": "DEC--TAN",
        "CRVAL1": 304.76,
        "CRVAL2": 42.5,
        "CRPIX1": 408.5,
        "CRPIX2": 408.5,
        "CDELT1": -0.0017083,
        "CDELT2": 0.0017083
      },
      "corners": [
        [304.09, 42.0],
        [305.45, 42.0],
        [305.45, 43.0],
        [304.09, 43.0]
      ]
    }
  ]
}
```

---

### 2. `GET /api/cells/<cell_id>/exposures`
Lists all SPHEREx observations covering the center of the specified cell.

**Path Parameters:**
- `cell_id`: Grid cell ID formatted as `<i_index>_<j_index>` (e.g., `226_131`).

**Query Parameters:**
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `start` | `float` | Earliest observation date in MJD. |
| `end` | `float` | Latest observation date in MJD. |
| `band` | `string` | Bandpass filter (e.g., `SPHEREx-D1`). Can be repeated or comma-separated. |
| `collection` | `string` | Data collection (default: `spherex_dr1,spherex_qr3`). |
| `obs_id` | `string` | Restrict to a single specific observation identifier. |

**Example Request:**
```bash
curl "http://localhost:8000/api/cells/226_131/exposures?start=60790&end=60800"
```

**Example Response:**
```json
{
  "exposures": [
    {
      "id": "2026W24_2B_0317_1",
      "mjd": 60795.421,
      "ready": true
    }
  ]
}
```

---

### 3. `GET /api/cells/<cell_id>/tiles/<exposure_id>.png`
Retrieves or on-demand renders a false-colour composite tile (PNG) for an observation within a grid cell.

**Path Parameters:**
- `cell_id`: Grid cell ID (e.g., `226_131`).
- `exposure_id`: Observation ID (e.g., `2026W24_2B_0317_1`).

**Response:**
- `image/png` binary stream.
- HTTP header `Cache-Control: public, max-age=31536000, immutable` on cached assets.

**Example Request:**
```bash
curl -O "http://localhost:8000/api/cells/226_131/tiles/2026W24_2B_0317_1.png"
```

---

### 4. `GET /api/getPic`
Directly returns a single grayscale cutout PNG centered at arbitrary coordinates.

**Query Parameters:**
| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `ra` | `float` | `0.0` | Right Ascension in degrees. |
| `dec` | `float` | `0.0` | Declination in degrees. |
| `radius` | `float` | `0.1` | Cutout radius in degrees. |
| `band` | `string` | `SPHEREx-D2` | Bandpass filter (e.g., `SPHEREx-D1` through `SPHEREx-D6`). |
| `start` | `float` | `None` | Earliest observation date in MJD. |
| `end` | `float` | `None` | Latest observation date in MJD. |

---

## Configuration & Environment Variables

### Backend Configuration

| Variable | Default | Description |
| :--- | :--- | :--- |
| `HOST` | `0.0.0.0` | Host interface to bind server. |
| `PORT` | `8000` | Port to listen on. |
| `CACHE_DIR` | `./.cache` | Directory for storing disk caches (tiles, cutouts, searches). |
| `DATA_DIR` | `$CACHE_DIR/data` | Directory for standalone cutout PNG images (`/api/getPic`). |
| `IRSA_DOWNLOADS` | `3` | Max concurrent cutout downloads from IRSA. |
| `IRSA_SEARCHES` | `3` | Max concurrent SIA2 search queries to IRSA. |
| `RGB_STRETCH` | `1.5` | Linear factor for Lupton asinh color stretch. |
| `RGB_Q` | `8.0` | Softening parameter for Lupton asinh color stretch. |
| `RGB_MIN` | `0.0` | Minimum value mapped to black in RGB rendering. |

### Frontend Configuration

| Variable | Default | Description |
| :--- | :--- | :--- |
| `BACKEND_URL` | `http://localhost:8000` | Destination URL for the `/api/*` Next.js proxy rewrite. |
| `PORT` | `3000` | Port for the Next.js server. |

---

## Prototypes

The `prototypes/` directory contains standalone research prototypes and offline simulation tools:

- **`prototypes/rgb-composite/`:** A standalone Python script (`rgb_prototype_demo.py`) demonstrating synthetic three-band image blending with customizable channel weighting (`red_weight`, `green_weight`, `blue_weight`). Useful for testing rendering balance before applying changes to the live pipeline.

---

## License

This project is licensed under the **Apache License 2.0**. See the [LICENSE.md](LICENSE.md) file for full license terms and conditions.

---

## Acknowledgments

- **NASA & the SPHEREx Science Team:** For mission data access and documentation.
- **IPAC / IRSA (Infrared Science Archive):** For providing the Simple Image Access (SIA2) service and FITS cutout servers.
- **Aladin Lite (CDS, Observatoire de Strasbourg):** For the interactive WebGL astronomical sky viewer.
- **Astropy Project:** For core coordinate transformations, WCS projections, and Lupton RGB visualization algorithms.
