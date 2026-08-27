# E3 formal exact-trial adapter

`tooling/e3_formal_adapter.py` accepts one exact registered E3 ID.  It owns no
global order, cursor, replacement policy, or suite journal.  Spec rehearsal is
non-physical and always marked `NOT_FORMAL_RESULT`; future physical execution
requires `formal_evaluation`, the exact sealed global position and pinned
commit/source hashes, explicit authorization, and a
`READY_FOR_FORMAL_LAUNCH` gate.

The real backend uses the frozen allocator modes, LADRC controller and IAPF
condition, the sealed GazeboRosForce overlay/driver, unscored staging with a
continuous 2 s stable gate, exact scored timing, and raw rosbag retention.
Failures and timeouts are durably retained and are never retried here.

`e3_wrench_compat.py` is a transport-only ROS Humble shim: it provides storage
for the sealed driver's `publishers` name (which collides with a read-only
`rclpy.Node` property) and selects the simulator-compatible sensor-data QoS for
`/clock`.  All disturbance state-machine and publish methods remain inherited
from the byte-unchanged sealed `harness/e3_wrench_driver.py`.

The engineering smoke fixture ID starts with `ENG-`, is absent from the sealed
610 permutation, and has no scientific interpretation.
