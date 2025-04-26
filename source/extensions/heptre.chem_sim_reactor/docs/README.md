# chem_sim_reactor

**Chemical Reaction Simulation Engine with NVIDIA Omniverse and LLM Integration**

Welcome to `chem_sim_reactor`, a Python-based Omniverse Kit extension that brings chemical reactions to life in a high-fidelity VR environment.

This project integrates real-time physics (NVIDIA PhysX), high-quality USD assets, and Large Language Model (LLM) driven backend automation to create dynamic, scalable, and interactive chemical simulations.



## Features

-  **Real-Time Chemical Reaction Simulations**
  Simulate molecular interactions, reaction dynamics, and visual effects with PhysX physics.

-  **LLM-Powered Backend (ChemAPI)**
  Automatically generate molecule structures and reaction setups using GPT APIs.

-  **Omniverse USD Asset Generation**
  Create USD representations of chemical compounds and reactions for seamless integration in Omniverse.

-  **WebXR Ready**
  Stream and interact with simulations directly in VR via the web (Omniverse WebXR).

-  **Remote and Scalable**
  Backend deployed on Google Cloud Platform for real-time, scalable access.



## Project Structure

- `chem_sim_reactor/`
  - Core Python extension code for Omniverse.
  - Reaction engines and USD generation logic.
- `backend/`
  - ChemAPI server built with FastAPI.
  - Integrates OpenAI GPT-3.5 for chemical data generation.
- `output_usd/`
  - Generated USD files for reactions and base compounds.



## Getting Started

### Prerequisites
- NVIDIA Omniverse Kit SDK
- Python 3.9+
- FastAPI
- Docker (for backend deployment)
- Google Cloud Run (optional for cloud deployment)

### Setup

Clone the repository:
```bash
https://github.com/your-org/chem_sim_reactor.git
```

Set up the backend:
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Launch Omniverse Kit and install the extension:
```bash
# In Omniverse Launcher, load the extension from the source folder.
```

### Usage
- Use the provided UI to query a chemical reaction.
- ChemAPI generates molecule structure and properties.
- USD files are created for compounds and reactions.
- Simulate and visualize in VR via Omniverse.
