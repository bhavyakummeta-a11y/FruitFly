# flybody fruit fly model

An anatomically detailed 3D model of *Drosophila melanogaster* (head, thorax, abdomen, wings, legs and joints) for the [MuJoCo](https://mujoco.org/) physics engine. Copied unchanged from **[TuragaLab/flybody](https://github.com/TuragaLab/flybody)**, which was built by Google DeepMind and HHMI Janelia.

| | |
|---|---|
| Source | `flybody/fruitfly/assets/` in TuragaLab/flybody |
| Commit | [`d015e9b`](https://github.com/TuragaLab/flybody/tree/d015e9bfe441bd90ae431bac24c55cb74bdbce26) (2025-07-30) |
| License | Apache-2.0. See [`LICENSE`](LICENSE). |
| Size | About 134 MB (85 `.obj` meshes) |

## Files

| File | What |
|---|---|
| `assets/fruitfly.xml` | The fly model in MuJoCo's format (MJCF): bodies, joints, actuators, and references to the meshes |
| `assets/floor.xml` | A scene with a floor that includes `fruitfly.xml`. Open this one to see the fly standing. |
| `assets/*.obj` | Meshes for each body part, such as `head_body.obj`, `wing_left_*.obj`, and `thorax_black.obj` |

**Not copied:** the Blender source model (`assets/blender_model`, 17 MB) and the build scripts (`build_fruitfly/`). Get them from the upstream repo if you need to edit the geometry.

## View it

```bash
pip install mujoco
python -m mujoco.viewer --mjcf=models/flybody/assets/floor.xml
```

## How we plan to use it

- **Fly passengers in the 737 cabin.** Convert the meshes, or a decimated copy of them, to a format FlightGear loads and seat them in the cabin. See [`docs/AIRCRAFT.md`](../../docs/AIRCRAFT.md). The full meshes are very detailed (`head_red.obj` alone is 31 MB), so reduce them first, for example with Blender's Decimate modifier.
- **Fly-in-a-body panel.** Animate the fly from the brain's decisions, for example DNp09 → walk and Giant Fibre → jump. flybody's walking and flight are driven by networks trained with reinforcement learning, not by the connectome. If we feed brain firing rates into those networks as commands, we label it that way, per the [honor-the-fly-brain rule](../../docs/PROJECT_PLAN.md#principle-honor-the-fly-brain).

To run flybody's own tasks and trained movement networks, install the full package instead: `pip install "flybody[tf] @ git+https://github.com/TuragaLab/flybody.git"` (Python 3.10).

## Citation

Vaxenburg, R., Siwanowicz, I., Merel, J., et al. (2025). Whole-body physics simulation of fruit fly locomotion. *Nature* 643, 1312–1320. https://doi.org/10.1038/s41586-025-09029-4
