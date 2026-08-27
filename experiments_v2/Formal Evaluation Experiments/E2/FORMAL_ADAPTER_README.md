# E2 formal exact-trial adapter

The adapter wraps the validated, frozen-snapshot E2 commitment wrapper and
production resolver.  It accepts one globally supplied registered ID and owns
no order, cursor, replacement, retry, or suite-journal authority.  Formal mode
is available only behind the explicit global launch gate; spec rehearsal and
the non-registered offline engineering fixture always retain
`NOT_FORMAL_RESULT` artifacts.  No Gazebo/PX4 layer is added because the sealed
E2 method is an offline parse/execution-snapshot experiment.
