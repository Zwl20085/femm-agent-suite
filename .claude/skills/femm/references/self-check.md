# Self-check tasks with known answers

Realistic tasks whose answers this project measured on FEMM 5.0 build 06oct2026. Use them to check
an install, a change to your own workflow, or your reading of the tools. A result far outside the
stated band means something in the toolchain or the setup is wrong; find out what before going on.

| # | Task | Tools | Expected |
|---|---|---|---|
| 1 | Run the install self-test. | `femm_selftest` | all checks pass; solenoid centre field within 1 % (0.7 % measured) |
| 2 | Build the C-core benchmark and read the gap flux density at `probe_gap_point`. | `femm_build_benchmark("ccore")`, `femm_solve`, `femm_point_values` | |By| about 0.238 T; `femm_estimate("ccore_gap_b", ...)` gives 0.2405 T |
| 3 | Health-check the solved C-core with `force_groups=[1]`, `reaction_groups=[2, 3]`. | `femm_health_check` | every applicable rule passes; W = W' = 1/2 L I^2 to 0.00 % |
| 4 | Force on the C-core armature, gap 1 to 3 mm, 9 steps of 0.25 mm. | `femm_experiment_force_vs_position(groups=[1], dy=0.25, steps=9)` | -9.74 N at 1 mm; WST vs virtual work within about 1.6 % RMS; flat-gap estimate -9.21 N |
| 5 | C-core coil inductance at 2 A. | `femm_experiment_inductance(current=2)` | 7.47 mH (the no-fringing formula gives 4.81 mH; explain the gap) |
| 6 | Cogging of the 12-slot / 4-pole SPM by both routes. | `femm_build_benchmark("spm")` then `femm_experiment_cogging(rotate_groups=[1, 10], torque_groups=[1], slots=12, poles=4)`; again with `params={"rotor_method": "age"}` and `method="age", gap_boundary="AGE", rotate_groups=[1]` | peak to peak 0.3824 N*m (rotate) vs 0.3835 N*m (air-gap element), 0.3 % apart; period 30 deg |
| 7 | SPM back-EMF at 1000 rpm. | `femm_experiment_backemf(rotate_groups=[1, 10], pole_pairs=2, rpm=1000)` | fundamental about 9.97 V peak, THD about 27 %, psi_pm fundamental 47.6 mWb |
| 8 | SPM Ld and Lq with id = iq = 5 A. | `femm_experiment_inductance(dq={...}, torque_groups=[1])` | Ld 0.427 mH, Lq 0.421 mH |
| 9 | SPM mean torque at iq = 10 A over 0-30 deg. | `femm_experiment_torque_vs_angle(..., drive={"circuits": ["A","B","C"], "pole_pairs": 2, "id": 0, "iq": 10})` | mean 1.415 N*m; 3/2 p psi iq gives 1.428 N*m |
| 10 | Round copper wire (r 5 mm) R(f), 1 Hz to 10 kHz. | `femm_build_benchmark("round_wire")`, `femm_experiment_ac_sweep` | within 1.3 % of the Bessel solution at 10 kHz (0.0 % up to 100 Hz); power balance 0.00 % |

Wrong answers that teach something:

- Task 2 with the probe point moved into the iron: you read the core, not the gap.
- Task 6 rotate route with `torque_groups=[1, 10]`: the rotor-side air layer is in the torque
  selection; the guidance is to leave it out.
- Task 6 air-gap route read with the WST block integral (code 22) instead of `mo_gapintegral`:
  about 1e-16 N*m, because the stress tensor does not see across the air-gap element.
- Any task with `femm_save_bitmap` in a headless session: no file. Use `femm_plot_field`.
