# Chemical Reaction Simulation Engine
**with NVIDIA Omniverse, OpenUSD, and LLM-based Automation**

<p align="center">
  <img src="readme-assets/banner.png" width="100%" />
</p>

## Overview

Welcome to the **Chemical Reaction Simulation Engine**, a project developed to create scalable, high-fidelity chemical simulations using **NVIDIA Omniverse**, **PhysX**, **OpenUSD**, and **Large Language Models (LLMs)**.

This simulation environment enables real-time, interactive exploration of complex chemical reactions, accurately modeling molecular bonding, diffusion, phase changes, and by-product formation within an immersive VR-ready platform.

Unlike educational chemistry apps, this project targets **high-fidelity scientific simulations**, designed for research, experimentation, and collaborative remote observation over the web.

## Objectives

- **Simulate Complex Chemical Reactions**: Build detailed, real-time simulations using NVIDIA Omniverse and PhysX for molecular interactions.
- **LLM-Driven Reaction Setup**: Automate reaction definitions, parameters, and initial conditions using GPT-powered ChemAPI.
- **OpenUSD Asset Integration**: Generate and manage 3D molecule structures as USD files for seamless compatibility.
- **Scalable, Web-Accessible Platform**: Deploy backend services on GCP for remote simulation access using WebXR streaming.
- **Dynamic Real-Time Adjustments**: Allow user-driven interaction and manipulation of temperature, concentration, and reaction variables live within Omniverse.

---

## Key Features

- **Physically Accurate Reaction Modeling**
- **Dynamic LLM Integration**
- **OpenUSD-based Visualization**
- **WebXR and Remote VR Access**
- **Cloud-native Backend Infrastructure**

---

## Project Architecture

```mermaid
flowchart TD
    A[User Input / Query] --> B(ChemAPI Backend - FastAPI)
    B --> C{LLM (OpenAI)}
    C --> D[Generate Compounds / Reaction Parameters]
    D --> E[Store in Firebase & SQL]
    D --> F[Convert to USD Assets]
    F --> G[NVIDIA Omniverse Kit]
    G --> H[WebXR Stream or Local VR Launch]
```

---

## Quick Start

### 1. Prerequisites

- **GPU**: NVIDIA RTX 3070 or higher
- **Software**:
  - NVIDIA Omniverse Kit, Code, Create
  - Blender
  - Unity (optional for VR)
  - Python 3.9+
  - Docker
- **Cloud**: GCP account for backend hosting

### 2. Setup Backend (ChemAPI)

```bash
git clone https://github.com/your-repo/chemapi-backend.git
cd chemapi-backend
docker build -t chemapi .
docker run -p 8000:8000 chemapi
```

### 3. Setup Omniverse Extension

- Clone and install `heptre.chem_sim_reactor`
- Connect to ChemAPI backend
- Import USD molecules
- Animate reactions

### 4. Launch Simulation

- Launch via Omniverse Kit
- Select reaction JSON or USD file
- Simulate and interact

---

## Repository Structure

| Directory | Purpose |
| :-------- | :------ |
| `/backend/` | ChemAPI FastAPI server |
| `/extensions/` | Omniverse Extension `heptre.chem_sim_reactor` |
| `/output_usd/` | Generated USD files |
| `/output_json/` | Raw JSON outputs |
| `/reaction_anim_builder.py` | Reaction animation builder |
| `/chem_api.py` | ChemAPI backend handler |
| `/Molecular.py` | Molecule structure utilities |

---

## Technology Stack

- **Omniverse Kit SDK**
- **PhysX Simulation Engine**
- **OpenUSD Asset System**
- **GCP Cloud Run, Firebase, SQL**
- **Python 3.9 (FastAPI, Docker)**
- **OpenAI GPT-3.5 API**

---

## Challenges and Learnings

- USD model conversions
- PhysX molecular scale simulation tuning
- Validating LLM-generated outputs
- Balancing fidelity vs performance for WebXR

---

## Limitations

- Not full quantum-level molecular simulation
- WebXR streaming requires high-end client GPUs

---

## License

This project is governed by the [NVIDIA Software License Agreement](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/).

---

## Additional Resources

- [NVIDIA Omniverse Developer Documentation](https://docs.omniverse.nvidia.com/)
- [OpenUSD Specification](https://openusd.org/release/index.html)
- [Google Cloud Run Documentation](https://cloud.google.com/run/docs)
- [OpenAI API Documentation](https://platform.openai.com/docs)

---

> **Developed by Ragavendiran Balasubramanian | M.Tech, AR/VR | IIT Jodhpur**