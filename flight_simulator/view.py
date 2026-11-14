"""Companion window: virtual obstacle scene at left, full route at right."""
import math


class View:
    def __init__(self, obstacles, scenery=False):
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.patches import Circle
        self.plt = plt
        self.obstacles = obstacles
        plt.ion()
        self.fig = plt.figure(figsize=(14, 9))
        self.scene = self.fig.add_subplot(121, projection='3d')
        self.ax = self.fig.add_subplot(122)
        self.fig.canvas.manager.set_window_title('Fly flight companion — obstacle course')
        self.fig.subplots_adjust(left=.06, right=.97, top=.78, bottom=.30, wspace=.22)
        self.alt_ax = self.fig.add_axes([.08, .09, .86, .13])
        self.alt_ax.set(xlabel='Flight time (s)', ylabel='Altitude (m)', title='Altitude hold — actual vs target')
        self.alt_line, = self.alt_ax.plot([], [], color='#147d92', label='Actual altitude')
        self.alt_target, = self.alt_ax.plot([], [], '--', color='#aa6633', label='Target')
        self.alt_ax.grid(alpha=.2)
        self.alt_ax.legend(loc='upper right', fontsize=8)
        self.times = []
        self.status = self.fig.text(.04, .96, '', va='top', fontsize=11)
        caption = ('Fixed scenery course — load its FlightGear scenery folder to see the same towers in the cockpit.' if scenery else 'Virtual obstacles, drawn live as towers in FlightGear (no collision there).')
        self.fig.text(.04, .025, caption + ' Close window or Ctrl-C to stop.', fontsize=9)
        self.scene.set(title='Obstacle view', xlabel='East (m)', ylabel='North (m)', zlabel='Altitude MSL (m)')
        self.ax.set(title='Flight path — full course', xlabel='East (m)', ylabel='North (m)')
        self.ax.set_aspect('equal', adjustable='box')
        self.ax.set_facecolor('#eef4f7')
        self.ax.grid(alpha=.2)
        angles = np.linspace(0, 2*np.pi, 30)
        for obstacle in obstacles:
            self.ax.add_patch(Circle((obstacle.east, obstacle.north), obstacle.radius,
                                    color='#e26853', alpha=.65))
            self.ax.text(obstacle.east + obstacle.radius + 30, obstacle.north, obstacle.name, fontsize=9)
            z = np.array([[obstacle.bottom]*len(angles), [obstacle.top]*len(angles)])
            x = np.tile(obstacle.east + obstacle.radius*np.cos(angles), (2, 1))
            y = np.tile(obstacle.north + obstacle.radius*np.sin(angles), (2, 1))
            self.scene.plot_surface(x, y, z, color='#e26853', alpha=.35, shade=False)
            self.scene.text(obstacle.east, obstacle.north, obstacle.top+50, obstacle.name, fontsize=8)
        self.line, = self.ax.plot([], [], color='#147d92', linewidth=2, label='Actual path')
        self.prediction, = self.ax.plot([], [], '--', color='#c47b18', label='Checked route ahead')
        self.route_line, = self.ax.plot([], [], ':', color='#777777', label='Cruise direction')
        self.plane, = self.ax.plot([], [], marker='^', color='#172c45', markersize=11)
        self.trail3, = self.scene.plot([], [], [], color='#147d92', linewidth=2)
        self.plane3, = self.scene.plot([], [], [], marker='o', color='#172c45', markersize=7)
        self.ax.legend(loc='upper right')
        self.x, self.y, self.z = [], [], []
        self.last_time = None
        plt.show(block=False)

    def update(self, state, phase, brain_name, stimulus, escape, target_heading=None, controller=None):
        if not self.plt.fignum_exists(self.fig.number):
            raise KeyboardInterrupt
        if state.time != self.last_time:
            self.x.append(state.east); self.y.append(state.north); self.z.append(state.altitude)
            self.times.append(state.time)
            self.last_time = state.time
        if len(self.x) > 6000:
            self.x, self.y, self.z = self.x[::2], self.y[::2], self.z[::2]
            self.times = self.times[::2]
        self.line.set_data(self.x, self.y)
        self.plane.set_data([state.east], [state.north])
        self.plane.set_marker((3, 0, -math.degrees(state.heading)))
        self.trail3.set_data(self.x, self.y); self.trail3.set_3d_properties(self.z)
        self.plane3.set_data([state.east], [state.north]); self.plane3.set_3d_properties([state.altitude])
        xs = [0, *self.x, *[o.east-o.radius for o in self.obstacles], *[o.east+o.radius for o in self.obstacles]]
        ys = [0, *self.y, *[o.north-o.radius for o in self.obstacles], *[o.north+o.radius for o in self.obstacles]]
        for axes in [self.ax, self.scene]:
            axes.set_xlim(min(xs)-600, max(xs)+600)
            axes.set_ylim(min(ys)-600, max(ys)+600)
        span = max(max(xs)-min(xs), max(ys)-min(ys)) + 1200
        cx, cy = (max(xs)+min(xs))/2, (max(ys)+min(ys))/2
        self.ax.set_xlim(cx-span/2, cx+span/2)
        self.ax.set_ylim(cy-span/2, cy+span/2)
        self.scene.set_zlim(0, max(1200, state.altitude+300, *[o.top+100 for o in self.obstacles]))
        target = '' if target_heading is None else f' | Target heading {math.degrees(target_heading)%360:.0f}°'
        self.status.set_text(f'{brain_name} | {phase} | {state.time:.1f} s{target}\n'
                             f'Altitude {state.altitude:.0f} m | Speed {state.speed:.1f} m/s | Bank {math.degrees(state.roll):.1f}°\n'
                             f'Looming {stimulus.looming_hz:.1f} Hz | Escape {escape:.1f} Hz | Threat: {stimulus.obstacle or "clear"}')
        goal = controller.altitude if controller is not None else self.z[0]
        self.alt_line.set_data(self.times, self.z)
        self.alt_target.set_data([0, max(state.time,1)], [goal,goal])
        self.alt_ax.set_xlim(0,max(30,state.time+5))
        extent=max(15,max(abs(z-goal) for z in self.z)+5)
        self.alt_ax.set_ylim(goal-extent,goal+extent)
        if controller is not None:
            path=controller.guidance.path
            self.prediction.set_data([p[0] for p in path],[p[1] for p in path])
            origin=controller.guidance.origin
            length=max(6000,math.hypot(state.east-origin[0],state.north-origin[1])+2000)
            self.route_line.set_data([origin[0],origin[0]+length*math.sin(controller.heading)],
                                     [origin[1],origin[1]+length*math.cos(controller.heading)])
            self.status.set_text(self.status.get_text()+f'\nTarget {goal:.0f} m | Error {state.altitude-goal:+.1f} m | Vertical speed {state.climb:+.1f} m/s | {controller.decision_source}')
        self.fig.canvas.draw_idle()
        self.plt.pause(.001)
