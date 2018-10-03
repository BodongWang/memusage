#!/bin/bash

function usage(){
        echo "This script will generate and Configure TC rules of Layer 2"
        echo "$0 <interface_name> <num_rules_of_rule> <skip_sw|skip_hw - optional> <set_index - optional> <set_prio - optional> "
        exit 1
}


ifs=$1
num_rules=$2
SKIP=${3:-skip_sw}
set_index=${4:-0}       # if set_index == 1, all filters share the same action
set_prio=${5:-0}        # if set_prio == 1, all filters will have different prio


if [[ $ifs == "" ]] || [[ $num_rules == "" ]] ; then
        usage
fi

echo "SKIP $SKIP ifs $ifs num_rules $num_rules INDEX $set_index PRIO $set_prio"

ifconfig $ifs up

echo "Clean tc rules"
TC=tc
$TC qdisc del dev $ifs ingress > /dev/null 2>&1

tmpdir="/tmp/tc_batch"
rm -fr $tmpdir
mkdir -p $tmpdir

if [[ "$SKIP" == "skip_sw" ]]; then
	OUT="$tmpdir/hw_batch"
		ethtool -K $ifs hw-tc-offload on
fi
if [[ "$SKIP" == "skip_hw" ]]; then
	OUT="$tmpdir/sw_batch"
		ethtool -K $ifs hw-tc-offload off
fi

n=0
prio=1

echo "Generating batches"

for ((count = 0; count < $num_rules; count++)); do
	s_i=$(($RANDOM % 100))
	s_j=$(($RANDOM % 100))
	s_k=$(($RANDOM % 100))
	s_l=$(($RANDOM % 100))
	s_m=$(($RANDOM % 100))
	s_o=$(($RANDOM % 100))												

	d_i=$(($RANDOM % 100))
	d_j=$(($RANDOM % 100))
	d_k=$(($RANDOM % 100))
	d_l=$(($RANDOM % 100))
	d_m=$(($RANDOM % 100))
	d_o=$(($RANDOM % 100))

# the last bit of the SRC_MAC has to be 0, because 1 indicates multi-cast, and SRC_MAC cannot be multicast	
	SMAC="$s_m:$s_o:$s_i:$s_j:$s_k:98"
	DMAC="$d_m:$d_o:$d_i:$d_j:$d_k:$d_l"
	echo "filter add dev ${ifs} prio $prio protocol ip \
		parent ffff: \
		flower \
		$SKIP \
		src_mac $SMAC \
		dst_mac $DMAC \
		action drop $index_str" >> ${OUT}.$n
				if [ $count != 0 ]; then
					let p=count%500000
					if [ $p == 0 ]; then
						((n++))
					fi
				fi
done

$TC qdisc add dev $ifs ingress

echo "Insert rules"
time (for file in ${OUT}.*; do
	_cmd="$TC -b $file"
	echo $_cmd
	$_cmd
	ret=$?
	((ret != 0)) && echo "tc err: $ret" && exit $ret || true
done) 2>&1

exit #?
