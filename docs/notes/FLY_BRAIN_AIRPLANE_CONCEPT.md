# Fly brain airplane simulation: concept notes

Added on 2026-11-14 from user-provided pasted text. The original text is preserved below.

> These are reference proposals, not implemented features or verified findings. The existing [project plan](../PROJECT_PLAN.md) remains the project direction: direct fly-brain control in Microsoft Flight Simulator. The autopilot-assisted approach and alternative simulators discussed here are options for consideration, not adopted changes. Embedded implementation prompts and Git commands are retained as notes.

---

You can use the fruit fly brain simulation to control an airplane, including taking off, flying, performing a barrel roll, and landing. However, you need to build a connection between the fly’s neurons and your flight simulator.

I looked through your Fly-Brain Handbook and fly_brain_starter.ipynb notebook. The notebook already gives you most of the brain simulation code. The main thing missing is the flight control system.

1. How your project would work

Your project would have three parts:

Flight simulator → Fly brain → Airplane controls

For example:

1. The airplane starts on the runway.
2. Your simulator sends information about the environment to the fly brain.
3. The fly brain processes that information through its neural network.
4. Your code reads the activity of certain neurons.
5. Based on that activity, your program controls the airplane.
6. The simulator displays the airplane taking off, flying, or landing.

The important distinction is that the fly brain does not naturally know how to fly an airplane. You must translate its biological responses into aircraft controls.

2. Which neurons should control the airplane?

Your handbook identifies these neurons:

Fly brain neuron	Biological behavior	Possible airplane control
DNp09	Walk forward	Increase throttle
MDN	Walk backward	Reduce throttle
Giant Fibre (DNp01)	Escape danger	Emergency maneuver
MN9	Extend mouth to eat	Approach target
LC4 / LPLC2	Detect approaching threats	Obstacle detection

These mappings are your project’s design choices, not flight behaviors that the fly brain has learned. Fly-Brain Handbook + Resources.docx

Example: Taking off

Suppose the airplane is on the runway.

Step 1: Your program tells the fly brain that moving forward is desirable.

Step 2: The fly brain processes the input.

Step 3: Your code measures activity in its output neurons.

Step 4: A flight controller translates those outputs into commands:

throttle = 1.0
pitch = 0.15
roll = 0.0
yaw = 0.0

These commands mean:

* Throttle: full power
* Pitch: raise the airplane’s nose
* Roll: keep wings level
* Yaw: fly straight

The exact values depend on the flight simulator you’re using.

Important: Your current notebook has no built-in flight dynamics, and its existing neuron groups do not directly provide independent pitch, roll, yaw, and throttle controls.

⸻

3. How to load the controls into your fly brain

Your notebook already contains this function:

simulate(inputs)

It accepts sensory neuron groups and their stimulation rates.

For example:

counts = simulate([
    (sugar, 200),
    (looming, 0)
])

This stimulates sugar-sensing neurons without stimulating the looming-neuron group.

You can then read the simulated brain activity:

eat = rate(counts, mn9)
escape = rate(counts, giant_fibre)
backward = rate(counts, mdn)

Next, create an interface that converts those biological outputs into airplane commands.

Example flight-control interface

Add this code after running the existing notebook cells.

def fly_brain_controller(counts):
    # Read the fly brain's activity
    forward = rate(counts, mn9)
    backward = rate(counts, mdn)
    danger = rate(counts, giant_fibre)
    # Default airplane controls
    controls = {
        "throttle": 0.0,
        "pitch": 0.0,
        "roll": 0.0,
        "yaw": 0.0
    }
    # Increase power when approach activity is detected
    if forward > 20:
        controls["throttle"] = 1.0
    # Reduce power when retreat activity is detected
    if backward > 20:
        controls["throttle"] = 0.2
    # Trigger an emergency response
    if danger > 0:
        controls["roll"] = 0.5
    return controls

Test it:

counts = simulate([
    (sugar, 200)
])
controls = fly_brain_controller(counts)
print(controls)

This is a prototype interface, not a complete autopilot. The thresholds are illustrative, and this particular example uses MN9 as an approach signal rather than DNp09.

You should first run the notebook’s existing experiments to confirm that its neural responses work as expected.

⸻

4. How to perform takeoff, a barrel roll, and landing

I would recommend building a flight state machine.

That means your airplane goes through different flight phases:

Flight phase	What the airplane needs to do	Controller responsibility
1. Takeoff	Accelerate along the runway	Throttle and pitch
2. Climb	Reach a safe altitude	Maintain climb
3. Cruise	Fly straight	Maintain stable flight
4. Barrel roll	Rotate around a flight path	Coordinate roll and pitch
5. Approach	Reduce speed and altitude	Control descent
6. Landing	Touch down on runway	Manage pitch, throttle, and alignment

Code example

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

These are simplified example commands. A real barrel roll requires coordinated, continuously changing controls, while a proper takeoff and landing require feedback from speed, altitude, orientation, and runway position.

Also, this code alone is not controlled by the fly brain yet. It defines the maneuvers that your fly-brain interface could trigger.

⸻

5. Which flight simulator should you use?

You have several possibilities.

Simulator	Advantages	Difficulty
PyBullet	Python-based physics environment	Medium
Unity	Good 3D airplane visuals	Medium–Hard
Pygame	Easy to build a basic 2D flight simulator	Easy
JSBSim	More realistic aircraft flight dynamics	Medium–Hard

My recommendation: Use Python with a simple aircraft simulation first.

You already have the fly brain running in Python, so this avoids having to connect multiple programming environments immediately.

Once the controls work, you can add a 3D visualization.

⸻

6. The most important challenge

Your handbook explains that the fly brain works by converting sensory information into recognizable behaviors.

For example:

Looming object → Giant Fibre activation → Escape

It also suggests using the fly brain for robot or drone obstacle avoidance. Fly-Brain Handbook + Resources.docx

For your airplane project, the biggest challenge is converting neural outputs into reliable flight commands.

There are two ways to approach this.

Option A: Fly-brain-assisted autopilot (easier)

The airplane has a normal flight controller, but the fly brain makes decisions about when to initiate behaviors.

For example:

* Fly brain detects a desirable direction → continue forward.
* Fly brain detects a threat → initiate an avoidance maneuver.
* Fly brain detects an undesirable condition → retreat or change direction.

A conventional autopilot handles stability, takeoff, and landing.

Option B: Fly-brain flight controller (harder)

You connect multiple neural outputs directly to throttle, pitch, roll, and yaw.

This would require identifying useful neuron groups, designing an output decoder, and testing whether their responses can reliably control an aircraft.

It would be a more ambitious experiment, but the fly brain is not guaranteed to provide meaningful aircraft control signals.

⸻

7. What I recommend building

For your project, I would aim for this:

An autonomous airplane simulation in which a fruit fly brain influences flight decisions.

Your demonstration could show the airplane:

1. Starting on a runway.
2. Taking off automatically.
3. Flying toward a target.
4. Encountering an obstacle.
5. Using the fly brain’s escape response to trigger a maneuver.
6. Returning to the runway.
7. Landing safely using the flight controller.

The display could show the airplane on one side and the neural activity on the other.

One important question

Do you want the fruit fly brain to actually control the airplane’s movements, or do you want to program the airplane’s movements and use the fly brain to decide when to perform them?

These are two very different projects.

The first requires building a neural-to-flight-control system. The second is much easier to implement using your existing notebook, and it can still demonstrate a real biological neural network making decisions.
