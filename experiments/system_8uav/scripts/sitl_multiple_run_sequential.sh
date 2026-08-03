#!/usr/bin/env bash
# Experiment-10 launcher derived from PX4's gazebo-classic
# sitl_multiple_run.sh. It serializes XRCE time synchronization so eight PX4
# clients do not compete for the Agent during the 500-sample convergence gate.

function cleanup() {
	pkill -x px4
	pkill gzclient
	pkill gzserver
}

function wait_for_xrce() {
	local instance=$1
	local deadline=$((SECONDS + xrce_start_timeout))
	local status=""

	while (( SECONDS < deadline )); do
		status=$("$build_path/bin/px4-uxrce_dds_client" \
			--instance "$instance" status 2>&1) || true
		if [[ "$status" == *"timesync converged: true"* ]]; then
			echo "XRCE client $instance time sync converged"
			return 0
		fi
		sleep 0.25
	done

	echo "ERROR: XRCE client $instance did not converge in ${xrce_start_timeout}s"
	echo "$status"
	return 1
}

function spawn_model() {
	MODEL=$1
	N=$2
	X=$3
	Y=$4
	X=${X:=0.0}
	Y=${Y:=$((3 * N))}

	SUPPORTED_MODELS=("iris" "plane" "standard_vtol" "rover" "r1_rover" "typhoon_h480")
	if [[ " ${SUPPORTED_MODELS[*]} " != *"$MODEL"* ]]; then
		echo "ERROR: Currently only vehicle model $MODEL is not supported!"
		echo "       Supported Models: [${SUPPORTED_MODELS[*]}]"
		exit 1
	fi

	working_dir="$build_path/rootfs/$n"
	[ ! -d "$working_dir" ] && mkdir -p "$working_dir"

	pushd "$working_dir" &>/dev/null || return 1
	echo "starting instance $N in $(pwd)"
	"$build_path/bin/px4" -i "$N" -d "$build_path/etc" >out.log 2>err.log &

	local output_file="/tmp/${MODEL}_${N}.sdf"
	local jinja_args=(
		"${src_path}/Tools/simulation/gazebo-classic/sitl_gazebo-classic/scripts/jinja_gen.py"
		"${src_path}/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/${MODEL}/${MODEL}.sdf.jinja"
		"${src_path}/Tools/simulation/gazebo-classic/sitl_gazebo-classic"
		--mavlink_tcp_port "$((4560 + N))"
		--mavlink_udp_port "$((14560 + N))"
		--mavlink_id "$((1 + N))"
		--gst_udp_port "$((5600 + N))"
		--video_uri "$((5600 + N))"
		--mavlink_cam_udp_port "$((14530 + N))"
		--output-file "$output_file"
	)

	python3 "${jinja_args[@]}"

	echo "Spawning ${MODEL}_${N} at ${X} ${Y}"
	gz model --spawn-file="$output_file" --model-name="${MODEL}_${N}" \
		-x "$X" -y "$Y" -z 0.83

	popd &>/dev/null || return 1
	wait_for_xrce "$N"
}

if [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
	echo "Usage: $0 [-n <num_vehicles>] [-m <vehicle_model>] [-w <world>] [-s <script>] [-x <xrce_timeout>]"
	exit 1
fi

while getopts n:m:w:s:t:l:x: option; do
	case "${option}" in
		n) NUM_VEHICLES=${OPTARG};;
		m) VEHICLE_MODEL=${OPTARG};;
		w) WORLD=${OPTARG};;
		s) SCRIPT=${OPTARG};;
		t) TARGET=${OPTARG};;
		l) LABEL=_${OPTARG};;
		x) XRCE_START_TIMEOUT=${OPTARG};;
		*) exit 2;;
	esac
done

num_vehicles=${NUM_VEHICLES:=3}
world=${WORLD:=empty}
target=${TARGET:=px4_sitl_default}
vehicle_model=${VEHICLE_MODEL:="iris"}
xrce_start_timeout=${XRCE_START_TIMEOUT:=30}
export PX4_SIM_MODEL=gazebo-classic_${vehicle_model}

if [ -z "$PX4_AUTOPILOT_DIR" ]; then
	echo "ERROR: PX4_AUTOPILOT_DIR is required"
	exit 1
fi
src_path=$PX4_AUTOPILOT_DIR
build_path=${src_path}/build/${target}

trap "cleanup" SIGINT SIGTERM EXIT

echo "killing running instances"
pkill -x px4 || true
sleep 1

# shellcheck source=/dev/null
source "${src_path}/Tools/simulation/gazebo-classic/setup_gazebo.bash" \
	"${src_path}" "${src_path}/build/${target}"

if [[ -n "$ROS_VERSION" ]] && [ "$ROS_VERSION" == "2" ]; then
	ros_args=(-s libgazebo_ros_init.so -s libgazebo_ros_factory.so)
else
	ros_args=()
fi

echo "Starting gazebo"
gzserver "${src_path}/Tools/simulation/gazebo-classic/sitl_gazebo-classic/worlds/${world}.world" \
	--verbose "${ros_args[@]}" &
sleep 5

n=0
if [ -z "${SCRIPT}" ]; then
	if [ "$num_vehicles" -gt 255 ]; then
		echo "Tried spawning $num_vehicles vehicles. The maximum number of supported vehicles is 255"
		exit 1
	fi

	while [ "$n" -lt "$num_vehicles" ]; do
		spawn_model "$vehicle_model" "$((n + 1))" || exit 1
		n=$((n + 1))
	done
else
	IFS=',' read -r -a target_specs <<< "$SCRIPT"
	for target_spec in "${target_specs[@]}"; do
		target_spec="$(echo "$target_spec" | tr -d ' ')"
		target_vehicle=$(echo "$target_spec" | cut -f1 -d:)
		target_number=$(echo "$target_spec" | cut -f2 -d:)
		target_x=$(echo "$target_spec" | cut -f3 -d:)
		target_y=$(echo "$target_spec" | cut -f4 -d:)

		if [ "$n" -gt 255 ]; then
			echo "Tried spawning $n vehicles. The maximum number of supported vehicles is 255"
			exit 1
		fi

		m=0
		while [ "$m" -lt "$target_number" ]; do
			export PX4_SIM_MODEL=gazebo-classic_${target_vehicle}
			spawn_model "${target_vehicle}${LABEL}" "$((n + 1))" \
				"$target_x" "$target_y" || exit 1
			m=$((m + 1))
			n=$((n + 1))
		done
	done
fi

echo "Starting gazebo client"
gzclient
