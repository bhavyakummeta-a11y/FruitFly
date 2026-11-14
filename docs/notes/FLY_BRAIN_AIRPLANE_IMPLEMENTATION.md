# Fly brain airplane simulation: implementation notes

Added on 2026-11-14 from user-provided pasted text. The original text is preserved below.

> These are reference proposals, not implemented features or verified findings. The existing [project plan](../PROJECT_PLAN.md) remains the project direction: direct fly-brain control in Microsoft Flight Simulator. The autopilot-assisted approach and alternative simulators discussed here are options for consideration, not adopted changes. Embedded implementation prompts and Git commands are retained as notes.

---

You can add the Fly Brain Airplane Simulator to your GitHub repository using VS Code or GitHub directly.

Step 1: Open your repository

1. Open your GitHub repository.
2. Click Code → Open with GitHub Desktop, or clone the repository in VS Code.
3. Open the project folder.

Step 2: Organize your files

I recommend this structure:

fly-brain-project/
│
├── fly_brain_starter.ipynb
├── fruit_fly_brain_creations.xlsx
│
├── flight_simulator/
│   ├── __init__.py
│   ├── brain_controller.py
│   ├── flight_mission.py
│   └── simulator.py
│
├── requirements.txt
├── README.md
└── .gitignore

Keep your existing fly brain notebook. Add the flight-control code as separate Python files.

Step 3: Add the controller

Create flight_simulator/brain_controller.py:

def fly_brain_controller(forward, backward, danger):
    controls = {
        "throttle": 0.0,
        "pitch": 0.0,
        "roll": 0.0,
        "yaw": 0.0
    }
    if forward > 20:
        controls["throttle"] = 1.0
    if backward > 20:
        controls["throttle"] = 0.2
    if danger > 0:
        controls["roll"] = 0.5
    return controls

This function accepts neuron firing rates from your fly brain notebook. It doesn’t run the neural simulation itself.

Step 4: Add the flight maneuvers

Create flight_simulator/flight_mission.py:

def flight_mission(phase):
    if phase == "TAKEOFF":
        return {
            "throttle": 1.0,
            "pitch": 0.2,
            "roll": 0.0
        }
    elif phase == "CLIMB":
        return {
            "throttle": 0.9,
            "pitch": 0.15,
            "roll": 0.0
        }
    elif phase == "CRUISE":
        return {
            "throttle": 0.7,
            "pitch": 0.0,
            "roll": 0.0
        }
    elif phase == "BARREL_ROLL":
        return {
            "throttle": 0.85,
            "pitch": 0.2,
            "roll": 0.7
        }
    elif phase == "LANDING":
        return {
            "throttle": 0.3,
            "pitch": -0.05,
            "roll": 0.0
        }
    return {
        "throttle": 0.0,
        "pitch": 0.0,
        "roll": 0.0
    }

These are demonstration control values, not complete aircraft maneuvers.

Step 5: Connect the fly brain

In your notebook, after running the existing simulation code, add:

from flight_simulator.brain_controller import fly_brain_controller
counts = simulate([
    (sugar, 200),
    (looming, 0)
])
controls = fly_brain_controller(
    forward=rate(counts, mn9),
    backward=rate(counts, mdn),
    danger=rate(counts, giant_fibre)
)
print(controls)

Run this from your repository’s root directory so Python can import flight_simulator.

Note: This only prints commands. You’ll still need to connect them to a flight physics simulator for the airplane to move.

Step 6: Upload everything to GitHub

Open the VS Code terminal:

git add .
git commit -m "Add fly brain airplane control system"
git push origin main

If you’re working on a different branch, replace main with your branch name.

Before pushing, ensure your .gitignore excludes API tokens, .env files, and other credentials.

⸻

Alternative: Let Codex implement it in your repository

If your repository is connected to Codex, you can paste this instruction:

Implement a Python-based airplane simulation integrated with my existing fruit fly brain neural network.

First, inspect the existing repository, especially fly_brain_starter.ipynb, and preserve the existing neural simulation code.

Create a flight_simulator Python package containing:

1. brain_controller.py — Read output firing rates from the existing fly brain simulation and convert them into airplane control decisions.
2. flight_mission.py — Implement a flight state machine with TAKEOFF, CLIMB, CRUISE, BARREL_ROLL, APPROACH, and LANDING.
3. simulator.py — Build a visual airplane simulation that displays the airplane’s position, orientation, altitude, and flight phase.
4. Connect the existing fly brain’s sensory stimulation and neural outputs to the flight controller. Reuse the notebook’s existing functions where possible.
5. Implement an automated demonstration in which the airplane takes off, climbs, cruises, performs a barrel roll, and lands.
6. Include a display showing neural activity and the current airplane controls.
7. Use a physics-based flight model rather than just animating predetermined movements. Ensure the barrel roll involves coordinated control inputs.
8. Separate neural decision-making from the conventional flight stabilization controller. Do not claim that the fly brain independently controls the aircraft unless its neural outputs actually determine the controls.
9. Include a requirements.txt and update README.md with setup and execution instructions.
10. Add basic tests, handle missing datasets gracefully, and never commit authentication tokens.

Keep everything compatible with the existing Python project. Implement a working demonstration that can run locally.

My recommendation: If you’re using Codex, connect your GitHub repository and use the prompt above. It gives Codex the instructions to build the simulator and connect it to your existing fly brain code, rather than requiring you to create every file manually.
