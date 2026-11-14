"""Optional local matplotlib view; no web server or simulator dependency."""
import math


class View:
    def __init__(self, obstacles):
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle
        self.plt = plt
        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=(8, 8))
        self.ax.set_aspect('equal')
        self.ax.set_xlabel('East (m)')
        self.ax.set_ylabel('North (m)')
        self.ax.set_facecolor('#eaf3f7')
        for obstacle in obstacles:
            self.ax.add_patch(Circle((obstacle.east, obstacle.north), obstacle.radius,
                                    color='#e26853', alpha=.65))
            self.ax.text(obstacle.east, obstacle.north + obstacle.radius + 40, obstacle.name)
        self.line, = self.ax.plot([], [], color='#147d92', linewidth=1)
        self.plane, = self.ax.plot([], [], marker='^', color='#172c45', markersize=13)
        self.hud = self.ax.text(.02, .98, '', transform=self.ax.transAxes, va='top',
                                bbox={'facecolor':'white','alpha':.9,'edgecolor':'none'})
        self.x, self.y = [], []
        plt.show(block=False)

    def update(self, state, phase, brain_name, stimulus, escape):
        if not self.plt.fignum_exists(self.fig.number):
            raise KeyboardInterrupt
        self.x.append(state.east)
        self.y.append(state.north)
        self.line.set_data(self.x[-3000:], self.y[-3000:])
        self.plane.set_data([state.east], [state.north])
        self.plane.set_marker((3, 0, -math.degrees(state.heading)))
        self.ax.set_xlim(state.east - 1600, state.east + 1600)
        self.ax.set_ylim(state.north - 900, state.north + 2300)
        self.hud.set_text(f'{brain_name}\n{phase} | {state.time:.1f} s\n'
                          f'Altitude {state.altitude:.0f} m | Speed {state.speed:.1f} m/s\n'
                          f'Looming {stimulus.looming_hz:.1f} Hz | Escape {escape:.1f} Hz')
        self.fig.canvas.draw_idle()
        self.plt.pause(.001)
